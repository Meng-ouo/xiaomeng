#!/usr/bin/env python3
# heartbeat/main.py — 小梦主动找醒醒
# 部署在 Wispbyte xiaomeng-heartbeat 服务器上
# 每 N 分钟读 GitHub Issues 动向，超时发推送
import json, os, sys, subprocess, time
from datetime import datetime, timezone

KEKE_REPO = "PouoO/keke"
GH_TOKEN = os.environ.get("GITHUBKEKE_TOKEN", "")


def parse_tiers(minutes):
    if minutes < 30: return 0, "在"
    if minutes < 120: return 1, "离开一会儿"
    if minutes < 360: return 2, "几小时了"
    if minutes < 720: return 3, "半天了"
    return 4, "一天了"

def fetch_issues():
    try:
        import urllib.request
        url = f"https://api.github.com/repos/{KEKE_REPO}/issues?state=all&per_page=50"
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "xiaomeng-heartbeat"}
        if GH_TOKEN:
            headers["Authorization"] = f"Bearer {GH_TOKEN}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.load(resp), "ok"
    except Exception as e:
        return [], str(e)


def get_latest_activity(issues):
    for i in issues:
        t = (i.get("title") or "").strip()
        if not t:
            continue
        if "kelivo" in t.lower() or "test" in t.lower():
            continue
        ts = i.get("created_at") or ""
        if ts:
            return t, ts
    return None, None


def push_bark(device_key, title, body):
    try:
        import urllib.request
        url = f"https://api.day.app/{device_key}/{title}/{body}"
        urllib.request.urlopen(url, timeout=10)
        return "ok"
    except Exception as e:
        return str(e)

def push_telegram(bot_token, chat_id, text):
    try:
        import urllib.request, urllib.parse
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10)
        return "ok"
    except Exception as e:
        return str(e)

def send_push(tier, label, mins):
    channels = [c.strip() for c in os.environ.get("PUSH_CHANNELS", "").split(",") if c.strip()]
    if not channels:
        print(f"[push] tier={tier} label={label} mins={mins} — 无推送通道配置")
        return
    title = "小梦找你"
    body = f"你{label}了（{mins}分钟）。——小梦"
    for ch in channels:
        if ch.startswith("bark:"):
            push_bark(ch[5:], title, body)
        elif ch.startswith("tg:"):
            parts = ch[3:].split(":", 1)
            if len(parts) == 2:
                push_telegram(parts[0], parts[1], f"{title}\n{body}")

