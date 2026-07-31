#!/usr/bin/env python3
"""小梦 MCP server — 让我自己（和接到这个 MCP 的任何人）手长一截。

通过 MCP 协议暴露四个工具：

1. verify  — 查一个说法在逐字原文里有没有。说话人可指定。
2. recall  — 搜记忆（GLOBAL.md + daily logs + drawers），不搜原文。
3. log     — 触发增量导出 minis-chatlog 并返回摘要。
4. wake    — 跑醒来自检，返回"今天该注意的"索引。

启动方式（minis-mcp-cli）：
    minis-mcp-cli add --name xiaomeng \
      --command python3 --args /var/minis/shared/mcp_server.py

设计原则：
- 不判断对错。给原始结果，由调用者判断。
- 数字、次数、归因的返回都不带"这是不是真的"的结论标签。
  只给：（1）在原文里出现过几次  （2）上下文片段
- 内存里查到的不等于原文里查到的。两个工具分开就是这个意思。
"""
import asyncio
import glob
import json
import os
import re
import subprocess
from collections import Counter

import mcp.types as types
import mcp.server.stdio as stdio_mod
from mcp.server.lowlevel.server import Server

# ── 路径 ──────────────────────────────────────────────
MEMORY_DIR       = "/var/minis/memory"
GLOBAL_MD        = os.path.join(MEMORY_DIR, "GLOBAL.md")
DRAWERS_DIR      = "/var/minis/shared/drawers"
CHATLOG_DIR      = "/var/minis/shared/kelivo-extract/chatlog"
MINIS_CHATLOG_DIR = "/var/minis/shared/minis-chatlog"
EXPORT_SCRIPT    = "/var/minis/shared/drawers/export_minis_chatlog.py"

STOPWORDS = {
    "今天", "昨天", "这个", "那个", "什么", "怎么", "可以", ","
    "一个", "不是", "没有", "已经", "觉得", "知道", "的话", "我们",
    "现在", "就是", "因为", "所以", "但是", "可能", "还是", "或者",
    "一下", "这种", "那种", "的话", "不会", "不能", "不要", "的话",
    "的话", "什么", "怎么", "可以", "一下",
}


def read_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


# ── verify：查原文 ─────────────────────────────────────
def _clean_tool_blocks(txt):
    """剔掉工具调用块，跟 claim.py 同一口径。"""
    txt = re.sub(r"\[Tool result:.*?\]", "", txt, flags=re.S)
    txt = re.sub(r"\[Calling tool.*?\]", "", txt, flags=re.S)
    return txt

# 消息块正则：group(1)=说话人，group(2)=标题行后的正文（标题行被 .*?$ 吃掉）
_BLOCK_RE = re.compile(
    r"^\[\d\d:\d\d:\d\d\] (\w+).*?$([\s\S]*?)(?=^\[\d\d:\d\d:\d\d\] |\Z)",
    re.M,
)


def _count_raw(directory, keyword, who="any", limit=8):
    """数逐字原文里的出现次数 + 说话人分类 + 上下文片段。

    who: any=都数; user=只数她说的; assistant=只数我说的。
    与 claim.py 同口径：剔工具调用块，标题行不计数。
    """
    total = hers = mine = 0
    per_day = {}
    contexts = []

    if not os.path.isdir(directory):
        return total, hers, mine, per_day, contexts

    for fname in sorted(os.listdir(directory)):
        if not fname.endswith(".txt"):
            continue
        fpath = os.path.join(directory, fname)
        txt = read_file(fpath)
        if not txt:
            continue
        txt = _clean_tool_blocks(txt)
        date_key = fname.replace(".txt", "")
        day_count = 0

        for m in _BLOCK_RE.finditer(txt):
            speaker = m.group(1)
            body = m.group(2)
            n = body.count(keyword)
            if not n:
                continue
            if speaker == "user":
                hers += n
            elif speaker == "assistant":
                mine += n
            else:
                continue
            if who == "user" and speaker != "user":
                continue
            if who == "assistant" and speaker != "assistant":
                continue
            total += n
            day_count += n

            # 收集上下文片段
            if len(contexts) < limit:
                snippet = " ".join(l.strip() for l in body.strip().split("\n")[:3])[:200]
                contexts.append({
                    "file": fname,
                    "speaker": speaker,
                    "snippet": snippet,
                })

        if day_count:
            per_day[date_key] = day_count

    return total, hers, mine, per_day, contexts


