---
name: xhs-note-fetcher
description: >
  Use when the user wants to fetch a Xiaohongshu (小红书) note via URL or note_id,
  download its images, run OCR on them, output a structured JSON, and generate
  a content analysis report (.docx) saved to the Desktop.
  Trigger on: "爬取笔记""下载小红书图片""OCR识别小红书图片""抓取笔记内容"
  "给我这篇笔记的文字""读取小红书链接""小红书笔记转文字""爬取+OCR"
  "生成分析报告""内容赛道分析""赛道分析报告"
  或用户粘贴小红书分享链接（含 xiaohongshu.com/explore/）时。
---

# 小红书笔记爬取 & OCR & 分析报告工具

两种输入模式，输出：

1. **结构化 JSON** — 标题、正文、互动数（含藏赞比）、图片 OCR 文字
2. **本地图片文件** — WebP 原图保存到本地
3. **内容分析报告 .docx** — 保存到桌面，含五大分析模块

| 模式 | 说明 | 触发方式 |
|------|------|---------|
| **A — 笔记链接** | 直接传入一条或多条笔记 URL | `python scripts/run.py "<url>"` |
| **B — 指定博主** | 按昵称搜索博主，按点赞排序爬取 Top N | `python scripts/run.py --blogger` |

核心理念：**脚本保下限，AI 冲上限。** 脚本负责数据采集和 OCR，AI 负责内容蒸馏和报告生成。

---

## 文件结构

```text
xhs-note-fetcher/
├── SKILL.md                       # 你现在看的这个文件
└── scripts/
    ├── run.py                     # 主入口：串联全流程（含模式 A/B 分支）
    ├── fetch_note.py              # Step 1+2：解析链接 + TikHub API → note.json
    ├── fetch_blogger.py           # 模式 B：搜索博主 + 拉取笔记列表（按点赞排序）
    ├── ocr_images.py              # Step 3：下载图片 + OCR → 更新 note.json
    ├── build_report.py            # Step 5：分析文字 → Word 报告
    ├── build_style_skill.py       # Step 6：写作风格文本 → 桌面 .md + Claude skill
    └── utils/
        ├── common.py              # 共用工具（parse_count / merge_lines / load_tikhub_token）
        ├── __init__.py
    └── __init__.py
```

---

## 前置要求

- Python 3.10+
- TikHub API Token（存于 `~/.xiaohongshu/tikhub_config.json` 或环境变量 `TIKHUB_API_TOKEN`）
- **不需要** Anthropic API Key — 分析由 Claude 在对话中直接完成
- 依赖包：`pip install pytesseract pillow python-docx`
- Tesseract 二进制：`brew install tesseract tesseract-lang`（需含 `chi_sim`）

---

## 执行流程

### Phase 0：环境检查

执行前验证以下三项，任一失败时先修复：

```bash
python3 -c "import pytesseract; pytesseract.get_tesseract_version()"
tesseract --list-langs | grep chi_sim
python3 -c "import docx"
```

Token 检查：
```bash
python3 -c "
import json, os
cfg = json.load(open(os.path.expanduser('~/.xiaohongshu/tikhub_config.json')))
print('TikHub Token OK:', cfg.get('tikhub_api_token','')[:8]+'...')
"
```

---

## ⛔ AI 执行铁律：用户确认节点（优先级高于一切）

**AI 在执行任何步骤前必须遵守以下规则，不得跳过、合并或自行推断。**

### 触发时 — 模式选择

询问用户：

```
请选择爬取方式：
  A — 直接粘贴笔记链接
  B — 指定博主昵称，按点赞排序批量爬取
```

---

### 模式 A 确认节点

| 节点 | AI 必须做的事 |
|------|-------------|
| 收到链接后 | 询问：**是否需要爬取图片并进行 OCR？**（是 / 否） |
| 开始爬取前 | 告知将爬取 N 篇，提示「最终生成一份报告和一个 Skill，不按来源分开；如需分开请分两次运行」，请用户确认 |

---

### 模式 B 确认节点

**每一步必须等用户回复后再执行下一步，不得连续执行。**

**B1. 信息收集后 — 搜索前确认**

收到昵称 / 小红书号 / 数量后，AI 复述并请确认：

```
即将搜索博主：
  昵称：XXX
  小红书号：XXX（或"未提供"）
  爬取数量：Top N
确认后开始搜索？
```

**B2. 搜索结果 — 账号确认**

