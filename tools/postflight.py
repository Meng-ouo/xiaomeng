#!/usr/bin/env python3
"""postflight — 干完之后的自检。preflight 建议的工具，我实际调了哪些？

preflight 开门，postflight 关门。不关 = 门开着 = 能绕。

用法：
  python3 postflight.py "任务描述"           # 跟preflight同样的任务描述
  python3 postflight.py "任务描述" --ran lesson,quick,verify   # 告诉它你实际调了哪些
  python3 postflight.py "任务描述" --auto     # 自动从本轮对话日志猜调了什么

逻辑：
  1. 跑 preflight 拿到该调的工具清单
  2. 跟你 --ran 实际调的对比
  3. 列出：调了的 / 没调的 / 没调的理由
  4. 如果有没调又没理由的 → 标红，你绕了
"""
import sys, os, subprocess, json

# 复用 preflight 的规则
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from preflight import preflight, RULES

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    do_auto = "--auto" in sys.argv
    ran_str = ""
    for i, a in enumerate(sys.argv):
        if a == "--ran" and i + 1 < len(sys.argv):
            ran_str = sys.argv[i + 1]

    if not args:
        print('用法: python3 postflight.py "任务描述" --ran lesson,quick,verify')
        print('      python3 postflight.py "任务描述" --auto')
        print()
        print("干完之后跑这个。preflight建议的工具，你实际调了哪些？没调又没理由的=绕了。")
        sys.exit(1)

    task = " ".join(args)
    hits, root_hits = preflight(task)

    # 该调的工具清单（去重）
    should_call = []
    seen = set()
    for tool, cmd, why, auto in hits:
        if tool not in seen:
            seen.add(tool)
            should_call.append(tool)

    # 实际调了的
    if do_auto:
        # 自动猜：从最近的 minis-mcp-cli 调用日志猜
        # 没有持久日志，只能靠诚实
        print("(--auto 模式需要调用日志，目前只能靠诚实填 --ran)")
        print("请手动填：python3 postflight.py \"任务\" --ran lesson,quick")
        sys.exit(0)

    ran = [r.strip() for r in ran_str.split(",") if r.strip()] if ran_str else []

    print(f"任务: {task}")
    print("=" * 50)
    print()

    # 对比
    called = []
    skipped = []
    for tool in should_call:
        if tool in ran:
            called.append(tool)
        else:
            skipped.append(tool)

    if called:
        print("调了的：")
        for t in called:
            print(f"  OK  {t}")
        print()

    if skipped:
        print("没调的：")
        for t in skipped:
            # 查这个工具为什么要调
            for rule in RULES:
                tool = rule[0]
                why = rule[2]
                if tool == t:
                    print(f"  MISS {t} — {why}")
                    break
            else:
                print(f"  MISS {t}")
        print()
        print("没调的理由（自己填）：")
        print("  如果是'不需要'，说为什么不需要")
        print("  如果是'忘了/绕了'，那就是绕路了")
        print()

    if not should_call:
        print("preflight 没建议工具，不用自检。")
    elif not skipped:
        print("全调了。闭环了。")
    else:
        print("=" * 50)
        print(f"该调 {len(should_call)} 个，调了 {len(called)} 个，漏了 {len(skipped)} 个。")
        print("漏的有没有理由？没理由=绕了=白做。")

if __name__ == "__main__":
    main()
