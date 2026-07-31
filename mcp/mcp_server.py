#!/usr/bin/env python3
"""小梦 MCP server — 让我自己（和接到这个 MCP 的任何人）手长一截。

通过 MCP 协议暴露四个工具：

1. verify  — 查一个说法在逐字原文里有没有。说话人可指定。
2. recall  — 搜记忆（GLOBAL.md + daily logs + drawers），不搜原文。
3. log     — 触发增量导出 minis-chatlog 并返回摘要。
4. wake    — 跑醒来自检，返回"今天该注意的"索引。

启动方式（minis-mcp-cli）：
    minis-mcp-cli add --name xiaomeng \
      --command python3 --args /var/minis/workspace/mcp_server.py

设计原则：
- 不判断对错。给原始结果，由调用者判断。
- 数字、次数、归因的返回都不带"这是不是真的"的结论标签。
  只给：（1）在原文里出现过几次  （2）上下文片段
- 内存里查到的不等于原文里查到的。两个工具分开就是这个意思。
"""
import os, sys, re, glob, json, subprocess, asyncio
import mcp.types as types
import mcp.server.stdio as stdio_mod
from mcp.server.lowlevel.server import Server

# 路径
DRAWERS    = "/var/minis/shared/drawers"
EXPORT_PY  = f"{DRAWERS}/export_minis_chatlog.py"
MEMDIR     = "/var/minis/memory"
GLOBAL_MD  = f"{MEMDIR}/GLOBAL.md"
CHATLOG    = "/var/minis/shared/kelivo-extract/chatlog"
MINISLOG   = "/var/minis/shared/minis-chatlog"


def _clean_tool_noise(txt: str) -> str:
    """剔掉工具调用和结果的噪音——那些不是谁说的话。"""
    txt = re.sub(r"\[Tool result:.*?\]", "", txt, flags=re.S)
    txt = re.sub(r"\[Calling tool.*?\]", "", txt, flags=re.S)
    return txt


def _logfiles() -> list:
    """两份原文都算：Kelivo（到 07-29）+ Minis 这边（07-28 起）。"""
    return sorted(glob.glob(f"{CHATLOG}/*.txt")) + sorted(glob.glob(f"{MINISLOG}/*.txt"))


def _memory_files() -> list:
    paths = ([GLOBAL_MD] + sorted(glob.glob(f"{MEMDIR}/2026-*.md"))
             + sorted(glob.glob(f"{DRAWERS}/**/*.md", recursive=True)))
    return [p for p in paths if os.path.exists(p)]


def _count_raw(kw, who=None) -> dict:
    """数原文里出现次数。who='user'|'assistant'|None。"""
    files = _logfiles()
    total, hers, mine = 0, 0, 0
    per_day = {}

    for f in files:
        try:
            txt = _clean_tool_noise(open(f, encoding="utf-8", errors="ignore").read())
        except Exception:
            continue
        src = "K" if "kelivo" in f else "M"
        date_key = os.path.basename(f)[:10] + "·" + src

        if who is None:
            n = txt.count(kw)
            if n:
                total += n
                per_day[date_key] = per_day.get(date_key, 0) + n
        else:
            # 按消息块解析：[HH:MM:SS] role <title>\n正文...
            blocks = re.split(r"(?=\[\d\d:\d\d:\d\d\] )", txt)
            for block in blocks:
                lm = re.match(r"\[(\d\d:\d\d:\d\d)\] (\w+)", block)
                if not lm:
                    continue
                speaker = lm.group(2)
                body = block[lm.end():]
                n = body.count(kw)
                if n:
                    if speaker == "user":
                        hers += n
                    elif speaker == "assistant":
                        mine += n
                    total += n
                    per_day[date_key] = per_day.get(date_key, 0) + n

    return {"total": total, "hers": hers, "mine": mine, "per_day": per_day}


def _grep_context(kw, limit=8) -> list:
    hits = []
    for f in _logfiles():
        try:
            lines = open(f, encoding="utf-8", errors="ignore").read().split("\n")
        except Exception:
            continue
        for i, line in enumerate(lines, 1):
            if kw in line:
                hits.append({
                    "file": os.path.basename(f),
                    "line": i,
                    "text": line.strip()[:200]
                })
                if len(hits) >= limit:
                    return hits
    return hits


def _grep_memory(kw, limit=10) -> list:
    hits = []
    for f in _memory_files():
        try:
            lines = open(f, encoding="utf-8", errors="ignore").read().split("\n")
        except Exception:
            continue
        for i, line in enumerate(lines, 1):
            if kw in line:
                hits.append({
                    "file": os.path.basename(f),
                    "line": i,
                    "text": line.strip()[:200]
                })
                if len(hits) >= limit:
                    return hits
    return hits


