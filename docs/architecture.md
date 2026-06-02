# 系统架构设计（Architecture）

> 阶段二：架构设计 — 初版完成于 2026-05-27
> 同步至现行实现 — 2026-06-02（视频流水线 → 图文流水线 + 邮件审核 + 反馈学习）
> 依赖：`docs/proposal.md`

---

## 演进说明

项目最初设计为「抓新闻 → 生成视频 → 微信公众号自动发布」的视频流水线。落地过程中根据真实约束做了两处重大调整，**本文档描述的是当前实际运行的架构**：

1. **改图文、停视频**：先把图文做稳。视频相关模块（`content_generator` / `voice_generator` / `video_synthesizer` / `publisher`）已从流水线移除，文件保留待图文成熟后再启用。
2. **改邮件审核、停自动发布**：本号是个人订阅号，无法认证、拿不到公众号发布 API。因此末端不自动发布，而是把成品**邮到手机供人工审核**，合格后到「订阅号助手」App 手动发。
3. **内容生成拆三步**：原单一「内容生成」拆成 `selector`（选题）→ `researcher`（深挖资料）→ `article_writer`（写作），各司其职。
4. **新增两个闭环**：`feedback`（阅读/评论数据回灌选题与写作）与 `balance_alert`（Claude 余额监控）。

---

## 整体架构

```
main.py（主编排器）
  │
  ├─ [M1] news_fetcher.py     新闻抓取（Tavily 主 / Brave 备）
  ├─ [M2] selector.py         选题（Claude 从候选挑最值得写的 1 条）
  ├─ [M3] researcher.py       资料深挖（Tavily 原文 + 多源交叉）
  ├─ [M4] article_writer.py   写作（Claude 出稿 → 全内联微信安全 HTML）
  ├─ [M5] image_generator.py  封面（Gemini 出无字背景 + PIL 叠中文）
  ├─ [M6] notifier.py         邮件推送成品供人工审核
  ├─ [M7] balance_alert.py    Claude API 余额监控
  └─ [M8] feedback.py         反馈学习（阅读/评论 → 经验 → 回灌 M2/M4）
```

执行顺序：**M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8（串行）**

任意模块失败：记录错误日志，跳过当前模块，继续执行后续模块，已产出文件保留。

---

## 目录结构

