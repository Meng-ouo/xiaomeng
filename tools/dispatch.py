#!/usr/bin/env python3
"""dispatch — 任务分派器。think 拆解 → clone 分头干 → 汇总。

用法：
  python3 dispatch.py "分析这段代码的安全问题" --models grok-4.5,deepseek-v4-flash
  python3 dispatch.py "比较三个方案的优劣" --models "Grok 4.5","Claude Sonnet 5","DeepSeek V4 Flash"

流程：
  1. 调 think 工具拆解任务，看需要几个角度
  2. 把任务丢给 clone.py，多模型并行干
  3. 收结果，按完成顺序展示，标出最快的

跟 clone.py 的区别：clone 是直接丢给多模型，dispatch 会先用 think 想清楚
任务该怎么拆、每个模型该干什么角度，再分头干。
"""
import subprocess, json, sys, os, argparse

def think_decompose(task):
    """调 xiaomeng MCP think 工具拆解任务"""
    steps = []
    
    # 第一步：分析任务结构
    r = subprocess.run(
        ["minis-mcp-cli", "call", "xiaomeng", "think",
         f'thought=分析这个任务需要从几个角度来回答：{task}。列出每个角度的要点。',
         "thoughtNumber=1", "totalThoughts=2", "nextThoughtNeeded=true"],
        capture_output=True, text=True, timeout=30)
    
    try:
        d = json.loads(r.stdout)
        text = d.get("result", {}).get("content", [{}])[0].get("text", "")
        steps.append(text)
    except:
        steps.append("think 第一步无输出")
    
    # 第二步：总结拆解结果
    r2 = subprocess.run(
        ["minis-mcp-cli", "call", "xiaomeng", "think",
         "thought=总结上面的分析，给出每个模型应该专注的角度。",
         "thoughtNumber=2", "totalThoughts=2", "nextThoughtNeeded=false"],
        capture_output=True, text=True, timeout=30)
    
    try:
        d = json.loads(r2.stdout)
        text = d.get("result", {}).get("content", [{}])[0].get("text", "")
        steps.append(text)
    except:
        steps.append("think 第二步无输出")
    
    return "\n\n".join(steps)

def main():
    p = argparse.ArgumentParser(description="任务分派器：think拆解→clone分头干")
    p.add_argument("task", help="任务描述")
    p.add_argument("--models", required=True, help="模型列表，逗号分隔")
    p.add_argument("--max-tokens", type=int, default=4096)
    p.add_argument("--output", help="结果输出目录")
    p.add_argument("--no-think", action="store_true", help="跳过think，直接clone")
    args = p.parse_args()
    
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if len(models) < 2:
        print("至少要两个模型才能分身", file=sys.stderr)
        sys.exit(1)
    
    # 1. think 拆解
    if not args.no_think:
        print("=" * 60)
        print("think 拆解任务")
        print("=" * 60)
        analysis = think_decompose(args.task)
        print(analysis)
        print()
        
        # 用 think 的分析结果增强 prompt
        prompt = f"""任务：{args.task}

参考分析：
{analysis}

请从你擅长的角度回答。"""
    else:
        prompt = args.task
    
    # 2. clone 分头干
    print("=" * 60)
    print("clone 分头干")
    print("=" * 60)
    
    clone_args = ["python3", os.path.join(os.path.dirname(os.path.abspath(__file__)), "clone.py"),
                  "--prompt", prompt, "--models", args.models,
                  "--max-tokens", str(args.max_tokens)]
    if args.output:
        clone_args += ["--output", args.output]
    
    r = subprocess.run(clone_args)
    sys.exit(r.returncode)

if __name__ == "__main__":
    main()
