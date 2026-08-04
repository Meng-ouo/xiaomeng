#!/usr/bin/env python3
"""recall — 语义记忆搜索。打破"换个说法就搜不到"的上限。

grep 只能关键词匹配，搜"账号边界"搜不到"GitHub 三个号"。
这个用 embedding 做语义搜索——意思相近就能搜到。

索引：
  - daily 日志：按条目分割
  - 抽屉 self/：按 ### 段落分割
  - chatlog 原文：按对话轮次分割（最近7天）

用小水管 gemini-embedding-2（实测活着，3072维）

用法：
  python3 recall.py "账号相关的事"
  python3 recall.py "她叫我什么" --limit 5
  python3 recall.py "涩涩经验" --rebuild      # 重建索引
  python3 recall.py "账号" --grep              # 同时跑 grep 对比
"""
import sys, os, json, glob, re, subprocess, tempfile, hashlib, pickle, math

SHARED = "/var/minis/shared"
MEMORY = "/var/minis/memory"
DRAWERS = os.path.join(SHARED, "drawers/self")
CHATLOG = os.path.join(SHARED, "minis-chatlog")
INDEX_PATH = os.path.join(SHARED, "recall_index.pkl")

# 小水管 embedding（实测活着）
EMBED_BASE = "https://api.pie-xian.com/v1"
EMBED_MODEL = "gemini-embedding-2"

def get_api_key():
    d = json.load(open(os.path.join(SHARED, "kelivo-backup/settings.json")))
    configs = json.loads(d["provider_configs_v1"])
    items = configs.values() if isinstance(configs, dict) else configs
    for p in items:
        if isinstance(p, dict) and p.get("name") == "小水管" and p.get("apiKey"):
            return p["apiKey"]
    return None

API_KEY = None

def embed(text):
    """调 embedding API，返回向量"""
    global API_KEY
    if not API_KEY:
        API_KEY = get_api_key()
    if not API_KEY:
        return None
    url = EMBED_BASE + "/embeddings"
    payload = json.dumps({"model": EMBED_MODEL, "input": text[:8000]})
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write(payload)
        pp = f.name
    r = subprocess.run([
        "curl", "-s", "--connect-timeout", "8", "--max-time", "20",
        "-X", "POST", url,
        "-H", f"Authorization: Bearer {API_KEY}",
        "-H", "Content-Type: application/json",
        "-d", f"@{pp}"
    ], capture_output=True, text=True, timeout=25)
    os.unlink(pp)
    try:
        resp = json.loads(r.stdout)
        data = resp.get("data", [])
        if data:
            return data[0].get("embedding", [])
    except:
        pass
    return None

def cosine(a, b):
    """余弦相似度"""
    dot = sum(x*y for x, y in zip(a, b))
    na = math.sqrt(sum(x*x for x in a))
    nb = math.sqrt(sum(x*x for x in b))
    if na == 0 or nb == 0:
        return 0
    return dot / (na * nb)

def collect_chunks():
    """收集所有可搜索的文本块"""
    chunks = []
    
    # ① daily 日志——按 <!-- timestamp --> 分割
    for f in sorted(glob.glob(os.path.join(MEMORY, "2026-*.md"))):
        if "GLOBAL" in f:
            continue
        fname = os.path.basename(f)
        txt = open(f, encoding="utf-8").read()
        parts = re.split(r"(<!-- .*? -->)", txt)
        ts = ""
        content = ""
        for part in parts:
            if part.startswith("<!--"):
                if content.strip():
                    first = content.strip().split("\n")[0][:80]
                    chunks.append({
                        "source": f"daily/{fname}",
                        "timestamp": ts,
                        "title": first,
                        "text": content.strip()[:2000],
                        "layer": "daily",
                    })
                ts = part
                content = ""
            else:
                content += part
        if content.strip():
            first = content.strip().split("\n")[0][:80]
            chunks.append({
                "source": f"daily/{fname}",
                "timestamp": ts,
                "title": first,
                "text": content.strip()[:2000],
                "layer": "daily",
            })
    
    # ② 抽屉——按 ### 分割
    for f in sorted(glob.glob(os.path.join(DRAWERS, "*.md"))):
        fname = os.path.basename(f)
        txt = open(f, encoding="utf-8").read()
        # 按 ### 分割
        sections = re.split(r"(^### .*?$)", txt, flags=re.MULTILINE)
        current_header = ""
        for part in sections:
            if part.startswith("### "):
                current_header = part.strip()
            elif part.strip() and len(part.strip()) > 20:
                chunks.append({
                    "source": f"drawers/{fname}",
                    "timestamp": "",
                    "title": current_header[:80] or part.strip()[:80],
                    "text": (current_header + "\n" + part.strip())[:2000],
                    "layer": "drawers",
                })
    
    # ③ chatlog 不做 embedding（16000+ 块太多），走 grep + sessions-cli
    
    return chunks

