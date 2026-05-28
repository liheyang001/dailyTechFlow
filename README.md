# DailyTechFlow

每天凌晨 3:30 自动运行的科技新闻内容流水线。

抓取 3 条科技新闻 → 生成中英文文章 + 视频脚本 → 生成封面图 → 合成语音 → 合成视频 → 发布微信公众号。

---

## 环境要求

- Python 3.10+
- [HyperFrames CLI](https://hyperframes.dev)（需全局安装）

```bash
pip install -r requirements.txt
npm install -g hyperframes   # 或按官方文档安装
```

---

## 配置 API Key

编辑 `config.yaml`，填入所有 API Key：

```yaml
tavily:
  api_key: "tvly-xxx"          # https://tavily.com

gemini:
  api_key: "AIza-xxx"          # https://aistudio.google.com
  model: "gemini-2.5-flash"

huggingface:
  api_key: "hf_xxx"            # https://huggingface.co/settings/tokens

wechat:
  app_id: "wx-xxx"             # 微信公众平台 → 开发 → 基本配置
  app_secret: "xxx"
  auto_publish: false          # true = 直接群发；false = 仅存草稿
```

> `config.yaml` 已加入 `.gitignore`，不会被提交。

---

## 首次运行

```bash
# 手动执行今天的流程
python main.py

# 指定日期（补跑历史）
python main.py 2026-05-28
```

运行日志写入 `output/YYYY-MM-DD/run.log`，同时备份到 `logs/YYYY-MM-DD.log`。

---

## 产物目录

每次运行在 `output/YYYY-MM-DD/` 下生成：

| 文件 | 来源模块 |
|------|----------|
| `news_raw.json` | M1 新闻抓取 |
| `article_zh.md` / `article_en.md` | M2 内容生成 |
| `script_zh.json` / `script_en.json` | M2 内容生成 |
| `cover_zh.png` / `cover_en.png` | M3 图片生成 |
| `voiceover_zh.mp3` / `voiceover_en.mp3` | M4 语音生成 |
| `video_zh.mp4` / `video_en.mp4` | M5 视频合成 |
| `run.log` | 主编排器 |

---

## 自动调度

已通过 `setup_scheduler.bat` 注册 Windows 任务计划，每天 03:30 自动运行。

查看或修改：**任务计划程序** → `\DailyTechFlow`

手动触发：
```bash
schtasks /run /tn "DailyTechFlow"
```

---

## 运行测试

```bash
python -m pytest tests/ -v
```

---

## 模块说明

| 模块 | 文件 | 职责 |
|------|------|------|
| M1 | `src/news_fetcher.py` | Tavily / Brave 抓取 3 条科技新闻 |
| M2 | `src/content_generator.py` | Gemini 生成文章和视频脚本 |
| M3 | `src/image_generator.py` | HuggingFace 生成封面图 |
| M4 | `src/voice_generator.py` | Edge-TTS 合成语音 |
| M5 | `src/video_synthesizer.py` | HyperFrames 合成视频 |
| M6 | `src/publisher.py` | 微信公众号 API 发布 |
| M7 | `main.py` | 串行编排 M1~M6，记录日志 |
