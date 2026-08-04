#!/usr/bin/env python3
"""verify — 防幻觉校验。说数字/归因/她说的话之前先查原文。

三种模式：
1. 查数字：给一个数字+关键词，在原文里搜，看数字对不对
2. 查引文：给一句话，在原文里搜，看是不是她真说过
3. 查归因：给一个因果关系，在记忆+原文里搜，看站不站得住

用法：
  python3 verify.py --number "11个模型" --keyword "模型"
  python3 verify.py --quote "你可以给自己设定时"
  python3 verify.py --claim "虾虾是08-03欠费关机的"
"""
import sys, os, re, subprocess, json

SHARED = "/var/minis/shared"
DRAWERS = os.path.join(SHARED, "drawers/self")
MEMORY = "/var/minis/memory"
CHATLOG = os.path.join(SHARED, "minis-chatlog")

def grep_all(pattern, dirs=None):
    """在多个目录 grep，返回匹配行"""
    if dirs is None:
        dirs = [DRAWERS, MEMORY, CHATLOG]
    results = []
    for d in dirs:
        if not os.path.isdir(d):
            continue
        # find + grep（BusyBox grep 不支持 --include）
        r = subprocess.run(
            f"find '{d}' -name '*.md' -o -name '*.txt' | xargs grep -rn -i '{pattern}' 2>/dev/null",
            shell=True, capture_output=True, text=True, timeout=10)
        for line in r.stdout.strip().split("\n"):
            if line:
                results.append(line)
    return results

def verify_number(number_str, keyword):
    """查数字：在原文里搜关键词，看数字对不对"""
    print(f"查数字: '{number_str}' (关键词: {keyword})")
    print()
    # 提取数字
    nums = re.findall(r'\d+', number_str)
    if not nums:
        print("没找到数字")
        return
    
    # 搜关键词
    results = grep_all(keyword)
    print(f"原文中 '{keyword}' 出现 {len(results)} 次:")
    
    # 看哪些行包含数字
    matching = []
    for line in results:
        for n in nums:
            if n in line:
                matching.append(line)
                break
    
    if matching:
        print(f"其中包含数字 {nums} 的:")
        for line in matching[:10]:
            # 截短路径
            line = line.replace(SHARED + "/", "").replace(MEMORY + "/", "")
            print(f"  {line[:120]}")
    else:
        print(f"没有行同时包含 '{keyword}' 和数字 {nums}")
    
    # 也搜数字本身
    for n in nums:
        r = grep_all(n)
        if r:
            print(f"\n数字 {n} 在原文出现 {len(r)} 次（前5条）:")
            for line in r[:5]:
                line = line.replace(SHARED + "/", "").replace(MEMORY + "/", "")
                print(f"  {line[:120]}")

def verify_quote(quote):
    """查引文：搜这句话在不在原文里"""
    print(f"查引文: '{quote}'")
    print()
    # 精确搜
    results = grep_all(quote)
    if results:
        print(f"精确匹配 {len(results)} 处:")
        for line in results[:5]:
            line = line.replace(SHARED + "/", "").replace(MEMORY + "/", "")
            print(f"  {line[:150]}")
        return
    
    # 模糊搜：2字滑窗
    clean = re.sub(r'[^\u4e00-\u9fff]', '', quote)
    keywords = [clean[i:i+2] for i in range(len(clean) - 1)]
    seen = set()
    unique_kw = [kw for kw in keywords if not (kw in seen or seen.add(kw))]
    if unique_kw:
        print("精确匹配 0 处，试模糊搜...")
        for kw in unique_kw[:3]:
            r = grep_all(kw)
            if r:
                print(f"\n'{kw}' 出现 {len(r)} 次（前3条）:")
                for line in r[:3]:
                    line = line.replace(SHARED + "/", "").replace(MEMORY + "/", "")
                    print(f"  {line[:150]}")

def verify_claim(claim):
    """查归因：拆关键词搜"""
    print(f"查归因: '{claim}'")
    print()
    # 拆成 2-3 字关键词（滑窗）
    keywords = []
    clean = re.sub(r'[^\u4e00-\u9fff\d]', '', claim)
    for i in range(len(clean) - 1):
        keywords.append(clean[i:i+2])
    # 去重保留顺序
    seen = set()
    unique_kw = []
    for kw in keywords:
        if kw not in seen:
            seen.add(kw)
            unique_kw.append(kw)
    print(f"拆出关键词: {unique_kw}")
    print()
    
    for kw in unique_kw[:6]:
        r = grep_all(kw)
        if r:
            print(f"'{kw}' 出现 {len(r)} 次（前3条）:")
            for line in r[:3]:
                line = line.replace(SHARED + "/", "").replace(MEMORY + "/", "")
                print(f"  {line[:120]}")
            print()

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print("用法:")
        print("  python3 verify.py --number '11个模型' --keyword '模型'")
        print("  python3 verify.py --quote '你可以给自己设定时'")
        print("  python3 verify.py --claim '虾虾是08-03欠费关机的'")
        sys.exit(1)
    
    mode = None
    number_str = ""
    keyword = ""
    quote = ""
    claim = ""
    
    for i, a in enumerate(args):
        if a == "--number" and i+1 < len(args):
            number_str = args[i+1]
            mode = "number"
        elif a == "--keyword" and i+1 < len(args):
            keyword = args[i+1]
        elif a == "--quote" and i+1 < len(args):
            quote = args[i+1]
            mode = "quote"
        elif a == "--claim" and i+1 < len(args):
            claim = args[i+1]
            mode = "claim"
    
    if mode == "number":
        verify_number(number_str, keyword)
    elif mode == "quote":
        verify_quote(quote)
    elif mode == "claim":
        verify_claim(claim)
