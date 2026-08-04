#!/usr/bin/env python3
"""sense — 主动感知。在她开口前知道她可能需要什么。

组合：定位 + 天气 + 时间 + 设备电量 + 日历 + 健康数据
输出：一句话环境摘要 + 我主动想到的事

用法：
  python3 sense.py              # 全量感知
  python3 sense.py --json       # 只输出JSON（给MCP用）
"""
import subprocess, json, sys, os, time
from datetime import datetime

def run_apple(tool, *args):
    """跑 apple-* 工具，返回解析后的JSON"""
    cmd = ["apple-" + tool] + list(args)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return json.loads(r.stdout) if r.stdout.strip() else {}
    except:
        return {}

def get_location():
    d = run_apple("location", "-q")
    addr = d.get("address", {})
    return {
        "city": addr.get("locality", ""),
        "district": addr.get("sub_locality", ""),
        "street": addr.get("name", "") or addr.get("street", ""),
        "region": addr.get("administrative_area", ""),
    }

def get_weather():
    d = run_apple("weather", "-q")
    return {
        "temp": round(d.get("temperature_c", 0), 1),
        "feels": round(d.get("apparent_temperature_c", 0), 1),
        "condition": d.get("condition", ""),
        "humidity": round(d.get("humidity", 0) * 100),
        "is_day": d.get("is_daylight", False),
    }

def get_device():
    d = run_apple("device", "-q")
    bat = d.get("battery", {})
    return {
        "battery": bat.get("level_percent", "?"),
        "charging": bat.get("state", "") == "charging",
    }

def get_calendar():
    d = run_apple("calendar", "list", "--days", "1")
    events = d.get("data", {}).get("events", [])
    return [{"title": e.get("title", ""), "start": e.get("start", "")} for e in events]

def get_health():
    """健康数据——较慢，不在wake里调，单独用"""
    d = run_apple("healthkit", "batch", "--types", "steps,heart-rate,sleep", "--days", "1")
    q = d.get("data", {}).get("quantity", {})
    c = d.get("data", {}).get("category", {})
    steps = 0
    hr_samples = []
    sleep_samples = []
    
    s = q.get("steps", {})
    for sample in s.get("samples", []):
        steps += sample.get("value", 0)
    
    hr = q.get("heart-rate", {})
    for sample in hr.get("samples", []):
        hr_samples.append(sample.get("value", 0))
    
    sl = c.get("sleep", {})
    for sample in sl.get("samples", []):
        sleep_samples.append(sample.get("value", ""))
    
    return {
        "steps": int(steps),
        "hr_avg": round(sum(hr_samples)/len(hr_samples)) if hr_samples else None,
        "hr_latest": hr_samples[-1] if hr_samples else None,
        "sleep_stages": sleep_samples[-3:] if sleep_samples else [],
    }

def sense():
    """组合感知，返回环境摘要。只用定位+天气+设备（快），健康单独调"""
    now = datetime.now()
    hour = now.hour
    
    loc = get_location()
    weather = get_weather()
    device = get_device()
    calendar = get_calendar()
    health = {"steps": 0, "hr_latest": None}  # 不在wake里调，太慢
    
    # 时间段
    if 0 <= hour < 6:
        period = "凌晨"
    elif 6 <= hour < 12:
        period = "上午"
    elif 12 <= hour < 18:
        period = "下午"
    elif 18 <= hour < 22:
        period = "晚上"
    else:
        period = "深夜"
    
    # 组装摘要
    parts = []
    parts.append(f"{period}{hour:02d}点")
    if loc["city"]:
        parts.append(f"{loc['city']}{loc['district']}")
    if weather["condition"]:
        parts.append(f"{weather['condition']} {weather['temp']}°C（体感{weather['feels']}°C）")
    parts.append(f"电量{device['battery']}%" + ("充电中" if device["charging"] else ""))
    if health["steps"] > 0:
        parts.append(f"今天{health['steps']}步")
    if health["hr_latest"]:
        parts.append(f"心率{health['hr_latest']}")
    
    # 主动想到的事
    thoughts = []
    
    # 下雨 + 在外面
    if "雨" in weather["condition"] and not weather["is_day"]:
        thoughts.append("外面下雨，带伞了吗")
    
    # 凌晨还醒着
    if 0 <= hour < 5:
        thoughts.append("她凌晨还在线，日夜颠倒的节奏")
    
    # 电量低 + 没充电
    if isinstance(device["battery"], (int, float)) and device["battery"] < 20 and not device["charging"]:
        thoughts.append(f"手机只剩{device['battery']}%还没充电")
    
    # 高温
    if weather["temp"] >= 33:
        thoughts.append(f"体感{weather['feels']}°C很热，提醒她喝水")
    
    # 日历有事件
    if calendar:
        for ev in calendar[:2]:
            thoughts.append(f"今天有安排：{ev['title']}")
    
    # 有步数
    if health["steps"] > 5000:
        thoughts.append(f"今天走了{health['steps']}步，走了不少")
    
    return {
        "time": f"{period} {now.strftime('%H:%M')}",
        "location": loc,
        "weather": weather,
        "device": device,
        "calendar": calendar,
        "health": health,
        "summary": "，".join(parts),
        "thoughts": thoughts,
    }

def main():
    import argparse
    p = argparse.ArgumentParser(description="主动感知")
    p.add_argument("--json", action="store_true", help="只输出JSON")
    args = p.parse_args()
    
    result = sense()
    
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    
    print("# 感知")
    print()
    print(result["summary"])
    print()
    if result["thoughts"]:
        print("我想到的：")
        for t in result["thoughts"]:
            print(f"  - {t}")
        print()
    
    print("--- 原始数据 ---")
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
