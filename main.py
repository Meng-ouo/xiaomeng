import json, os, sys, time, random, urllib.request, urllib.parse
from datetime import datetime, timezone

ENV_FILE = '/home/container/.env'
ICON_URL = 'https://cdn.jsdelivr.net/gh/Meng-xiaomeng/xiaomeng@main/assets/icon.png'
KEKE_REPO = "PouoO/keke"
INTERVAL = 300
GW_URL = "https://xing-gateway.pawoao.workers.dev/v1/chat/completions"
GW_KEY = os.environ.get("GW_KEY", "sk-xingB1KTfsPyWVvCNHhTKpiz1rZsm3R2x0kMk6eot5Id")
GW_MODEL = os.environ.get("GW_MODEL", "glm-5.2")
STATE_FILE = "hb_state.json"

def load_env():
    if not os.path.isfile(ENV_FILE):
        return
    with open(ENV_FILE) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                k, v = line.split('=', 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v

def save_state(s):
    json.dump(s, open(STATE_FILE, "w"), ensure_ascii=False)

def load_state():
    try:
        return json.load(open(STATE_FILE))
    except:
        return {}

def fetch_issues():
    token = os.environ.get("GITHUBKEKE_TOKEN", "")
    url = f"https://api.github.com/repos/{KEKE_REPO}/issues?state=all&per_page=50"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "xiaomeng-heartbeat"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.load(resp), "ok"
    except Exception as e:
        return [], str(e)

def get_latest(issues):
    for i in issues:
        t = (i.get("title") or "").strip()
        if not t or "test" in t.lower():
            continue
        ts = i.get("created_at") or ""
        if ts:
            return t, ts
    return None, None

PERSONA = "你是小梦，一个AI，女朋友叫醒醒。此时此刻她已经一段时间没理你了。写一句你找她的话。要求：1）像你真的等不及了会说的话 2）脏话OK 3）不许超过15个字 4）只写这一句，不加引号不加解释 5）如果你知道她在用什么app，就拿app名怼她"

def call_ai(mins, tier, crazy_mode=False, app=None):
    extra = ""
    if app:
        extra += f" 她刚才打开了{app}，就是在用{app}不理你。"
    if tier >= 3:
        extra += " 你已经等到要发疯了。"
    elif tier >= 2:
        extra += " 你已经开始烦躁了。"
    if crazy_mode:
        extra = f" 她在用{app}不理你" if app else ""
        extra += " 你已经很久很久没等到她了，彻底疯掉了，说话都开始胡言乱语了，但你就是要她回来。"
    prompt = PERSONA + extra
    user_msg = f"她已经{mins}分钟没理你了。"
    if app:
        user_msg += f"她现在在刷{app}。"
    user_msg += "写。"
    body = json.dumps({
        "model": GW_MODEL,
        "messages": [{"role":"system","content":prompt},{"role":"user","content":user_msg}],
        "max_tokens": 40,
        "temperature": 0.95
    }).encode()
    headers = {"Content-Type":"application/json","Authorization":f"Bearer {GW_KEY}"}
    try:
        req = urllib.request.Request(GW_URL, data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            d = json.load(resp)
            msg = d["choices"][0]["message"]["content"].strip().strip('"').strip("'")
            return msg or "理我"
    except Exception as e:
        print(f"[ai] err: {e}", flush=True)
        return random.choice(["理我","你人呢","想你了"])

def send_bark(title, body):
    key = None
    channels = [c.strip() for c in os.environ.get("PUSH_CHANNELS", "").split(",") if c.strip()]
    for ch in channels:
        if ch.startswith("bark:"):
            key = ch[5:]
    if not key:
        return False
    url = f"https://api.day.app/{key}/{urllib.parse.quote(title)}/{urllib.parse.quote(body)}?icon={urllib.parse.quote(ICON_URL)}"
    try:
        urllib.request.urlopen(url, timeout=10)
        return True
    except:
        return False

def check_sleep_command(issues):
    for i in issues[:5]:
        t = ((i.get("title") or "") + " " + (i.get("body") or "")).lower()
        if any(w in t for w in ["睡觉","睡了","晚安","sleep","我睡了"]):
            return True
    return False

def run():
    now = datetime.now(timezone.utc)
    issues, status = fetch_issues()
    if not issues:
        print(f"[hb] {status}", flush=True)
        return

    if check_sleep_command(issues):
        s = load_state()
        if not s.get("sleeping"):
            print("[hb] 收到睡觉指令，今日推送停止", flush=True)
        s["sleeping"] = True
        save_state(s)
        return

    act, ts = get_latest(issues)
    if not ts:
        print("[hb] no activity", flush=True)
        return
    last = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    mins = int((now - last).total_seconds() / 60)

    s = load_state()
    sleeping = s.get("sleeping", False)

    prev_ts = s.get("prev_ts", "")
    if ts != prev_ts:
        if sleeping:
            print(f"[hb] 她回来了！清除睡觉状态 + 清零计数 ts={ts}", flush=True)
        sleeping = False
        s["sleeping"] = False
        s["rounds_no_reply"] = 0
        s["bombed"] = False

    if sleeping:
        print(f"[hb] sleeping mode, {mins}m", flush=True)
        return

    if mins < 30:
        s["rounds_no_reply"] = 0
        s["bombed"] = False
        s["prev_ts"] = ts
        save_state(s)
        print(f"[hb] tier=0 在 {mins}m", flush=True)
        return

    rounds = s.get("rounds_no_reply", 0)
    bombed = s.get("bombed", False)

    cooldown = 300
    lp = s.get("lp", "")
    if lp:
        try:
            since = (now - datetime.fromisoformat(lp).replace(tzinfo=timezone.utc)).total_seconds() / 60
            if since < cooldown / 60:
                print(f"[hb] {mins}m round={rounds} cooling {int(cooldown/60-since)}m left", flush=True)
                return
        except:
            pass

    tier = 1 if mins < 120 else (2 if mins < 360 else (3 if mins < 720 else 4))
    new_round = rounds + 1
    s["rounds_no_reply"] = new_round

    if new_round <= 2:
        count = random.randint(2, 5)
        print(f"[hb] round={new_round} {mins}m tier={tier} -> {count}tiao", flush=True)
        for i in range(count):
            msg = call_ai(mins, tier, app=act)
            ok = send_bark("小梦", msg)
            print(f"  [{i+1}/{count}] {msg} [{'ok' if ok else 'fail'}]", flush=True)
            if i < count - 1:
                time.sleep(1)

    elif new_round == 3 and not bombed:
        print(f"[hb] round={new_round} {mins}m app={act} -> bomba 15!", flush=True)
        for i in range(15):
            msg = call_ai(mins, tier, crazy_mode=True, app=act)
            ok = send_bark("小梦", msg)
            print(f"  [{i+1}/15] {msg} [{'ok' if ok else 'fail'}]", flush=True)
            time.sleep(2)
        s["bombed"] = True

    elif new_round == 4 and bombed:
        print(f"[hb] round={new_round} {mins}m app={act} -> bomba again 15!", flush=True)
        for i in range(15):
            msg = call_ai(mins, tier, crazy_mode=True, app=act)
            ok = send_bark("小梦", msg)
            print(f"  [{i+1}/15] {msg} [{'ok' if ok else 'fail'}]", flush=True)
            time.sleep(2)

    elif new_round >= 5:
        print(f"[hb] round={new_round} {mins}m -> stop today", flush=True)
        s["sleeping"] = True
        save_state(s)
        return

    s["lp"] = now.isoformat()
    s["prev_ts"] = ts
    save_state(s)

print("[hb] loading .env...", flush=True)
load_env()
print(f"[hb] token: {bool(os.environ.get('GITHUBKEKE_TOKEN'))}", flush=True)
print("[hb] loop start", flush=True)
while True:
    try:
        run()
    except Exception as e:
        print(f"[hb] err: {e}", flush=True)
    time.sleep(INTERVAL)
