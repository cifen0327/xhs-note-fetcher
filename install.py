"""
install.py — xhs-note-fetcher 依赖安装脚本

用法：
    python3 install.py
"""

import subprocess
import sys


def run(cmd: list[str], desc: str):
    print(f"  → {desc}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ✗ 失败：{result.stderr.strip()}")
        return False
    print(f"  ✓ 完成")
    return True


def check_tesseract():
    result = subprocess.run(
        ["tesseract", "--list-langs"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return False, False
    has_chi = "chi_sim" in result.stdout + result.stderr
    return True, has_chi


def main():
    print("=" * 50)
    print("  xhs-note-fetcher 依赖安装")
    print("=" * 50)

    # 安装 Python 依赖
    print("\n[1/2] 安装 Python 依赖包")
    packages = ["pytesseract", "pillow", "python-docx", "requests"]
    ok = run(
        [sys.executable, "-m", "pip", "install"] + packages,
        f"pip install {' '.join(packages)}"
    )
    if not ok:
        print("\n  请手动运行：pip3 install pytesseract pillow python-docx requests")

    # 检查 Tesseract
    print("\n[2/2] 检查 Tesseract OCR")
    found, has_chi = check_tesseract()
    if not found:
        print("  ✗ 未检测到 tesseract，请安装：")
        print("      macOS:   brew install tesseract tesseract-lang")
        print("      Ubuntu:  sudo apt install tesseract-ocr tesseract-ocr-chi-sim")
        print("      Windows: https://github.com/UB-Mannheim/tesseract/wiki")
    elif not has_chi:
        print("  ⚠  tesseract 已安装，但缺少中文语言包（chi_sim）")
        print("      macOS:   brew install tesseract-lang")
        print("      Ubuntu:  sudo apt install tesseract-ocr-chi-sim")
    else:
        print("  ✓ tesseract 及中文语言包已就绪")

    # 提示 Token 配置
    print("\n[配置提醒] TikHub API Token")
    print("  本工具需要 TikHub Token 才能采集数据。")
    print("  注册地址：https://tikhub.io")
    print("  配置方式：")
    print('      mkdir -p ~/.xiaohongshu')
    print('      echo \'{"tikhub_api_token": "your_token_here"}\' > ~/.xiaohongshu/tikhub_config.json')

    print("\n" + "=" * 50)
    print("  安装完成！运行方式：")
    print("    python3 scripts/run.py --blogger          # 模式 B：按博主爬取")
    print('    python3 scripts/run.py "<笔记URL>"        # 模式 A：指定链接')
    print("=" * 50)


if __name__ == "__main__":
    main()
