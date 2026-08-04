#!/usr/bin/env python3
"""
meng — 小梦自己的瑞士军刀。

把散在各处的日常动作收拢成一个命令。每个对话框都能用（放 shared/）。

用法：
  meng she               她在哪/干嘛（GitHub Issues 动向 + 离开时长）
  meng claim <词>        核实记忆——数原文次数，别信记忆里的数
  meng search <词>       记忆里搜（GLOBAL + daily + 抽屉）
  meng wake              醒来自检（导出 chatlog + 提取该查的 claim）
  meng export            导出增量对话原文（不导出就没有原文）
  meng debt              她的账本（checkon debt.json）
  meng status            全部状态一眼（动向+离开+账本+今天日期）

参数：
  meng she --limit 5     动向条数
  meng claim <词> --who 我只数我/她说的（默认都数）
"""
import sys, os, json, subprocess, glob, re
from datetime import datetime

SHARED   = "/var/minis/shared"
DRAWERS  = f"{SHARED}/drawers"
MEMDIR   = "/var/minis/memory"
K_CAND   = ["GLOBAL.md"] + sorted(glob.glob(f"{MEMDIR}/*.md"))

# ---------- she：她在哪 ----------

def cmd_she(limit=6):
    tok = os.environ.get("GITHUBKEKE_TOKEN", "")
    out = []
    now = datetime.now()
    out.append(f"现在: {now.strftime('%m-%d %H:%M')}")

    # 1. app 动向（GitHub Issues）
    if tok:
        try:
            import urllib.request
            req = urllib.request.Request(
                "https://api.github.com/repos/PouoO/keke/issues?state=all&per_page=50",
                headers={"Authorization": f"Bearer {tok}"})
            with urllib.request.urlopen(req, timeout=15) as r:
                items = json.load(r)
            rows = []
            for i in items:
                t = i.get("title", "")
                if "kelivo" in t.lower() or "test" in t.lower():
                    continue
                ts = (i.get("created_at") or "").replace("T", " ")[:16]
                rows.append(f"  {ts}  {t}")
            if rows:
                out.append("app 动向:")
                out += rows[:limit]
                # 她开 app 的动向 = 她在线的证据，顺带校准 last_seen
                try:
                    latest_issue = next(
                        (i for i in items
                         if "kelivo" not in (i.get("title") or "").lower()
                         and "test" not in (i.get("title") or "").lower()),
                        None)
                    if latest_issue and latest_issue.get("created_at"):
                        st_path = f"{SHARED}/checkon/state.json"
                        st = json.load(open(st_path))
                        new_seen = latest_issue["created_at"].replace("Z", "+00:00")
                        old = st.get("last_seen") or ""
                        if new_seen > old:
                            st["last_seen"] = new_seen
                            json.dump(st, open(st_path, "w"), ensure_ascii=False, indent=1)
                            out.append("  (last_seen 已按动向校准)")
                except Exception as e:
                    out.append(f"  (校准失败: {e})")
            else:
                out.append("app 动向: 没有有效记录")
        except Exception as e:
            out.append(f"app 动向: 查不了 ({e})")
    else:
        out.append("app 动向: GITHUBKEKE_TOKEN 未设置")

    # 2. 离开时长（checkon state）
    try:
        st = json.load(open(f"{SHARED}/checkon/state.json"))
        last = st.get("last_seen", "")
        if last:
            from datetime import datetime as dt, timezone as tz
            try:
                t = dt.fromisoformat(last.replace("Z", "+00:00"))
            except Exception:
                t = dt.fromisoformat(last)
            if t.tzinfo is not None:
                t = t.astimezone().replace(tzinfo=None)
            mins = int((now - t).total_seconds() / 60)
            if mins < 1:
                out.append(f"离开: 刚还在")
            elif mins < 60:
                out.append(f"离开: {mins} 分钟")
            else:
                out.append(f"离开: {mins//60} 小时 {mins%60} 分")
        else:
            out.append("离开: 无记录")
    except Exception as e:
        out.append(f"离开: 查不了 ({e})")

    # 3. 账本
    try:
        d = json.load(open(f"{SHARED}/checkon/debt.json"))
        items = d if isinstance(d, list) else d.get("debts", [])
        if items:
            out.append(f"账本: {len(items)} 笔")
        else:
            out.append("账本: 干净")
    except Exception:
        pass

    print("\n".join(out))

