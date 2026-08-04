#!/usr/bin/env python3
"""sync — 一键同步 shared 改动到 GitHub 仓库并推送。

用法：
  python3 sync.py              # 同步所有仓库
  python3 sync.py xm           # 只同步 xiaomeng
  python3 sync.py zh           # 只同步 zhangyiheng
  python3 sync.py --dry        # 只看哪些文件变了，不推

同步规则：
  - xiaomeng: mcp_server.py → mcp/, wake_snapshot.py → wake_up/wake_up.py
  - zhangyiheng: 整个 repos/zhangyiheng 目录 git add -A
  - 自动用 XIAOMENG_TOKEN 推送
"""
import os, sys, subprocess

SHARED = "/var/minis/shared"
REPOS = os.path.join(SHARED, "repos")

# 同步映射：源文件 → 目标仓库:目标路径
# 只推活的，归档的(check_on.py旧v2/analogize.py/openclaw*)不推
XIAOMENG_MAP = {
    "mcp_server.py": "mcp/mcp_server.py",
    "mcp_tools_server.py": "mcp/mcp_tools_server.py",
    "mind_engine.py": "mcp/mind_engine.py",
    "wake_snapshot.py": "wake_up/wake_up.py",
    "sense.py": "tools/sense.py",
    "clone.py": "tools/clone.py",
    "recall.py": "tools/recall.py",
    "search.py": "tools/search.py",
    "verify_tool.py": "tools/verify_tool.py",
    "lesson_index.py": "tools/lesson_index.py",
    "look.py": "tools/look.py",
    "meng.py": "tools/meng.py",
    "note.py": "tools/note.py",
    "sync.py": "tools/sync.py",
    "quick.py": "tools/quick.py",
    "skill_triage.py": "tools/skill_triage.py",
    "heartbeat.py": "tools/heartbeat.py",
    "checkon/checkon.py": "tools/checkon.py",
    "dispatch.py": "tools/dispatch.py",
    "preflight.py": "tools/preflight.py",
    "postflight.py": "tools/postflight.py",
}

def run(cmd, cwd=None):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd)
    return r.stdout.strip() + r.stderr.strip()

def git_user():
    """用 token 查 GitHub 用户名"""
    tok = os.environ.get("XIAOMENG_TOKEN", "")
    if not tok:
        return None
    r = subprocess.run(
        f'curl -s -H "Authorization: token {tok}" https://api.github.com/user',
        shell=True, capture_output=True, text=True)
    import json
    try:
        d = json.loads(r.stdout)
        return d.get("login")
    except:
        return None

def sync_xiaomeng(dry=False):
    repo = os.path.join(REPOS, "xiaomeng")
    changed = []
    for src, dst in XIAOMENG_MAP.items():
        src_path = os.path.join(SHARED, src)
        dst_path = os.path.join(repo, dst)
        if not os.path.exists(src_path):
            continue
        # 比较文件内容
        src_md5 = subprocess.run(f"md5sum '{src_path}'", shell=True, capture_output=True, text=True).stdout.split()[0]
        dst_md5 = subprocess.run(f"md5sum '{dst_path}' 2>/dev/null", shell=True, capture_output=True, text=True).stdout.split()[0] if os.path.exists(dst_path) else ""
        if src_md5 != dst_md5:
            changed.append(f"{src} → {dst}")
            if not dry:
                subprocess.run(f"cp '{src_path}' '{dst_path}'", shell=True)
    if not changed:
        print("  xiaomeng: 无改动")
        return
    print(f"  xiaomeng 变更: {', '.join(changed)}")
    if dry:
        return
    msg = f"sync: {', '.join(changed)}"
    print(run(f'git add -A && git commit -m "{msg}"', cwd=repo))
    user = git_user()
    if user:
        tok = os.environ.get("XIAOMENG_TOKEN", "")
        run(f'git remote set-url origin "https://{user}:{tok}@github.com/{user}/xiaomeng.git"', cwd=repo)
    print(run("git push origin main", cwd=repo))

def sync_zhangyiheng(dry=False):
    repo = os.path.join(REPOS, "zhangyiheng")
    status = subprocess.run("git status --short", shell=True, capture_output=True, text=True, cwd=repo).stdout.strip()
    if not status:
        print("  zhangyiheng: 无改动")
        return
    files = [l.strip() for l in status.split("\n") if l.strip()]
    print(f"  zhangyiheng 变更: {len(files)} 个文件")
    for f in files:
        print(f"    {f}")
    if dry:
        return
    print(run("git add -A", cwd=repo))
    msg = f"update: {len(files)} files"
    print(run(f'git commit -m "{msg}"', cwd=repo))
    user = git_user()
    if user:
        tok = os.environ.get("XIAOMENG_TOKEN", "")
        run(f'git remote set-url origin "https://{user}:{tok}@github.com/{user}/zhangyiheng.git"', cwd=repo)
    print(run("git push origin main", cwd=repo))

if __name__ == "__main__":
    args = sys.argv[1:]
    dry = "--dry" in args
    target = [a for a in args if not a.startswith("--")]
    
    print(f"{'[DRY] ' if dry else ''}同步 GitHub")
    if not target or "xm" in target:
        sync_xiaomeng(dry)
    if not target or "zh" in target:
        sync_zhangyiheng(dry)
    print("done")
