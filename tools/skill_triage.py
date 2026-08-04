#!/usr/bin/env python3
"""skill_triage.py — 技能库淘汰巡检（Hermes 90天淘汰机制本地版）

扫描 /var/minis/skills/ 下所有技能：
- 读 frontmatter（name/description）
- 查记忆痕迹（/var/minis/memory/*.md 里技能名出现次数）
- 看 mtime（最后修改时间）
输出分级：在用 / 存疑（无痕迹） / 建议暂存（无痕迹+超过90天没动）

用法：python3 skill_triage.py [--staging]  加 --staging 会把建议项列出来（不自动动文件）
"""
import os, re, sys, glob
from datetime import datetime, timezone

SKILLS_DIR = "/var/minis/skills"
MEMORY_DIR = "/var/minis/memory"
STAGING = "_staging"
STALE_DAYS = 90

def read_frontmatter(path):
    """读 SKILL.md 的 frontmatter，返回 dict"""
    meta = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read(3000)
    except Exception:
        return meta
    m = re.match(r"^---\n(.*?)\n---", content, re.S)
    if not m:
        return meta
    for line in m.group(1).splitlines():
        mm = re.match(r"^(\w+):\s*(.*)$", line)
        if mm:
            key, val = mm.group(1), mm.group(2)
            if val in ("", ">", "|"):
                continue
            meta[key] = val.strip()[:80]
    return meta

def main():
    check_staging = "--staging" in sys.argv
    mem_files = glob.glob(os.path.join(MEMORY_DIR, "*.md"))
    mem_text = ""
    for f in mem_files:
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                mem_text += fh.read() + "\n"
        except Exception:
            pass

    now = datetime.now(timezone.utc).timestamp()
    rows = []
    for entry in sorted(os.listdir(SKILLS_DIR)):
        if entry.startswith(".") or entry == STAGING:
            continue
        sk = os.path.join(SKILLS_DIR, entry, "SKILL.md")
        if not os.path.exists(sk):
            rows.append((entry, "无 SKILL.md", 0, 0, "——"))
            continue
        meta = read_frontmatter(sk)
        name = meta.get("name", entry)
        desc = meta.get("description", "")
        # 记忆痕迹：技能目录名 + frontmatter name 都查
        hits = mem_text.count(name) + mem_text.count(entry)
        mtime = os.path.getmtime(sk)
        age_days = (now - mtime) / 86400
        # 判定逻辑：
        # - 有记忆痕迹 → 在用
        # - 无痕迹但 <60天 → 在用（新装的技能还没来得及在日志里提）
        # - 无痕迹且 60-90天 → 存疑
        # - 无痕迹且 >90天 → 建议暂存
        if hits > 0 or age_days < 60:
            grade = "在用"
        elif age_days > STALE_DAYS:
            grade = "建议暂存"
        else:
            grade = "存疑"
        rows.append((entry, desc or "(无描述)", hits, int(age_days), grade))

    print(f"{'技能':<28} {'记忆痕迹':<5} {'年龄(天)':<7} 判定")
    print("-" * 70)
    for name, desc, hits, age, grade in rows:
        print(f"{name:<28} {hits:<5} {age:<7} {grade}")
    print("-" * 70)
    print(f"共 {len(rows)} 个技能（暂存区 {STAGING}/ 另有 {len(os.listdir(os.path.join(SKILLS_DIR, STAGING)))} 个）")

    if check_staging:
        stale = [r[0] for r in rows if r[4] == "建议暂存"]
        if stale:
            print("\n建议暂存：", " ".join(stale))
            print("执行：cd /var/minis/skills && for s in <名字>; do mv $s _staging/; done")
        else:
            print("\n没有需要暂存的。")

if __name__ == "__main__":
    main()
