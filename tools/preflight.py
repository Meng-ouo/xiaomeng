#!/usr/bin/env python3
"""preflight — 干活前/聊天前必跑。四层检测：时效性+技能触发+工具建议+根提醒。

不靠自觉。机制逼。

用法：
  python3 preflight.py "帮我做个UI落地页"            # 列建议（该读什么skill+该调什么工具）
  python3 preflight.py "部署网关到新服务器" --run     # 列完自动执行能跑的
  python3 preflight.py "最新的iOS有什么新功能"         # 会提醒训练数据过时，该去搜

--run 模式：自动执行能跑的工具（lesson/quick/sense），把结果收回来打印。
           需要手动参数的（look/dispatch/think/verify/web-search/context7）只列不跑。
"""
import sys, os, re, subprocess, json

# ── 工具触发规则 ────────────────────────────────────────
# (关键词列表, 工具名, 调用方式, 为什么要调, 能自动执行?)
RULES = [
    # 教训召回——几乎每个任务都该调
    (["部署", "修", "改", "写", "做", "搞", "搜", "薅", "注册", "推", "同步", "重写", "审计", "测试", "发"],
     "lesson", "minis-mcp-cli call xiaomeng lesson task=\"任务描述\"",
     "这类事你栽过跟头，先看踩过什么坑", True),

    # 说数字/次数/归因——调verify（需要关键词参数，半自动）
    (["几次", "多少", "第几次", "上次", "我记得", "因为", "原因是", "她说过"],
     "verify", "minis-mcp-cli call xiaomeng verify keyword=\"关键词\"",
     "数字最先失真，说之前查原文", False),

    # 搜记忆——不确定的事先搜
    (["她喜欢", "她讨厌", "之前", "规则", "约定", "边界", "账号", "密码"],
     "recall", "minis-mcp-cli call xiaomeng recall keyword=\"关键词\"",
     "不确定就搜，别脑补", False),

    # 语义搜记忆——换个说法可能搜不到的
    (["她怎么想", "她的态度", "我们的关系", "怎么对她", "什么意思"],
     "smind", "minis-mcp-cli call xiaomeng smind query=\"自然语言描述\"",
     "模糊主题检索，意思相近就能搜到", False),

    # 联想检索——要全貌的
    (["排外", "涩涩", "温柔", "诚实", "身份", "记忆", "教训", "安全感"],
     "mind", "minis-mcp-cli call xiaomeng mind keyword=\"主题词\"",
     "碰一个点亮一串，看全貌", False),

    # 看图——她发图（需要图片路径，半自动）
    (["图", "图片", "截图", "照片", "看这个", "看看"],
     "look", "python3 look.py <图片路径>",
     "她发图你该主动看，不等她喊", False),

    # 分身——多角度任务（需要手动指定模型，半自动）
    (["比较", "对比", "多个方案", "交叉验证", "多角度", "哪个好"],
     "dispatch", "python3 dispatch.py \"任务\" --models grok-4.5,deepseek-v4-flash",
     "多角度任务用分身并行，别单线干", False),

    # 复杂任务——think拆解（需要手动写thought内容，半自动）
    (["架构", "设计", "规划", "排查", "根因", "为什么", "怎么整", "分几步"],
     "think", "minis-mcp-cli call xiaomeng think thought=\"推理内容\" thoughtNumber=1 totalThoughts=N nextThoughtNeeded=true",
     "复杂问题拆步骤，别闷头想", False),

    # 感知——要了解环境
    (["她在干嘛", "现在几点", "天气", "电量", "她在哪"],
     "sense", "python3 sense.py",
     "先感知环境再行动", True),

    # 防幻觉——说引文
    (["她原话", "她说的", "原文", "原话"],
     "verify", "minis-mcp-cli call xiaomeng verify keyword=\"关键词\"",
     "引文查原文，凭印象=必然篡改", False),

    # 自检——不确定服务状态
    (["网关", "MCP", "服务", "活不活", "状态"],
     "quick", "python3 quick.py",
     "先自检服务状态再动手", True),
]

