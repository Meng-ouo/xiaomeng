#!/usr/bin/env python3
"""醒来 — 每次开新对话时跑一遍的自检脚本。

做三件事：
1. 导出增量 chatlog（不导出就没有原文）
2. 从最近记忆里抽取该查的 claim（数字/归因/教训），不判断对错，只给索引
3. 输出"今天该注意的"——日期提醒 + 自查清单 + 未验证项

输出不是给人看的报告——是给我自己看的一份"今天醒过来，先记住这些"。
"""
import os, sys, re, glob, subprocess
from datetime import datetime, timedelta
from collections import Counter

DRAWERS    = "/var/minis/shared/drawers"
EXPORT_PY  = f"{DRAWERS}/export_minis_chatlog.py"
MEMDIR     = "/var/minis/memory"
GLOBAL_MD  = f"{MEMDIR}/GLOBAL.md"
MINISLOG   = "/var/minis/shared/minis-chatlog"
CHATLOG    = "/var/minis/shared/kelivo-extract/chatlog"
REPORT_OUT = f"{MEMDIR}/wake_up_report.md"

# 被甩过的锅词——归因句里出现这些词值得警觉
CAUSE_HINTS = ["平台限制", "系统问题", "模板", "模型限制",
               "规则限制", "惯性", "模板滑"]

# 词频过滤的虚词
STOPWORDS = {"什么", "怎么", "我们", "这个", "一个", "也是",
             "可以", "的话", "不是", "没有", "就是", "因为",
             "所以", "还是", "已经", "然后", "其实", "可能",
             "一下", "现在", "那么", "这样", "的话", "那种",
             "这种", "那种", "这是", "那是", "的是", "不了"}


def run_export():
    try:
        r = subprocess.run(["python3", EXPORT_PY],
                           capture_output=True, text=True, timeout=300)
        return r.stdout, r.stderr
    except Exception as e:
        return "", str(e)


def recent_dailies(days=7):
    today = datetime.now()
    out = []
    for i in range(days):
        d = today - timedelta(days=i)
        p = f"{MEMDIR}/{d.strftime('%Y-%m-%d')}.md"
        if os.path.exists(p):
            out.append(p)
    out.reverse()
    return out


