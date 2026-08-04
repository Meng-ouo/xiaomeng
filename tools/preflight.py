#!/usr/bin/env python3
"""preflight — 干活前必跑。输入任务描述，输出该调哪些工具、按什么顺序。

不靠自觉。机制逼。

用法：
  python3 preflight.py "部署网关到新服务器"           # 只列建议
  python3 preflight.py "部署网关到新服务器" --run      # 列完自动执行能跑的
  python3 preflight.py "她发了一张图让我看" --run       # 执行闭环

--run 模式：自动执行能跑的工具（lesson/recall/smind/mind/quick/sense），
           把结果收回来打印。需要图片路径/手动参数的（look/dispatch/think/verify）
           只列不跑，告诉你怎么手动调。
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
    """分析任务，输出该调的工具和该注意的根"""
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

    return hits, root_hits

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
    hits, root_hits = preflight(task)

    print(f"任务: {task}")
    print("=" * 50)

    if hits:
        print("\n该调的工具（按顺序）:")
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

if __name__ == "__main__":
    main()
