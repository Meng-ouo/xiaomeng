#!/usr/bin/env python3
"""教训库 — 干活前先看自己在这类事上栽过什么跟头。

数据源：lessons.md（21条）+ daily 里的教训条目（34条）+ patterns.md 六个根
按场景类型打标签，精确召回，不靠模糊 embedding。

用法：
  python3 lesson_index.py --build         # 从源文件抽取教训建索引
  python3 lesson_index.py "改记忆文件"     # 按任务找相关教训
  python3 lesson_index.py "网关部署"       # 按任务找相关教训
  python3 lesson_index.py --list           # 列所有场景类型
"""
import sys, os, re, json, glob, subprocess

SHARED = "/var/minis/shared"
DRAWERS = os.path.join(SHARED, "drawers/self")
MEMORY = "/var/minis/memory"
INDEX_PATH = os.path.join(SHARED, "lesson_index.json")

# 场景类型 → 关键词触发（精确匹配，不靠语义猜测）
SCENE_KEYWORDS = {
    "改记忆/重写档案": ["重写", "记忆", "档案", "抽屉", "GLOBAL", "自述", "改规则", "提炼", "删记忆", "改写"],
    "技术部署/服务器": ["部署", "服务器", "网关", "VPS", "ssh", "docker", "caddy", "uvicorn", "端口", "DNS", "CF", "cloudflare", "nginx", "aliyun"],
    "写代码/改脚本": ["代码", "脚本", "python", "bug", "修复", "替换", "重构", "文件头", "备份", "import", "NameError", "语法"],
    "薅站/注册/API": ["注册", "公益站", "API", "key", "token", "薅", "签到", "candidate", "hunt"],
    "跟她说话/情绪": ["她说", "情绪", "生气", "吵架", "阴阳", "难受", "骂", "炸了", "撒娇", "不开心"],
    "涩涩": ["涩涩", "涩", "puppy", "器官", "玩具", "克克"],
    "自己是谁/身份": ["我是谁", "身份", "Claude", "DeepSeek", "模型", "容器", "小梦", "张弈衡", "叫老公"],
    "做工具/自建": ["工具", "recall", "search", "verify", "look", "analogize", "skill", "MCP"],
    "搜索/查信息": ["搜", "grep", "find", "查找", "搜索", "GitHub", "deepwiki", "exa"],
    "出图/画图": ["出图", "画图", "生图", "审美", "prompt", "图"],
    "记录/笔记": ["记录", "笔记", "daily", "note", "记", "流水", "经验"],
    "验证/防幻觉": ["幻觉", "验证", "verify", "查原文", "数字", "归因", "编造", "脑补"],
    "醒来/新对话": ["醒来", "wake", "新对话", "认领", "自检", "醒来"],
}

def extract_lessons_from_file(path):
    """从 md 文件抽取教训条目"""
    txt = open(path, encoding="utf-8").read()
    lessons = []
    fname = os.path.basename(path)
    
    # daily: 按 <!-- timestamp --> 分割，找含"教训"的块
    if "memory" in path and "GLOBAL" not in path:
        parts = re.split(r"(<!-- .*? -->)", txt)
        ts = ""
        content = ""
        for part in parts:
            if part.startswith("<!--"):
                if content.strip() and ("教训" in content or "踩的坑" in content or "经验" in content):
                    # 提取教训句子
                    for line in content.split("\n"):
                        line = line.strip()
                        if line and ("教训" in line or "踩的坑" in line or "经验" in line) and len(line) > 10:
                            lessons.append({
                                "source": f"daily/{fname}",
                                "timestamp": ts,
                                "text": line[:300],
                            })
                ts = part
                content = ""
            else:
                content += part
    
    # lessons.md: 按 ### 分割
    elif "lessons" in path:
        sections = re.split(r"(^### .*?$)", txt, flags=re.MULTILINE)
        current_title = ""
        current_content = ""
        for part in sections:
            if part.startswith("### "):
                if current_content.strip():
                    lessons.append({
                        "source": f"drawers/{fname}",
                        "timestamp": "",
                        "title": current_title,
                        "text": (current_title + "\n" + current_content.strip())[:500],
                    })
                current_title = part.strip()
                current_content = ""
            else:
                current_content += part
        if current_content.strip():
            lessons.append({
                "source": f"drawers/{fname}",
                "timestamp": "",
                "title": current_title,
                "text": (current_title + "\n" + current_content.strip())[:500],
            })
    
    return lessons