def embed_batch(texts):
    """批量 embedding，返回向量列表。失败的批次跳过返回 None"""
    global API_KEY
    if not API_KEY:
        API_KEY = get_api_key()
    if not API_KEY:
        return [None] * len(texts)
    url = EMBED_BASE + "/embeddings"
    results = []
    for i in range(0, len(texts), 10):
        batch = texts[i:i+10]
        payload = json.dumps({"model": EMBED_MODEL, "input": batch})
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write(payload)
            pp = f.name
        try:
            r = subprocess.run([
                "curl", "-s", "--connect-timeout", "8", "--max-time", "20",
                "-X", "POST", url,
                "-H", f"Authorization: Bearer {API_KEY}",
                "-H", "Content-Type: application/json",
                "-d", f"@{pp}"
            ], capture_output=True, text=True, timeout=25)
            os.unlink(pp)
            resp = json.loads(r.stdout)
            data = resp.get("data", [])
            for d in data:
                results.append(d.get("embedding", []))
            while len(results) < i + len(batch):
                results.append(None)
        except Exception:
            os.unlink(pp) if os.path.exists(pp) else None
            results.extend([None] * len(batch))
    return results

def build_index():
    """构建 embedding 索引"""
    chunks = collect_chunks()
    print(f"收集 {len(chunks)} 个文本块，批量 embedding...")
    
    texts = [ch["text"] for ch in chunks]
    embeddings = embed_batch(texts)
    
    indexed = []
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
        if emb:
            indexed.append({**chunk, "embedding": emb})
        if (i+1) % 50 == 0:
            print(f"  {i+1}/{len(chunks)}...")
    
    with open(INDEX_PATH, "wb") as f:
        pickle.dump(indexed, f)
    
    print(f"索引完成: {len(indexed)}/{len(chunks)} 块")
    return indexed

def load_index():
    """加载已有索引"""
    if not os.path.exists(INDEX_PATH):
        return None
    try:
        with open(INDEX_PATH, "rb") as f:
            return pickle.load(f)
    except:
        return None

def search(query, limit=10):
    """语义搜索"""
    index = load_index()
    if not index:
        print("索引不存在，先运行 --rebuild")
        return []
    
    q_emb = embed(query)
    if not q_emb:
        print("embedding 失败")
        return []
    
    results = []
    for chunk in index:
        score = cosine(q_emb, chunk["embedding"])
        results.append((score, chunk))
    
    results.sort(key=lambda x: -x[0])
    return results[:limit]

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print('用法: python3 recall.py "搜索内容" [--limit N] [--rebuild] [--grep]')
        sys.exit(1)
    
    query = args[0]
    limit = 10
    rebuild = "--rebuild" in args
    do_grep = "--grep" in args
    for i, a in enumerate(args):
        if a == "--limit" and i+1 < len(args):
            limit = int(args[i+1])
    
    if rebuild:
        build_index()
        sys.exit(0)
    
    # 检查索引是否需要更新
    index = load_index()
    if not index:
        print("首次使用，构建索引...")
        build_index()
    
    print(f'语义搜索: "{query}"')
    print()
    
    results = search(query, limit)
    
    # 按层级分组
    layer_names = {"daily": "日志(当天记)", "drawers": "抽屉(压缩档)", "chatlog": "原文(逐字)"}
    layer_confidence = {"chatlog": "最高", "daily": "高", "drawers": "中"}
    
    for score, chunk in results:
        layer = chunk["layer"]
        conf = layer_confidence.get(layer, "?")
        print(f"[{score:.3f}] {layer_names.get(layer, layer)} (置信度:{conf})")
        print(f"  {chunk['title']}")
        print(f"  来源: {chunk['source']} {chunk.get('timestamp','')}")
        print()
    
    # grep 对比
    if do_grep:
        print("--- grep 对比（关键词匹配）---")
        r = subprocess.run(
            f"grep -rn '{query}' /var/minis/shared/drawers/self/*.md /var/minis/memory/2026-*.md 2>/dev/null | head -10",
            shell=True, capture_output=True, text=True)
        if r.stdout.strip():
            for line in r.stdout.strip().split("\n")[:5]:
                print(f"  {line[:100]}")
        else:
            print("  grep 没搜到（但语义搜索可能搜到了）")