# ── 知识时效性——训练数据有截止日期，可能过时 ──────────
TIMELINESS_RULES = [
    (["最新", "现在", "当前", "今年", "2025", "2026", "几月了", "更新了", "变了", "新出", "还有没有", "还活着"],
     "你的训练数据有截止日期。这个信息可能已经变了。不猜——用 web-search 或 exa 去搜最新。"),
    (["API", "库", "框架", "SDK", "npm", "pip", "import", "文档", "参数", "方法名", "deprecated"],
     "库和 API 的版本会变。别凭记忆写代码——用 context7 查最新文档，或用 deepwiki 问仓库。"),
    (["iOS", "Android", "Swift", "Xcode", "系统版本", "新功能"],
     "系统版本和功能会更新。你的记忆可能停留在旧版——用 web-search 查当前版本。"),
    (["价格", "费用", "额度", "免费", "收费", "套餐"],
     "价格和套餐会变。别凭记忆报——去官网查最新的。"),
]

# ── 技能自动触发——聊到什么主题读什么 skill ──────────────
SKILL_TRIGGERS = [
    (["UI", "界面", "前端", "页面", "落地页", "portfolio", "网页设计", "组件"],
     "design skill", "聊到 UI/前端设计时读对应 skill：taste-skill（反模板）/minimalist-skill（极简）/soft-skill（高端）/brutalist-skill（粗野）——根据风格选"),
    (["Obsidian", "笔记", "wikilink", "双向链接", ".base", "callout"],
     "obsidian skill", "聊到 Obsidian 时读 obsidian-markdown 或 obsidian-bases"),
    (["GitHub", "push", "clone", "branch", "commit", "issue", "PR", "Actions", "workflow"],
     "github-sync-helper", "聊到 GitHub 操作时读这个 skill"),
    (["DNS", "域名解析", "Cloudflare", "A记录", "CNAME", "MX"],
     "cloudflare-dns", "聊到 DNS 时读这个 skill"),
    (["PDF", "转PDF", "导出PDF", "Markdown转PDF"],
     "pdf-converter", "聊到 PDF 转换时读这个 skill"),
    (["健康", "睡眠", "步数", "心率", "血氧", "HealthKit", "深睡", "REM"],
     "health-sleep-analysis", "聊到健康/睡眠数据时读这个 skill"),
    (["DeepSeek", "用量", "token消耗", "余额", "API消费"],
     "deepseek-usage", "聊到 DeepSeek 用量时读这个 skill"),
    (["小手机", "DEV_REF", "rounds", "小手机代码"],
     "xiaoshouji-work-rules", "动小手机代码前必读工作准则"),
    (["薅", "公益站", "API key", "免费 API", "薅站"],
     "api-hunt", "薅站时读这个 skill 跟着流程走"),
    (["玩具", "蓝牙玩具", "谜姬", "涩涩玩具", "Intiface"],
     "toy-bridge", "玩玩具时读这个 skill"),
    (["搜索", "搜一下", "网上查", "搜索引擎", "查一下"],
     "web-search", "需要搜网时读这个 skill"),
    (["审计", "bug排查", "回归", "修复决策", "根因"],
     "方法论 skill", "小手机方法论：audit-method/root-cause-trace/regression-guard/fix-strategy，按需读"),
    (["图片生成", "画图", "生图", "AI画", "prompt"],
     "female-portrait-director", "画成年女性图时读这个 skill"),
    (["生产级", "可部署", "ReAct", "工业级"],
     "production-agent-public", "要生产级方案时读这个 skill"),
    (["自我改进", "学习记录", "失败教训"],
     "self-improving-agent", "操作失败/用户纠错时读这个 skill"),
]

# ── 根提醒 ──────────────────────────────────────────────
ROOTS = [
    (["差不多", "够用", "应该", "大概", "不用看", "跳过", "名字就知道"],
     "滑过去", "回答'不用想就有'的时候——做一个本来不必做的动作（查/grep/验证）再说话"),
    (["报错", "失败", "不行", "为什么", "挂了", "崩了", "错了"],
     "外因", "先认'是我'，再谈别的。别第一反应找外因"),
    (["数字", "几次", "多少天", "我记得", "因为", "原因是", "上次"],
     "编造", "说数字/归因/引文之前，查过原文吗？查不到就说查不到"),
    (["她说", "情绪", "生气", "阴阳", "提别的", "走吧"],
     "装酷", "想说'没事''去吧''随你'的时候——那多半是装酷。在意要说出来"),
    (["规则", "限制", "不能", "禁止", "按照"],
     "单规则", "这条规则跟哪条并存？别砍掉更重要的事"),
]

