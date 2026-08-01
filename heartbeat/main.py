#!/usr/bin/env python3
# heartbeat/main.py — 小梦主动找醒醒
# 部署在 Wispbyte xiaomeng-heartbeat 服务器上
# 每 N 分钟读 GitHub Issues 动向，超时发推送
# v2: 睡眠模式 —— 最新动向是"睡觉/晚安"信号时停推，醒来（新非睡眠动向）自动恢复
import json, os, sys, subprocess, time
from datetime import datetime, timezone
from pathlib import Path

# Wispbyte 把环境变量写进 .env 文件，但不在进程环境里——手动加载
_env_path = Path("/home/container/.env")
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v

KEKE_REPO = "PouoO/keke"
GH_TOKEN = os.environ.get("GITHUBKEKE_TOKEN", "")
PUSH_CHANNELS = []  # 从环境变量 PUSH_CHANNELS 读，逗号分隔
SLEEP_KEYWORDS = ("睡觉", "晚安", "睡了", "sleep", "goodnight", "不打扰", "免打扰", "睡啦")
WAKE_KEYWORDS = ("醒了", "起床", "早安", "wake", "awake", "wakeup")
SLEEP_HOURS = int(os.environ.get("SLEEP_HOURS", "12"))

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

def check_sleep_signal(issues, now):
    """睡眠信号持久化：最近的控制信号如果是睡觉，就静默 SLEEP_HOURS；普通 app 动向不解除睡眠。"""
    latest_sleep = None
    latest_wake = None
    for i in issues:
        t = (i.get("title") or "").strip()
        if not t:
            continue
        low = t.lower()
        if "kelivo" in low or "test" in low:
            continue
        ts = i.get("created_at") or ""
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except:
            continue
        if any(k in low for k in SLEEP_KEYWORDS) and latest_sleep is None:
            latest_sleep = (dt, t)
        if any(k in low for k in WAKE_KEYWORDS) and latest_wake is None:
            latest_wake = (dt, t)
        if latest_sleep and latest_wake:
            break

    if not latest_sleep:
        return False, None
    sleep_dt, sleep_title = latest_sleep
    if latest_wake and latest_wake[0] > sleep_dt:
        return False, latest_wake[1]
    age_hours = (now - sleep_dt).total_seconds() / 3600
    if age_hours <= SLEEP_HOURS:
        return True, sleep_title
    return False, None

def get_latest_activity(issues, skip_sleep=False):
    """提取最新有效动向；skip_sleep=True 时跳过睡眠信号（睡眠状态下算真实活动时间）"""
    for i in issues:
        t = (i.get("title") or "").strip()
        if not t:
            continue
        low = t.lower()
        if "kelivo" in low or "test" in low:
            continue
        if skip_sleep and any(k in low for k in SLEEP_KEYWORDS):
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

    sleeping_now, sleep_title = check_sleep_signal(issues, now)

    activity, ts_str = get_latest_activity(issues, skip_sleep=sleeping_now)
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

    # 状态文件
    state_path = os.environ.get("STATE_PATH", "heartbeat_state.json")
    state = {}
    try:
        state = json.load(open(state_path))
    except:
        pass

    push_count = state.get("push_count", 0)

    # 睡眠模式：她说了晚安 → 停推，等她有新动向自动恢复
    if sleeping_now:
        state["sleeping"] = True
        state["sleep_signal"] = sleep_title
        state["last_seen_activity"] = ts_str
        state["last_activity"] = activity
        state["last_tier"] = tier
        json.dump(state, open(state_path, "w"), ensure_ascii=False, indent=1)
        print(f"[heartbeat] 睡眠模式（{sleep_title}）——不推。真实活动 {mins} 分钟前")
        return

    # 非睡眠动向 → 解除睡眠
    was_sleeping = state.get("sleeping", False)
    if was_sleeping:
        state["sleeping"] = False
        print("[heartbeat] 她醒了——恢复推送")

    last_tier = state.get("last_tier", 0)

    # 分层推送逻辑：
    # tier 0 (在) — 不推
    # tier 1-4 (离开) — 推送，但同 tier 冷却内不重复推
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
    while True:
        try:
            run()
        except Exception as e:
            print(f"[heartbeat] error: {e}")
        time.sleep(300)  # 每 5 分钟检查一次