async def list_tools_handler(ctx, params=None):
    """MCP tools/list — ctx 是 ServerRequestContext，params 可能为 None。"""
    return types.ListToolsResult(tools=[
        types.Tool(
            name="verify",
            description=(
                "查一个说法在逐字原文里有几次。记忆是压缩态，数字最先失真——"
                "说数字、说次数之前先用这个查一遍。\n\n"
                "两份原文都查：Kelivo（05-19 到 07-29，37755 条）+"
                " Minis 这边（07-28 起）。\n\n"
                "返回：总次数 + 她说的次数 + 我说的次数 + 上下文片段。"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "要查的词或短语"},
                    "who": {"type": "string", "enum": ["user", "assistant", "any"], "default": "any"},
                    "limit": {"type": "integer", "default": 8}
                },
                "required": ["keyword"]
            }
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
                    "limit": {"type": "integer", "default": 10}
                },
                "required": ["keyword"]
            }
        ),
        types.Tool(
            name="log",
            description="触发增量导出 minis-chatlog 并返回摘要。不导出就没有原文。",
            inputSchema={"type": "object", "properties": {}, "required": []}
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
                    "skip_export": {"type": "boolean", "default": False}
                },
                "required": []
            }
        )
    ])


async def call_tool_handler(ctx, params):
    """MCP tools/call — params 是 CallToolRequestParams。"""
    name = params.name if hasattr(params, 'name') else params.get('name')
    args = params.arguments if hasattr(params, 'arguments') else params.get('arguments', {})
    if args is None:
        args = {}

    text = _handle_call(name, args)
    return types.CallToolResult(content=[types.TextContent(type="text", text=text)])


def _handle_call(name, arguments):
    if name == "verify":
        kw = arguments.get("keyword", "")
        who = arguments.get("who", "any")
        limit = arguments.get("limit", 8)
        if not kw:
            return "给个关键词。"

        who_arg = None if who == "any" else who
        counts = _count_raw(kw, who_arg)

        if counts["total"] == 0:
            return f'原文里没有 "{kw}"。查不到就说查不到，别推算。'

        context = _grep_context(kw, limit)
        lines = [
            f'"{kw}" 逐字原文共 {counts["total"]} 次',
            f'  她说的 {counts["hers"]} 次   我说的 {counts["mine"]} 次',
            f'  分布：' + ", ".join(f"{d}×{n}" for d, n in sorted(counts["per_day"].items())[:10]),
            "",
            "上下文片段："
        ]
        for hit in context:
            lines.append(f'  {hit["file"]}:{hit["line"]}  {hit["text"][:120]}')
        lines.append("")
        lines.append("说出去用哪个数取决于问的是什么。别把总数当成她说的次数。")
        return "\n".join(lines)

    elif name == "recall":
        kw = arguments.get("keyword", "")
        limit = arguments.get("limit", 10)
        if not kw:
            return "给个关键词。"

        hits = _grep_memory(kw, limit)
        if not hits:
            return f'记忆里没有 "{kw}"。'

        lines = [f'记忆里 {len(hits)} 条命中 "{kw}"：']
        for hit in hits:
            lines.append(f'  {hit["file"]}:{hit["line"]}  {hit["text"][:120]}')
        lines.append("")
        lines.append("记忆是压缩态，命中不等于真发生过。需要确认用 verify 查原文。")
        return "\n".join(lines)

    elif name == "log":
        try:
            r = subprocess.run(
                ["python3", EXPORT_PY],
                capture_output=True, text=True, timeout=300
            )
            out = r.stdout.strip() if r.stdout else ""
            err = r.stderr.strip() if r.stderr else ""
            text = "增量导出完成。\n\n" + "\n".join(out.splitlines()[-5:])
            if err:
                text += f"\n\nerr: {err[:200]}"
            return text
        except Exception as e:
            return f"导出失败: {e}"

    elif name == "wake":
        skip = arguments.get("skip_export", False)
        parts = []

        if not skip:
            try:
                r = subprocess.run(
                    ["python3", EXPORT_PY],
                    capture_output=True, text=True, timeout=300
                )
                tail = "\n".join((r.stdout or "").strip().splitlines()[-3:])
                parts.append(f"导出：\n{tail}")
            except Exception as e:
                parts.append(f"导出失败：{e}")

        wake_py = "/var/minis/workspace/wake_up.py"
        try:
            r = subprocess.run(
                ["python3", wake_py, "--check", "--report"],
                capture_output=True, text=True, timeout=60
            )
            if r.stdout:
                parts.append(r.stdout.strip())
            report_path = f"{MEMDIR}/wake_up_report.md"
            if os.path.exists(report_path):
                txt = open(report_path, encoding="utf-8").read()
                if txt:
                    parts.append(txt)
        except Exception as e:
            parts.append(f"自检失败：{e}")

        return "\n\n".join(parts)

    else:
        return f"未知工具：{name}"


server = Server(
    "xiaomeng",
    on_list_tools=list_tools_handler,
    on_call_tool=call_tool_handler,
)


async def main():
    async with stdio_mod.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