- 唯一精确命中 → 展示昵称 + 小红书号，询问「确认是这个账号吗？」
- 多个同名 / 无精确匹配 / 小红书号不符 → 展示候选列表，请用户选择序号

等用户确认后再调用笔记列表接口。

**B3. 笔记列表就绪 — 预览确认**

展示：

```
已获取「XXX」笔记列表：
  共 M 篇，将爬取 Top N 篇（按点赞降序）
  Top 3 预览：
    1. [12000 赞] 标题一
    2. [8800 赞]  标题二
    3. [7200 赞]  标题三
（如第 N / N+1 名点赞并列，实际纳入 N+k 篇，此处说明）
```

**B4. 是否继续爬取其他博主**

```
是否继续爬取其他博主？（继续 / 不了）
```
继续 → 回到 B1；不了 → 进入 B5

**B5. 是否补充额外链接**

```
是否要额外补充其他笔记链接？（补充 / 不用）
```
补充 → 用户粘贴，逐行输入，空行结束；不用 → 进入 B6

**B6. 开始爬取前 — 最终确认**

汇总并告知：

```
即将开始爬取，请最终确认：
  总笔记数：N 篇
  来源：博主 A（M1 篇）[+ 博主 B（M2 篇）] [+ 手动链接（M3 条）]

  ⚠️  最终的分析报告和写作 Skill 是一份，不按博主分开。
      如需分别生成，请分两次运行本工具。

  是否爬取图片并进行 OCR？（是 / 否）

确认后开始爬取？
```

用户确认后方可调用脚本。

---

### Phase 1：一键运行（推荐）

#### 模式 A — 指定笔记链接

```bash
cd ~/.claude/skills/xhs-note-fetcher

# 单篇或多篇：爬取 + OCR（AI 随后在对话中生成报告）
python3 scripts/run.py "https://www.xiaohongshu.com/explore/<note_id>?xsec_token=<token>"
python3 scripts/run.py "<url1>" "<url2>" "<url3>"

# 跳过 OCR（笔记无图或已有缓存）
python3 scripts/run.py "<url>" --skip-ocr
```

#### 模式 B — 按博主批量爬取

```bash
cd ~/.claude/skills/xhs-note-fetcher
python3 scripts/run.py --blogger
```

脚本会交互式引导完成以下步骤：

**B1. 收集博主信息**
```
博主昵称（必填）：<输入昵称>
小红书号（选填，用于核对）：<输入或回车跳过>
爬取数量 Top N（必填）：<输入正整数>
```

**B2. 搜索 + 身份核对**

调用 `/api/v1/xiaohongshu/web_v3/fetch_search_users`：
- 昵称**完全相等**才算命中，直接继续
- 多个同名 / 无精确匹配 → 打印候选列表，用户输入序号选择
- 提供了小红书号但 subTitle 不符 → 同样降级为候选选择

**B3. 拉取笔记列表 + 排序**

调用 `/api/v1/xiaohongshu/web_v1/fetch_user_posted_notes` 分页拉取：
- 全量拉取后按点赞降序排序
- 截取 Top N，**第 N / N+1 点赞并列时全部纳入**并提示实际数量
- 要求数量 > 博主发文总量时，**全量爬取**并提示

**B4. 是否继续添加博主**
```
是否继续采集其他博主？（y/n）
```
选 `y` → 回到 B1 循环；所有博主的笔记汇入同一列表

**B5. 是否追加手动链接**
```
是否要额外加入其他笔记链接？（y/n）
是 → 逐行粘贴，空行结束
```

**B6. 统一爬取 → OCR → 报告**

汇总后调用 `fetch_note.py` + `ocr_images.py`，与模式 A 后续流程完全一致（混合出一份报告）。

---

### Phase 2：分步执行

#### Step 1+2：爬取笔记数据

```bash
python3 scripts/fetch_note.py "<url>"
# 端点：web_v3/fetch_note_detail
# 响应路径：data.data.items[0].noteCard
# 输出：~/Downloads/xhs_<note_id>/note.json
```

`note.json` 结构：
```json
{
  "note_id": "...",
  "title": "...",
  "desc": "...",
  "author": "...",
  "interact": {
    "liked": 20000,
    "collected": 7372,
    "commented": 71,
    "shared": 369,
    "collect_like_ratio": 0.37
  },
  "images": [
    { "index": 1, "filename": "01.webp", "url": "...", "ocr_text": "" }
  ]
}
```

#### Step 3：下载图片 + OCR