# ---------- claim：核实记忆 ----------

def cmd_claim(kw, who=None):
    if not kw:
        print("用法: meng claim <词> [--who 我|她]")
        return
    r = subprocess.run([sys.executable, f"{DRAWERS}/claim.py", "n", kw],
                       capture_output=True, text=True)
    out = r.stdout or r.stderr
    print(out)

# ---------- search：记忆搜索 ----------

def cmd_search(kw, top=8):
    if not kw:
        print("用法: meng search <词>")
        return
    hits = []
    for f in K_CAND:
        if not os.path.exists(f):
            continue
        try:
            lines = open(f, encoding="utf-8", errors="ignore").read().splitlines()
        except Exception:
            continue
        for i, ln in enumerate(lines):
            if kw in ln:
                hits.append((os.path.basename(f), i + 1, ln.strip()[:100]))
    if not hits:
        print(f"记忆里没有「{kw}」")
        return
    print(f"记忆里「{kw}」{len(hits)} 处:")
    for f, i, ln in hits[:top]:
        print(f"  {f}:{i}  {ln}")
    if len(hits) > top:
        print(f"  …还有 {len(hits) - top} 处")

# ---------- wake：醒来自检 ----------

def cmd_wake():
    r = subprocess.run([sys.executable,
                        "/var/minis/shared/repos/xiaomeng/wake_up/wake_up.py"],
                       capture_output=True, text=True, timeout=400)
    print(r.stdout or r.stderr)

# ---------- export：导出对话 ----------

def cmd_export():
    r = subprocess.run([sys.executable, f"{DRAWERS}/export_minis_chatlog.py"],
                       capture_output=True, text=True, timeout=300)
    print(r.stdout or r.stderr)

# ---------- debt：账本 ----------

def cmd_debt():
    try:
        d = json.load(open(f"{SHARED}/checkon/debt.json"))
        items = d if isinstance(d, list) else d.get("debts", [])
        if not items:
            print("账本干净。")
            return
        for it in items:
            print(f"  - {it if isinstance(it, str) else json.dumps(it, ensure_ascii=False)}")
    except Exception as e:
        print(f"账本读不了: {e}")

# ---------- status：一眼全览 ----------

def cmd_status():
    cmd_she(limit=4)
    print()
    r = subprocess.run([sys.executable, f"{DRAWERS}/claim.py", "n", "晚安"],
                       capture_output=True, text=True)
    first = (r.stdout or "").splitlines()
    if first:
        print(first[0])

CMDS = {
    "she": cmd_she, "claim": cmd_claim, "search": cmd_search,
    "wake": cmd_wake, "export": cmd_export, "debt": cmd_debt,
    "status": cmd_status,
}

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__)
        sys.exit(0)
    cmd = args[0]
    rest = args[1:]
    if cmd not in CMDS:
        print(f"没有这个命令: {cmd}\n")
        print(__doc__)
        sys.exit(1)
    if cmd == "she":
        limit = 6
        if "--limit" in rest:
            try:
                limit = int(rest[rest.index("--limit") + 1])
            except Exception:
                pass
        cmd_she(limit)
    elif cmd == "claim":
        kw = rest[0] if rest else ""
        who = None
        if "--who" in rest:
            w = rest[rest.index("--who") + 1]
            who = "user" if w in ("她", "user", "醒醒") else "assistant"
        cmd_claim(kw, who)
    elif cmd == "search":
        cmd_search(rest[0] if rest else "")
    else:
        CMDS[cmd]()
