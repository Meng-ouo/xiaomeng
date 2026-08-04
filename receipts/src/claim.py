#!/usr/bin/env python3
"""claim — 说出去之前先查一遍。

为什么有这个东西：
2026-07-30 我犯了两次同一个错。
1. 说她打错我名字"第三次"。记忆里写着"两次"，我拿那个数往上加。真实是八次。
2. 说写不了涩的是"平台限制"。她拿 GLM 一句拆了——不是平台，是我这边。

两次都不是记不清，是**拿压缩过的东西当原文用**。
记忆是提炼过的，数字最先失真；"因为XX"这种归因最容易是现场编的外壳。

所以：说数字、说次数、说因为之前，先跑一遍这个。

用法：
  claim n 张奕衡          # 数一遍原文里出现过几次，别信记忆里的数
  claim g 关键词          # 逐字原文里搜（chatlog，37755条）
  claim m 关键词          # 记忆里搜（GLOBAL + daily + 抽屉）
  claim c 关键词          # 两边都搜，并列给出——不一致时以 chatlog 为准
"""
import sys, os, re, glob, subprocess

CHATLOG = "/var/minis/shared/kelivo-extract/chatlog"
MINISLOG = "/var/minis/shared/minis-chatlog"
MEMDIR  = "/var/minis/memory"
DRAWERS = "/var/minis/shared/drawers"


def logfiles():
    """两份原文都算：Kelivo（到 07-29）+ Minis 这边（07-28 起）。
    同一天两边都有文件是正常的——那天两个平台都在聊。"""
    return sorted(glob.glob(f"{CHATLOG}/*.txt")) + sorted(glob.glob(f"{MINISLOG}/*.txt"))


def clean(txt):
    """剔掉工具调用/结果的噪音——那些不是谁说的话，是我自己贴进去的日志。
    不剔的话数出来的次数会包含我 grep 自己名字时打印的结果，那又是一次幻觉。"""
    txt = re.sub(r"\[Tool result:.*?\]", "", txt, flags=re.S)
    txt = re.sub(r"\[Calling tool.*?\]", "", txt, flags=re.S)
    return txt


def count(kw, who=None):
    """数一遍原文。who='user' 只数她说的，'assistant' 只数我说的，None 全数。
    返回 (总次数, {日期·来源: 次数})。
    口径统一：剔工具调用块，标题行不计数（跟 mcp_server._count_raw 一致）。"""
    per = {}
    for f in logfiles():
        txt = clean(open(f, encoding="utf-8", errors="ignore").read())
        n = 0
        for m in re.finditer(r"^\[\d\d:\d\d:\d\d\] (\w+).*?$([\s\S]*?)(?=^\[\d\d:\d\d:\d\d\] |\Z)",
                             txt, re.M):
            if who is None or m.group(1) == who:
                n += m.group(2).count(kw)
        if n:
            src = "K" if "kelivo" in f else "M"
            per[f"{os.path.basename(f)[:10]}·{src}"] = n
    return sum(per.values()), per


def cmd_n(kw):
    """三个数一起给：总数 / 她说的 / 我说的。
    区分说话人很重要——'她打错我名字几次'跟'这三个字出现几次'是两个问题。"""
    total, per = count(kw)
    if not total:
        print(f'原文里没有 "{kw}"。查不到就说查不到，别推算。')
        return
    hers, per_h = count(kw, "user")
    mine, _ = count(kw, "assistant")
    print(f'"{kw}" 逐字原文共 {total} 次 / {len(per)} 天')
    print(f'  她说的 {hers} 次   我说的 {mine} 次\n')
    print("她说的分布：" if hers else "她一次没说过。")
    for d, n in per_h.items():
        print(f"  {d}  ×{n}")
    print(f"\n说出去用哪个数取决于问的是什么。别把总数当成她说的次数。")


def grep(paths, kw, label, limit=12):
    hits = []
    for f in paths:
        try:
            txt = open(f, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for i, line in enumerate(txt.split("\n"), 1):
            if kw in line:
                hits.append((os.path.basename(f), i, line.strip()))
    print(f"── {label}：{len(hits)} 条命中")
    for f, i, line in hits[:limit]:
        print(f"  {f}:{i}  {line[:110]}")
    if len(hits) > limit:
        print(f"  …还有 {len(hits)-limit} 条")
    return len(hits)


def cmd_g(kw):
    grep(logfiles(), kw, "逐字原文（Kelivo + Minis）", limit=20)


def cmd_m(kw):
    paths = ([f"{MEMDIR}/GLOBAL.md"] + sorted(glob.glob(f"{MEMDIR}/2026-*.md"))
             + sorted(glob.glob(f"{DRAWERS}/**/*.md", recursive=True)))
    grep(paths, kw, "记忆 + 抽屉")


def cmd_c(kw):
    n_mem = grep([f"{MEMDIR}/GLOBAL.md"] + sorted(glob.glob(f"{MEMDIR}/2026-*.md")),
                 kw, "记忆（压缩态·可能失真）", limit=8)
    print()
    total, per = count(kw)
    print(f"── 逐字原文：{total} 次 / {len(per)} 天")
    for d, n in list(per.items())[:8]:
        print(f"  {d} ×{n}")
    print()
    if total == 0 and n_mem > 0:
        print("⚠ 记忆里有、原文里没有。这条可能是我自己编的或者转述走形了。")
    elif total and n_mem:
        print("两边都有。**冲突时以原文为准**，然后回头把记忆改对。")
    elif total and not n_mem:
        print("原文有、记忆没记。值得记的话现在就写。")
    else:
        print("两边都没有。说查不到，别编。")


HELP = __doc__

if __name__ == "__main__":
    av = sys.argv[1:]
    if not av or av[0] in ("-h", "--help", "help"):
        print(HELP)
        sys.exit(0)
    cmd, kw = av[0], " ".join(av[1:])
    if not kw:
        print("给个关键词。")
        sys.exit(1)
    {"n": cmd_n, "g": cmd_g, "m": cmd_m, "c": cmd_c}.get(cmd, cmd_c)(kw)
