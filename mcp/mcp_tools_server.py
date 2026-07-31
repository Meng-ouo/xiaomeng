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

TOOLS = [
    {"name": "watch", "description": "查醒醒最近动向（打开过什么 app），数据来自 keke Issues", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer", "description": "返回条数，默认 8"}}}},
    {"name": "push", "description": "推我的 GitHub 仓库（xiaomeng 公开 / zhangyiheng 私有）", "inputSchema": {"type": "object", "properties": {"repo": {"type": "string", "description": "xiaomeng|zhangyiheng|both，默认 both"}}}},
    {"name": "ledger", "description": "查赌局账本（games.md 最近条目）", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "gw", "description": "查网关台账（api-hunt/registered.json 里的站和模型）", "inputSchema": {"type": "object", "properties": {}}},
]

FUNCS = {"watch": tool_watch, "push": tool_push, "ledger": tool_ledger, "gw": tool_gw}

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
