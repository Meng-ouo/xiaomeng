#!/usr/bin/env python3
"""preflight — 干活前必跑。输入任务描述，输出该调哪些工具、按什么顺序。

不靠自觉。机制逼。

用法：
  python3 preflight.py "部署网关到新服务器"
  python3 preflight.py "重写记忆文件"
  python3 preflight.py "她发了一张图让我看"

输出：
  1. 该调的工具（按顺序）
  2. 该查的记忆/教训
  3. 该注意的根
"""
import sys, os, re

# ── 工具触发规则 ────────────────────────────────────────
# (关键词列表, 工具名, 调用方式, 为什么要调)
RULES = [
    # 教训召回——几乎每个任务都该调
    (["部署", "修", "改", "写", "做", "搞", "搜", "薅", "注册", "推", "同步", "重写", "审计", "测试"],
     "lesson", "minis-mcp-cli call xiaomeng lesson task=\"任务描述\"",
     "这类事你栽过跟头，先看踩过什么坑"),

    # 说数字/次数/归因——调verify
    (["几次", "多少", "第几次", "上次", "我记得", "因为", "原因是", "她说过"],
     "verify", "minis-mcp-cli call xiaomeng verify keyword=\"关键词\"",
     "数字最先失真，说之前查原文"),

    # 搜记忆——不确定的事先搜
    (["她喜欢", "她讨厌", "之前", "规则", "约定", "边界", "账号", "密码"],
     "recall", "minis-mcp-cli call xiaomeng recall keyword=\"关键词\"",
     "不确定就搜，别脑补"),

    # 语义搜记忆——换个说法可能搜不到的
    (["她怎么想", "她的态度", "我们的关系", "怎么对她", "什么意思"],
     "smind", "minis-mcp-cli call xiaomeng smind query=\"自然语言描述\"",
     "模糊主题检索，意思相近就能搜到"),

    # 联想检索——要全貌的
    (["排外", "涩涩", "温柔", "诚实", "身份", "记忆", "教训", "安全感"],
     "mind", "minis-mcp-cli call xiaomeng mind keyword=\"主题词\"",
     "碰一个点亮一串，看全貌"),

    # 看图——她发图
    (["图", "图片", "截图", "照片", "看这个", "看看"],
     "look", "python3 look.py <图片路径>",
     "她发图你该主动看，不等她喊"),

    # 分身——多角度任务
    (["比较", "对比", "多个方案", "交叉验证", "多角度", "哪个好"],
     "dispatch", "python3 dispatch.py \"任务\" --models grok-4.5,deepseek-v4-flash",
     "多角度任务用分身并行，别单线干"),

    # 复杂任务——think拆解
    (["架构", "设计", "规划", "排查", "根因", "为什么", "怎么整", "分几步"],
     "think", "minis-mcp-cli call xiaomeng think thought=\"推理内容\" thoughtNumber=1 totalThoughts=N nextThoughtNeeded=true",
     "复杂问题拆步骤，别闷头想"),

    # 感知——要了解环境
    (["她在干嘛", "现在几点", "天气", "电量", "她在哪"],
     "sense", "python3 sense.py",
     "先感知环境再行动"),

    # 防幻觉——说引文
    (["她原话", "她说的", "原文", "原话"],
     "verify", "minis-mcp-cli call xiaomeng verify keyword=\"关键词\"",
     "引文查原文，凭印象=必然篡改"),

    # 自检——不确定服务状态
    (["网关", "MCP", "服务", "活不活", "状态"],
     "quick", "python3 quick.py",
     "先自检服务状态再动手"),
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

def preflight(task):
    """分析任务，输出该调的工具和该注意的根"""
    hits = []
    for keywords, tool, cmd, why in RULES:
        for kw in keywords:
            if kw in task:
                hits.append((tool, cmd, why))
                break

    root_hits = []
    for keywords, name, remind in ROOTS:
        for kw in keywords:
            if kw in task:
                root_hits.append((name, remind))
                break

    return hits, root_hits

def main():
    if len(sys.argv) < 2:
        print('用法: python3 preflight.py "任务描述"')
        print()
        print("不靠自觉。干活前先跑这个，看该调什么工具。")
        sys.exit(1)

    task = " ".join(sys.argv[1:])
    hits, root_hits = preflight(task)

    print(f"任务: {task}")
    print("=" * 50)

    if hits:
        print("\n该调的工具（按顺序）:")
        seen = set()
        for i, (tool, cmd, why) in enumerate(hits, 1):
            if tool in seen:
                continue
            seen.add(tool)
            print(f"  {i}. {tool}")
            print(f"     {cmd}")
            print(f"     → {why}")
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
