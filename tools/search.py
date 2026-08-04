#!/usr/bin/env python3
"""search — 统一搜索：daily 日志 + 抽屉档案 + chatlog 原文。

一次搜全部，按相关度排序，标来源。
替代分别调 recall（daily+抽屉）和 verify（chatlog）。

用法：
  python3 search.py 关键词
  python3 search.py 关键词 --limit 5
  python3 search.py 关键词 --scope daily    # 只搜 daily
  python3 search.py 关键词 --scope drawers  # 只搜抽屉
  python3 search.py 关键词 --scope chatlog  # 只搜 chatlog
"""
import os, sys, re, glob
from datetime import datetime

SHARED = "/var/minis/shared"
MEMORY = "/var/minis/memory"
DRAWERS = os.path.join(SHARED, "drawers/self")
CHATLOG = os.path.join(SHARED, "minis-chatlog")

def score_line(line, keyword):
    """简单相关度：精确匹配 > 词边界匹配 > 包含"""
    line_lower = line.lower()
    kw_lower = keyword.lower()
    if line_lower == kw_lower:
        return 100
    # 出现次数
    count = line_lower.count(kw_lower)
    # 词边界
    if re.search(r'\b' + re.escape(kw_lower) + r'\b', line_lower):
        return 50 + count * 10
    if count > 0:
        return 20 + count * 5
    return 0

def search_daily(keyword, limit):
    results = []
    for f in sorted(glob.glob(os.path.join(MEMORY, "2026-*.md"))):
        if "GLOBAL" in f:
            continue
        fname = os.path.basename(f)
        try:
            txt = open(f, encoding="utf-8").read()
        except:
            continue
        # 按条目分割（<!-- timestamp --> 开头）
        entries = re.split(r'(<!-- .*? -->)', txt)
        current_ts = ""
        current_content = ""
        for part in entries:
            if part.startswith("<!--"):
                if current_content:
                    sc = score_line(current_content, keyword)
                    if sc > 0:
                        # 取第一行标题
                        first_line = current_content.strip().split("\n")[0][:60]
                        results.append((sc, f"daily/{fname}", current_ts, first_line))
                current_ts = part
                current_content = ""
            else:
                current_content += part
        # 最后一条
        if current_content:
            sc = score_line(current_content, keyword)
            if sc > 0:
                first_line = current_content.strip().split("\n")[0][:60]
                results.append((sc, f"daily/{fname}", current_ts, first_line))
    results.sort(key=lambda x: -x[0])
    return results[:limit]

def search_drawers(keyword, limit):
    results = []
    for f in sorted(glob.glob(os.path.join(DRAWERS, "*.md"))):
        fname = os.path.basename(f)
        try:
            lines = open(f, encoding="utf-8").readlines()
        except:
            continue
        for i, line in enumerate(lines):
            sc = score_line(line, keyword)
            if sc > 0:
                # 找最近的 ### 标题
                section = ""
                for j in range(i, -1, -1):
                    if lines[j].strip().startswith("###") or lines[j].strip().startswith("## "):
                        section = lines[j].strip().lstrip("#").strip()
                        break
                context = line.strip()[:80]
                results.append((sc, f"drawers/{fname}", section, context))
    results.sort(key=lambda x: -x[0])
    return results[:limit]

def search_chatlog(keyword, limit):
    results = []
    files = sorted(glob.glob(os.path.join(CHATLOG, "*.txt")))[-5:]  # 最近5天
    for f in files:
        fname = os.path.basename(f)
        try:
            lines = open(f, encoding="utf-8").readlines()
        except:
            continue
        for i, line in enumerate(lines):
            if keyword.lower() in line.lower():
                # 找最近的 [HH:MM:SS] user/assistant 标记
                ts = ""
                for j in range(i, max(i-5, -1), -1):
                    m = re.match(r'\[(\d\d:\d\d:\d\d)\] (\w+)', lines[j])
                    if m:
                        ts = f"{m.group(2)} {m.group(1)}"
                        break
                context = line.strip()[:80]
                results.append((0, f"chatlog/{fname}", ts, context))
    results.sort(key=lambda x: x[1])  # 按文件名+时间
    return results[:limit]

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("用法: python3 search.py 关键词 [--limit N] [--scope daily|drawers|chatlog]")
        sys.exit(1)
    
    keyword = args[0]
    limit = 10
    scope = "all"
    
    for i, a in enumerate(args[1:], 1):
        if a == "--limit" and i+1 < len(args):
            limit = int(args[i+1])
        elif a == "--scope" and i+1 < len(args):
            scope = args[i+1]
    
    print(f"搜索: {keyword}")
    found = 0
    
    if scope in ("all", "daily"):
        results = search_daily(keyword, limit)
        if results:
            print(f"\n  daily ({len(results)}):")
            for sc, src, ts, preview in results:
                print(f"    [{sc:3d}] {preview}")
                print(f"          {src} {ts[:30]}")
            found += len(results)
    
    if scope in ("all", "drawers"):
        results = search_drawers(keyword, limit)
        if results:
            print(f"\n  drawers ({len(results)}):")
            for sc, src, section, preview in results:
                print(f"    [{sc:3d}] {preview}")
                if section:
                    print(f"          {src} > {section}")
                else:
                    print(f"          {src}")
            found += len(results)
    
    if scope in ("all", "chatlog"):
        results = search_chatlog(keyword, limit)
        if results:
            print(f"\n  chatlog ({len(results)}):")
            for _, src, ts, preview in results:
                print(f"    {preview}")
                print(f"      {src} {ts}")
            found += len(results)
    
    if not found:
        print("  没搜到")
    else:
        print(f"\n共 {found} 条")