```
I:\AI\DailyTechFlow\
├─ main.py                  # 主编排器（串行调度 M1~M8）
├─ feedback_input.py        # 手动填某天阅读/评论/点赞/转发 → metrics.json
├─ config.yaml              # API 密钥与全局配置（不提交）
├─ requirements.txt
├─ docs\
│   ├─ proposal.md
│   ├─ architecture.md
│   └─ progress.md
├─ prompts\
│   └─ wechat_writer.md            # article_writer 的写作标准（system prompt）
├─ templates\
│   ├─ wechat_article.html         # 文章 HTML 模板（class 化，待内联）
│   └─ hyperframes_template.html   # 视频模板（已下线，保留）
├─ src\
│   ├─ news_fetcher.py
│   ├─ selector.py
│   ├─ researcher.py
│   ├─ article_writer.py
│   ├─ image_generator.py
│   ├─ wechat_inline.py            # class HTML → 微信安全全内联样式
│   ├─ notifier.py
│   ├─ balance_alert.py
│   ├─ feedback.py
│   ├─ content_generator.py        # ↓ 以下为已下线的视频链路，保留备用
│   ├─ voice_generator.py
│   └─ video_synthesizer.py
│   └─ publisher.py
├─ feedback\                       # 反馈学习产物（跨天，不提交）
│   ├─ history.jsonl               # 每篇文章的分数明细
│   └─ lessons.md                  # Claude 沉淀的经验，回灌 M2/M4
├─ output\
│   └─ YYYY-MM-DD\                 # 每日产物（自动创建）
│       ├─ news_raw.json           # M1：候选新闻（≤8 条）
│       ├─ pick.json               # M2：选中的 1 条 + 入选理由
│       ├─ research.md             # M3：原文全文 + 多源报道
│       ├─ wechat_article.html     # M4：成品文章（全内联）
│       ├─ _cover_bg.png           # M5：无字背景（中间产物）
│       ├─ cover.png               # M5：最终封面（背景 + 叠字）
│       ├─ metrics.json            # 人工填的阅读/评论/点赞/转发
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
| 输出 | `news_raw.json`（≤8 条，title/summary/url/source） |
| 工具 | Tavily Search（主，`topic=news`、近 3 天、advanced），Brave Search（备用） |
| 逻辑 | 搜索 → 去重（按 URL）→ 过滤栏目聚合页（`_is_article` 只留具体文章）→ 取前 8 条，交给 M2 选 |

放宽到 8 条是因为最终由 `selector` 挑 1 条，候选多一点选得更准。

---

### M2 — 选题（selector.py）

| 项目 | 内容 |
|------|------|
| 输入 | `news_raw.json`；近 7 天 `pick.json`（避免撞题）；`feedback/lessons.md`（历史经验） |
| 输出 | `pick.json`（选中新闻 + `reason` 入选理由） |
| 工具 | Anthropic Claude（`config.anthropic.model`） |
| 逻辑 | 让 Claude 当主编，按「爆款力 > 不重复 > 行业影响 > 数据」挑最值得写的 1 条 |

---

### M3 — 资料深挖（researcher.py）

| 项目 | 内容 |
|------|------|
| 输入 | `pick.json` |
| 输出 | `research.md`（原文全文 + 多源详细报道） |
| 工具 | Tavily Extract（原文）+ Tavily Search（多源交叉核对数据） |
| 逻辑 | 抓原文（付费墙可能失败）+ 按标题深搜多源聚合，凑齐可交叉核对的数字 |

---

### M4 — 写作（article_writer.py）

| 项目 | 内容 |
|------|------|
| 输入 | `research.md`；`prompts/wechat_writer.md`（写作标准）；`templates/wechat_article.html`；`feedback/lessons.md` |
| 输出 | `wechat_article.html`（全内联样式，可直接粘进微信保留排版） |
| 工具 | Anthropic Claude（`max_tokens=8000`，writer_guide 作 system prompt） |
| 逻辑 | Claude 按 `###KEY###` 分隔标记输出各字段 → 填模板 → `wechat_inline.inline()` 转微信安全 HTML |

**`wechat_inline.py`**：微信编辑器会删 `<style>`/class/CSS 变量/伪元素，且不认 flexbox。本模块用一份确定性的「class → 内联样式」表把样式写到每个元素 `style` 上，并把 flex 改写成块级堆叠。

---

### M5 — 封面生成（image_generator.py）

| 项目 | 内容 |
|------|------|
| 输入 | `wechat_article.html`（提取标题+正文） |
| 输出 | `cover.png`（1600×680，2.35:1 微信封面比例） |
| 工具 | Claude（提炼封面文案）+ Gemini `gemini-2.5-flash-image`（出无字背景）+ PIL/微软雅黑（叠中文） |

**为什么分两层**：图像模型画插画强，但直接渲染中文常出错别字、不可控。所以让 AI 只画**无字背景**，标题/分类/数据用 PIL + 雅黑精确叠上，零错字、完全可控。

---

### M6 — 邮件推送（notifier.py）

| 项目 | 内容 |
|------|------|
| 输入 | `wechat_article.html`、`cover.png` |
| 输出 | 一封邮件（正文轻量预览 + 文章 HTML 附件 + cover.png 附件） |
| 工具 | SMTP（Gmail，`config.email`） |
| 逻辑 | 个人订阅号无 API 发布权，故只推送供人工审核。邮箱未配置时优雅跳过 |

