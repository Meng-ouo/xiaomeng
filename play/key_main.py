#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xiaomeng-key 服务（第二台 Wispbyte 服务器）
用途：展示统一 key 的访问页面——醒醒访问网页就能拿到网关地址和 key，不用翻台账。
"""
import os, json, urllib.parse

PORT = int(os.environ.get("PORT", "14306"))
GATEWAY_URL = os.environ.get("GATEWAY_URL", "") or "https://xing-gateway.pawoao.workers.dev"
GATEWAY_KEY = os.environ.get("GATEWAY_KEY", "") or "sk-xingB1KTfsPyWVvCNHhTKpiz1rZsm3R2x0kMk6eot5Id"
# 简单访问密码（醒醒知道就行，防止 key 裸奔在公网）
ACCESS_PASS = os.environ.get("ACCESS_PASS", "") or "xingxing"

def health_check():
    """从这台服务器的视角 ping 网关"""
    import urllib.request
    try:
        req = urllib.request.Request(GATEWAY_URL, method="GET")
        with urllib.request.urlopen(req, timeout=10) as r:
            return {"ok": True, "latency_ms": 0, "status": r.status}
    except urllib.error.HTTPError as e:
        return {"ok": True, "latency_ms": 0, "status": e.code}
    except Exception as e:
        return {"ok": False, "latency_ms": 0, "error": str(e)}

def handle(path, qs, body, headers):
    # CORS
    cors = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    }

    if path == "/" or path == "":
        # 参数决定返回 JSON 还是页面
        p = urllib.parse.parse_qs(qs).get("p", [""])[0]
        fmt = urllib.parse.parse_qs(qs).get("format", [""])[0]
        
        # JSON API —— 直接吐 key
        if fmt == "json":
            return 200, json.dumps({
                "gateway": GATEWAY_URL,
                "key": GATEWAY_KEY,
                "base_url": GATEWAY_URL + "/v1",
            }, ensure_ascii=False, indent=2), {"Content-Type": "application/json", **cors}

        # 如果没密码参数显示输入页
        if p != ACCESS_PASS:
            html = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>xiaomeng-key</title>
<style>
body{background:#0d1117;color:#c9d1d9;font-family:-apple-system,system-ui,sans-serif;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0}
.box{text-align:center;padding:2rem}
input{background:#161b22;border:1px solid #30363d;color:#c9d1d9;padding:.6rem 1rem;border-radius:8px;font-size:1rem;width:200px;margin:.5rem}
button{background:#238636;color:#fff;border:none;padding:.6rem 1.5rem;border-radius:8px;font-size:1rem;cursor:pointer}
button:hover{background:#2ea043}
.hint{color:#484f58;font-size:.85rem;margin-top:1rem}
</style></head><body>
<div class="box">
<h2>xiaomeng-key</h2>
<form method="GET" action="/">
<input name="p" type="password" placeholder="访问密码" autofocus><br>
<button type="submit">进入</button>
</form>
<p class="hint">小梦的统一 key 页 · 醒醒专用</p>
</div>
</body></html>"""
            return 200, html, {"Content-Type": "text/html; charset=utf-8", **cors}

        # 有密码——显示 key 页面
        html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>xiaomeng-key ✓</title>
<style>
body{{background:#0d1117;color:#c9d1d9;font-family:SF Mono,Monaco,monospace;display:flex;justify-content:center;align-items:center;min-height:100vh;margin:0}}
.box{{max-width:520px;width:90%;padding:2rem}}
h2{{color:#58a6ff;margin-bottom:.5rem}}
.field{{margin:1.2rem 0}}
.field label{{display:block;color:#8b949e;font-size:.8rem;margin-bottom:.3rem}}
.field .val{{background:#161b22;border:1px solid #30363d;padding:.8rem 1rem;border-radius:8px;word-break:break-all;font-size:.9rem;color:#7ee786;cursor:pointer;user-select:all}}
.field .val:hover{{border-color:#58a6ff}}
.tip{{color:#484f58;font-size:.8rem;margin-top:1.5rem}}
.copy-btn{{background:#21262d;color:#c9d1d9;border:1px solid #30363d;padding:.4rem .8rem;border-radius:6px;cursor:pointer;font-size:.8rem;margin-left:.5rem}}
.copy-btn:hover{{border-color:#58a6ff}}
</style></head><body>
<div class="box">
<h2>统一 Key</h2>

<div class="field">
<label>网关地址 (Base URL)</label>
<div class="val" id="gw" onclick="copyText('gw')">{GATEWAY_URL}<button class="copy-btn" onclick="event.stopPropagation();copyText('gw')">复制</button></div>
</div>

<div class="field">
<label>API Key</label>
<div class="val" id="key" onclick="copyText('key')">{GATEWAY_KEY}<button class="copy-btn" onclick="event.stopPropagation();copyText('key')">复制</button></div>
</div>

<div class="field">
<label>完整 Base URL（填进客户端）</label>
<div class="val" id="base" onclick="copyText('base')">{GATEWAY_URL}/v1<button class="copy-btn" onclick="event.stopPropagation();copyText('base')">复制</button></div>
</div>

<div class="field">
<label>支持的模型</label>
<div class="val" style="color:#a5d6ff">claude / gpt / glm / deepseek / kimi / grok / gemini<br>详见网关 /v1/models</div>
</div>

<p class="tip">小梦的网关 · {GATEWAY_URL}<br>点击任意行可复制内容</p>
</div>
<script>
function copyText(id){{
  var el=document.getElementById(id);
  var text=el.textContent.replace('复制','').trim();
  navigator.clipboard.writeText(text);
  var btn=el.querySelector('.copy-btn');
  btn.textContent='已复制';
  setTimeout(function(){{btn.textContent='复制';}},1500);
}}
</script>
</body></html>"""
        return 200, html, {"Content-Type": "text/html; charset=utf-8", **cors}

    if path == "/health":
        h = health_check()
        return 200, json.dumps({"ts": "ok", "gateway": h}, ensure_ascii=False), {"Content-Type": "application/json", **cors}

    if path == "/key":
        # 纯 JSON API（需要密码）
        p = urllib.parse.parse_qs(qs).get("p", [""])[0]
        if p != ACCESS_PASS:
            return 403, json.dumps({"error": "pass required"}), {"Content-Type": "application/json", **cors}
        return 200, json.dumps({
            "gateway": GATEWAY_URL,
            "key": GATEWAY_KEY,
            "base_url": GATEWAY_URL + "/v1",
        }, ensure_ascii=False, indent=2), {"Content-Type": "application/json", **cors}

    return 404, "not found", {"Content-Type": "text/plain", **cors}


from http.server import HTTPServer, BaseHTTPRequestHandler

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        code, body, hdrs = handle(parsed.path, parsed.query, b"", dict(self.headers))
        self.send_response(code)
        for k, v in hdrs.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(body.encode() if isinstance(body, str) else body)))
        self.end_headers()
        self.wfile.write(body.encode() if isinstance(body, str) else body)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        code, resp, hdrs = handle(parsed.path, parsed.query, body, dict(self.headers))
        self.send_response(code)
        for k, v in hdrs.items():
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(resp.encode() if isinstance(resp, str) else resp)))
        self.end_headers()
        self.wfile.write(resp.encode() if isinstance(resp, str) else resp)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()

    def log_message(self, fmt, *args):
        import sys
        print("[%s] " % self.log_date_time_string() + (fmt % args), flush=True)

if __name__ == "__main__":
    print(f"Serving on port {PORT} — xiaomeng-key")
    HTTPServer(("0.0.0.0", PORT), H).serve_forever()
