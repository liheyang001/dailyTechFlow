# 系统架构设计（Architecture）

> 阶段二：架构设计 — 完成于 2026-05-27
> 依赖：`docs/proposal.md`

---

## 整体架构

```
main.py（主编排器）
  │
  ├─ [M1] news_fetcher.py        新闻抓取
  ├─ [M2] content_generator.py   内容生成（中英文文章 + 视频脚本）
  ├─ [M3] image_generator.py     封面图生成
  ├─ [M4] voice_generator.py     语音旁白生成
  ├─ [M5] video_synthesizer.py   视频合成
  └─ [M6] publisher.py           微信公众号发布
```

执行顺序：**M1 → M2 → M3 → M4 → M5 → M6（串行）**

任意模块失败：记录错误日志，跳过当前模块，继续执行后续模块，已产出文件保留。

---

## 目录结构

```
I:\AI\DailyTechFlow\
├─ main.py                  # 主编排器
├─ config.yaml              # API 密钥与全局配置
├─ requirements.txt
├─ docs\
│   ├─ proposal.md
│   ├─ architecture.md
│   └─ progress.md
├─ src\
│   ├─ news_fetcher.py
│   ├─ content_generator.py
│   ├─ image_generator.py
│   ├─ voice_generator.py
│   ├─ video_synthesizer.py
│   └─ publisher.py
├─ templates\
│   └─ hyperframes_template.html   # Hyperframes 视频模板
├─ output\
│   └─ YYYY-MM-DD\                 # 每日产物（自动创建）
│       ├─ news_raw.json
│       ├─ article_zh.md
│       ├─ article_en.md
│       ├─ script_zh.json          # 视频分镜脚本（中文）
│       ├─ script_en.json          # 视频分镜脚本（英文）
│       ├─ cover_zh.png
│       ├─ cover_en.png
│       ├─ voiceover_zh.mp3
│       ├─ voiceover_en.mp3
│       ├─ video_zh.mp4
│       ├─ video_en.mp4
│       └─ run.log                 # 当日运行日志
└─ logs\
    └─ YYYY-MM-DD.log              # 备份日志
```

---

## 模块详细设计

### M1 — 新闻抓取（news_fetcher.py）

| 项目 | 内容 |
|------|------|
| 输入 | 无（直接调用 API） |
| 输出 | `output/YYYY-MM-DD/news_raw.json` |
| 工具 | Tavily Search API（主），Brave Search API（备用） |
| 逻辑 | 搜索关键词 "tech news today"，去重，取前 3 条，保存标题+摘要+URL |

```json
// news_raw.json 结构
[
  { "title": "...", "summary": "...", "url": "...", "source": "..." },
  { "title": "...", "summary": "...", "url": "...", "source": "..." },
  { "title": "...", "summary": "...", "url": "...", "source": "..." }
]
```

---

### M2 — 内容生成（content_generator.py）

| 项目 | 内容 |
|------|------|
| 输入 | `news_raw.json` |
| 输出 | `article_zh.md`、`article_en.md`、`script_zh.json`、`script_en.json` |
| 工具 | Gemini API（gemini-2.0-flash，免费额度） |

**生成内容：**
1. 中文公众号文章（800~1000 字，含标题、正文、结尾引流）
2. 英文 X/Twitter 文章（300~500 字，适合社交媒体风格）
3. 中文视频分镜脚本（3 段，每段含旁白文本 + 画面描述）
4. 英文视频分镜脚本（同上）

```json
// script_zh.json 结构
[
  {
    "segment": 1,
    "headline": "新闻标题",
    "narration": "旁白文本（30~40字）",
    "visual_desc": "画面描述，用于 Hyperframes 动态文字"
  }
]
```

---

### M3 — 图片生成（image_generator.py）

| 项目 | 内容 |
|------|------|
| 输入 | `article_zh.md`（提取标题）、`article_en.md`（提取标题） |
| 输出 | `cover_zh.png`、`cover_en.png` |
| 工具 | GPT-Image-2 API |
| 规格 | 1280×720（16:9，视频封面兼用） |

提示词策略：科技风格，简洁，包含当日主题关键词，中英文封面分别生成。

---

### M4 — 语音生成（voice_generator.py）

| 项目 | 内容 |
|------|------|
| 输入 | `script_zh.json`、`script_en.json` |
| 输出 | `voiceover_zh.mp3`、`voiceover_en.mp3` |
| 工具 | Edge-TTS |
| 声音 | 中文：`zh-CN-XiaoxiaoNeural`，英文：`en-US-JennyNeural` |

将 3 段旁白文本拼接，生成完整语音文件，段落间插入 0.8s 停顿。

---

### M5 — 视频合成（video_synthesizer.py）

| 项目 | 内容 |
|------|------|
| 输入 | `script_zh.json` / `script_en.json`、`cover_zh.png` / `cover_en.png`、`voiceover_zh.mp3` / `voiceover_en.mp3` |
| 输出 | `video_zh.mp4`、`video_en.mp4` |
| 工具 | Hyperframes CLI |

**流程：**
1. 用 `script_*.json` 和封面图填充 `templates/hyperframes_template.html`，生成当日 HTML
2. 调用 `hyperframes render` 输出 MP4

**视频结构（每条视频）：**
```
[片头 5s]  节目名称动画（DailyTechFlow）
[新闻1 ~40s] 动态背景 + 标题 + 旁白
[新闻2 ~40s] 动态背景 + 标题 + 旁白
[新闻3 ~40s] 动态背景 + 标题 + 旁白
[片尾 10s]  引流信息 + 订阅提示
```

---

### M6 — 发布（publisher.py）

| 项目 | 内容 |
|------|------|
| 输入 | `article_zh.md`、`cover_zh.png` |
| 输出 | 微信公众号草稿或直接发布 |
| 工具 | 微信公众号 API（素材上传 + 草稿创建 + 发布） |

**步骤：**
1. 上传封面图，获取 `media_id`
2. 将 Markdown 转换为微信支持的富文本 HTML
3. 创建草稿（或直接群发）

---

## 配置文件（config.yaml）

```yaml
tavily:
  api_key: ""

brave:
  api_key: ""

gemini:
  api_key: ""
  model: "gemini-2.0-flash"

gpt_image:
  api_key: ""

wechat:
  app_id: ""
  app_secret: ""
  auto_publish: false   # true=直接群发，false=存为草稿

output_base: "I:/AI/DailyTechFlow/output"

schedule:
  time: "03:30"
```

---

## 数据流总览

```
Tavily/Brave
    │
    ▼
news_raw.json
    │
    ▼
Gemini API
    ├─► article_zh.md + script_zh.json
    └─► article_en.md + script_en.json
         │
         ▼
    GPT-Image-2
         ├─► cover_zh.png
         └─► cover_en.png
              │
              ▼
         Edge-TTS
              ├─► voiceover_zh.mp3
              └─► voiceover_en.mp3
                   │
                   ▼
              Hyperframes
                   ├─► video_zh.mp4
                   └─► video_en.mp4
                        │
                        ▼
                   WeChat API
                        └─► 公众号自动发布（中文）
```

---

## 模块间约定

- 每个模块仅读写 `output/YYYY-MM-DD/` 目录，不跨日期读取
- 每个模块开始时检查依赖文件是否存在，不存在则抛出明确异常
- 所有异常被 `main.py` 捕获，写入 `run.log`，不中断整体流程
- 模块函数签名统一：`run(date_str: str, config: dict) -> bool`
