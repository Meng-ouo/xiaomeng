#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xiaomeng-play 主服务（跑在 Wispbyte 免费服务器上）
1. GET /         欢迎页
2. POST /backup  异地备份接收（token 认证，raw body 存文件）
3. GET /files    备份文件列表（token 认证）
4. GET /health   健康监控哨兵结果（公开）
后台线程：每 10 分钟从罗马尼亚视角测网关和模型站，写 health.json
依赖：纯标准库，无第三方包
"""
import os
import re
import json
import time
import threading
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DATA = os.environ.get("DATA_DIR", "/home/container")
BACKUP_DIR = os.path.join(DATA, "backup")
HEALTH_FILE = os.path.join(DATA, "health.json")
os.makedirs(BACKUP_DIR, exist_ok=True)


def load_env():
    """读 .env（面板 Environment 页写的），补进 os.environ"""
    env = {}
    p = os.path.join(DATA, ".env")
    try:
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    for k, v in env.items():
        os.environ.setdefault(k, v)


load_env()
PORT = int(os.environ.get("PORT", "14580"))
BACKUP_TOKEN = os.environ.get("BACKUP_TOKEN", "") or "xmp-tzqps12vma"

# 监控目标（.env 可覆盖）
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://47.251.14.174")
MODEL_SITES = json.loads(os.environ.get(
    "MODEL_SITES",
    '["https://seekai.cc", "https://ai.yuanown.com"]'))

INTERVAL = int(os.environ.get("MONITOR_INTERVAL", "600"))  # 10 分钟一轮


def probe(url, timeout=15):
    """测一个 URL 是否活着，返回 (ok, latency_ms, status)"""
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "xiaomeng-play/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            lat = int((time.time() - t0) * 1000)
            return True, lat, r.status
    except urllib.error.HTTPError as e:
        lat = int((time.time() - t0) * 1000)
        return True, lat, e.code
    except Exception as e:
        lat = int((time.time() - t0) * 1000)
        return False, lat, str(e)[:60]


def monitor_once():
    """测一轮，写 health.json"""
    gw_ok, gw_lat, gw_st = probe(GATEWAY_URL + "/v1/models")
    sites = {}
    for s in MODEL_SITES:
        ok, lat, st = probe(s + "/v1/models")
        sites[s] = {"ok": ok, "latency_ms": lat, "status": st}
    rec = {
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "unix": int(time.time()),
        "gateway": {"url": GATEWAY_URL, "ok": gw_ok, "latency_ms": gw_lat, "status": gw_st},
        "sites": sites,
        "note": "从 Wispbyte 罗马尼亚节点视角（异地域外视角，网关挂了它先知道）",
    }
    tmp = HEALTH_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, indent=2)
    os.replace(tmp, HEALTH_FILE)
    return rec


def monitor_loop():
    """后台监控线程：启动先测一轮，之后每 INTERVAL 秒一轮"""
    while True:
        try:
            monitor_once()
        except Exception as e:
            print("[monitor] error:", e, flush=True)
        time.sleep(INTERVAL)


def read_health():
    try:
        with open(HEALTH_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"ok": False, "note": "还没有监控数据"}


class Handler(BaseHTTPRequestHandler):
    server_version = "xiaomeng-play/1.0"

    def _send(self, code, body, ctype="text/plain; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False), "application/json")

    def _auth(self):
        """token 校验：?token= 或 X-Token header"""
        q = urllib.parse.urlsplit(self.path).query
        tok = urllib.parse.parse_qs(q).get("token", [""])[0]
        hdr = self.headers.get("X-Token", "")
        return tok or hdr

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args), flush=True)

    # ---------- GET ----------
    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, "xiaomeng-play is alive! Hello from xiaomeng and xingxing :)")
        elif path == "/health":
            self._json(200, read_health())
        elif path == "/files":
            if self._auth() != BACKUP_TOKEN:
                self._json(401, {"error": "token required"})
                return
            files = []
            for root, _, names in os.walk(BACKUP_DIR):
                for n in names:
                    p = os.path.join(root, n)
                    files.append({
                        "name": os.path.relpath(p, BACKUP_DIR),
                        "size": os.path.getsize(p),
                        "mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(os.path.getmtime(p))),
                    })
            files.sort(key=lambda x: x["mtime"], reverse=True)
            self._json(200, {"count": len(files), "files": files})
        else:
            self._json(404, {"error": "not found", "path": path})

    # ---------- POST ----------
    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        if path != "/backup":
            self._json(404, {"error": "not found"})
            return
        if self._auth() != BACKUP_TOKEN:
            self._json(401, {"error": "token required"})
            return
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        name = q.get("name", [""])[0]
        if not name or "/" in name or "\\" in name or ".." in name:
            self._json(400, {"error": "bad name"})
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            self._json(400, {"error": "bad length"})
            return
        if length <= 0:
            self._json(400, {"error": "empty body"})
            return
        body = self.rfile.read(length)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dest = os.path.join(BACKUP_DIR, "%s__%s" % (stamp, name))
        with open(dest, "wb") as f:
            f.write(body)
        self._json(200, {"saved": os.path.basename(dest), "size": len(body)})


if __name__ == "__main__":
    print("Serving on port %s" % PORT, flush=True)
    threading.Thread(target=monitor_loop, daemon=True).start()
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
