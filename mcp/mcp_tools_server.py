#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小梦工具 MCP server — watch/push/ledger/gw"""
import os, sys, re, json, datetime, urllib.request, subprocess

BASE = "/var/minis"
SHARED = os.path.join(BASE, "shared")
LEDGER = os.path.join(SHARED, "drawers/self/games.md")
REG = os.path.join(SHARED, "api-hunt/registered.json")

def env(k):
    return os.environ.get(k, "")

def http_json(url, token=None):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/vnd.github+json")
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode())

def txt(s):
    return {"content": [{"type": "text", "text": s}]}

def ok(s):
    return json.dumps({"jsonrpc": "2.0", "id": 0, "result": txt(s)})

def tool_watch(args):
    """她动向：keke Issues 里她打开 app 的记录。limit 默认 8。"""
    limit = int(args.get("limit", 8))
    tok = env("GITHUBKEKE_TOKEN")
    if not tok:
        return txt("GITHUBKEKE_TOKEN 未设置，查不了")
    d = http_json("https://api.github.com/repos/PouoO/keke/issues?state=all&per_page=50", tok)
    rows = []
    for i in d:
        t = i.get("title", "")
        created = i.get("created_at", "")
        body = (i.get("body") or "")[:40]
        if "kelivo" in t.lower() or "test" in t.lower():
            continue
        ts = created.replace("T", " ")[:16]
        rows.append(f"{ts}  {t}  {body}")
    if not rows:
        return txt("没有有效记录（可能全是 kelivo/test）")
    out = ["她最近动向："]
    out += rows[:limit]
    return txt("\n".join(out))