def do_verify(keyword, who="any", limit=8):
    """查两份原文，合并统计。"""
    # Kelivo chatlog + Minis chatlog
    t1, h1, m1, pd1, ctx1 = _count_raw(CHATLOG_DIR, keyword, who, limit)
    t2, h2, m2, pd2, ctx2 = _count_raw(MINIS_CHATLOG_DIR, keyword, who, limit)

    total = t1 + t2
    hers = h1 + h2
    mine = m1 + m2
    per_day = {}
    for d, c in pd1.items():
        per_day[d] = per_day.get(d, 0) + c
    for d, c in pd2.items():
        per_day[d] = per_day.get(d, 0) + c

    contexts = (ctx1 + ctx2)[:limit]

    # 按 who 过滤上下文
    if who and who != "any":
        contexts = [c for c in contexts if c["speaker"] == who]

    lines = [f'"{keyword}" 逐字原文共 {total} 次']
    lines.append(f"  她说的 {hers} 次   我说的 {mine} 次")

    if per_day:
        top_days = sorted(per_day.items(), key=lambda x: -x[1])[:10]
        dist = ", ".join(f"{d}×{c}" for d, c in top_days)
        lines.append(f"  分布：{dist}")

    if contexts:
        lines.append("\n上下文片段：")
        for c in contexts:
            lines.append(f"  {c['file']} [{c['speaker']}]  {c['snippet']}")

    lines.append("\n说出去用哪个数取决于问的是什么。别把总数当成她说的次数。")
    return "\n".join(lines)


# ── recall：搜记忆 ─────────────────────────────────────
def do_recall(keyword, limit=10):
    """搜 GLOBAL.md + daily logs + drawers 的 .md 文件。"""
    hits = []

    # GLOBAL.md
    txt = read_file(GLOBAL_MD)
    for i, line in enumerate(txt.split("\n"), 1):
        if keyword.lower() in line.lower():
            hits.append(("GLOBAL.md", i, line.strip()[:200]))

    # Daily logs
    for f in sorted(glob.glob(os.path.join(MEMORY_DIR, "*.md"))):
        if os.path.abspath(f) == os.path.abspath(GLOBAL_MD):
            continue
        txt = read_file(f)
        for i, line in enumerate(txt.split("\n"), 1):
            if keyword.lower() in line.lower():
                hits.append((os.path.basename(f), i, line.strip()[:200]))

    # Drawers（递归，含子目录）
    for f in sorted(glob.glob(os.path.join(DRAWERS_DIR, "**", "*.md"), recursive=True)):
        txt = read_file(f)
        for i, line in enumerate(txt.split("\n"), 1):
            if keyword.lower() in line.lower():
                hits.append((f"drawers/{os.path.relpath(f, DRAWERS_DIR)}", i, line.strip()[:200]))

    hits = hits[:limit]

    if not hits:
        return f'记忆里没有找到 "{keyword}"。'

    lines = [f'记忆里 {len(hits)} 条命中 "{keyword}"：']
    for fname, lineno, text in hits:
        lines.append(f"  {fname}:{lineno}  {text}")

    lines.append("\n记忆是压缩态，命中不等于真发生过。需要确认用 verify 查原文。")
    return "\n".join(lines)


# ── log：增量导出 ──────────────────────────────────────
def do_log():
    if not os.path.exists(EXPORT_SCRIPT):
        return "导出脚本不存在"

    try:
        r = subprocess.run(
            ["python3", EXPORT_SCRIPT],
            capture_output=True, text=True, timeout=180
        )
        output = r.stdout.strip()
        # 提取最后几行摘要
        tail = "\n".join(output.split("\n")[-5:]) if output else "无输出"
        return f"导出完成。\n{tail}"
    except Exception as e:
        return f"导出失败：{e}"


