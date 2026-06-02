# DailyTechFlow

每天凌晨 3:30 自动运行的科技新闻**图文**内容流水线。

抓科技新闻 → 选最值得写的 1 条 → 深挖资料 → 写成微信公众号文章 → 生成封面 → 邮件推送成品供人工审核。

> 注：项目早期为「生成视频 + 自动发布」设计，现已改为图文流水线 + 邮件审核（个人订阅号无 API 发布权）。视频相关模块文件保留但已下线。详见 `docs/architecture.md`。

---

## 环境要求

- Python 3.10+
- Windows（封面叠字使用系统自带的微软雅黑字体 `msyh.ttc` / `msyhbd.ttc`）

```bash
pip install -r requirements.txt
```

---

## 配置 API Key

编辑 `config.yaml`（已加入 `.gitignore`，不会被提交）：

```yaml
tavily:                              # M1 搜索 + M3 抓取原文
  api_key: "tvly-xxx"               # https://tavily.com

brave:                              # M1 备用搜索（可留空）
  api_key: ""

gemini:                             # M5 封面背景图（gemini-2.5-flash-image）
  api_key: "AIza-xxx"               # https://aistudio.google.com
  model: "gemini-2.5-flash"

anthropic:                          # M2 选题 / M4 写作 / M5 文案 / M7 探活 / M8 沉淀
  api_key: "sk-ant-xxx"             # https://console.anthropic.com
  model: "claude-sonnet-4-6"

email:                              # M6 推送成品 + M7 余额告警
  smtp_host: "smtp.gmail.com"
  smtp_port: 587
  sender: "you@gmail.com"
  password: "xxxx xxxx xxxx xxxx"   # Gmail 应用专用密码（需先开两步验证，非登录密码）
  recipient: "you@gmail.com"
  alert_threshold: 5.00

feedback:                           # M8 反馈学习
  source: "manual"                  # manual=手填数据；wechat=自动拉（休眠）
  comment_weight: 50
  like_weight: 20
  share_weight: 100
  min_articles: 3                   # 攒够几篇有数据才开始沉淀经验
  lookback_days: 30

output_base: "I:/AI/DailyTechFlow/output"
schedule:
  time: "03:30"
```

---

## 首次运行

```bash
# 手动执行今天的流程
python main.py

# 指定日期（补跑历史）
python main.py 2026-05-28
```

运行日志写入 `output/YYYY-MM-DD/run.log`，同时备份到 `logs/YYYY-MM-DD.log`。
任一模块失败会记录日志并跳过，不中断整体流程。

---

## 产物目录

每次运行在 `output/YYYY-MM-DD/` 下生成：

| 文件 | 来源模块 |
|------|----------|
| `news_raw.json` | M1 新闻抓取（候选 ≤8 条） |
| `pick.json` | M2 选题（选中 1 条 + 入选理由） |
| `research.md` | M3 资料深挖 |
| `wechat_article.html` | M4 写作（全内联，可直接粘进微信） |
| `cover.png` | M5 封面（1600×680，2.35:1） |
| `metrics.json` | 人工填的阅读/评论/点赞/转发 |
| `run.log` | 主编排器 |

反馈学习的跨天产物在 `feedback/`：`history.jsonl`（分数明细）、`lessons.md`（沉淀的经验，回灌选题与写作）。

---

## 审核与发布

个人订阅号无 API 发布权，流水线**不自动发布**。M6 把成品（文章 HTML + 封面）邮到你邮箱，审核合格后到「订阅号助手」App 手动发布。

发布后，用命令把后台数据填回来，喂给反馈学习：

```bash
python feedback_input.py <阅读> <评论> [日期] [--likes N] [--shares N]
# 例：python feedback_input.py 1500 8 --likes 30 --shares 5
```

---

## 自动调度

通过 `setup_scheduler.bat` 注册 Windows 任务计划，每天 03:30 自动运行（实际执行 `run_pipeline.bat`）。

查看或修改：**任务计划程序** → 找到 DailyTechFlow 相关任务。

---

## 运行测试

```bash
python -m pytest tests/ -v
```

---

## 模块说明

| 模块 | 文件 | 职责 |
|------|------|------|
| M1 | `src/news_fetcher.py` | Tavily / Brave 抓新闻，过滤聚合页，取候选 ≤8 条 |
| M2 | `src/selector.py` | Claude 从候选挑最值得写的 1 条（避开近期重题 + 参考历史经验） |
| M3 | `src/researcher.py` | Tavily 抓原文 + 多源交叉核对数据 |
| M4 | `src/article_writer.py` | Claude 出稿 → `wechat_inline` 转微信安全全内联 HTML |
| M5 | `src/image_generator.py` | Claude 提炼文案 + Gemini 出无字背景 + PIL 叠中文 |
| M6 | `src/notifier.py` | 邮件推送成品供人工审核 |
| M7 | `src/balance_alert.py` | Claude API 余额监控，不足则邮件提醒 |
| M8 | `src/feedback.py` | 阅读/评论数据打分 → 沉淀经验 → 回灌 M2/M4 |
| 编排 | `main.py` | 串行调度 M1~M8，记录日志 |
