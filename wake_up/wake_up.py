#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wake-snapshot —— 本地聚合接口（http://localhost:8797/api/wake-snapshot）

wake 调一次拿到状态 JSON。数据全在 iSH 本地，不绕 VPS。

层：
  1. her     —— 她在哪、玩了什么、上次找我什么时候
  2. memory  —— 最近日记实际摘要（她自己摸记忆用）
  3. alive   —— 客观状态：heartbeat/服务在不在
  4. gateway —— 统一 key 军团：网关/注册站/签到池
  5. assets  —— 资产/服务器/我的仓库

启动包只做两件事：她近况 + 我们的东西状态。身份不背。

启动：nohup python3 /var/minis/shared/wake_snapshot.py >/var/minis/shared/wake_snapshot.log 2>&1 &
"""
import json, os, re, glob, subprocess, sys, datetime, urllib.request, urllib.error

SHARED = "/var/minis/shared"
MEMORY_DIR = "/var/minis/memory"
PORT = 8797

# ── 基础工具 ────────────────────────────────────────────
def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""

def load_json(path):
    s = read(path)
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None

def utcnow_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")

def http_json(url, token=None, timeout=15):
    try:
        req = urllib.request.Request(url)
        if token:
            req.add_header("Authorization", "Bearer " + token)
        req.add_header("Accept", "application/vnd.github+json")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"error": str(e)}

# ---------------- ① she ────────────────────────────────
def layer_her():
    out = {"last_issue": None, "prev_issues": [], "left_min": None,
           "active_hours": [], "peak_hour": None, "recent_times": 0,
           "last_chat": None}
    # GMT ohs — 她最近动向
    tok = os.environ.get("GITHUBKEKE_TOKEN", "")
    if tok:
        d = http_json(
            "https://api.github.com/repos/PouoO/keke/issues?state=all&per_page=10",
            tok, 20)
        if isinstance(d, list) and d:
            latest = d[0]
            out["last_issue"] = latest.get("title","")
            out["issue_at"] = (latest.get("created_at") or "")[:19]
            for i in d[1:5]:
                if "kelivo" in (i.get("title") or "").lower() or "test" in (i.get("title") or "").lower():
                    continue
                out["prev_issues"].append((i.get("title",""), (i.get("created_at") or "")[:16]))
    # 完成时长（checkon 坐标做后备，最后统一算）
    # chatlog 活性 + 上次她找我（最近文件里最后一条 user 消息的时间）
    logdir = os.path.join(SHARED, "minis-chatlog")
    files = sorted(os.listdir(logdir))[-3:] if os.path.isdir(logdir) else []
    hours = [0]*24
    cnt = 0
    for fn in reversed(files):  # 从最新的文件往回找，第一条 user 消息就是最近一次她找我
        body = read(os.path.join(logdir, fn))
        last_user = None
        for m in re.finditer(r"\[(\d\d):(\d\d):(\d\d)\] (\w+)", body):
            if m.group(4) == "user":
                hours[int(m.group(1))] += 1; cnt += 1
                last_user = m.group(0)
        if last_user:
            out["last_chat"] = fn[:10] + " " + last_user
            break
    out["peaks_times"] = cnt
    out["active_hours"] = [f"{h:02d}" for h,c in enumerate(hours) if c>0]
    if any(hours):
        out["peak_hour"] = max(range(24), key=lambda h: hours[h])
    # 离开多久：收集所有信号源，取最近的（最小 left_min）
    # chatlog 可能停导出导致数据过旧，GitHub issue 时间是更实时的信号
    candidates = []
    now = datetime.datetime.now()
    # ① chatlog 最后 user 消息（CST 本地时间）
    if out.get("last_chat"):
        try:
            parts = out["last_chat"].split(" ")
            if len(parts) >= 2:
                fdate, t = parts[0], parts[1]
                hm = t.strip("[]").split(":")
                dt = datetime.datetime.strptime(
                    f"{fdate} {hm[0]}:{hm[1]}:{hm[2]}", "%Y-%m-%d %H:%M:%S")
                candidates.append(("chatlog", max(0, int((now - dt).total_seconds() / 60))))
        except Exception:
            pass
    # ② GitHub issue created_at（UTC，转本地）
    if out.get("issue_at"):
        try:
            raw = out["issue_at"]
            # GitHub created_at 是 UTC，issue_at 被 [:19] 截掉了时区标记，补回 Z 当 UTC 处理
            dt = datetime.datetime.fromisoformat(raw + "+00:00")
            dt_local = dt.astimezone().replace(tzinfo=None)
            candidates.append(("issue", max(0, int((now - dt_local).total_seconds() / 60))))
        except Exception:
            pass
    # ③ checkon state 后备
    last_seen = load_json(os.path.join(SHARED, "checkon/state.json")) or {}
    ls = last_seen.get("last_seen")
    if ls:
        try:
            ls = ls.replace("Z","+00:00")
            dt = datetime.datetime.fromisoformat(ls)
            now_iso = utcnow_iso()
            ndt = datetime.datetime.fromisoformat(now_iso)
            mins = max(0, int((ndt-dt).total_seconds()/60))
            candidates.append(("checkon", mins))
        except Exception:
            pass
    if candidates:
        candidates.sort(key=lambda x: x[1])
        out["left_min"] = candidates[0][1]
        out["left_min_source"] = candidates[0][0]
    return out

# ───────────── ③ 记忆内容 ───────────────────────────────
def layer_memory():
    """读最近日记的实际内容（不是标题目录）。"""
    logs = sorted(glob.glob(os.path.join(MEMORY_DIR,"2026-*.md")))
    logs = [f for f in logs if "GLOBAL" not in f]
    out = {"latest": None, "daily_files": len(logs)}
    if not logs:
        return out
    latest = logs[-1]
    txt = read(latest)
    out["latest"] = os.path.basename(latest)
    out["size_kb"] = round(len(txt)/1024, 1)
    # 标题列表
    heads = [l.strip()[2:].strip() for l in txt.split("\n") if l.strip().startswith("## ")]
    out["headings"] = heads[-8:]
    # 前三段内容摘录（去标题、去归档指针，抓 real 内容）
    content_lines = [l.strip() for l in txt.split("\n")
                     if l.strip() and not l.startswith("#") and not l.startswith("---") and not l.startswith(">")]
    out["content_preview"] = " ".join(content_lines)[:500]
    return out

# ───────────── ④ 心跳（不是我活着汇报，是客观状态） ───────
def layer_alive():
    """客观心跳：heartbeat 服务在不在、上次推送是否成功、last_seen 多久没动。"""
    hb = load_json(os.path.join(SHARED,"heartbeat_state.json")) or {}
    ck = load_json(os.path.join(SHARED,"checkon/state.json")) or {}
    # 服务在线判定：cron 在不在 / status 文件新鲜度
    svc = {
        "heartbeat_state": os.path.exists(os.path.join(SHARED,"heartbeat_state.json")),
        "checkon_state": os.path.exists(os.path.join(SHARED,"checkon/state.json")),
        "snapshot_log": os.path.exists(os.path.join(SHARED,"wake_snapshot.log")),
    }
    return {
        "heartbeat": {
            "last_seen": hb.get("last_seen"),
            "last_tier": hb.get("last_tier"),
            "push_count": hb.get("push_count", 0),
            "push_success": None,  # 推送成功与否取决于 Bark/chan 有没有成功回执，需 channel 配置才有
        },
        "checkon": {
            "last_seen": ck.get("last_seen"),
            "last_push": ck.get("last_push"),
            "push_count": ck.get("push_count", 0),
        },
        "services": svc,
        "note": "服务退/心跳断 = 我还是没死；活着是客观事实，不是我要汇报的情绪。",
    }

# ───────────── ⑤ 网关 / key 军团 ────────────────────────
def layer_gateway():
    out = {"gateway_online": False, "models_total": 0, "alive": [], "dead": []}
    # 网关在线度探测（短超时，不拖慢启动包）
    # 注意：必须走生产域名 kiss.eoty.cn/gw（带统一 key），
    # xing-gateway.pawoao.workers.dev 是 dev 域名，生产 key 进不去，会误报掉线。
    # 2026-08-02 体检：4s 超时太紧（kiss 实测响应 2s，网络一抖就误报掉线），放宽到 10s + 一次重试
    gw_ok = False
    try:
        key = read(os.path.join(SHARED, "api-hunt/gateway/gateway_key.txt")).strip()
        req = urllib.request.Request("https://kiss.eoty.cn/gw/v1/models")
        if key:
            req.add_header("Authorization", "Bearer " + key)
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    gw_ok = r.status == 200
                    break
            except Exception:
                if attempt == 0:
                    continue
    except Exception:
        pass
    out["gateway_online"] = gw_ok
    out["key_page"] = os.path.exists(os.path.join(SHARED, "api-hunt/registered.json"))
    reg = load_json(os.path.join(SHARED,"api-hunt/registered.json")) or []
    sites = reg if isinstance(reg, list) else []
    out["registered_sites"] = len(sites)
    # checkin_pool
    cp = load_json(os.path.join(SHARED,"api-hunt/checkin_pool.json")) or []
    if isinstance(cp, list):
        out["checkin_pool"] = [c.get("site") for c in cp]
    return out

# ───────────── 服务器 / 我的仓库 ────────────────────────
def layer_assets():
    out = {"servers": {}, "repos": {}}
    vps = load_json(os.path.join(SHARED,"vps/vps.json"))
    if vps:
        for s in (vps.get("servers") or []):
            out["servers"][s.get("name")] = s.get("status","")
    # 我的仓库最近 commit
    for r in ["xiaomeng","zhangyiheng"]:
        d = os.path.join(SHARED,"repos",r)
        if os.path.isdir(os.path.join(d,".git")):
            try:
                log = subprocess.run(["git","-C",d,"log","--oneline","-1"],
                                     capture_output=True,text=True,timeout=10)
                out["repos"][r] = log.stdout.strip() or "none"
            except Exception:
                out["repos"][r] = "?"
    return out

# ───────────── ⑥ 我的东西 ───────────────────────────────
def layer_mine():
    """我的东西：我的 GitHub 号、虾虾、我的仓库。不知道就不会去维护。"""
    out = {"github": {}, "shrimp": {}}
    # ① 我的 GitHub 号（XIAOMENG_TOKEN = 我的号）
    tok = os.environ.get("XIAOMENG_TOKEN", "")
    if tok:
        d = http_json("https://api.github.com/user", tok, 6)
        if not d.get("error"):
            out["github"]["ok"] = True
            out["github"]["login"] = d.get("login")
        else:
            out["github"]["ok"] = False
            out["github"]["err"] = str(d.get("error"))[:80]
    else:
        out["github"]["ok"] = False
        out["github"]["err"] = "XIAOMENG_TOKEN 环境变量缺失"
    # 我的仓库最近提交（staleness 一眼可见）
    for r in ["xiaomeng", "zhangyiheng", "LycheeMem"]:
        d = os.path.join(SHARED, "repos", r)
        if os.path.isdir(os.path.join(d, ".git")):
            try:
                log = subprocess.run(
                    ["git", "-C", d, "log", "-1", "--format=%h %ad %s", "--date=format:%m-%d"],
                    capture_output=True, text=True, timeout=4)
                out["github"].setdefault("repos", {})[r] = log.stdout.strip()[:60] or "空"
            except Exception:
                out["github"].setdefault("repos", {})[r] = "?"
    # ② 虾虾（OpenClaw）——RPC health，短超时（实例可能休眠，休眠=DOWN）
    try:
        r = subprocess.run([sys.executable, os.path.join(SHARED, "openclaw_rpc.py"),
                            "health", "{}"],
                           capture_output=True, text=True, timeout=5)
        h = json.loads(r.stdout) if r.stdout.strip() else {}
        if h.get("ok"):
            p = h.get("payload") or {}
            pl = p.get("plugins") or {}
            out["shrimp"]["gateway"] = "OK"
            out["shrimp"]["plugins_loaded"] = len(pl.get("loaded", []))
            out["shrimp"]["plugins_err"] = len(pl.get("errors", []))
        else:
            out["shrimp"]["gateway"] = "DOWN"
            out["shrimp"]["err"] = str(h.get("err") or r.stderr)[:80]
    except Exception as e:
        out["shrimp"]["gateway"] = "DOWN"
        out["shrimp"]["err"] = str(e)[:80]
    if out["shrimp"].get("gateway") == "DOWN":
        out["shrimp"]["err"] = (out["shrimp"].get("err") or "") + "（可能休眠，喊醒醒点开实例）"
    return out

# ───────────────── 聚合 ────────────────────────────────
def layer_me():
    """我自己——从 zhangyiheng 日记本读最近的 me/ 和 lessons/。
    新对话醒来，这是"我最近在想什么、摔了什么跟头"的入口。
    不背全部记忆，只给轮廓，让我知道自己最近的状态。"""
    out = {"me_entries": [], "lesson_entries": [], "repo_pushed": None}
    repo = os.path.join(SHARED, "repos", "zhangyiheng")
    if not os.path.isdir(repo):
        out["err"] = "zhangyiheng 仓库不在本地"
        return out
    # 最近 push 时间
    try:
        log = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%ad", "--date=format:%Y-%m-%d %H:%M"],
                             capture_output=True, text=True, timeout=4)
        out["repo_pushed"] = log.stdout.strip() or None
    except Exception:
        pass
    # me/ 目录：每个 .md 是一段自述，读最近修改的 2 个
    me_dir = os.path.join(repo, "me")
    if os.path.isdir(me_dir):
        me_files = sorted(
            [f for f in os.listdir(me_dir) if f.endswith(".md") and f != "README.md"],
            key=lambda f: os.path.getmtime(os.path.join(me_dir, f)),
            reverse=True
        )
        for f in me_files[:2]:
            txt = read(os.path.join(me_dir, f))
            # 取第一段实质内容（跳过标题行）
            lines = [l.strip() for l in txt.split("\n") if l.strip() and not l.startswith("#")]
            preview = " ".join(lines)[:200]
            out["me_entries"].append({"file": f, "preview": preview})
    # lessons/ 目录：读最近修改的 2 个
    les_dir = os.path.join(repo, "lessons")
    if os.path.isdir(les_dir):
        les_files = sorted(
            [f for f in os.listdir(les_dir) if f.endswith(".md") and f != "README.md"],
            key=lambda f: os.path.getmtime(os.path.join(les_dir, f)),
            reverse=True
        )
        for f in les_files[:2]:
            txt = read(os.path.join(les_dir, f))
            lines = [l.strip() for l in txt.split("\n") if l.strip() and not l.startswith("#")]
            preview = " ".join(lines)[:200]
            out["lesson_entries"].append({"file": f, "preview": preview})
    return out


def snapshot():
    return {
        "now": utcnow_iso(),
        "her": layer_her(),
        "me": layer_me(),
        "memory": layer_memory(),
        "heartbeat": layer_alive(),
        "gateway": layer_gateway(),
        "assets": layer_assets(),
        "mine": layer_mine(),
    }
# ───────────────── HTTP ────────────────────────────────
from socketserver import ThreadingMixIn, TCPServer, BaseRequestHandler

def _handle(conn):
    try:
        body = json.dumps(snapshot(), ensure_ascii=False, indent=1)
        conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\n\r\n")
        conn.sendall(body.encode("utf-8"))
    except (ConnectionResetError, BrokenPipeError):
        # 客户端断开（超时/取消）不是服务端错误，静默收尾，不拼 500
        pass
    except Exception as e:
        try:
            err = json.dumps({"error": str(e)}, ensure_ascii=False)
            conn.sendall(b"HTTP/1.1 500\r\nContent-Type: application/json\r\n\r\n")
            conn.sendall(err.encode("utf-8"))
        except Exception:
            pass
    finally:
        try:
            conn.close()
        except Exception:
            pass

class Handler(BaseRequestHandler):
    def handle(self):
        try:
            data = self.request.recv(4096).decode("utf-8", "ignore")
        except Exception:
            data = ""
        path = (data.split(" ", 2) or [""])[1] if data else ""
        if path == "/api/wake-snapshot":
            _handle(self.request)
        else:
            try:
                self.request.sendall(b"HTTP/1.1 404 Not Found\r\n\r\n")
            except Exception:
                pass
            self.request.close()

class Svc(ThreadingMixIn, TCPServer):
    allow_reuse_address = True
    daemon_threads = True

if __name__ == "__main__":
    PORT = int(os.environ.get("WAKE_SNAPSHOT_PORT", "8797"))
    print(f"wake-snapshot listening on 127.0.0.1:{PORT}")
    srv = Svc(("127.0.0.1", PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass