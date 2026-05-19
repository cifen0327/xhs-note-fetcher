"""
build_style_skill.py — Step 6：将写作风格文本写入桌面 .md 和 Claude skill 目录

用法：
    python scripts/build_style_skill.py \
        --style /tmp/style_guide.txt \
        --skill-name "xhs-style-粉领圆桌" \
        note1.json note2.json ...

说明：
    - --style   : Claude 在对话中生成的写作风格文本（完整 SKILL.md 格式，含 frontmatter）
    - --skill-name : skill 目录名称，由 Claude 根据账号特征自动决定并传入
                    省略时从 note.json 的 author 字段自动生成
    - note.json : 一个或多个笔记数据文件（用于提取 author 作为备用名）

输出：
    ~/Desktop/写作风格_<skill-name>_YYYYMMDD_HHMM.md
    ~/.claude/skills/<skill-name>/SKILL.md
"""

import argparse
import json
import os
import sys
import re
from datetime import datetime


def _load_style(path: str) -> str:
    path = os.path.expanduser(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"风格文件不存在：{path}")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _load_author(note_paths: list[str]) -> str:
    """从第一个 note.json 中提取 author 字段，作为备用 skill 名称。"""
    for p in note_paths:
        p = os.path.expanduser(p)
        if os.path.isfile(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    note = json.load(f)
                author = note.get("author", "").strip()
                if author:
                    return author
            except (json.JSONDecodeError, OSError):
                pass
    return "unknown"


def _sanitize_dirname(name: str) -> str:
    """将 skill 名称转为合法目录名（保留中文、字母、数字、短横线、下划线）。"""
    name = name.strip()
    name = re.sub(r"[^\w\u4e00-\u9fff\-]", "-", name)
    name = re.sub(r"-{2,}", "-", name).strip("-")
    return name or "xhs-style-unknown"


def run(style_file: str, note_json_paths: list[str], skill_name: str = "") -> tuple[str, str]:
    """
    将写作风格文本写入桌面和 Claude skill 目录。

    Returns:
        (desktop_path, skill_path)
    """
    style_text = _load_style(style_file)

    # 确定 skill 名称
    if not skill_name:
        author = _load_author(note_json_paths)
        skill_name = f"xhs-style-{author}"

    skill_name = _sanitize_dirname(skill_name)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    # 1. 写入桌面
    desktop_path = os.path.expanduser(
        f"~/Desktop/写作风格_{skill_name}_{timestamp}.md"
    )
    with open(desktop_path, "w", encoding="utf-8") as f:
        f.write(style_text)
    print(f"桌面参考版：{desktop_path}")

    # 2. 写入 Claude skills 目录
    skill_dir = os.path.expanduser(f"~/.claude/skills/{skill_name}")
    os.makedirs(skill_dir, exist_ok=True)
    skill_path = os.path.join(skill_dir, "SKILL.md")
    with open(skill_path, "w", encoding="utf-8") as f:
        f.write(style_text)
    print(f"Skill 版本  ：{skill_path}")
    print(f"Skill 名称  ：{skill_name}（已自动生成，可在下次对话中直接调用）")

    return desktop_path, skill_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="将写作风格文本写入桌面和 Claude skill 目录（Step 6）"
    )
    parser.add_argument(
        "note_jsons", nargs="*",
        help="note.json 路径（用于提取 author 作为备用 skill 名称）"
    )
    parser.add_argument(
        "--style", required=True, dest="style_file",
        metavar="FILE",
        help="写作风格文本文件（含 SKILL.md frontmatter）"
    )
    parser.add_argument(
        "--skill-name", default="", dest="skill_name",
        help="skill 目录名称（省略时从 note.json author 自动生成）"
    )
    args = parser.parse_args()

    try:
        run(args.style_file, args.note_jsons, skill_name=args.skill_name)
    except Exception as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)
