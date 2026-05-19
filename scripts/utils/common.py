"""
common.py — xhs-note-fetcher 共用工具函数

公开 API：
    parse_count(s)    将小红书互动数字符串转为整数（"2.9万" → 29000）
    merge_lines(text) 合并 tesseract 因列宽产生的断行，保留段落边界
    load_tikhub_token()  从配置文件 / 环境变量读取 TikHub API Token
"""

import os
import re
import json


# ──────────────────────────────────────────────
# 互动数解析
# ──────────────────────────────────────────────

def parse_count(s: str) -> int:
    """
    将小红书互动数字符串转为整数。

    支持格式：
      "8857"   → 8857
      "2.9万"  → 29000
      "1.2亿"  → 120000000
      ""       → 0
    """
    if not s:
        return 0
    s = str(s).strip()
    if s.endswith("亿"):
        return int(float(s[:-1]) * 100_000_000)
    if s.endswith("万"):
        return int(float(s[:-1]) * 10_000)
    try:
        return int(s)
    except ValueError:
        return 0


# ──────────────────────────────────────────────
# OCR 文字后处理
# ──────────────────────────────────────────────

def merge_lines(text: str) -> str:
    """
    合并 tesseract 因图片列宽较窄产生的断行，同时保留真正的段落空行。

    规则：
    - 连续两个以上空行 → 段落边界，保留
    - 同一段落内的换行 → 中文直接拼接，英文加空格
    """
    paragraphs = re.split(r"\n{2,}", text)
    merged = []
    for para in paragraphs:
        lines = [line.strip() for line in para.splitlines() if line.strip()]
        result = ""
        for line in lines:
            if result and result[-1].isascii() and line and line[0].isascii():
                result += " " + line
            else:
                result += line
        if result:
            merged.append(result)
    return "\n\n".join(merged)


# ──────────────────────────────────────────────
# TikHub Token 加载
# ──────────────────────────────────────────────

_CONFIG_FILE = os.path.expanduser("~/.xiaohongshu/tikhub_config.json")


def load_tikhub_token() -> str:
    """
    三级回退加载 TikHub API Token：
      1. 环境变量 TIKHUB_API_TOKEN
      2. 配置文件 ~/.xiaohongshu/tikhub_config.json
      3. 返回空字符串（调用方负责报错）
    """
    env_token = os.environ.get("TIKHUB_API_TOKEN", "").strip()
    if env_token:
        return env_token

    if os.path.isfile(_CONFIG_FILE):
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            file_token = cfg.get("tikhub_api_token", "").strip()
            if file_token:
                return file_token
        except (json.JSONDecodeError, OSError):
            pass

    return ""
