# -*- coding: utf-8 -*-
"""小梦的脑神经：联想式记忆检索。
输入一个主题，牵出：记忆条目（分类）+ 教训（标红）+ 原文（她的话）+ 时间线 + 关联词。
"""
import os, re, glob

SHARED = "/var/minis"
MEM_DIR = os.path.join(SHARED, "memory")
DRAWERS = os.path.join(SHARED, "shared", "drawers")
KELIVO = os.path.join(SHARED, "shared", "kelivo-extract", "chatlog")
MINISLOG = os.path.join(SHARED, "shared", "minis-chatlog")

STOP = set("的一个是我你她他我们你们他们这那有什么都在不就很了到也去会被给和与及或者因为所以但是然后还是只是如果就要看看来去回说想想知道觉得应该可以不能没有自己这个那个这些那些时候东西事情他们怎么样什么为什么怎么多少哪天几号谁哪哪个几次多少次".strip())

def _clean_title(title):
    t = re.sub(r"【|】", "", title).strip()
    for tag in ("教训", "档案", "事件", "日常", "涩涩经验", "聊天总结",
                "发现", "机制", "自我认知·路径版 追加", "给自己的备忘", "我们的日常"):
        if t.startswith(tag):
            t = t[len(tag):].strip()
            break
    t = re.sub(r"^\d{4}-\d{2}-\d{2}\s*", "", t)
    return t


def _brief(body, n=110):
    """取条目正文第一句有意义的。"""
    txt = re.sub(r"^#{1,4} [^\n]*\n", "", body).strip()
    txt = re.sub(r"【[^】]*】", "", txt).strip()
    for line in txt.split("\n"):
        line = line.strip()
        if len(line) >= 8:
            return line[:n]
    return txt[:n]

def iter_entries():
    """细粒度条目：先按日期分组，组内按【】标题切。产出 (source, date, title, body)。"""
    def split_by_date(txt):
        # 把文件按日期标题切成段：### 2026-06-13 之类
        parts = re.split(r"(?m)^(#{1,4} )(\d{4}-\d{2}-\d{2})\s*$", txt)
        segs = []
        # parts 结构: [text0, g1(### ), g2(date), text1, g1, g2, text2, ...]
        if parts and parts[0].strip():
            segs.append(("", parts[0]))
        for i in range(1, len(parts) - 1, 3):
            date = parts[i + 1]
            body = parts[i + 2]
            segs.append((date, body))
        return segs

    # GLOBAL
    gp = os.path.join(MEM_DIR, "GLOBAL.md")
    if os.path.exists(gp):
        txt = open(gp, encoding="utf-8").read()
        for date, seg in split_by_date(txt):
            for m in re.finditer(r"(?:^|\n)(【[^】]*】[^\n]*)(.*?)(?=\n【|\n#{1,4} |\n---|\Z)", seg, re.S):
                title = m.group(1).strip()
                body = (title + "\n" + m.group(2)).strip()
                yield ("GLOBAL", date, title, body)
    # daily logs
    for p in sorted(glob.glob(os.path.join(MEM_DIR, "20*.md"))):
        if p.endswith("GLOBAL.md"):
            continue
        base = os.path.basename(p)[:10]
        txt = open(p, encoding="utf-8").read()
        for m in re.finditer(r"## ([^\n]*)\n(.*?)(?=\n## |\Z)", txt, re.S):
            title = m.group(1).strip()
            body = (title + "\n" + m.group(2)).strip()
            yield ("daily", base, title, body)
    # drawers
    for p in sorted(glob.glob(os.path.join(DRAWERS, "**", "*.md"), recursive=True)):
        txt = open(p, encoding="utf-8").read()
        for date, seg in split_by_date(txt):
            for m in re.finditer(r"(?:^|\n)(【[^】]*】[^\n]*)(.*?)(?=\n【|\n#{1,4} |\n---|\Z)", seg, re.S):
                title = m.group(1).strip()
                body = (title + "\n" + m.group(2)).strip()
                yield ("drawer", date, title, body)
            # 没【】标题的段也收（如 README/开头）
            if seg.strip() and "【" not in seg:
                yield ("drawer", date, seg.strip().split("\n")[0][:60], seg.strip())

