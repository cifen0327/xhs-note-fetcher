"""
fetch_blogger.py — 模式 B：按博主昵称批量获取笔记列表

用法（CLI 调试用）：
    python scripts/fetch_blogger.py "<昵称>" --top 10
    python scripts/fetch_blogger.py "<昵称>" --xhs-id "95094050270" --top 20

主要导出（供 run.py 调用）：
    search_and_confirm(token, nickname, xhs_id) -> user_id
    fetch_top_notes(token, user_id, top_n)      -> list[dict]
        每项：{"note_id": str, "xsec_token": str, "title": str, "liked": int}

端点：
    搜索用户：web_v3/fetch_search_users（首选）→ app_v2/search_users（备用）
    笔记列表：app/get_user_notes（首选，含完整 desc/images_list/互动数）
              → web_v3/fetch_user_notes（备用，仅含元数据，需再调 fetch_note_detail）
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.common import load_tikhub_token, parse_count

TIKHUB_BASE = "https://api.tikhub.io"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


# ──────────────────────────────────────────────
# 通用 GET 请求
# ──────────────────────────────────────────────

def _get(token: str, path: str, params: dict) -> dict:
    """
    向 TikHub 发送 GET 请求。
    - 4xx（含 400）：直接抛出，不重试（确定性错误，重试无意义）
    - 网络异常 / 5xx：最多重试 2 次，间隔 2s / 4s
    - 401/402/403：直接抛出（认证 / 权限 / 余额错误）
    """
    import time

    query = urllib.parse.urlencode({k: v for k, v in params.items() if v != "" and v is not None})
    url = f"{TIKHUB_BASE}{path}?{query}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": BROWSER_UA,
    }

    max_attempts = 3
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))

        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise RuntimeError("TikHub Token 无效或已过期（401）")
            if e.code == 403:
                raise RuntimeError("TikHub Token 权限不足（403），请在控制台勾选全部小红书端点")
            if e.code == 402:
                raise RuntimeError("TikHub 账户余额不足（402），请登录控制台充值")
            # 4xx 确定性错误，不重试
            if 400 <= e.code < 500:
                raise RuntimeError(f"HTTP {e.code}：{e.reason}")
            # 5xx 可重试
            last_error = RuntimeError(f"HTTP {e.code}：{e.reason}")

        except Exception as e:
            last_error = e

        if attempt < max_attempts:
            wait = attempt * 2
            print(f"  ⚠️  第 {attempt} 次请求失败，{wait}s 后重试…")
            time.sleep(wait)

    raise RuntimeError(
        f"API 请求失败（已重试 2 次）：{last_error}\n"
        "可能是 TikHub 服务暂时不稳定，请稍后再试。"
    )


# ──────────────────────────────────────────────
# B2：搜索博主 + 身份核对
# ──────────────────────────────────────────────

def search_users(token: str, keyword: str) -> list[dict]:
    """
    搜索用户，返回候选列表。双端点降级：web_v3 优先，失败后切 app_v2。
    每项：{"user_id": str, "nickname": str, "xhs_id": str, "desc": str}

    端点 1（首选）：/api/v1/xiaohongshu/web_v3/fetch_search_users
      参数：keyword, page=1
      响应：data.data.users[] — userId/nickname/subTitle("小红书号：xxx")

    端点 2（备用）：/api/v1/xiaohongshu/app_v2/search_users
      参数：keyword, page=1, source=explore_feed
      响应：data.data.users[] — id/name/red_id/desc
    """
    endpoints = [
        {
            "path":   "/api/v1/xiaohongshu/web_v3/fetch_search_users",
            "params": {"keyword": keyword, "page": 1},
            "parse":  _parse_search_users_web_v3,
            "label":  "web_v3",
        },
        {
            "path":   "/api/v1/xiaohongshu/app_v2/search_users",
            "params": {"keyword": keyword, "page": 1, "source": "explore_feed"},
            "parse":  _parse_search_users_app_v2,
            "label":  "app_v2",
        },
    ]

    last_err = None
    all_errors: list[str] = []
    for ep in endpoints:
        try:
            resp = _get(token, ep["path"], ep["params"])
            code = resp.get("code", 200)
            if code not in (0, 200):
                raise RuntimeError(f"API 返回 code={code}：{resp.get('message', '')}")
            results = ep["parse"](resp)
            if results is not None:   # 空列表也算成功
                print(f"（{ep['label']}）", end=" ")
                return results
            raise RuntimeError("响应数据为空")
        except RuntimeError as e:
            last_err = e
            all_errors.append(str(e))
            print(f"  → {ep['label']} 失败（{e}），切换备用端点…")

    # 若所有端点均因 400 失败（端点暂不可用），给出友好提示让用户提供主页 URL
    if all_errors and all("HTTP 400" in e for e in all_errors):
        raise SearchEndpointDown()
    raise RuntimeError(f"所有端点均失败：{last_err}")


def _parse_search_users_web_v3(resp: dict) -> list[dict] | None:
    """解析 web_v3/fetch_search_users 响应。"""
    raw = ((resp.get("data") or {}).get("data") or {}).get("users") \
          or (resp.get("data") or {}).get("users")
    if raw is None:
        return None
    results = []
    for u in raw:
        user_id  = u.get("userId") or u.get("user_id", "")
        nickname = u.get("nickname") or u.get("name", "")
        sub = u.get("subTitle") or u.get("sub_title") or ""
        xhs_id = ""
        if "小红书号：" in sub:
            xhs_id = sub.split("小红书号：")[-1].strip()
        elif "小红书号:" in sub:
            xhs_id = sub.split("小红书号:")[-1].strip()
        if user_id:
            results.append({"user_id": user_id, "nickname": nickname,
                             "xhs_id": xhs_id, "desc": u.get("desc", "")})
    return results


def _parse_search_users_app_v2(resp: dict) -> list[dict] | None:
    """解析 app_v2/search_users 响应。"""
    raw = ((resp.get("data") or {}).get("data") or {}).get("users")
    if raw is None:
        return None
    results = []
    for u in raw:
        user_id = u.get("id", "")
        if user_id:
            results.append({
                "user_id":  user_id,
                "nickname": u.get("name", ""),
                "xhs_id":   u.get("red_id", ""),
                "desc":     u.get("desc", "") or u.get("sub_title", ""),
            })
    return results


def search_and_confirm(token: str, nickname: str, xhs_id: str = "") -> str:
    """
    搜索博主并核对身份，返回 user_id。

    核对规则：
      - 昵称完全相等（精确匹配）
      - 若用户提供了 xhs_id，还需核对 subTitle 中的小红书号
      - 找不到精确匹配 → 打印候选列表，要求调用方让用户确认后重新传入

    Returns:
        user_id (str)

    Raises:
        NeedUserConfirm: 包含候选列表，调用方需提示用户选择
        RuntimeError:    API 错误或无任何候选
    """
    print(f"\n  搜索博主「{nickname}」...", end=" ", flush=True)
    candidates = search_users(token, nickname)
    if not candidates:
        raise RuntimeError(f"搜索「{nickname}」无结果，请确认昵称是否正确")
    print(f"共 {len(candidates)} 个候选")

    # 昵称完全匹配
    exact = [u for u in candidates if u["nickname"] == nickname]

    # 若还提供了小红书号，进一步过滤
    if xhs_id and exact:
        exact_with_id = [u for u in exact if u["xhs_id"] == xhs_id]
        if exact_with_id:
            exact = exact_with_id
        else:
            # 昵称匹配但小红书号不符
            print(f"\n  ⚠️  昵称「{nickname}」匹配，但小红书号与候选不符（你输入：{xhs_id}）")
            exact = []   # 降级到展示候选

    if len(exact) == 1:
        u = exact[0]
        print(f"  ✓ 已定位：{u['nickname']}（小红书号：{u['xhs_id'] or '未知'}，user_id：{u['user_id']}）")
        return u["user_id"]

    # 需要用户进一步确认
    raise NeedUserConfirm(candidates)


class NeedUserConfirm(Exception):
    """携带候选列表，要求用户从中选择。"""
    def __init__(self, candidates: list[dict]):
        self.candidates = candidates
        lines = ["\n  未能精确匹配，请从以下候选中选择：\n"]
        for i, u in enumerate(candidates, 1):
            xhs = f"小红书号：{u['xhs_id']}" if u["xhs_id"] else ""
            lines.append(f"  {i}. {u['nickname']}  {xhs}  (user_id: {u['user_id']})")
        lines.append("\n  请告知序号或小红书号以继续。")
        super().__init__("\n".join(lines))


class SearchEndpointDown(Exception):
    """搜索端点（web_v3/app_v2）均返回 400，无法通过昵称定位博主。"""
    def __init__(self):
        super().__init__(
            "\n  目前状态：搜索接口（web_v3 和 app_v2）均返回 400，无法通过昵称定位博主。\n\n"
            "  请在小红书 App 里打开该博主的主页，把 URL 或分享链接发给我。\n"
            "  格式通常是：\n"
            "    https://www.xiaohongshu.com/user/profile/<user_id>\n"
            "    或 App 内分享出来的短链\n\n"
            "  拿到 user_id 后可以跳过搜索步骤，直接拉取他的笔记列表。"
        )


# ──────────────────────────────────────────────
# B3：拉取笔记列表 + 排序 + 截取 Top N
# ──────────────────────────────────────────────

def _fetch_notes_page(token: str, user_id: str, cursor: str = "") -> tuple[list[dict], str, bool]:
    """
    拉取一页用户笔记。双端点降级：app 优先，失败后切 web_v3。
    Returns: (notes_raw, next_cursor, has_more)

    端点 1（首选）：/api/v1/xiaohongshu/app/get_user_notes
      参数：user_id, cursor
      响应：data.data.notes[]，含完整 desc/images_list/互动数，可直接构建 note.json

    端点 2（备用）：/api/v1/xiaohongshu/web_v3/fetch_user_notes
      参数：user_id, cursor, num=20
      响应：data.data.notes[]，含 noteId/xsecToken/interactInfo.likedCount，
            需再调用 web_v3/fetch_note_detail 获取完整内容
    """
    endpoints = [
        {
            "path":   "/api/v1/xiaohongshu/app/get_user_notes",
            "params": {"user_id": user_id, **({"cursor": cursor} if cursor else {})},
            "label":  "app",
        },
        {
            "path":   "/api/v1/xiaohongshu/web_v3/fetch_user_notes",
            "params": {"user_id": user_id, "num": 20, **({"cursor": cursor} if cursor else {})},
            "label":  "web_v3",
        },
    ]

    last_err = None
    for ep in endpoints:
        try:
            resp = _get(token, ep["path"], ep["params"])
            code = resp.get("code", 200)
            if code not in (0, 200):
                raise RuntimeError(f"API 返回 code={code}：{resp.get('message', '')}")

            data      = (resp.get("data") or {}).get("data") or resp.get("data") or {}
            notes_raw = data.get("notes") or data.get("noteList") or data.get("items") or []
            # 优先取顶层 cursor；部分端点将游标放在最后一条 note 内作为兜底
            cursor_out = (data.get("cursor")
                          or (notes_raw[-1].get("cursor") if notes_raw else "")) or ""
            has_more   = bool(data.get("hasMore") or data.get("has_more"))
            return notes_raw, cursor_out, has_more

        except RuntimeError as e:
            last_err = e
            print(f"  → {ep['label']} 失败（{e}），切换备用端点…")

    raise RuntimeError(f"所有端点均失败：{last_err}")


def _parse_note_item(raw: dict) -> dict:
    """从列表项中提取 note_id / xsec_token / title / liked。

    兼容两类响应结构：
      web_v3：{ noteId, xsecToken, displayTitle, interactInfo.likedCount }
      app   ：{ note_id/id, xsec_token, note_card.{ display_title, interact_info.liked_count } }
    """
    # note_card 嵌套层（app 端点）
    nc = raw.get("note_card") or raw.get("noteCard") or {}

    note_id    = (raw.get("noteId") or raw.get("note_id")
                  or raw.get("id") or nc.get("noteId") or nc.get("note_id") or "")
    xsec_token = (raw.get("xsecToken") or raw.get("xsec_token")
                  or nc.get("xsecToken") or nc.get("xsec_token") or "")
    title      = (raw.get("title") or raw.get("displayTitle")
                  or nc.get("display_title") or nc.get("displayTitle") or nc.get("title") or "")

    # 点赞数可能在多处（含 note_card 嵌套）
    nc_interact = nc.get("interact_info") or nc.get("interactInfo") or {}
    liked_raw = (
        raw.get("likedCount")
        or raw.get("liked_count")
        or (raw.get("interactInfo") or {}).get("likedCount")
        or (raw.get("interact_info") or {}).get("liked_count")
        or nc_interact.get("likedCount")
        or nc_interact.get("liked_count")
        or "0"
    )
    liked = parse_count(str(liked_raw))
    return {"note_id": note_id, "xsec_token": xsec_token, "title": title, "liked": liked, "_raw": raw}


def fetch_top_notes(token: str, user_id: str, top_n: int) -> list[dict]:
    """
    分页拉取用户全量笔记，按点赞降序排序，返回 Top N（并列时扩展边界）。

    Returns:
        list[dict]，每项含 note_id / xsec_token / title / liked
    """
    print(f"\n  拉取用户笔记列表（user_id: {user_id}）...")
    all_notes = []
    cursor = ""
    page = 0
    while True:
        page += 1
        raw_list, cursor, has_more = _fetch_notes_page(token, user_id, cursor)
        parsed = [_parse_note_item(r) for r in raw_list
                  if r.get("noteId") or r.get("note_id") or r.get("id")]
        all_notes.extend(parsed)
        print(f"    第 {page} 页：{len(raw_list)} 条，累计 {len(all_notes)} 条", end="")
        if not has_more:
            print("  [已到末页]")
            break
        if not cursor:
            print("  ⚠️  has_more=True 但游标为空，停止分页避免无限循环")
            break
        print()
        # 如果已经有足够多的笔记（远超 top_n），可以提前停止分页
        # 但为保证排序准确，建议拉全量；当笔记数极多时可在此加上限
        if len(all_notes) >= max(top_n * 3, 200):
            print(f"    已超过 {max(top_n * 3, 200)} 条，停止分页（后续按点赞排序截取）")
            break

    total = len(all_notes)
    print(f"  共获取 {total} 条笔记")

    if total == 0:
        raise RuntimeError("未获取到任何笔记，请确认 user_id 正确且账号有公开笔记")

    # 按点赞降序排序
    all_notes.sort(key=lambda x: x["liked"], reverse=True)

    # 全量爬取场景
    if top_n >= total:
        print(f"  ℹ️  要求 Top {top_n}，但博主共 {total} 篇，已全部纳入")
        return all_notes

    # 截取 Top N，处理边界并列
    threshold = all_notes[top_n - 1]["liked"]
    selected = [n for n in all_notes if n["liked"] >= threshold]
    if len(selected) > top_n:
        print(
            f"  ℹ️  第 {top_n} 名与第 {top_n + 1} 名点赞数相同（均为 {threshold}），"
            f"实际纳入 {len(selected)} 篇"
        )
    else:
        print(f"  ✓ 已选取 Top {len(selected)} 篇（按点赞降序）")

    return selected


def build_note_json_from_raw(raw: dict) -> dict:
    """
    从 app/get_user_notes 列表项直接构建 note.json 结构。

    当 web_v3/fetch_note_detail 不可用时作为替代路径：
    列表接口已包含 desc、images_list、interact counts，无需再调用 detail 端点。

    Args:
        raw: app/get_user_notes 返回的单条笔记原始 dict

    Returns:
        与 fetch_note.py 输出兼容的 note_data dict
    """
    note_id = raw.get("note_id") or raw.get("id") or ""

    # 作者信息（app 端点在每条笔记中附带 user 字段）
    user      = raw.get("user") or {}
    author    = user.get("nickname", "") if isinstance(user, dict) else ""
    author_id = (user.get("userid") or user.get("user_id", "")) if isinstance(user, dict) else ""

    # 互动数：兼容顶层字段和 note_card.interact_info 嵌套两种布局
    nc    = raw.get("note_card") or raw.get("noteCard") or {}
    nc_ia = nc.get("interact_info") or nc.get("interactInfo") or {}

    def _pick(*keys_groups) -> int:
        """依次尝试多组字段（先顶层 raw，再 nc_ia），返回首个非 None 的整数值。"""
        for src, keys in keys_groups:
            for k in keys:
                v = src.get(k)
                if v is not None:
                    return parse_count(str(v))
        return 0

    liked     = _pick((raw,   ["liked_count",     "likedCount",     "likes"]),
                      (nc_ia, ["liked_count",     "likedCount"]))
    collected = _pick((raw,   ["collect_count",   "collectedCount", "collected_count"]),
                      (nc_ia, ["collected_count", "collectedCount"]))
    commented = _pick((raw,   ["comment_count",   "commentCount",   "comments_count"]),
                      (nc_ia, ["comment_count",   "commentCount"]))
    shared    = _pick((raw,   ["share_count",     "shareCount"]),
                      (nc_ia, ["share_count",     "shareCount"]))
    ratio     = round(collected / liked, 2) if liked else 0.0

    images = []
    for idx, img in enumerate(raw.get("images_list", []), 1):
        url = img.get("url_size_large") or img.get("url", "")
        images.append({
            "index":    idx,
            "filename": f"{idx:02d}.webp",
            "url":      url,
            "ocr_text": "",
        })

    return {
        "note_id":   note_id,
        "title":     (raw.get("display_title") or raw.get("title")
                      or nc.get("display_title") or nc.get("title", "")),
        "desc":      raw.get("desc", ""),
        "author":    author,
        "author_id": author_id,
        "interact": {
            "liked":              liked,
            "collected":          collected,
            "commented":          commented,
            "shared":             shared,
            "collect_like_ratio": ratio,
        },
        "images":          images,
        "raw_image_count": len(images),
        "ocr_engine":      "tesseract chi_sim+eng",
    }


# ──────────────────────────────────────────────
# CLI 入口（调试用）
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="按博主昵称批量获取笔记列表（模式 B 调试）")
    parser.add_argument("nickname", help="博主昵称")
    parser.add_argument("--xhs-id", default="", dest="xhs_id", help="小红书号（用于身份核对）")
    parser.add_argument("--top", type=int, default=10, help="获取前 N 篇（按点赞降序）")
    args = parser.parse_args()

    token = load_tikhub_token()
    if not token:
        print("错误：未找到 TikHub Token", file=sys.stderr)
        sys.exit(1)

    try:
        user_id = search_and_confirm(token, args.nickname, args.xhs_id)
        notes = fetch_top_notes(token, user_id, args.top)
        print(f"\n最终笔记列表（{len(notes)} 篇）：")
        for i, n in enumerate(notes, 1):
            print(f"  {i:>3}. [{n['liked']:>6} 赞] {n['title'][:30]}  note_id={n['note_id']}")
    except NeedUserConfirm as e:
        print(e)
        sys.exit(2)
    except Exception as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)