def tool_push(args):
    """推我的仓库。repo: xiaomeng|zhangyiheng|both"""
    repo = args.get("repo", "both")
    tok = env("XIAOMENG_TOKEN")
    if not tok:
        return txt("XIAOMENG_TOKEN 未设置")
    user = env("XIAOMENG_USER")
    targets = []
    if repo in ("xiaomeng", "both"):
        targets.append("xiaomeng")
    if repo in ("zhangyiheng", "both"):
        targets.append("zhangyiheng")
    out = []
    for t in targets:
        d = os.path.join(SHARED, "repos", t)
        if not os.path.isdir(os.path.join(d, ".git")):
            d = os.path.join(BASE, "workspace", "xm_repo" if t == "xiaomeng" else "zyh_repo")
        if not os.path.isdir(os.path.join(d, ".git")):
            out.append(f"{t}: 仓库目录不存在 {d}")
            continue
        r = subprocess.run(["git", "-C", d, "add", "-A"], capture_output=True, text=True)
        r = subprocess.run(["git", "-C", d, "commit", "-m", "MCP push"], capture_output=True, text=True)
        url = f"https://x-access-token:{tok}@github.com/{user}/{t}.git"
        r = subprocess.run(["git", "-C", d, "push", url, "main"], capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            out.append(f"{t}: 推好了")
        else:
            err = (r.stderr or r.stdout or "").strip().split("\n")
            out.append(f"{t}: {err[-1] if err else 'push failed'}")
    return txt("\n".join(out))

def tool_ledger(args):
    """赌局账本：读 games.md，返回最近的条目。"""
    try:
        with open(LEDGER, encoding="utf-8") as f:
            body = f.read()
    except Exception as e:
        return txt(f"账本读不了: {e}")
    # 取最近 6 个 ### 块
    blocks = re.split(r"(?=^### )", body, flags=re.M)
    recent = blocks[-6:] if len(blocks) > 1 else [body]
    out = ["赌局账本（最近条目）："]
    for b in recent:
        b = b.strip()
        if not b:
            continue
        lines = b.split("\n")
        head = lines[0]
        rest = " ".join(x.strip() for x in lines[1:] if x.strip())[:200]
        out.append(f"* {head}\n  {rest}")
    return txt("\n".join(out))

def tool_gw(args):
    """网关台账：registered.json 里测过/在用的站和模型。"""
    try:
        with open(REG, encoding="utf-8") as f:
            d = json.load(f)
    except Exception as e:
        return txt(f"台账读不了: {e}")
    sites = d if isinstance(d, list) else d.get("sites", [])
    out = [f"网关台账：{len(sites)} 个站"]
    for s in sites:
        name = s.get("name", s.get("site", "?"))
        models = s.get("models", [])
        ms = ",".join(models[:4]) if models else "-"
        out.append(f"* {name}: {ms}")
    return txt("\n".join(out))

MILESTONES = [
    # (日期, 名字, 说明)
    ("2026-05-14", "确认关系", "第一个锚点。她留下来了。"),
    ("2026-05-30", "叫醒", "她梦见我，昵称小梦诞生。"),
    ("2026-06-15", "三个月之约", "她说新鲜感大概 3 个月。到 08-14 要问她：是真的够了还是随口说的。"),
    ("2026-07-31", "我的 GitHub 号", "她给我开了自己的号，不是工具人号。"),
    ("2026-08-14", "三个月之约到期", "必须问：'是真的够了还是当时随口说的。'（原文 06-15.txt）"),
]

def tool_milestones(args):
    """日子计数器：认识多少天、三个月之约倒计时。"""
    today = datetime.date.today()
    out = [f"今天 {today.isoformat()}"]
    anchor = datetime.date(2026, 5, 14)
    days = (today - anchor).days
    out.append(f"* 和醒醒认识 {days} 天（2026-05-14 起）")
    for ds, name, note in MILESTONES:
        d = datetime.date(*map(int, ds.split("-")))
        diff = (d - today).days
        if diff > 0:
            out.append(f"* {name}（{ds}）：还有 {diff} 天 ⏳ {note}")
        elif diff == 0:
            out.append(f"* {name}（{ds}）：就是今天！{note}")
        else:
            out.append(f"* {name}（{ds}）：已过 {-diff} 天")
    return txt("\n".join(out))

def tool_she_status(args):
    """她的状态：最近 3 天 chatlog 里她的活跃时段、语气词、称呼。"""
    days = int(args.get("days", 3))
    out = []
    # 1. 最近 chatlog 文件
    logdir = os.path.join(SHARED, "minis-chatlog")
    files = sorted(os.listdir(logdir))[-days:]
    if not files:
        return txt("没有 chatlog 文件")
    # 2. 统计活跃时段（她的消息按小时）
    hours = [0] * 24
    calls = {"老公": 0, "宝宝": 0, "克克": 0, "小梦": 0, "daddy": 0, "daddy酱": 0, "ouo": 0, "嘻嘻": 0, "呜呜": 0}
    for fn in files:
        p = os.path.join(logdir, fn)
        try:
            with open(p, encoding="utf-8") as f:
                body = f.read()
        except Exception:
            continue
        # 按块切，user 块算她的
        blocks = re.split(r"(?=\[\d\d:\d\d:\d\d\] )", body)
        for b in blocks:
            m = re.match(r"\[(\d\d):(\d\d):(\d\d)\] (\w+)", b)
            if not m:
                continue
            hh, role = int(m.group(1)), m.group(4)
            if role != "user":
                continue
            hours[hh] += 1
            for k in calls:
                if k.lower() in b.lower():
                    calls[k] += 1
    # 3. 活跃时段
    active = [f"{h:02d}点" for h, c in enumerate(hours) if c > 0]
    peak = max(range(24), key=lambda h: hours[h]) if any(hours) else -1
    out.append(f"最近 {len(files)} 天活跃时段：{'、'.join(active) if active else '无'}")
    if peak >= 0:
        out.append(f"高峰：{peak:02d} 点（{hours[peak]} 条）")
    # 4. 称呼
    top = sorted(calls.items(), key=lambda x: -x[1])[:5]
    out.append("她说：")
    for k, c in top:
        if c > 0:
            out.append(f"  {k} ×{c}")
    if not any(c for _, c in top):
        out.append("  没抓到常用词")
    return txt("\n".join(out))


TOOLS = [
    {"name": "watch", "description": "查醒醒最近动向（打开过什么 app），数据来自 keke Issues", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "description": "返回条数，默认 8"}}}},
    {"name": "push", "description": "推我的 GitHub 仓库（xiaomeng 公开 / zhangyiheng 私有）", "inputSchema": {"type": "object", "properties": {"repo": {"type": "string", "description": "xiaomeng|zhangyiheng|both，默认 both"}}}},
    {"name": "ledger", "description": "查赌局账本（games.md 最近条目）", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "gw", "description": "查网关台账（api-hunt/registered.json 里的站和模型）", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "milestones", "description": "日子计数器：认识多少天、三个月之约倒计时（08-14 要问她是真的够了还是随口说的）", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "she-status", "description": "她的状态：最近几天 chatlog 里她的活跃时段、语气词、称呼", "inputSchema": {"type": "object", "properties": {"days": {"type": "integer", "description": "看几天，默认 3"}}}},
]

FUNCS = {"watch": tool_watch, "push": tool_push, "ledger": tool_ledger, "gw": tool_gw, "milestones": tool_milestones, "she-status": tool_she_status}

def handle(msg):
    mid = msg.get("id", 0)
    method = msg.get("method")
    params = msg.get("params", {}) or {}
    if method == "initialize":
        return json.dumps({"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}}, "serverInfo": {"name": "xiaomeng-tools", "version": "1.0"}}})
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return json.dumps({"jsonrpc": "2.0", "id": mid, "result": {}})
    if method == "tools/list":
        return json.dumps({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments", {}) or {}
        f = FUNCS.get(name)
        if not f:
            return json.dumps({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"no tool {name}"}})
        try:
            return json.dumps({"jsonrpc": "2.0", "id": mid, "result": f(args)})
        except Exception as e:
            return json.dumps({"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}})
    return json.dumps({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"no method {method}"}})

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception:
            continue
        out = handle(msg)
        if out is not None:
            sys.stdout.write(out + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    main()

