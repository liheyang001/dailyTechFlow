# 任务进度追踪（Progress）

> 阶段三：任务拆解 — 初版完成于 2026-05-27
> 同步至现行实现 — 2026-06-02
> 依赖：`docs/architecture.md`

---

## 整体进度

现行**图文流水线**（M1~M8）已全部实现并有对应单测，`pytest` 全绿（137 passed）。
视频链路（content/voice/video/publisher）已下线、文件保留，不计入当前进度。

- [x] M0 项目脚手架
- [x] M1 新闻抓取（news_fetcher）
- [x] M2 选题（selector）
- [x] M3 资料深挖（researcher）
- [x] M4 写作（article_writer）+ 微信内联（wechat_inline）
- [x] M5 封面生成（image_generator）
- [x] M6 邮件推送（notifier）
- [x] M7 余额监控（balance_alert）
- [x] M8 反馈学习（feedback）+ 手动填数（feedback_input）
- [x] 主编排器（main.py）+ 任务调度（Windows 计划任务）

---

## M1 — 新闻抓取（src/news_fetcher.py）

- [x] `run(date_str, config) -> bool`
- [x] Tavily Search（`topic=news`、近 3 天、advanced），失败回退 Brave
- [x] 去重（按 URL）+ 过滤栏目聚合页（`_is_article`），取前 8 条
- [x] 序列化 `news_raw.json`（title/summary/url/source）
- [x] 单测 `tests/test_news_fetcher.py`

## M2 — 选题（src/selector.py）

- [x] `run(date_str, config) -> bool`，读 `news_raw.json`
- [x] 注入近 7 天 `pick.json`（避免撞题）与 `feedback/lessons.md`（历史经验）
- [x] Claude 按「爆款力 > 不重复 > 行业影响 > 数据」挑 1 条，越界回退第 1 条
- [x] 输出 `pick.json`（选中新闻 + 入选理由）
- [x] 单测 `tests/test_*`（解析/选题逻辑）

## M3 — 资料深挖（src/researcher.py）

- [x] `run(date_str, config) -> bool`，读 `pick.json`
- [x] Tavily Extract 抓原文 + Tavily Search 多源交叉核对
- [x] 输出 `research.md`
- [x] 单测覆盖

## M4 — 写作（src/article_writer.py + src/wechat_inline.py）

- [x] `run(date_str, config) -> bool`，读 `research.md` + 写作标准 + 模板
- [x] Claude 按 `###KEY###` 分隔标记出稿，填模板
- [x] `wechat_inline.inline()` 转微信安全全内联 HTML（去 style/class/flex/伪元素）
- [x] 输出 `wechat_article.html`
- [x] 单测 `tests/test_wechat_inline.py` 等

## M5 — 封面生成（src/image_generator.py）

- [x] `run(date_str, config) -> bool`
- [x] Claude 从文章提炼封面文案（分类/标题/数据/标语/钩子/场景）
- [x] Gemini `gemini-2.5-flash-image` 出无字背景，PIL + 雅黑叠中文
- [x] 输出 `cover.png`（1600×680）
- [x] 单测 `tests/test_image_generator.py`

## M6 — 邮件推送（src/notifier.py）

- [x] `run(date_str, config) -> bool`
- [x] 正文轻量预览 + 文章 HTML 附件 + cover.png 附件
- [x] 邮箱未配置时优雅跳过，不中断流水线
- [x] 单测 `tests/test_notifier.py`

## M7 — 余额监控（src/balance_alert.py）

- [x] `run(date_str, config) -> bool`
- [x] haiku 最小探活，命中余额/额度错误则邮件提醒
- [x] 未配置 key 或邮箱时跳过
- [x] 单测覆盖

## M8 — 反馈学习（src/feedback.py + feedback_input.py）

- [x] `run(date_str, config) -> bool`，跨天聚合 `pick.json` + `metrics.json`
- [x] 加权打分（阅读/评论/点赞/转发）排名，写 `history.jsonl`
- [x] 攒够 `min_articles` 后 Claude 沉淀 `lessons.md`，回灌 M2/M4
- [x] `manual` 采集器（手填）可用可测；`wechat` 采集器已写
- [x] `feedback_input.py` 命令行填数
- [x] 单测 `tests/test_feedback.py`、`tests/test_feedback_input.py`

## 编排 & 调度

- [x] `main.py` 串行调度 M1~M8，捕获异常写 `run.log` + 备份日志
- [x] 日期目录自动创建、运行摘要（各模块耗时/状态）
- [x] Windows 任务计划脚本（`setup_scheduler.bat` / `run_pipeline.bat`）

---

## 休眠 / 待办

- [ ] **视频链路**（content_generator / voice_generator / video_synthesizer）：文件保留，暂从流水线移除，待图文稳定后再启用。
- [ ] **feedback `wechat` 自动采集**：代码已写但未经真实验证（需已认证账号 + 数据统计权限 + 凭据齐全）。凭据补齐前保持 `source=manual`。
- [ ] **publisher 自动发布**：个人订阅号无 API 发布权，现以邮件推送 + 人工发布替代。账号升级认证后可再启用。
