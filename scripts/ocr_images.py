"""
ocr_images.py — Step 3：下载图片 + Tesseract OCR + 更新 note.json

用法：
    python scripts/ocr_images.py <note_json_path>

示例：
    python scripts/ocr_images.py ~/Downloads/xhs_6936699d/note.json

依赖：
    pip install pytesseract pillow
    brew install tesseract tesseract-lang   # macOS

行为：
    - 读取 note.json 中的 images[].url 和 images[].filename
    - 下载图片到与 note.json 同级目录（已存在则跳过）
    - Pillow 内存转 RGB，传给 tesseract（chi_sim+eng）
    - merge_lines() 后处理断行
    - 将 ocr_text 写回 note.json 中对应 image 条目
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.common import merge_lines

DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.xiaohongshu.com/",
}


# ──────────────────────────────────────────────
# 环境检查
# ──────────────────────────────────────────────

def check_env():
    """检查 pytesseract / tesseract 是否可用，不可用时给出修复提示。"""
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
    except ImportError:
        raise RuntimeError(
            "pytesseract 未安装。请运行：pip install pytesseract pillow"
        )
    except Exception:
        raise RuntimeError(
            "未找到 tesseract 二进制。请运行：brew install tesseract tesseract-lang"
        )


# ──────────────────────────────────────────────
# 图片下载
# ──────────────────────────────────────────────

def download_image(url: str, dest: str, retries: int = 3) -> bool:
    """
    下载图片到 dest 路径。

    Returns:
        True 表示成功（含命中缓存），False 表示全部重试失败。
    """
    if os.path.isfile(dest) and os.path.getsize(dest) > 0:
        return True  # 命中本地缓存

    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=DOWNLOAD_HEADERS)
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
            if len(data) < 1024:
                raise ValueError(f"响应过小 ({len(data)} bytes)，疑似错误页")
            with open(dest, "wb") as f:
                f.write(data)
            return True
        except (urllib.error.URLError, urllib.error.HTTPError, ValueError, OSError) as e:
            if attempt < retries:
                time.sleep(1.5 * attempt)
            else:
                print(f"  ⚠ 下载失败（{attempt}/{retries}）: {url[:60]}… — {e}")
    return False


# ──────────────────────────────────────────────
# 单张图片 OCR
# ──────────────────────────────────────────────

def ocr_image(image_path: str) -> str:
    """
    对单张图片执行 OCR，返回后处理后的文字字符串。

    - Pillow 在内存中将 WebP 转 RGB（不保存 PNG 到磁盘）
    - tesseract chi_sim+eng 双语识别
    - merge_lines() 合并断行
    """
    import pytesseract
    from PIL import Image

    try:
        img = Image.open(image_path).convert("RGB")
        raw = pytesseract.image_to_string(img, lang="chi_sim+eng")
        return merge_lines(raw)
    except Exception as e:
        print(f"  ⚠ OCR 失败: {image_path} — {e}")
        return ""


# ──────────────────────────────────────────────
# 主函数
# ──────────────────────────────────────────────

def run(note_json_path: str) -> None:
    """
    读取 note.json → 下载图片 → OCR → 将 ocr_text 写回 note.json。
    """
    note_json_path = os.path.expanduser(note_json_path)
    if not os.path.isfile(note_json_path):
        raise FileNotFoundError(f"note.json 不存在：{note_json_path}")

    with open(note_json_path, "r", encoding="utf-8") as f:
        note = json.load(f)

    images = note.get("images", [])
    if not images:
        print("  笔记中没有图片，跳过 OCR。")
        return

    save_dir = os.path.dirname(note_json_path)
    total = len(images)

    check_env()
    print(f"  共 {total} 张图片，开始下载 + OCR...")

    for img in images:
        url = img.get("url", "")
        filename = img.get("filename", "")
        if not url or not filename:
            continue

        local_path = os.path.join(save_dir, filename)
        idx = img.get("index", "?")
        print(f"  [{idx}/{total}] {filename}", end=" ", flush=True)

        # 下载
        ok = download_image(url, local_path)
        if not ok:
            print("→ 下载失败，跳过")
            continue

        # OCR
        ocr_text = ocr_image(local_path)
        img["ocr_text"] = ocr_text
        preview = ocr_text[:40].replace("\n", " ") if ocr_text else "(空)"
        print(f"→ {preview}...")

    note["ocr_engine"] = "tesseract chi_sim+eng"

    # 写回 note.json
    with open(note_json_path, "w", encoding="utf-8") as f:
        json.dump(note, f, ensure_ascii=False, indent=2)

    print(f"  OCR 完成，已更新 {note_json_path}")


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="小红书图片下载 + OCR（Step 3）")
    parser.add_argument("note_json", help="note.json 路径")
    args = parser.parse_args()

    try:
        run(args.note_json)
    except Exception as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)
