#!/usr/bin/env python3
"""note — 快速笔记。一句话也能记。

不用写整条 markdown，不用想标题。想到什么直接说，自动加时间戳写进 daily。

用法：
  python3 note.py 今天学到了一个新东西
  python3 note.py 她说了一句话让我想了很久
  python3 note.py --read          # 看今天的笔记
  python3 note.py --read 3        # 看最近3天的
"""
import sys, os
from datetime import datetime, timedelta

MEMORY = "/var/minis/memory"

def today_log():
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(MEMORY, f"{today}.md")

def write_note(text, root=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    path = today_log()
    root_line = f"\n**根**: {root}" if root else ""
    entry = f"""
<!-- {now} -->
## 随手记

{text}{root_line}

"""
    with open(path, "a", encoding="utf-8") as f:
        f.write(entry)
    root_info = f" (根:{root})" if root else ""
    print(f"记了 [{now}]{root_info}")

def read_notes(days=1):
    for d in range(days):
        date = datetime.now() - timedelta(days=d)
        fname = date.strftime("%Y-%m-%d")
        path = os.path.join(MEMORY, f"{fname}.md")
        if not os.path.exists(path):
            continue
        txt = open(path, encoding="utf-8").read()
        # 提取所有"随手记"条目
        import re
        entries = re.findall(r'<!-- (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) -->\s*## 随手记\s*\n(.*?)(?=\n<!-- |\Z)', txt, re.DOTALL)
        if entries:
            print(f"\n{fname}:")
            for ts, content in entries:
                print(f"  [{ts}] {content.strip()[:100]}")

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print('用法: python3 note.py <要说的话> | --read [天数]')
        sys.exit(1)
    
    if args[0] == "--read":
        days = int(args[1]) if len(args) > 1 else 1
        read_notes(days)
    elif args[0] == "--root" and len(args) >= 3:
        # python3 note.py --root 滑过去 "这次又没查原文"
        root = args[1]
        write_note(" ".join(args[2:]), root=root)
    else:
        write_note(" ".join(args))