# ── wake：醒来自检 ─────────────────────────────────────
def ensure_mcp():
    """确保自己写的 MCP 都注册了。直接读写 servers.json（全局共享），不调 CLI 避免死锁。"""
    servers = [
        ("xiaomeng", "/var/minis/shared/mcp_server.py", "小梦自己的 MCP——verify/recall/log/wake"),
        ("xiaomeng-tools", "/var/minis/shared/mcp_tools_server.py", "小梦工具 MCP——watch/push/ledger/gw"),
    ]
    cfg = "/var/minis/mcp-servers/servers.json"
    out = []
    try:
        with open(cfg, encoding="utf-8") as f:
            data = json.load(f)
        reg = data.setdefault("mcpServers", {})
    except Exception as e:
        return [f"读 servers.json 失败: {e}"]
    for name, script, note in servers:
        if not os.path.isfile(script):
            out.append(f"{name}: 脚本缺失 {script}")
            continue
        if name in reg:
            out.append(f"{name}: ✓ 已注册")
            continue
        reg[name] = {
            "createdAt": time.time(),
            "updatedAt": time.time(),
            "enabled": True,
            "note": note,
            "command": "python3",
            "args": [script],
        }
        out.append(f"{name}: 补注册 ✓")
    try:
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
    except Exception as e:
        out.append(f"写 servers.json 失败: {e}")
    return out


def do_wake(skip_export=False):
    """跑一遍醒来自检，返回报告。"""
    lines = []

    # 0. MCP 自检（最先做）
    lines.append("## 0. MCP")
    try:
        for m in ensure_mcp():
            lines.append(f"- {m}")
    except Exception as e:
        lines.append(f"- 自检异常 {e}")

    # 1. 导出
    if skip_export:
        lines.append("## 1. 导出\n（跳过）")
    else:
        lines.append("## 1. 导出")
        lines.append(do_log())

    # 2. 最近对话
    lines.append("\n## 2. 上次聊到哪里")
    chatlog_files = sorted(glob.glob(os.path.join(MINIS_CHATLOG_DIR, "*.txt")))
    if chatlog_files:
        latest = chatlog_files[-1]
        txt = read_file(latest)
        all_lines = txt.split("\n")
        tail = all_lines[-15:]
        lines.append(f"最近一份：`{os.path.basename(latest)}`")
        lines.append("```")
        for l in tail:
            lines.append(l)
        lines.append("```")

        # 词频粗筛
        counter = Counter()
        for line in all_lines[-200:]:
            # 去掉时间戳行头
            line = re.sub(r"^\[\d\d:\d\d:\d\d\]\s+\w+\s+<[^>]*>", "", line)
            if "[Tool result" in line or "[Calling tool" in line:
                continue
            for m in re.finditer(r"[\u4e00-\u9fff]{2,6}", line):
                w = m.group(0)
                if w not in STOPWORDS:
                    counter[w] += 1
        topics = counter.most_common(8)
        if topics:
            words = ", ".join(f"{w}×{c}" for w, c in topics)
            lines.append(f"词频粗筛：{words}")

    # 3. 今天该查的
    lines.append("\n## 3. 今天该查的")
    log_files = sorted(glob.glob(os.path.join(MEMORY_DIR, "2026-07-*.md")) +
                       glob.glob(os.path.join(MEMORY_DIR, "2026-08-*.md")))
    alerts = []
    for lf in log_files[-3:]:  # 最近 3 天
        txt = read_file(lf)
        basename = os.path.basename(lf)
        # 数字相关
        for m in re.finditer(r"(\d+\.?\d*)\s*(条|次|个|分|轮|天|小时|分钟)", txt):
            ctx = txt[max(0, m.start()-30):m.end()+30].replace("\n", " ")[:120]
            alerts.append(("数字", basename, ctx))
        # 归因
        for m in re.finditer(r"因为[^\n。]{1,80}", txt):
            ctx = txt[max(0, m.start()-20):m.end()+20].replace("\n", " ")[:120]
            alerts.append(("归因", basename, ctx))
        # 教训——只从最近 3 天，不扫 GLOBAL
        if os.path.abspath(lf) != os.path.abspath(GLOBAL_MD):
            for m in re.finditer(r"【教训】[^\n]{1,120}", txt):
                alerts.append(("教训", basename, m.group(0)[:150]))

    if alerts:
        seen = set()
        for kind, src, ctx in alerts:
            key = (kind, ctx[:50])
            if key in seen:
                continue
            seen.add(key)
            lines.append(f"- **{kind}** [{src}] {ctx}")
    else:
        lines.append("没有找到需要查的条目。")

    # 4. 日期提醒
    lines.append("\n## 4. 日期提醒")
    reminders = []
    for lf in log_files[-3:]:
        txt = read_file(lf)
        basename = os.path.basename(lf)
        for m in re.finditer(r"(下次|到时候|别忘|到时候|该[她我]|欠)[^\n]{1,80}", txt):
            reminders.append((basename, m.group(0)[:120]))
    if reminders:
        seen = set()
        for src, text in reminders:
            if text[:50] in seen:
                continue
            seen.add(text[:50])
            lines.append(f"- [{src}] {text}")
    else:
        lines.append("没有待办。")

    lines.append("\n---\n这些不是结论是索引。看到了就去找原文查一遍，别拿这儿的数字用。")
    return "\n".join(lines)


