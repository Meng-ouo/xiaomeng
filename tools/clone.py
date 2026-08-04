#!/usr/bin/env python3
"""clone — 分身脚本。同时丢多个模型分头干同一个任务，收结果。

用法：
  python3 clone.py --prompt "总结这段话" --models grok-4.5,deepseek-v4-flash
  python3 clone.py --prompt "这段代码有什么问题" --models "Grok 4.5","Claude Sonnet 5"
  python3 clone.py --input task.json --models grok-4.5,claude-sonnet-5 --output /tmp/results/

原理：每个模型一个子进程，并行跑 minis-model-use run，先回来的先用。
适合：需要多角度回答、交叉验证、或者哪个快用哪个的场景。
"""
import subprocess, json, sys, os, time, argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

def run_one(model, prompt, input_file, system, max_tokens, temperature):
    """跑一个模型，返回结果字典"""
    cmd = ["minis-model-use", "run", "--model", model]
    if input_file:
        cmd += ["--input", input_file]
    else:
        cmd += ["--prompt", prompt]
    if system:
        cmd += ["--system", system]
    if max_tokens:
        cmd += ["--max-tokens", str(max_tokens)]
    if temperature is not None:
        cmd += ["--temperature", str(temperature)]
    cmd += ["--output", "/dev/stdout"]
    
    t0 = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        elapsed = time.time() - t0
        # 提取 output_text
        content = r.stdout.strip()
        try:
            d = json.loads(content)
            content = d.get("data", {}).get("output_text", content)
        except (json.JSONDecodeError, AttributeError):
            pass
        return {
            "model": model,
            "content": content,
            "error": r.stderr.strip() if r.stderr else None,
            "elapsed": round(elapsed, 1),
            "ok": r.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"model": model, "content": "", "error": "timeout (120s)", "elapsed": 120, "ok": False}
    except Exception as e:
        return {"model": model, "content": "", "error": str(e), "elapsed": 0, "ok": False}

def main():
    p = argparse.ArgumentParser(description="分身：多模型并行干活")
    p.add_argument("--prompt", help="任务文本")
    p.add_argument("--input", help="任务JSON文件（OpenAI messages格式）")
    p.add_argument("--models", required=True, help="模型列表，逗号分隔")
    p.add_argument("--system", help="自定义system prompt")
    p.add_argument("--max-tokens", type=int, default=4096)
    p.add_argument("--temperature", type=float, default=None)
    p.add_argument("--output", help="结果输出目录")
    args = p.parse_args()
    
    if not args.prompt and not args.input:
        print("错误：需要 --prompt 或 --input", file=sys.stderr)
        sys.exit(1)
    
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if len(models) == 1:
        print("只有一个模型，不需要分身。直接用 minis-model-use run。", file=sys.stderr)
        sys.exit(1)
    
    print(f"分身启动：{len(models)} 个模型并行")
    print(f"任务：{(args.prompt or args.input)[:80]}")
    print(f"模型：{', '.join(models)}")
    print("=" * 60)
    print()
    
    results = []
    with ThreadPoolExecutor(max_workers=len(models)) as pool:
        futures = {
            pool.submit(run_one, m, args.prompt, args.input, args.system, 
                       args.max_tokens, args.temperature): m
            for m in models
        }
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            status = "OK" if r["ok"] else "FAIL"
            print(f"[{status}] {r['model']} ({r['elapsed']}s)")
            if r["ok"] and r["content"]:
                print(r["content"][:500])
            elif r["error"]:
                print(f"  错误：{r["error"][:200]}")
            print("-" * 40)
    
    # 按完成顺序排
    results.sort(key=lambda x: x["elapsed"])
    fastest = results[0]["model"] if results else "?"
    print()
    print(f"最快：{fastest} ({results[0]['elapsed']}s)" if results else "")
    
    # 写文件
    if args.output:
        os.makedirs(args.output, exist_ok=True)
        for r in results:
            safe = r["model"].replace("/", "_").replace(" ", "_")
            path = os.path.join(args.output, f"{safe}.txt")
            with open(path, "w") as f:
                f.write(r["content"] or r["error"] or "")
        print(f"结果已写入 {args.output}/")
    
    # 返回JSON
    print()
    print("--- JSON ---")
    print(json.dumps(results, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
