# xhs-note-fetcher

![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)
![License: MIT](https://img.shields.io/badge/License-MIT-green)
![Claude Code Skill](https://img.shields.io/badge/Claude%20Code-Skill-orange)

**中文** | [English](#english)

> ⚠️ **免责声明 / Disclaimer**：本工具仅供个人学习研究使用，严禁用于商业用途或任何侵权行为。使用前请阅读 [DISCLAIMER.md](./DISCLAIMER.md)。

---

## 功能简介

一个面向 Claude Code 的小红书内容研究工具，输入博主主页或笔记链接，自动完成：

- **笔记数据采集** — 标题、正文、互动数（点赞 / 收藏 / 评论 / 分享 / 藏赞比）
- **图片 OCR 识别** — 下载封面图文，提取图片内文字
- **内容分析报告** — 五模块分析（赛道定位 / 结构共性 / 观点共性 / 数据面板 / 选题矩阵），输出 `.docx` 到桌面
- **写作风格 Skill** — 自动生成可被 Claude 直接调用的仿写 Skill

两种使用模式：

| 模式 | 说明 |
|------|------|
| **A — 笔记链接** | 直接传入一条或多条笔记 URL |
| **B — 指定博主** | 输入博主昵称，按点赞排序爬取 Top N 篇 |

---

## 快速上手

### 1. 安装依赖

```bash
python3 install.py
```

需要提前安装 Tesseract：

```bash
brew install tesseract tesseract-lang   # macOS
```

### 2. 配置 TikHub Token

本工具通过 [TikHub API](https://tikhub.io) 采集数据，需要注册并获取 Token。

```bash
mkdir -p ~/.xiaohongshu
cat > ~/.xiaohongshu/tikhub_config.json << 'EOF'
{"tikhub_api_token": "your_token_here"}
EOF
```

> TikHub 提供免费额度，部分端点需付费。每次笔记采集约消耗 $0.001–$0.003。

### 3. 运行

```bash
cd ~/.claude/skills/xhs-note-fetcher

# 模式 A：指定笔记链接
python3 scripts/run.py "https://www.xiaohongshu.com/explore/<note_id>?xsec_token=<token>"

# 模式 B：按博主批量爬取（交互式）
python3 scripts/run.py --blogger
```

---

## 与 Claude Code 集成

本工具以 Claude Code Skill 形式设计，可在 Claude Code 对话中直接调用：

1. 将仓库克隆到 `~/.claude/skills/xhs-note-fetcher`
2. 在 Claude Code 中说：**「爬取博主 XXX 的 Top5 笔记」**，Claude 会自动识别并启动本 Skill
3. 数据采集由脚本完成，分析报告由 Claude 在对话中直接生成，无需额外 API Key

---

## 端点降级策略

TikHub 各端点可用性随时变化，本工具内置自动降级：

| 功能 | 首选端点 | 备用端点 |
|------|---------|---------|
| 搜索博主 | `web_v3/fetch_search_users` | `app_v2/search_users` |
| 笔记列表 | `app/get_user_notes`（含完整数据） | `web_v3/fetch_user_notes` |
| 笔记详情 | 由列表数据直接构建（app 路径） | `web_v3/fetch_note_detail` |

若搜索端点全部不可用，工具会提示你粘贴博主主页 URL（`xiaohongshu.com/user/profile/<user_id>`）手动指定博主。

---

## 项目结构

```text
xhs-note-fetcher/
├── SKILL.md                  # Claude Code Skill 入口
├── README.md
├── DISCLAIMER.md             # 免责声明
├── LICENSE                   # MIT
├── install.py                # 一键安装依赖
└── scripts/
    ├── run.py                # 主入口（模式 A/B）
    ├── fetch_note.py         # 笔记详情采集
    ├── fetch_blogger.py      # 博主搜索 + 笔记列表
    ├── ocr_images.py         # 图片下载 + OCR
    ├── build_report.py       # 生成 Word 分析报告
    ├── build_style_skill.py  # 生成写作风格 Skill
    └── utils/
        └── common.py         # 公共工具函数
```

---

## 输出文件

```text
~/Downloads/xhs_<note_id>/
  note.json        ← 结构化数据（含互动数 + OCR 文字）
  01.webp ~ N.webp ← 原始图片

~/Desktop/
  赛道分析_<账号名>_YYYYMMDD_HHMM.docx   ← 五模块分析报告
  写作风格_<skill-name>_YYYYMMDD_HHMM.md  ← 写作风格参考版

~/.claude/skills/xhs-style-<账号名>/
  SKILL.md                                ← 可被 Claude 直接调用的仿写 Skill
```

---

## License

MIT © 磁粉

---

<a name="english"></a>

## English

### What it does

A Claude Code Skill for Xiaohongshu (RedNote) content research. Given a blogger's profile URL or note links, it automatically:

- Fetches note data (title, body, engagement metrics: likes / collects / comments / shares / collect-like ratio)
- Downloads images and runs OCR to extract text
- Generates a 5-module analysis report (`.docx`) via Claude
- Produces a writing-style Skill that Claude can use for imitation writing

### Quick Start

```bash
# Install dependencies
python3 install.py

# macOS: install Tesseract
brew install tesseract tesseract-lang

# Configure TikHub Token
mkdir -p ~/.xiaohongshu
echo '{"tikhub_api_token": "your_token_here"}' > ~/.xiaohongshu/tikhub_config.json

# Run — Mode A: specific note URL
python3 scripts/run.py "https://www.xiaohongshu.com/explore/<note_id>?xsec_token=<token>"

# Run — Mode B: fetch top N notes from a blogger (interactive)
python3 scripts/run.py --blogger
```

### Claude Code Integration

Clone to `~/.claude/skills/xhs-note-fetcher`, then just tell Claude:
> "Fetch the Top 5 notes from blogger XXX"

Claude will automatically invoke this Skill. Data collection is handled by scripts; analysis is done by Claude directly in the conversation — no extra API key needed.

### Disclaimer

This tool is for **personal research only**. Do not use it for commercial purposes or any activity that infringes on others' rights. See [DISCLAIMER.md](./DISCLAIMER.md) for full details.

### License

MIT © 磁粉