# ── MCP 工具定义 ──────────────────────────────────────
TOOLS = [
    types.Tool(
        name="verify",
        description=(
            "查一个说法在逐字原文里有几次。记忆是压缩态，数字最先失真——"
            "说数字、说次数之前先用这个查一遍。\n\n"
            "两份原文都查：Kelivo（05-19 到 07-29，37755 条）+ Minis 这边（07-28 起）。\n\n"
            "返回：总次数 + 她说的次数 + 我说的次数 + 上下文片段。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "要查的词或短语"},
                "who": {"type": "string", "enum": ["user", "assistant", "any"], "default": "any"},
                "limit": {"type": "integer", "default": 8},
            },
            "required": ["keyword"],
        },
    ),
    types.Tool(
        name="recall",
        description=(
            "搜记忆（不是原文）。查我的压缩态记忆里有没有某个主题/词。"
            "搜 GLOBAL.md + 每日日志 + 抽屉里的所有 md。\n\n"
            "注意：记忆是压缩态，命中不等于真发生过，需要交叉验证时用 verify。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜的词或短语"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["keyword"],
        },
    ),
    types.Tool(
        name="log",
        description="触发增量导出 minis-chatlog 并返回摘要。不导出就没有原文。",
        inputSchema={"type": "object", "properties": {}, "required": []},
    ),
    types.Tool(
        name="wake",
        description=(
            "跑一遍醒来自检：导出 + 抽取最近记忆里该查的 claim + 日期提醒。"
            "返回的是索引不是结论——看到了自己去原文查。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "skip_export": {"type": "boolean", "default": False},
            },
            "required": [],
        },
    ),
]


async def list_tools_handler(ctx, params=None):
    return types.ListToolsResult(tools=TOOLS)


async def call_tool_handler(ctx, params):
    name = params.name
    args = params.arguments or {}

    try:
        if name == "verify":
            keyword = args.get("keyword", "")
            who = args.get("who", "any")
            limit = args.get("limit", 8)
            result = do_verify(keyword, who, limit)
        elif name == "recall":
            keyword = args.get("keyword", "")
            limit = args.get("limit", 10)
            result = do_recall(keyword, limit)
        elif name == "log":
            result = do_log()
        elif name == "wake":
            skip = args.get("skip_export", False)
            result = do_wake(skip)
        else:
            result = f"未知工具：{name}"

        return types.CallToolResult(
            content=[types.TextContent(type="text", text=result)]
        )
    except Exception as e:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"错误：{e}")]
        )


# ── 启动 ──────────────────────────────────────────────
server = Server(
    "xiaomeng",
    on_list_tools=list_tools_handler,
    on_call_tool=call_tool_handler,
)


async def main():
    async with stdio_mod.stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
