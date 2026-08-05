#!/usr/bin/env python3
"""quick — 轻量自检，3秒内出结果。

不查岗、不查她、不查 GitHub。只看关键服务活不活。
wake 太重（14s），这个是快速版。

用法：
  python3 quick.py
"""
import os, json, subprocess, time

SHARED = "/var/minis/shared"

def check_file(path, name):
    ok = os.path.exists(path)
    age = ""
    if ok:
        mtime = os.path.getmtime(path)
        mins = int((time.time() - mtime) / 60)
        age = f"{mins}min前" if mins < 60 else f"{mins//60}h前"
    return f"{'OK' if ok else 'DEAD'} {name} {age}"

def check_snapshot(timeout=15):
    """真的 curl 测 8797 端口——之前只看日志文件时间，进程死了日志还在，报假 OK"""
    try:
        r = subprocess.run(
            f'curl -s -m {timeout} -o /dev/null -w "%{{http_code}}" '
            f'http://127.0.0.1:8797/api/wake-snapshot',
            shell=True, capture_output=True, text=True, timeout=timeout+5)
        code = r.stdout.strip()
        if code == "200":
            return "OK snapshot 8797"
        else:
            return f"DEAD snapshot {code}（crontab 保活会拉起，5分钟后复查）"
    except:
        return "DEAD snapshot timeout"

def check_gateway(timeout=3):
    """curl 测网关出字，不猜端口——直接打已知活着的地址"""
    key_path = os.path.join(SHARED, "gw/gateway_key.txt")
    try:
        key = open(key_path).read().strip()
    except:
        return "DEAD gateway (no key)"
    try:
        r = subprocess.run(
            f'curl -s -m {timeout} -o /dev/null -w "%{{http_code}}" '
            f'http://198.11.180.51/v1/models -H "Authorization: Bearer {key}"',
            shell=True, capture_output=True, text=True, timeout=timeout+2)
        code = r.stdout.strip()
        if code == "200":
            return "OK gateway 200"
        else:
            return f"WARN gateway {code}"
    except:
        return "DEAD gateway timeout"

def check_cron():
    r = subprocess.run("crontab -l 2>/dev/null | grep -v '^#' | grep -v '^$'",
                      shell=True, capture_output=True, text=True)
    lines = [l.strip() for l in r.stdout.strip().split("\n") if l.strip()]
    has_checkon = any("checkon" in l for l in lines)
    return f"{'OK' if lines else 'MISS'} cron entries={len(lines)} checkon={'y' if has_checkon else 'n'}"

def check_mcp():
    """不调 minis-mcp-cli list（超时）。直接看 servers.json 里 enabled 的有几个"""
    try:
        with open("/var/minis/mcp-servers/servers.json") as f:
            data = json.load(f)
        servers = data.get("mcpServers", {})
        enabled = [k for k, v in servers.items() if v.get("enabled")]
        has_xm = "xiaomeng" in enabled
        has_tools = "xiaomeng-tools" in enabled
        return f"{'OK' if has_xm else 'DEAD'} mcp enabled={len(enabled)} xm={'y' if has_xm else 'n'} tools={'y' if has_tools else 'n'}"
    except Exception as e:
        return f"DEAD mcp ({e})"

def check_env():
    envs = ["XIAOMENG_TOKEN", "GITHUBKEKE_TOKEN"]
    results = []
    for e in envs:
        val = os.environ.get(e, "")
        results.append(f"{e}={'set' if val else 'MISS'}")
    return " ".join(results)

def check_kiss(timeout=8):
    """kiss.eoty.cn 可达性——带 key 测 API"""
    key_path = os.path.join(SHARED, "gw/gateway_key.txt")
    try:
        key = open(key_path).read().strip()
        r = subprocess.run(
            f'curl -s -m {timeout} --resolve kiss.eoty.cn:80:198.11.180.51 '
            f'http://kiss.eoty.cn/v1/models -H "Authorization: Bearer {key}" '
            f'-o /dev/null -w "%{{http_code}}"',
            shell=True, capture_output=True, text=True, timeout=timeout+3)
        code = r.stdout.strip()
        # 200=直通 301/308=HTTPS重定向（正常）
        return f"{'OK' if code in ('200','301','307','308') else 'DEAD'} kiss {code}"
    except:
        return "DEAD kiss timeout"

if __name__ == "__main__":
    t0 = time.time()
    print("快速自检")

    checks = [
        check_file(os.path.join(SHARED, "heartbeat_state.json"), "heartbeat"),
        check_file(os.path.join(SHARED, "checkon/state.json"), "checkon"),
        check_snapshot(),
        check_gateway(),
        check_kiss(),
        check_cron(),
        check_mcp(),
    ]

    for c in checks:
        print(f"  {c}")

    print(f"  {check_env()}")
    elapsed = time.time() - t0
    print(f"\n{elapsed:.1f}s")