```bash
python3 scripts/ocr_images.py ~/Downloads/xhs_<note_id>/note.json
# 下载 *.webp 到同级目录，将 ocr_text 写回 note.json
```

OCR 说明：
- Pillow 内存转 RGB（**不保存 PNG**，节省磁盘）
- `tesseract chi_sim+eng` 双语识别
- `merge_lines()` 合并图片列宽导致的断行

#### Step 5：生成分析报告

Step 5 由 **Claude 在对话中** 完成，不调用任何外部 AI API：

1. Claude 读取所有 `note.json` 文件，在对话中直接生成五模块分析文字
2. Claude 将分析文字写入临时文件（如 `/tmp/analysis.txt`），格式如下：

```
==模块1==
内容品类：...
核心情绪钩子：...
目标读者画像：
  - 年龄/身份：...
  - 核心诉求/焦虑：...
  - 认知水平与信息偏好：...
  - 内容消费场景（何时刷、为何收藏）：...
藏赞比均值：...

==模块2==
标题模式：...
开头模式：...
正文结构：...
结尾CTA：...
受众适配观察：（结构选择如何服务于目标读者的阅读习惯和认知节奏）...

==模块3==
核心价值主张：...
信息不对称点：...
受众心理假设：...
口吻与立场：（账号以何种身份感与读者对话，措辞风格如何匹配受众认知层次）...

==模块4==
篇目 | 作者 | 点赞 | 收藏 | 评论 | 分享 | 藏赞比
笔记标题 | 作者名 | 8000 | 2400 | 120 | 300 | 0.30
...
爆款原因分析：...

==模块5==
已验证选题：...
- 方向1
...
```

3. 运行脚本写入 Word：
```bash
python3 scripts/build_report.py --analysis /tmp/analysis.txt \
    --account-name "<ai-generated-name>" \
    ~/Downloads/xhs_<id1>/note.json ~/Downloads/xhs_<id2>/note.json ...
# 输出：~/Desktop/赛道分析_<account-name>_YYYYMMDD_HHMM.docx
# --account-name 与 Step 6 的 --skill-name 保持一致，方便桌面文件对应
```

也可省略 `--analysis` 仅生成互动数据底稿：
```bash
python3 scripts/build_report.py --account-name "<ai-generated-name>" \
    ~/Downloads/xhs_<note_id>/note.json
```

#### Step 6：生成写作风格 Skill

Step 6 由 **Claude 在对话中** 完成，紧接 Step 5 之后：

1. Claude 根据五模块分析内容，生成写作风格文本，格式为完整 SKILL.md（含 frontmatter）：

```markdown
---
name: xhs-style-账号名
description: >
  模仿「账号名」小红书写作风格生成笔记。触发词：
  "用XX风格写""模仿这个账号写""仿写""写一篇类似的"。
---

# 写作风格模板库：账号名

## 账号定位
...（从模块1提炼：品类、情绪钩子、目标读者）

## 受众画像与适配规则
目标读者：...（年龄/身份/核心焦虑）
内容适配原则：
  - 案例选取：优先使用读者亲历场景（校园/职场/关系），避免距离感过远的案例
  - 概念密度：根据读者认知层次调整（大学生受众需更多类比降门槛；职场受众可直接给框架）
  - 口吻：...（陪伴者/过来人/平等对话/专业权威——选其一说明）
  - 禁忌：不使用的表达方式或容易造成距离感的用词

## 标题公式
...（从模块2提炼）

## 开头模板
...

## 正文结构
...（含：分点逻辑、案例使用方式、语言风格特征）

## 结尾 CTA
...

## 核心观点库
...（从模块3提炼）

## 受众适配示例
同一主题，面向不同受众时的调整示例：
- 原始角度：...
- 调整为[受众A]时：案例换成___，口吻改为___，概念降/升维到___
- 调整为[受众B]时：...

## 示例 Prompt
用户说"帮我用这个风格写一篇关于X的笔记"时，按以下格式输出：
1. 确认目标读者（与账号默认受众一致，或用户指定调整）
2. 按受众适配规则选取案例和调整口吻
3. 套用标题/开头/正文/结尾模板输出
...
```

2. Claude 自动决定 skill 名称（如 `xhs-style-自我提升`），写在 frontmatter 的 `name:` 字段中
3. Claude 将完整风格文本写入 `/tmp/style_guide.txt`
4. 运行脚本写入两个目标：

