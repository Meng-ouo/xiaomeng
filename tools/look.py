#!/usr/bin/env python3
"""look — 我看图的工具。打破"看不了图"的上限。

三层看：
1. apple-vision：原生 OCR/分类/人脸/条码
2. kelivo 活的识图 provider（实测 2026-08-05）：
   - ouo / Claude Opus 4.8（最准）
   - 小水管 / command-a-vision（天生识图）
   - 嘻嘻-1010 / llama-vision
3. 平台 minis-model-use 后备（Grok 4.5 / Sonnet 5）

用法：
  python3 look.py /path/to/image.png
  python3 look.py /path/to/image.png --ask "这张图里的人在干嘛"
  python3 look.py /path/to/image.png --ocr-only
  python3 look.py /path/to/image.png --understand-only
"""
import sys, os, subprocess, json, tempfile, base64

KELIVO_SETTINGS = "/var/minis/shared/kelivo-backup/settings.json"

# 实测活的识图 provider，按质量排序
VISION_PROVIDERS = [
    ("ouo", "tabbit/Claude-Opus-4.8"),
    ("小水管", "command-a-vision-07-2025"),
    ("嘻嘻-1010", "meta/llama-3.2-11b-vision-instruct"),
]

def load_provider(name):
    try:
        d = json.load(open(KELIVO_SETTINGS))
        configs = json.loads(d["provider_configs_v1"])
        items = configs.values() if isinstance(configs, dict) else configs
        for p in items:
            if isinstance(p, dict) and p.get("name") == name and p.get("apiKey"):
                base = p.get("baseUrl","")
                return {"base_url": base, "api_key": p["apiKey"],
                        "chat_path": p.get("chatPath","/chat/completions") or "/chat/completions"}
    except:
        pass
    return None

def apple_vision(img):
    r = subprocess.run(["apple-vision", "analyze", img], capture_output=True, text=True, timeout=30)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except:
        return None

def call_vision_api(provider_info, model, b64, mime, question):
    url = provider_info["base_url"].rstrip("/") + provider_info["chat_path"]
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": question},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
        ]}],
        "max_tokens": 500
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(payload, f)
        pp = f.name
    r = subprocess.run([
        "curl", "-s", "--connect-timeout", "10", "--max-time", "30",
        "-X", "POST", url,
        "-H", f"Authorization: Bearer {provider_info['api_key']}",
        "-H", "Content-Type: application/json",
        "-d", f"@{pp}"
    ], capture_output=True, text=True, timeout=35)
    os.unlink(pp)
    try:
        resp = json.loads(r.stdout)
        choices = resp.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
            if content:
                return content
        err = resp.get("error", {})
        if err:
            return None, err.get("message", "")[:80]
    except:
        pass
    return None, "no response"

def model_use_fallback(b64, mime, question):
    """平台 minis-model-use 后备"""
    payload = {"messages": [{"role": "user", "content": [
        {"type": "text", "text": question},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
    ]}], "max_tokens": 500}
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(payload, f)
        pp = f.name
    for model in ["grok-4.5", "claude-sonnet-5"]:
        r = subprocess.run(["minis-model-use", "run", "--model", model, "--input", pp],
                          capture_output=True, text=True, timeout=60)
        try:
            d = json.loads(r.stdout)
            if d.get("ok") and d.get("data", {}).get("output_text"):
                os.unlink(pp)
                return d["data"]["output_text"], model
        except:
            pass
    os.unlink(pp)
    return None, None

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or not os.path.exists(args[0]):
        print("用法: python3 look.py <图片路径> [--ask '问题'] [--ocr-only] [--understand-only]")
        sys.exit(1)

    img = args[0]
    ask = None
    ocr_only = "--ocr-only" in args
    understand_only = "--understand-only" in args
    for i, a in enumerate(args):
        if a == "--ask" and i+1 < len(args):
            ask = args[i+1]

    print(f"看图: {os.path.basename(img)}")
    print()

    # ① apple-vision
    if not understand_only:
        print("--- apple-vision ---")
        d = apple_vision(img)
        if d:
            data = d.get("data", d)
            ocr = data.get("ocr", {})
            ocr_text = ocr.get("text", "") if isinstance(ocr, dict) else str(ocr)
            if ocr_text:
                print(f"文字: {ocr_text[:300]}")
            for c in (data.get("classification", []) or [])[:3]:
                if isinstance(c, dict):
                    print(f"分类: {c.get('label','')} ({c.get('confidence',0):.0%})")
            faces = data.get("faces", {})
            fc = faces.get("count", 0) if isinstance(faces, dict) else 0
            if fc:
                print(f"人脸: {fc} 个")
            for b in (data.get("barcodes", []) or [])[:3]:
                if isinstance(b, dict):
                    print(f"条码: {b.get('payload','')[:50]}")
            img_info = data.get("image", {})
            if isinstance(img_info, dict) and img_info.get("width"):
                print(f"尺寸: {img_info['width']}x{img_info['height']}")
        else:
            print("vision 不可用")
        print()

    # ② kelivo + 平台后备
    if not ocr_only:
        print("--- 模型理解 ---")
        q = ask or "描述这张图片的内容，用中文"
        ext = os.path.splitext(img)[1].lower().lstrip(".")
        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/png")
        with open(img, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        for name, model in VISION_PROVIDERS:
            pi = load_provider(name)
            if not pi:
                continue
            result = call_vision_api(pi, model, b64, mime, q)
            if isinstance(result, tuple):
                print(f"  {name}/{model} 失败: {result[1]}")
                continue
            elif result:
                print(f"[{name}/{model}]")
                print(result)
                break
        else:
            # 全失败，试平台后备
            print("kelivo 全挂，试平台后备...")
            result, model = model_use_fallback(b64, mime, q)
            if result:
                print(f"[平台/{model}]")
                print(result)
            else:
                print("全挂了")
