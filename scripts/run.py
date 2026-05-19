"""
run.py — xhs-note-fetcher 主入口，串联全流程

用法：
    # 模式 A（指定笔记链接，原有方式）
    python scripts/run.py <url1> [<url2> ...] [--skip-ocr]

    # 模式 B（按博主批量爬取，交互式）
    python scripts/run.py --blogger

示例：
    # 模式 A：单篇 / 多篇
    python scripts/run.py "https://www.xiaohongshu.com/explore/..."
    python scripts/run.py "https://...url1..." "https://...url2..."

    # 模式 A：跳过 OCR
    python scripts/run.py "https://...url..." --skip-ocr

    # 模式 B：交互式指定博主
    python scripts/run.py --blogger

流程：
    Step 1+2  fetch_note.py      解析链接 → TikHub API → note.json
    Step 3    ocr_images.py      下载图片 → OCR → 更新 note.json
    Step 5    由 AI 在对话中直接分析 note.json，生成报告文字，
              再调用 build_report.py --analysis <file> 写入 docx
    Step 6    由 AI 在对话中生成写作风格 SKILL.md 文本（含 frontmatter），
              再调用 build_style_skill.py --style <file> 写入桌面和 ~/.claude/skills/
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch_note
import ocr_images
from utils.common import load_tikhub_token, parse_count


# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def _ask(prompt: str) -> str:
    """交互式输入，EOF 时返回空字符串。"""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def _print_next_steps(note_json_paths: list[str]):
    """打印 Step 5/6 的后续操作提示。"""
    paths_arg = " ".join(f'"{p}"' for p in note_json_paths)
    print("\n爬取和 OCR 完成。数据目录：")
    for p in note_json_paths:
        print(f"  {p}")
    print("\nStep 5（生成报告）：")
    print("  1. 让 AI 读取以上 note.json 文件，在对话中生成分析文字")
    print("  2. AI 将分析文字写入临时文件（如 /tmp/analysis.txt）")
    print("  3. 运行：")
    print(f"     python3 scripts/build_report.py --analysis /tmp/analysis.txt {paths_arg}")
    print("\nStep 6（生成写作风格 Skill）：")
    print("  1. 让 AI 根据五模块分析，生成写作风格 SKILL.md 文本（含 frontmatter），写入 /tmp/style_guide.txt")
    print("  2. 运行（--skill-name 由 AI 根据账号特征自动决定）：")
    print(f"     python3 scripts/build_style_skill.py --style /tmp/style_guide.txt --skill-name \"<ai-generated-name>\" {paths_arg}")
    print("  输出：~/Desktop/写作风格_<skill-name>_*.md  +  ~/.claude/skills/<skill-name>/SKILL.md")


# ──────────────────────────────────────────────
# 模式 A：笔记链接
# ──────────────────────────────────────────────

def run_mode_a(urls: list[str], skip_ocr: bool = False) -> list[str]:
    """爬取指定链接列表，返回所有 note.json 路径。"""
    note_json_paths = []

    for i, url in enumerate(urls, 1):
        print(f"\n[{i}/{len(urls)}] 爬取笔记...")
        note_json_path = fetch_note.run(url)
        note_json_paths.append(note_json_path)

    if not skip_ocr:
        for i, path in enumerate(note_json_paths, 1):
            print(f"\n[{i}/{len(note_json_paths)}] OCR 处理...")
            ocr_images.run(path)

    return note_json_paths


# ──────────────────────────────────────────────
# 模式 B：按博主批量爬取（交互式）
# ──────────────────────────────────────────────

def _collect_one_blogger(token: str) -> list[dict]:
    """
    交互式收集一个博主的信息，返回笔记列表。
    每项：{"note_id": str, "xsec_token": str, "title": str, "liked": int}
    """
    from fetch_blogger import search_and_confirm, fetch_top_notes, NeedUserConfirm, SearchEndpointDown
    import urllib.parse as _urlparse

    # 收集昵称
    nickname = ""
    while not nickname:
        nickname = _ask("  博主昵称（必填）：")
        if not nickname:
            print("  昵称不能为空，请重新输入")

    xhs_id = _ask("  小红书号（选填，用于核对，可直接回车跳过）：")

    # 收集数量
    top_n = 0
    while top_n <= 0:
        raw = _ask("  爬取数量 Top N（必填，输入正整数）：")
        try:
            top_n = int(raw)
            if top_n <= 0:
                raise ValueError
        except ValueError:
            print("  请输入有效的正整数")

    # B2：搜索 + 核对
    user_id = ""
    while True:
        try:
            user_id = search_and_confirm(token, nickname, xhs_id)
            break
        except SearchEndpointDown as e:
            # 搜索端点不可用，引导用户直接提供主页 URL
            print(e)
            url_input = _ask("\n  请粘贴博主主页 URL（或直接输入 user_id）：").strip()
            if not url_input:
                raise RuntimeError("未提供博主主页 URL，无法继续")
            if "user/profile/" in url_input:
                path = _urlparse.urlparse(url_input).path
                user_id = path.rstrip("/").split("/")[-1].split("?")[0]
            else:
                user_id = url_input.split("?")[0].strip()
            print(f"  ✓ 已解析 user_id：{user_id}")
            break
        except NeedUserConfirm as e:
            print(e)
            candidates = e.candidates
            choice = _ask("  请输入序号选择（或直接回车取消）：")
            if not choice:
                raise RuntimeError("用户取消博主选择")
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(candidates):
                    user_id = candidates[idx]["user_id"]
                    print(f"  ✓ 已选择：{candidates[idx]['nickname']}（user_id: {user_id}）")
                    break
                else:
                    print("  序号超出范围，请重试")
            except ValueError:
                print("  请输入有效序号，请重试")

    # B3：拉取笔记列表
    notes = fetch_top_notes(token, user_id, top_n)
    return notes


def run_mode_b(skip_ocr: bool = False) -> list[str]:
    """
    模式 B 交互式主流程。
    循环采集多个博主 → 可追加手动链接 → 统一爬取 OCR。
    返回所有 note.json 路径。
    """
    token = load_tikhub_token()
    if not token:
        raise RuntimeError(
            "未找到 TikHub API Token。\n"
            "请设置环境变量 TIKHUB_API_TOKEN，\n"
            "或确保 ~/.xiaohongshu/tikhub_config.json 存在且含有效 token。"
        )

    all_notes: list[dict] = []   # {"note_id", "xsec_token", "title", "liked"}
    extra_urls: list[str] = []   # 用户手动补充的链接

    print("\n══════════════════════════════════════════")
    print("  模式 B：按博主批量爬取")
    print("══════════════════════════════════════════")

    # ── B1-B3：循环采集博主 ────────────────────────
    while True:
        print("\n─── 添加博主 ───────────────────────────────")
        blogger_notes = _collect_one_blogger(token)
        all_notes.extend(blogger_notes)
        print(f"\n  当前笔记池：共 {len(all_notes)} 篇")

        ans = _ask("\n  是否继续采集其他博主？（y/n，默认 n）：").lower()
        if ans != "y":
            break

    # ── B5：是否追加手动链接 ──────────────────────
    ans = _ask("\n  是否要额外加入其他笔记链接？（y/n，默认 n）：").lower()
    if ans == "y":
        print("  请逐行粘贴笔记链接，输入空行结束：")
        while True:
            line = _ask("  > ")
            if not line:
                break
            extra_urls.append(line)
        if extra_urls:
            print(f"  已添加 {len(extra_urls)} 条额外链接")

    # ── 汇总并开始爬取 ────────────────────────────
    if not all_notes and not extra_urls:
        raise RuntimeError("笔记列表为空，请至少添加一个博主或链接")

    total = len(all_notes) + len(extra_urls)
    print(f"\n══════════════════════════════════════════")
    print(f"  共 {total} 篇笔记，开始保存...")
    print(f"══════════════════════════════════════════")

    note_json_paths = []

    # 博主列表笔记：
    #   app/get_user_notes 成功时 → _raw 含 images_list，直接用 build_note_json_from_raw
    #   web_v3/fetch_user_notes 成功时 → _raw 无 images_list，回退到 fetch_note.run()（调用 web_v3/fetch_note_detail）
    from fetch_blogger import build_note_json_from_raw
    for i, note in enumerate(all_notes, 1):
        print(f"\n[{i}/{total}] 保存笔记数据...")
        raw = note.get("_raw")
        if raw and raw.get("images_list"):
            # app/get_user_notes 路径：列表数据已完整，无需调用 detail 端点
            try:
                note_data = build_note_json_from_raw(raw)
                out_dir = os.path.expanduser(f"~/Downloads/xhs_{note_data['note_id']}")
                os.makedirs(out_dir, exist_ok=True)
                out_path = os.path.join(out_dir, "note.json")
                import json as _json
                with open(out_path, "w", encoding="utf-8") as f:
                    _json.dump(note_data, f, ensure_ascii=False, indent=2)
                print(f"  已写入 {out_path}（来自 app/get_user_notes，跳过 detail 端点）")
                note_json_paths.append(out_path)
            except Exception as e:
                print(f"  ⚠️  跳过（{e}）")
        else:
            # web_v3/fetch_user_notes 路径：调用 web_v3/fetch_note_detail 获取完整内容
            url = (f"https://www.xiaohongshu.com/explore/{note['note_id']}?xsec_token={note['xsec_token']}"
                   if note.get("xsec_token") else note["note_id"])
            try:
                path = fetch_note.run(url)
                note_json_paths.append(path)
            except Exception as e:
                print(f"  ⚠️  跳过（{e}）")

    # 手动追加链接仍走 fetch_note.run()
    offset = len(all_notes)
    for i, url in enumerate(extra_urls, 1):
        print(f"\n[{offset + i}/{total}] 爬取笔记（手动链接）...")
        try:
            path = fetch_note.run(url)
            note_json_paths.append(path)
        except Exception as e:
            print(f"  ⚠️  跳过（{e}）")

    if not skip_ocr:
        for i, path in enumerate(note_json_paths, 1):
            print(f"\n[{i}/{len(note_json_paths)}] OCR 处理...")
            try:
                ocr_images.run(path)
            except Exception as e:
                print(f"  ⚠️  OCR 失败，已跳过（{e}）")

    return note_json_paths


# ──────────────────────────────────────────────
# 统一出口
# ──────────────────────────────────────────────

def run(urls: list[str], skip_ocr: bool = False, blogger_mode: bool = False) -> list[str]:
    if blogger_mode:
        note_json_paths = run_mode_b(skip_ocr=skip_ocr)
    else:
        note_json_paths = run_mode_a(urls, skip_ocr=skip_ocr)

    _print_next_steps(note_json_paths)
    return note_json_paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="小红书笔记爬取 + OCR（全流程）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
模式 A（默认）：直接传入笔记链接
  python scripts/run.py "https://www.xiaohongshu.com/explore/<id>?xsec_token=<token>"

模式 B：交互式指定博主批量爬取
  python scripts/run.py --blogger
        """,
    )
    parser.add_argument(
        "urls",
        nargs="*",
        help="模式 A：一个或多个小红书笔记链接（模式 B 时留空）",
    )
    parser.add_argument(
        "--blogger",
        action="store_true",
        help="启用模式 B：交互式指定博主昵称批量爬取",
    )
    parser.add_argument("--skip-ocr", action="store_true", help="跳过图片 OCR 步骤")
    args = parser.parse_args()

    if not args.blogger and not args.urls:
        parser.print_help()
        sys.exit(0)

    try:
        run(args.urls, skip_ocr=args.skip_ocr, blogger_mode=args.blogger)
    except Exception as e:
        print(f"\n错误：{e}", file=sys.stderr)
        sys.exit(1)