```bash
python3 scripts/build_style_skill.py \
    --style /tmp/style_guide.txt \
    --skill-name "<name-from-frontmatter>" \
    ~/Downloads/xhs_<id1>/note.json ~/Downloads/xhs_<id2>/note.json ...
# 输出：
#   ~/Desktop/写作风格_<skill-name>_YYYYMMDD_HHMM.md  ← 桌面参考版
#   ~/.claude/skills/<skill-name>/SKILL.md             ← 可直接被 Claude 调用
```

5. Claude 向用户报告实际生成的 skill 名称和路径

---

## 报告五模块说明

| 模块 | 内容 |
|------|------|
| **模块1 赛道定位卡** | 品类、核心情绪钩子、目标读者画像（年龄/身份/焦虑/消费场景）、藏赞比均值 |
| **模块2 结构共性** | 标题/开头/正文/结尾 CTA 的可复用模式 + 结构选择如何服务目标读者 |
| **模块3 观点共性** | 价值主张、信息不对称点、受众心理假设、账号与读者的对话口吻与立场 |
| **模块4 互动数据面板** | 横向对比表格（点赞/收藏/评论/分享/藏赞比）+ 爆款原因分析 |
| **模块5 选题矩阵** | 已验证选题 + 10 个可延伸方向 |

多篇笔记时，**所有数据汇总后一次调用 AI**（节省 token，且模块2-3的共性分析需要多篇对比）。

---

## 输出目录结构

```text
~/Downloads/xhs_<note_id>/
  note.json        ← 结构化数据（含藏赞比 + OCR 文字）
  01.webp          ← 原始图片
  02.webp
  ...

~/Desktop/
  赛道分析_<account-name>_YYYYMMDD_HHMM.docx  ← 五模块分析报告（与 skill 同名）
  写作风格_xhs-style-<account-name>_YYYYMMDD_HHMM.md ← 写作风格参考版

~/.claude/skills/xhs-style-<account-name>/
  SKILL.md                               ← 写作风格 Skill（可被 Claude 直接调用）
```

---

## 常见错误处理

| 错误 | 原因 | 解法 |
|------|------|------|
| `API 请求失败（已重试 2 次）` | TikHub 服务暂时不稳定 | 稍后再试；若持续失败请检查 TikHub 服务状态 |
| `401 Unauthorized` | TikHub Token 失效 | 更新 `~/.xiaohongshu/tikhub_config.json` |
| `402 余额不足` | TikHub 账户余额耗尽 | 登录 tikhub.io 控制台充值 |
| `403 Forbidden` | TikHub 端点权限未开通 | 登录 tikhub.io 控制台，勾选全部小红书端点 |
| 搜索端点返回 400（`SearchEndpointDown`）| `web_v3/fetch_search_users` 和 `app_v2/search_users` 均不可用 | 脚本/AI 会提示用户在小红书 App 打开博主主页，复制 URL（格式：`xiaohongshu.com/user/profile/<user_id>`），粘贴后自动解析 user_id，跳过搜索步骤直接拉取笔记列表 |
| `web_v3/fetch_note_detail` 返回 400/422 | detail 端点不可用或缺少 xsec_token | 模式 B 已自动降级：优先用 `app/get_user_notes`（列表数据含完整 desc/images/互动数），直接用 `build_note_json_from_raw()` 构建 note.json；若 app 端点也不可用则回退到 `web_v3/fetch_user_notes` + `web_v3/fetch_note_detail` |
| `TesseractNotFoundError` | tesseract 未安装 | `brew install tesseract tesseract-lang` |
| `ModuleNotFoundError: pytesseract` | 依赖缺失 | `pip3 install pytesseract pillow` |
| `ModuleNotFoundError: docx` | 依赖缺失 | `pip3 install python-docx` |
| 图片下载 403 | CDN 防盗链 | `ocr_images.py` 已加 `Referer` 头，自动重试 3 次 |
| 报告缺少分隔符 | 分析文件格式不符 | 确认 `==模块N==` 分隔符格式正确后重跑 |

---

## 注意事项

- 互动数字段在 API 中是**字符串**（`"8857"`），`fetch_note.py` 中的 `parse_count()` 已统一转整数
- 藏赞比 = 收藏 ÷ 点赞，> 0.3 通常代表高实用价值干货
- CDN 图片链接有有效期，下载需在爬取后**立即执行**
- `xsec_token` 来自分享链接的查询参数，建议始终传入以提高成功率
