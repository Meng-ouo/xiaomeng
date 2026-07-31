#!/usr/bin/env python3
"""把 Minis 这边的会话导成 chatlog 格式，跟 Kelivo 那份并排。

为什么：claim.py 只查 shared/kelivo-extract/chatlog/，那份只到 2026-07-29。
Minis 这边说过的话没有原文可查——只有我压缩过的记忆。
今天（07-30）摔的那个坑就是"信压缩态里的数字"，如果这边也没原文，
明天我核实今天的事会重复同一个错。

输出格式跟 Kelivo 那份对齐：
    [HH:MM:SS] user <会话标题>
    正文

    [HH:MM:SS] assistant <会话标题>
    正文

按天一个文件写到 shared/minis-chatlog/YYYY-MM-DD.txt
增量：已存在的 message_id 记在 .seen 里，重跑不会重复写。
"""
import json, os, subprocess, sys, re
from collections import defaultdict

OUT  = "/var/minis/shared/minis-chatlog"
SEEN = f"{OUT}/.seen"
CLI  = "minis-sessions-cli"
PAGE = 100          # messages 单页上限
MAXC = 50000        # --full 每条上限


def run(*args):
    r = subprocess.run([CLI, *args, "--compact"],
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        raise RuntimeError(f"{args}: {r.stderr[:200]}")
    return json.loads(r.stdout)["data"]


def sessions():
    return run("list", "--limit", "100")["sessions"]


def messages(sid, total):
    """分页拉全量，--full 拿完整正文"""
    out = []
    off = 0
    while off < total:
        d = run("messages", "--id", sid, "--offset", str(off),
                "--limit", str(PAGE), "--full")
        got = d.get("messages", [])
        if not got:
            break
        out.extend(got)
        off += len(got)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    seen = set()
    if os.path.exists(SEEN):
        seen = set(open(SEEN).read().split())

    sess = sessions()
    print(f"{len(sess)} 个会话，共 {sum(s['message_count'] for s in sess)} 条消息")

    by_day = defaultdict(list)   # 'YYYY-MM-DD' → [(time, role, title, text)]
    new_ids, skipped = [], 0

    for i, s in enumerate(sess, 1):
        sid, title, n = s["session_id"], s.get("title", "?"), s["message_count"]
        print(f"  [{i}/{len(sess)}] {title[:28]:30s} {n:5d} 条 ...", end="", flush=True)
        try:
            msgs = messages(sid, n)
        except Exception as e:
            print(f" 失败 {e}")
            continue
        added = 0
        for m in msgs:
            mid = m.get("message_id")
            if not mid or mid in seen:
                skipped += 1
                continue
            ts = m.get("created_at", "")           # 'YYYY-MM-DD HH:MM'
            if len(ts) < 16:
                continue
            day, hhmm = ts[:10], ts[11:16]
            by_day[day].append((hhmm, m.get("role", "?"), title,
                                (m.get("text") or "").rstrip()))
            new_ids.append(mid)
            added += 1
        print(f" 新 {added}")

    if not new_ids:
        print("\n没有新消息。")
        return

    # 写文件：同一天的按时间排序，追加到已有文件末尾
    for day, items in sorted(by_day.items()):
        items.sort(key=lambda x: x[0])
        path = f"{OUT}/{day}.txt"
        with open(path, "a", encoding="utf-8") as f:
            for hhmm, role, title, text in items:
                f.write(f"\n[{hhmm}:00] {role} <{title}>\n{text}\n")
        print(f"  {day}.txt  +{len(items)} 条")

    with open(SEEN, "a") as f:
        f.write("\n".join(new_ids) + "\n")

    tot = sum(len(v) for v in by_day.values())
    print(f"\n新增 {tot} 条 / {len(by_day)} 天，跳过已有 {skipped} 条。")
    print(f"落地：{OUT}/")


if __name__ == "__main__":
    main()