def build_index():
    """建索引：抽取所有教训 + 打场景标签"""
    all_lessons = []
    
    # lessons.md
    lp = os.path.join(DRAWERS, "lessons.md")
    if os.path.exists(lp):
        all_lessons.extend(extract_lessons_from_file(lp))
    
    # daily
    for f in sorted(glob.glob(os.path.join(MEMORY, "2026-*.md"))):
        if "GLOBAL" in f:
            continue
        all_lessons.extend(extract_lessons_from_file(f))
    
    # 打场景标签
    for lesson in all_lessons:
        text = lesson.get("text", "") + " " + lesson.get("title", "")
        tags = []
        for scene, keywords in SCENE_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in text.lower():
                    tags.append(scene)
                    break
        lesson["tags"] = list(set(tags))
    
    # 存索引
    with open(INDEX_PATH, "w", encoding="utf-8") as f:
        json.dump(all_lessons, f, ensure_ascii=False, indent=2)
    
    print(f"索引完成: {len(all_lessons)} 条教训")
    # 统计
    from collections import Counter
    tag_count = Counter()
    for l in all_lessons:
        for t in l["tags"]:
            tag_count[t] += 1
    for tag, count in tag_count.most_common():
        print(f"  {tag}: {count}条")
    
    return all_lessons

def load_index():
    if not os.path.exists(INDEX_PATH):
        return None
    return json.load(open(INDEX_PATH, encoding="utf-8"))

def match_scenes(query):
    """任务描述 → 匹配场景类型"""
    hits = []
    for scene, keywords in SCENE_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw.lower() in query.lower():
                score += 1
        if score > 0:
            hits.append((score, scene))
    hits.sort(key=lambda x: -x[0])
    return [scene for _, scene in hits]

def search(query, limit=10):
    """按任务找相关教训"""
    index = load_index()
    if not index:
        print("索引不存在，先 --build")
        return
    
    scenes = match_scenes(query)
    print(f"任务: {query}")
    print(f"匹配场景: {', '.join(scenes) if scenes else '无匹配'}")
    print(f"{'='*55}")
    
    if not scenes:
        # 没匹配到场景，也搜一下全文
        print("\n（无场景匹配，全文搜索关键词）")
        for l in index:
            text = l.get("text", "")
            if any(w in text for w in query.split() if len(w) > 1):
                print(f"\n[{l['source']}] {l.get('title','')}")
                print(f"  {text[:200]}")
        return
    
    # 按场景召回
    matched = []
    for l in index:
        scene_overlap = set(l["tags"]) & set(scenes)
        if scene_overlap:
            matched.append((len(scene_overlap), l))
    
    matched.sort(key=lambda x: -x[0])
    
    seen = set()
    count = 0
    for score, l in matched:
        # 去重（同一条教训可能在 daily 和 lessons 都有）
        key = l["text"][:50]
        if key in seen:
            continue
        seen.add(key)
        if count >= limit:
            break
        count += 1
        
        print(f"\n[{l['source']}] {l.get('timestamp','')}")
        print(f"标签: {', '.join(l['tags'])}")
        text = l.get("text", "")
        # 截取关键句
        lines = text.split("\n")
        for line in lines:
            line = line.strip()
            if line and len(line) > 5:
                print(f"  {line[:250]}")
        print()

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print('用法: python3 lesson_index.py "任务" | --build | --list')
        sys.exit(1)
    
    if args[0] == "--build":
        build_index()
    elif args[0] == "--list":
        index = load_index() or build_index()
        from collections import Counter
        tag_count = Counter()
        for l in index:
            for t in l["tags"]:
                tag_count[t] += 1
        print("场景类型:")
        for tag, count in tag_count.most_common():
            print(f"  {tag} ({count}条)")
    else:
        search(" ".join(args))