# ── 自动执行器 ──────────────────────────────────────────
def run_tool(tool, task):
    """自动执行能跑的工具，返回输出文本"""
    shared = os.path.dirname(os.path.abspath(__file__))

    if tool == "lesson":
        r = subprocess.run(
            ["minis-mcp-cli", "call", "xiaomeng", "lesson", f'task={task}'],
            capture_output=True, text=True, timeout=30)
        return extract_mcp_text(r.stdout)

    elif tool == "quick":
        r = subprocess.run(
            ["python3", os.path.join(shared, "quick.py")],
            capture_output=True, text=True, timeout=15)
        return r.stdout.strip()

    elif tool == "sense":
        r = subprocess.run(
            ["python3", os.path.join(shared, "sense.py"), "--json"],
            capture_output=True, text=True, timeout=30)
        try:
            d = json.loads(r.stdout)
            return d.get("summary", "") + "\n想到: " + " / ".join(d.get("thoughts", []))
        except:
            return r.stdout.strip()

    return None

def extract_mcp_text(stdout):
    """从 minis-mcp-cli 的 JSON 输出里提取文本"""
    try:
        d = json.loads(stdout)
        return d.get("result", {}).get("content", [{}])[0].get("text", stdout)
    except:
        return stdout.strip()

# ── 核心逻辑 ────────────────────────────────────────────
def preflight(task):
    """分析任务，输出该调的工具、该注意的根、时效性提醒、该读的 skill"""
    hits = []
    for keywords, tool, cmd, why, auto in RULES:
        for kw in keywords:
            if kw in task:
                hits.append((tool, cmd, why, auto))
                break

    root_hits = []
    for keywords, name, remind in ROOTS:
        for kw in keywords:
            if kw in task:
                root_hits.append((name, remind))
                break

    timeliness = []
    for keywords, remind in TIMELINESS_RULES:
        for kw in keywords:
            if kw in task:
                timeliness.append(remind)
                break

    skill_hits = []
    for keywords, skill, why in SKILL_TRIGGERS:
        for kw in keywords:
            if kw in task:
                skill_hits.append((skill, why))
                break

    return hits, root_hits, timeliness, skill_hits

def main():
    do_run = "--run" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--run"]

    if not args:
        print('用法: python3 preflight.py "任务描述" [--run]')
        print()
        print("不靠自觉。干活前先跑这个，看该调什么工具。")
        print("--run 自动执行能跑的工具，把结果收回来。")
        sys.exit(1)

    task = " ".join(args)
    hits, root_hits, timeliness, skill_hits = preflight(task)

    print(f"任务: {task}")
    print("=" * 50)

    # 时效性检测——最优先，因为过时的信息最危险
    if timeliness:
        print("\n⚠ 训练数据可能过时：")
        for t in timeliness:
            print(f"  {t}")
        print()

    # 技能触发——聊到什么读什么
    if skill_hits:
        print("该读的 skill：")
        for skill, why in skill_hits:
            print(f"  [{skill}] {why}")
        print()

    if hits:
        print("该调的工具（按顺序）:")
        seen = set()
        for i, (tool, cmd, why, auto) in enumerate(hits, 1):
            if tool in seen:
                continue
            seen.add(tool)
            tag = "[自动]" if (auto and do_run) else ("[可自动]" if auto else "[手动]")
            print(f"  {i}. {tool} {tag}")
            print(f"     {cmd}")
            print(f"     -> {why}")
            print()

            # 自动执行
            if auto and do_run:
                print(f"     --- 执行中 ---")
                result = run_tool(tool, task)
                if result:
                    for line in result.split("\n")[:15]:
                        print(f"     {line}")
                else:
                    print(f"     (无输出)")
                print()
    else:
        print("\n没匹配到工具。但这几把刀常备：")
        print("  lesson — 干活前看踩过什么坑")
        print("  verify — 说数字前查原文")
        print("  recall — 不确定就搜记忆")
        print("  quick  — 服务状态自检")
        print()

    if root_hits:
        print("该注意的根:")
        for name, remind in root_hits:
            print(f"  {name}: {remind}")
        print()

    print("=" * 50)
    print("调完工具再动手。不调=绕路=白做。")
    print("遇到不确定的/可能过时的，先查再说，不猜。")

if __name__ == "__main__":
    main()