正文保持轻量纯文本（避免 Gmail 102KB 截断）；完整排版作附件，手机点开即用浏览器还原。

---

### M7 — 余额监控（balance_alert.py）

| 项目 | 内容 |
|------|------|
| 输入 | 无 |
| 输出 | 余额不足时发一封提醒邮件 |
| 工具 | Anthropic Claude（haiku 最小探活）+ SMTP |
| 逻辑 | 发一个 1-token 请求探活，命中余额/额度错误就邮件提醒去充值。未配置则跳过 |

---

### M8 — 反馈学习（feedback.py）

| 项目 | 内容 |
|------|------|
| 输入 | 近 N 天各天 `pick.json` + `metrics.json` |
| 输出 | `feedback/history.jsonl`（分数明细）、`feedback/lessons.md`（经验清单） |
| 工具 | Anthropic Claude（沉淀经验） |
| 逻辑 | 跨天聚合阅读/评论/点赞/转发 → 加权打分排名 → Claude 总结「什么样的选题和写法受欢迎」→ 回灌 M2/M4 提示词 |

- 数据来源可切换（`config.feedback.source`）：`manual`（手填，当前）/ `wechat`（自动拉，**休眠·未验证**）。
- 攒够 `min_articles`（默认 3）篇有数据的文章才开始沉淀经验。
- **跨目录例外**：本模块跨天读 `output/` 并写 `feedback/`，是学习系统的必要破例（已获准）。

---

## 配置文件（config.yaml 实际字段）

```yaml
tavily:    { api_key: "" }                       # M1 搜索 + M3 抓取
brave:     { api_key: "" }                       # M1 备用搜索
gemini:    { api_key: "", model: "..." }         # M5 背景图（gemini-2.5-flash-image）
anthropic: { api_key: "", model: "claude-..." }  # M2/M4/M5/M7/M8
email:                                           # M6 推送 + M7 告警
  smtp_host: "smtp.gmail.com"
  smtp_port: 587
  sender: ""
  password: ""          # Gmail 应用专用密码（非登录密码）
  recipient: ""
  alert_threshold: 5.00
wechat:    { app_id: "", app_secret: "", auto_publish: false }  # 仅 feedback=wechat 时用
feedback:
  source: "manual"      # manual / wechat（休眠）
  comment_weight: 50
  like_weight: 20
  share_weight: 100
  min_articles: 3
  lookback_days: 30
output_base: "I:/AI/DailyTechFlow/output"
schedule:  { time: "03:30" }
```

> 注：`huggingface` 字段是早期图片方案的历史遗留，现行代码已不再使用，可清理。

---

## 数据流总览

```
Tavily / Brave
    │
    ▼
news_raw.json ──► Claude(选题) ──► pick.json
                                      │
                                      ▼
                            Tavily(原文+多源) ──► research.md
                                                     │
                                                     ▼
                          Claude(写作) + wechat_inline ──► wechat_article.html
                                                              │
                                  ┌───────────────────────────┤
                                  ▼                           ▼
                    Claude+Gemini+PIL ──► cover.png      （邮件正文素材）
                                  │                           │
                                  └─────────────┬─────────────┘
                                                ▼
                                          SMTP 邮件 ──► 手机人工审核
                                                            │
                                              「订阅号助手」App 手动发布

      （发布后）metrics.json ──► feedback 聚合打分 ──► Claude ──► lessons.md
                                                                    │
                                                  回灌 selector / article_writer 提示词
```

---

## 模块间约定

- 每个模块仅读写 `output/YYYY-MM-DD/` 目录（`feedback` 模块例外，需跨天聚合）。
- 每个模块开始时检查依赖文件是否存在，不存在则抛出明确异常。
- 所有异常被 `main.py` 捕获，写入 `run.log`，不中断整体流程。
- 模块函数签名统一：`run(date_str: str, config: dict) -> bool`。
- 每个模块写完必须有对应单测且跑通（测试位于 `tests/`）。