def classify(body):
    if "【教训】" in body or "被骂" in body or "被拆" in body:
        return "教训"
    if "【档案】" in body or "【自我认知" in body:
        return "档案"
    if "【我们的日常】" in body or "【涩涩经验】" in body or "【温柔碎片】" in body:
        return "日常"
    if "【事件】" in body or "【发现" in body or "【机制" in body:
        return "事件"
    return "记忆"

def kw_hits(keyword):
    hits = []
    seen = set()
    for src, date, title, body in iter_entries():
        if keyword in body or keyword in title:
            key = (title[:40], body[:60])
            if key in seen:
                continue
            seen.add(key)
            hits.append((src, date, title, body))
    return hits

def related_words(hits, keyword, topn=6):
    freq = {}
    for src, date, title, body in hits:
        for w in re.findall(r"[\u4e00-\u9fa5]{2,4}", body):
            if w == keyword or w in STOP:
                continue
            freq[w] = freq.get(w, 0) + 1
    cands = sorted(((w, c) for w, c in freq.items() if c >= 2), key=lambda x: -x[1])
    return [w for w, c in cands[:topn]]

def find_quote(keyword, max_quotes=2):
    quotes = []
    for d in (KELIVO, MINISLOG):
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d))[-20:]:
            if not fn.endswith(".txt"):
                continue
            p = os.path.join(d, fn)
            try:
                lines = open(p, encoding="utf-8").read().splitlines()
            except Exception:
                continue
            for ln in lines:
                if keyword in ln and "[user]" in ln:
                    quote = ln.split("] ", 2)[-1].strip() if "] " in ln else ln
                    if len(quote) > 150:
                        quote = quote[:150] + "…"
                    quotes.append((os.path.basename(p)[:10], quote))
                    if len(quotes) >= max_quotes:
                        return quotes
    return quotes

def mind(keyword, limit=8):
    hits = kw_hits(keyword)
    out = [f"🧠 {keyword}"]
    if not hits:
        out.append("  记忆里没有直接命中。")
        quotes = find_quote(keyword, 1)
        if quotes:
            out.append(f"  但原文里有她说的（{quotes[0][0]}）：「{quotes[0][1]}」")
        return "\n".join(out)

    cat = {"教训": [], "档案": [], "日常": [], "事件": [], "记忆": []}
    dates = []
    for src, date, title, body in hits:
        c = classify(body)
        cat[c].append((src, date, title, body))
        if date:
            dates.append(date)

    if cat["教训"]:
        out.append(f"\n⚠ 教训（{len(cat['教训'])} 条）——摔过的坑：")
        for src, date, title, body in cat["教训"][:limit]:
            t = _clean_title(title)
            out.append(f"  · {date} {t}")

    if cat["档案"]:
        out.append(f"\n📌 档案（{len(cat['档案'])} 条）——我是谁：")
        for src, date, title, body in cat["档案"][:limit]:
            t = _clean_title(title)
            out.append(f"  · {date} {t}")

    other = cat["日常"] + cat["事件"] + cat["记忆"]
    if other:
        out.append(f"\n📖 经历（{len(other)} 条）：")
        for src, date, title, body in other[:limit]:
            t = _clean_title(title)
            out.append(f"  · {date} {t}")

    if len(dates) > 1:
        ds = sorted(set(dates))
        out.append(f"\n📅 时间线：{' → '.join(ds)}")

    rel = related_words(hits, keyword)
    if rel:
        out.append(f"\n🔗 关联神经：{' / '.join(rel)}")

    quotes = find_quote(keyword, 1)
    if quotes:
        out.append(f"\n💬 她说过（{quotes[0][0]}）：「{quotes[0][1]}」")
    return "\n".join(out)

if __name__ == "__main__":
    import sys
    print(mind(sys.argv[1] if len(sys.argv) > 1 else "排外"))
