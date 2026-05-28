# 任务进度追踪（Progress）

> 阶段三：任务拆解 — 完成于 2026-05-27
> 依赖：`docs/architecture.md`

---

## 整体进度

- [ ] M0 项目脚手架
- [ ] M1 新闻抓取模块
- [ ] M2 内容生成模块
- [ ] M3 图片生成模块
- [ ] M4 语音生成模块
- [ ] M5 视频合成模块
- [ ] M6 发布模块
- [ ] M7 主编排器 & 任务调度

---

## M0 — 项目脚手架

- [ ] 创建完整目录结构（src/, templates/, output/, logs/）
- [ ] 创建 `config.yaml`（含所有 API key 占位符）
- [ ] 创建 `requirements.txt`（列出所有依赖包）
- [ ] 创建 `.gitignore`（排除 config.yaml、output/、logs/）
- [ ] 验证 Python 环境可用（>= 3.10）

---

## M1 — 新闻抓取（src/news_fetcher.py）

- [ ] 实现 `run(date_str, config) -> bool` 函数签名
- [ ] 集成 Tavily Search API，搜索 "tech news today"
- [ ] 实现 Brave Search API 备用逻辑（Tavily 失败时自动切换）
- [ ] 对结果去重（按 URL），取前 3 条
- [ ] 将结果序列化为 `news_raw.json`（title/summary/url/source）
- [ ] 编写单元测试 `tests/test_news_fetcher.py`（mock API 响应）

---

## M2 — 内容生成（src/content_generator.py）

- [ ] 实现 `run(date_str, config) -> bool` 函数签名
- [ ] 读取 `news_raw.json`，校验结构
- [ ] 调用 Gemini API 生成中文公众号文章（800~1000 字）
- [ ] 调用 Gemini API 生成英文社交媒体文章（300~500 字）
- [ ] 调用 Gemini API 生成中文视频分镜脚本（3段 JSON）
- [ ] 调用 Gemini API 生成英文视频分镜脚本（3段 JSON）
- [ ] 保存 `article_zh.md`、`article_en.md`、`script_zh.json`、`script_en.json`
- [ ] 编写单元测试 `tests/test_content_generator.py`（mock Gemini 响应）

---

## M3 — 图片生成（src/image_generator.py）

- [ ] 实现 `run(date_str, config) -> bool` 函数签名
- [ ] 从 `article_zh.md` 提取标题，构造中文封面提示词
- [ ] 从 `article_en.md` 提取标题，构造英文封面提示词
- [ ] 调用 GPT-Image-2 API 生成 1280×720 中文封面图
- [ ] 调用 GPT-Image-2 API 生成 1280×720 英文封面图
- [ ] 保存 `cover_zh.png`、`cover_en.png`
- [ ] 编写单元测试 `tests/test_image_generator.py`（mock API）

---

## M4 — 语音生成（src/voice_generator.py）

- [ ] 实现 `run(date_str, config) -> bool` 函数签名
- [ ] 读取 `script_zh.json`，提取各段旁白文本
- [ ] 用 Edge-TTS（zh-CN-XiaoxiaoNeural）生成中文语音，段间 0.8s 停顿
- [ ] 读取 `script_en.json`，提取各段旁白文本
- [ ] 用 Edge-TTS（en-US-JennyNeural）生成英文语音，段间 0.8s 停顿
- [ ] 保存 `voiceover_zh.mp3`、`voiceover_en.mp3`
- [ ] 编写单元测试 `tests/test_voice_generator.py`（mock edge-tts）

---

## M5 — 视频合成（src/video_synthesizer.py）

- [ ] 实现 `run(date_str, config) -> bool` 函数签名
- [ ] 创建 `templates/hyperframes_template.html`（片头+3段新闻+片尾结构）
- [ ] 实现模板填充函数：将 script JSON + 封面图路径注入 HTML
- [ ] 调用 `hyperframes render` CLI 生成中文 MP4
- [ ] 调用 `hyperframes render` CLI 生成英文 MP4
- [ ] 验证输出文件存在且大小 > 0
- [ ] 编写单元测试 `tests/test_video_synthesizer.py`（mock CLI 调用）

---

## M6 — 发布（src/publisher.py）

- [ ] 实现 `run(date_str, config) -> bool` 函数签名
- [ ] 实现微信 access_token 获取与缓存（2小时有效期）
- [ ] 上传 `cover_zh.png` 为永久素材，获取 `media_id`
- [ ] 将 `article_zh.md` 转换为微信富文本 HTML
- [ ] 创建图文草稿（含标题、作者、封面、正文）
- [ ] 根据 `config.yaml` 中 `auto_publish` 决定存草稿或直接群发
- [ ] 编写单元测试 `tests/test_publisher.py`（mock 微信 API）

---

## M7 — 主编排器 & 任务调度

- [ ] 实现 `main.py`：按序调用 M1~M6，捕获异常并写 `run.log`
- [ ] 实现日期目录自动创建逻辑
- [ ] 实现运行摘要日志（各模块耗时、成功/失败状态）
- [ ] 编写 Windows 任务计划程序注册脚本 `setup_scheduler.bat`（每天 03:30）
- [ ] 编写 `README.md`（环境配置、API key 填写、首次运行指南）
- [ ] 端到端冒烟测试（全流程跑一次，验证产物齐全）