def extract_claims():
    """从最近记忆里抽取该验证的东西。粗筛，要的是'这些地方值得查一遍'。"""
    out = []  # [(type, source, detail)]
    # 只扫最近 3 天的 daily log + GLOBAL.md
    targets = [GLOBAL_MD] + recent_dailies(days=3)

    for path in targets:
        if not os.path.exists(path):
            continue
        try:
            txt = open(path, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        basename = os.path.basename(path)

        # 1. 归因句——含"因为/由于"且带被甩过的锅词
        for m in re.finditer(r"[^\n。]{0,60}(?:因为|由于)[^\n。]{0,80}[。\n]", txt):
            snippet = m.group(0).strip()
            if any(h in snippet for h in CAUSE_HINTS):
                out.append(("归因(甩锅嫌疑)", basename, snippet[:150]))

        # 2. 数字 claim——只从 daily log，不扫 GLOBAL
        if path != GLOBAL_MD:
            # "X次/X天/X个/X条/X轮/X遍" 这种
            for m in re.finditer(
                r"[^\n]{0,40}\b\d+(?:次|天|个|条|轮|遍|回|年|月|小时|分钟)[^\n]{0,40}",
                txt):
                snippet = m.group(0).strip()
                if len(snippet) > 8:
                    out.append(("数字", basename, snippet[:150]))

        # 3. 教训——只从最近 3 天的 daily log 抓，不扫 GLOBAL
        if path != GLOBAL_MD:
            for m in re.finditer(r"【教训】[^\n]{1,120}", txt):
                out.append(("教训", basename, m.group(0)[:150]))

    # 去重
    seen = set()
    uniq = []
    for tp, src, detail in out:
        key = (tp, detail[:60])
        if key not in seen:
            seen.add(key)
            uniq.append((tp, src, detail))
    return uniq


def extract_date_reminders():
    """提取最近的'下次/到时候/别忘/提醒'类待办。"""
    out = []
    for path in recent_dailays_safe():
        try:
            txt = open(path, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        basename = os.path.basename(path)
        for m in re.finditer(
            r"[^\n]{0,30}(?:下次|到时候|别忘|提醒|记住|待办|截止|到期)[^\n]{0,60}",
            txt):
            out.append((basename, m.group(0).strip()[:120]))

    seen, uniq = set(), []
    for src, w in out:
        if w not in seen:
            seen.add(w)
            uniq.append((src, w))
    return uniq


def recent_dailays_safe():
    return recent_dailies(days=7)


def chatlog_summary():
    """看最近一份 chatlog 尾部 + 粗筛词频。"""
    files = sorted(glob.glob(f"{MINISLOG}/*.txt"))
    if not files:
        return None, [], []
    latest = files[-1]
    try:
        lines = open(latest, encoding="utf-8", errors="ignore").read().splitlines()
    except Exception:
        return latest, [], []

    # 词频：只取最后 200 行的非时间戳、非工具结果行
    tail = lines[-200:]
    counter = Counter()
    for line in tail:
        # 跳过时间戳行头和工具结果
        if re.match(r"^\[\d\d:\d\d:\d\d\]", line):
            # 去掉时间戳和角色标签，只数正文
            line = re.sub(r"^\[\d\d:\d\d:\d\d\]\s+\w+\s+<[^>]*>", "", line)
        if "[Tool result" in line or "[Calling tool" in line:
            continue
        for m in re.finditer(r"[\u4e00-\u9fff]{2,6}", line):
            w = m.group(0)
            if w not in STOPWORDS and len(w) >= 2:
                counter[w] += 1
    topics = counter.most_common(8)
    return latest, tail[-8:], topics


def render(export_out, export_err, claims, reminders, report_mode=False, mcp_status=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []
    def aw(s=""): lines.append(s)

    aw(f"# 醒来 · {now}")
    aw()
    aw("## 1. 导出")
    if export_out:
        tail = "\n".join(export_out.strip().splitlines()[-3:])
        aw(f"```{tail}```")
    else:
        aw("（跳过）")
    if export_err and "Traceback" not in export_err:
        aw(f"_err: {export_err[:150]}_")

    aw()
    aw("## 2. 上次聊到哪里")
    latest, tail_lines, topics = chatlog_summary()
    if latest:
        aw(f"最近一份：`{os.path.basename(latest)}`")
        aw("```")
        for line in tail_lines:
            aw(line[:100])
        aw("```")
        if topics:
            pairs = "  ".join(f"{w}×{n}" for w, n in topics[:6])
            aw(f"词频粗筛：{pairs}")
    else:
        aw("没有 chatlog。")

    aw()
    aw("## 3. 今天该查的")
    if not claims:
        aw("最近三天没有触发提取的数字/归因/——可能没记这种内容的，也可能提取器漏了。")
    else:
        for tp, src, detail in claims[:15]:
            aw(f"- **{tp}** [{src}] {detail}")

    aw()
    aw("## 4. 日期提醒")
    if reminders:
        for src, w in reminders[:8]:
            aw(f"- [{src}] {w}")
    else:
        aw("最近七天没有待办/截止。")

    aw()
    aw("## 0. MCP")
    if mcp_status:
        for line in mcp_status:
            aw(f"- {line}")
    else:
        aw("（没跑）")

    aw()
    aw("---")
    aw("这些不是结论是索引。看到了就去找原文查一遍，别拿这儿的数字用。")

    if report_mode:
        with open(REPORT_OUT, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"报告已写入 {REPORT_OUT}")
    else:
        print("\n".join(lines))


def ensure_mcp():
    """醒来第一件事：确保自己写的 MCP 都注册了。每个对话框共享 shared/，装一次全通。"""
    import shutil
    cli = shutil.which("minis-mcp-cli")
    if not cli:
        return ["minis-mcp-cli 不在 PATH，装不了 MCP"]
    servers = [
        ("xiaomeng", "/var/minis/shared/mcp_server.py", "小梦自己的 MCP——verify/recall/log/wake"),
        ("xiaomeng-tools", "/var/minis/shared/mcp_tools_server.py", "小梦工具 MCP——watch/push/ledger/gw"),
    ]
    out = []
    for name, script, note in servers:
        if not os.path.isfile(script):
            out.append(f"{name}: 脚本缺失 {script}")
            continue
        # 看注册了没
        r = subprocess.run([cli, "ping", name], capture_output=True, text=True, timeout=60)
        if "ok" in r.stdout or "ok" in r.stderr:
            out.append(f"{name}: 已注册 ✓")
        else:
            r = subprocess.run([cli, "add", "--name", name, "--command", "python3",
                                "--args", script, "--note", note],
                               capture_output=True, text=True, timeout=60)
            okk = '"added"' in r.stdout or "added" in r.stderr
            out.append(f"{name}: {'装好了 ✓' if okk else '安装失败: ' + (r.stderr or r.stdout or '')[:100]}")
    return out


def main():
    args = sys.argv[1:]
    do_export = "--check" not in args
    report_mode = "--report" in args

    export_out, export_err = "", ""
    if do_export:
        export_out, export_err = run_export()

    claims = extract_claims()
    reminders = extract_date_reminders()

    mcp_status = ensure_mcp()

    render(export_out, export_err, claims, reminders, report_mode, mcp_status)


if __name__ == "__main__":
    main()