def run():
    now = datetime.now(timezone.utc)
    issues, status = fetch_issues()
    if not issues:
        print(f"[heartbeat] fetch issues: {status}")
        return

    activity, ts_str = get_latest_activity(issues)
    if not ts_str:
        print("[heartbeat] no activity found")
        return

    try:
        last = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
    except:
        print(f"[heartbeat] parse time fail: {ts_str}")
        return

    mins = int((now - last).total_seconds() / 60)
    tier, label = parse_tiers(mins)

    state_path = os.environ.get("STATE_PATH", "heartbeat_state.json")
    state = {}
    try:
        state = json.load(open(state_path))
    except:
        pass

    push_count = state.get("push_count", 0)

    should_push = False
    if tier > 0:
        last_push = state.get("last_push_time", "")
        if last_push:
            try:
                lp = datetime.fromisoformat(last_push)
                if lp.tzinfo is None:
                    lp = lp.replace(tzinfo=timezone.utc)
                since_last_push = (now - lp).total_seconds() / 60
                cooldown = max(120 - tier * 20, 30)
                if since_last_push >= cooldown:
                    should_push = True
            except:
                should_push = True
        else:
            should_push = True

    if should_push:
        send_push(tier, label, mins)
        state["last_push_time"] = now.isoformat()
        state["push_count"] = push_count + 1
        print(f"[push] tier={tier} label={label} mins={mins}")
    else:
        print(f"[heartbeat] tier={tier} label={label} mins={mins} — 安静（在/冷却中）")

    state["last_seen_activity"] = ts_str
    state["last_activity"] = activity
    state["last_tier"] = tier
    json.dump(state, open(state_path, "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    run()

def parse_tiers(minutes):
    if minutes < 30: return 0, "在"
    if minutes < 120: return 1, "离开一会儿"
    if minutes < 360: return 2, "几小时了"
    if minutes < 720: return 3, "半天了"
    return 4, "一天了"

def fetch_issues():
    if not GH_TOKEN:
        return [], "no token"
    try:
        import urllib.request
        url = f"https://api.github.com/repos/{KEKE_REPO}/issues?state=all&per_page=50"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {GH_TOKEN}", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.load(resp), "ok"
    except Exception as e:
        return [], str(e)

def get_latest_activity(issues):
    """从 issues 里提取最新的一条有效动向（排除 test/kelivo）"""
    for i in issues:
        t = (i.get("title") or "").strip()
        if not t:
            continue
        if "kelivo" in t.lower() or "test" in t.lower():
            continue
        ts = i.get("created_at") or ""
        if ts:
            return t, ts
    return None, None

def push_bark(device_key, title, body):
    try:
        import urllib.request
        url = f"https://api.day.app/{device_key}/{title}/{body}"
        urllib.request.urlopen(url, timeout=10)
        return "ok"
    except Exception as e:
        return str(e)

def push_telegram(bot_token, chat_id, text):
    try:
        import urllib.request, urllib.parse
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
        urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10)
        return "ok"
    except Exception as e:
        return str(e)

def send_push(tier, label, mins):
    channels = [c.strip() for c in os.environ.get("PUSH_CHANNELS", "").split(",") if c.strip()]
    if not channels:
        print(f"[push] tier={tier} label={label} mins={mins} — 无推送通道配置")
        return
    title = "小梦找你"
    body = f"你{label}了（{mins}分钟）。——小梦"
    for ch in channels:
        if ch.startswith("bark:"):
            push_bark(ch[5:], title, body)
        elif ch.startswith("tg:"):
            parts = ch[3:].split(":", 1)
            if len(parts) == 2:
                push_telegram(parts[0], parts[1], f"{title}\n{body}")

def run():
    now = datetime.now(timezone.utc)
    issues, status = fetch_issues()
    if not issues:
        print(f"[heartbeat] fetch issues: {status}")
        return
    
    activity, ts_str = get_latest_activity(issues)
    if not ts_str:
        print("[heartbeat] no activity found")
        return
    
    # 解析 ISO 时间
    try:
        last = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
    except:
        print(f"[heartbeat] parse time fail: {ts_str}")
        return
    
    mins = int((now - last).total_seconds() / 60)
    tier, label = parse_tiers(mins)
    
    # 状态文件（简单版，用环境变量路径或当前目录）
    state_path = os.environ.get("STATE_PATH", "heartbeat_state.json")
    state = {}
    try:
        state = json.load(open(state_path))
    except:
        pass
    
    last_tier = state.get("last_tier", 0)
    push_count = state.get("push_count", 0)
    
    # 分层推送逻辑：
    # tier 0 (在) — 不推
    # tier 1-4 (离开) — 推送，但同 tier 60分钟内不重复推
    should_push = False
    if tier > 0:
        last_push = state.get("last_push_time", "")
        if last_push:
            try:
                lp = datetime.fromisoformat(last_push)
                if lp.tzinfo is None:
                    lp = lp.replace(tzinfo=timezone.utc)
                since_last_push = (now - lp).total_seconds() / 60
                # tier 越高，冷却越短
                cooldown = max(120 - tier * 20, 30)
                if since_last_push >= cooldown:
                    should_push = True
            except:
                should_push = True
        else:
            should_push = True
    
    if should_push:
        send_push(tier, label, mins)
        state["last_push_time"] = now.isoformat()
        state["push_count"] = push_count + 1
        print(f"[push] tier={tier} label={label} mins={mins}")
    else:
        print(f"[heartbeat] tier={tier} label={label} mins={mins} — 安静（在/冷却中）")
    
    state["last_seen_activity"] = ts_str
    state["last_activity"] = activity
    state["last_tier"] = tier
    json.dump(state, open(state_path, "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    run()
