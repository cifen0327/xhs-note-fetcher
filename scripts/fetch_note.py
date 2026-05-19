"""
fetch_note.py — Step 1+2：解析小红书链接，调用 TikHub API，输出 note.json

用法：
    python scripts/fetch_note.py <url_or_note_id> [-o <output_dir>] [--xsec-token <token>]

端点：web_v3/fetch_note_detail → data.data.items[0].noteCard
    端点返回空数据时，停止执行并报告错误。

输出：
    <output_dir>/xhs_<note_id>/note.json
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.common import parse_count, load_tikhub_token

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

TIKHUB_BASE = "https://api.tikhub.io"
ENDPOINT_V3 = "/api/v1/xiaohongshu/web_v3/fetch_note_detail"


# ──────────────────────────────────────────────
# 链接解析
# ──────────────────────────────────────────────

def parse_xhs_url(raw: str) -> tuple[str, str]:
    """
    从小红书分享链接或裸 note_id 中提取 (note_id, xsec_token)。

    支持格式：
      https://www.xiaohongshu.com/explore/<note_id>?xsec_token=<token>
      https://www.xiaohongshu.com/discovery/item/<note_id>?xsec_token=<token>
      <note_id>（纯 ID，不含 http）
    """
    raw = raw.strip()
    if raw.startswith("http"):
        parsed = urllib.parse.urlparse(raw)
        note_id = parsed.path.rstrip("/").split("/")[-1]
        xsec_token = urllib.parse.parse_qs(parsed.query).get("xsec_token", [""])[0]
    else:
        note_id = raw
        xsec_token = ""
    return note_id, xsec_token


# ──────────────────────────────────────────────
# TikHub 通用 GET 请求
# ──────────────────────────────────────────────

def _call_api(token: str, path: str, params: dict) -> dict:
    """
    向 TikHub 发送 GET 请求，返回解析后的 JSON。
    遇到可重试错误（网络异常、5xx）最多重试 2 次；
    401/403/402 等认证错误直接报错，不重试。
    """
    import time

    query = urllib.parse.urlencode({k: v for k, v in params.items() if v})
    url = f"{TIKHUB_BASE}{path}?{query}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": BROWSER_UA,
    }

    max_attempts = 3   # 首次 + 重试 2 次
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))

        except urllib.error.HTTPError as e:
            # 认证 / 权限错误不重试，直接抛出
            if e.code == 401:
                raise RuntimeError("TikHub Token 无效或已过期（401）")
            if e.code == 403:
                raise RuntimeError("TikHub Token 权限不足（403），请在控制台确认已开通小红书端点")
            if e.code == 402:
                raise RuntimeError("TikHub 账户余额不足（402），请登录控制台充值")
            last_error = RuntimeError(f"HTTP {e.code}：{e.reason}")

        except Exception as e:
            last_error = e

        if attempt < max_attempts:
            wait = attempt * 2   # 2s, 4s
            print(f"  ⚠️  第 {attempt} 次请求失败，{wait}s 后重试…")
            time.sleep(wait)

    raise RuntimeError(
        f"API 请求失败（已重试 2 次）：{last_error}\n"
        "可能是 TikHub 服务暂时不稳定，请稍后再试。"
    )


# ──────────────────────────────────────────────
# 各端点的字段提取
# ──────────────────────────────────────────────

def _extract_web_v3(api_resp: dict, fallback_note_id: str = "") -> dict | None:
    """
    提取 web_v3/fetch_note_detail 响应。
    路径：data.data.items[0].noteCard
    返回结构化 dict；数据为空时返回 None。
    """
    try:
        note = api_resp["data"]["data"]["items"][0]["noteCard"]
    except (KeyError, IndexError, TypeError):
        return None

    user = note.get("user", {})
    interact = note.get("interactInfo", {})

    # 空数据检测
    if not (note.get("title") or note.get("desc") or
            (isinstance(user, dict) and user.get("nickname")) or
            note.get("imageList")):
        return None

    liked     = parse_count(str(interact.get("likedCount",     "0") or "0"))
    collected = parse_count(str(interact.get("collectedCount", "0") or "0"))
    commented = parse_count(str(interact.get("commentCount",   "0") or "0"))
    shared    = parse_count(str(interact.get("shareCount",     "0") or "0"))

    images = []
    for i, img in enumerate(note.get("imageList", [])):
        url = img.get("urlDefault") or img.get("url", "")
        if url:
            images.append({
                "index": i + 1,
                "url": url,
                "filename": f"{i + 1:02d}.webp",
                "ocr_text": "",
            })

    tags = [t.get("name", "") for t in note.get("tagList", []) if t.get("name")]
    note_id = note.get("noteId") or fallback_note_id

    return _build_result(note_id, note.get("title", ""), note.get("desc", ""),
                         user, tags, liked, collected, commented, shared, images)


def _build_result(note_id, title, desc, user, tags,
                  liked, collected, commented, shared, images) -> dict:
    """组装统一格式的 note_data dict。"""
    collect_like_ratio = round(collected / liked, 2) if liked > 0 else 0.0
    author    = user.get("nickname", "") if isinstance(user, dict) else ""
    author_id = (user.get("userId") or user.get("userid", "")) if isinstance(user, dict) else ""
    return {
        "note_id":   note_id,
        "title":     title,
        "desc":      desc,
        "author":    author,
        "author_id": author_id,
        "tags":      tags,
        "interact": {
            "liked":              liked,
            "collected":          collected,
            "commented":          commented,
            "shared":             shared,
            "collect_like_ratio": collect_like_ratio,
        },
        "images":          images,
        "raw_image_count": len(images),
        "ocr_engine":      "tesseract chi_sim+eng",
    }


# ──────────────────────────────────────────────
# 笔记详情端点调用
# ──────────────────────────────────────────────

def fetch_note_detail(token: str, note_id: str,
                      xsec_token: str = "", original_url: str = "") -> dict:
    """
    调用 web_v3/fetch_note_detail 端点，返回结构化 note_data。
    数据为空时抛出 RuntimeError。
    """
    params = {"note_id": note_id}
    if xsec_token:
        params["xsec_token"] = xsec_token

    print(f"  尝试端点：web_v3/fetch_note_detail ...", end=" ", flush=True)
    try:
        resp = _call_api(token, ENDPOINT_V3, params)
        code = resp.get("code", 200)
        if code not in (0, 200):
            msg = f"API 返回错误码 {code}：{resp.get('message', '')}"
            print(f"× {msg}")
            raise RuntimeError(msg)

        note_data = _extract_web_v3(resp, fallback_note_id=note_id)
        if note_data is None:
            print("× 返回数据为空")
            raise RuntimeError(
                "端点返回数据为空（title/desc/author/images 均空）\n"
                "可能原因：xsec_token 失效、笔记已删除、TikHub 节点暂时不可用。"
            )

        print("✓")
        return note_data

    except RuntimeError:
        raise
    except Exception as e:
        print(f"× {e}")
        raise RuntimeError(f"请求失败：{e}")


# ──────────────────────────────────────────────
# 主函数
# ──────────────────────────────────────────────

def run(url_or_id: str, xsec_token_override: str = "", output_dir: str = "") -> str:
    """
    完整执行 Step 1+2：解析链接 → 调 API → 写 note.json。

    Returns:
        note.json 的绝对路径
    """
    note_id, xsec_token = parse_xhs_url(url_or_id)
    if xsec_token_override:
        xsec_token = xsec_token_override
    if not note_id:
        raise ValueError(f"无法从输入中提取 note_id：{url_or_id!r}")

    original_url = url_or_id.strip() if url_or_id.startswith("http") else ""

    print(f"  note_id    : {note_id}")
    print(f"  xsec_token : {xsec_token[:20]}..." if xsec_token else "  xsec_token : (无)")

    token = load_tikhub_token()
    if not token:
        raise RuntimeError(
            "未找到 TikHub API Token。\n"
            "请设置环境变量 TIKHUB_API_TOKEN，\n"
            "或确保 ~/.xiaohongshu/tikhub_config.json 存在且含有效 token。"
        )

    note_data = fetch_note_detail(token, note_id, xsec_token, original_url)

    if not output_dir:
        output_dir = os.path.expanduser(f"~/Downloads/xhs_{note_data['note_id']}")
    os.makedirs(output_dir, exist_ok=True)

    out_path = os.path.join(output_dir, "note.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(note_data, f, ensure_ascii=False, indent=2)

    print(f"  已写入 {out_path}")
    print(f"  标题：{note_data['title']}")
    print(f"  图片：{note_data['raw_image_count']} 张")
    print(f"  互动：点赞 {note_data['interact']['liked']}，"
          f"收藏 {note_data['interact']['collected']}，"
          f"藏赞比 {note_data['interact']['collect_like_ratio']}")

    return out_path


# ──────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="小红书笔记爬取（Step 1+2）")
    parser.add_argument("url", help="小红书笔记链接或 note_id")
    parser.add_argument("-o", "--output", default="", help="输出目录（默认 ~/Downloads/xhs_<note_id>/）")
    parser.add_argument("--xsec-token", default="", dest="xsec_token", help="xsec_token（链接已包含时可省略）")
    args = parser.parse_args()

    try:
        run(args.url, xsec_token_override=args.xsec_token, output_dir=args.output)
    except Exception as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)
