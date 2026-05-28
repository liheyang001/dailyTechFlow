# 运行总控提示词（Master Prompt）

> 阶段四：分布式编码 — 每个模块复制对应的【子 Agent 提示词】到新对话窗口独立执行。

---

## 使用方式

1. 打开一个**全新的对话窗口**（干净上下文）
2. 复制对应模块的【子 Agent 提示词】粘贴进去
3. 等子 Agent 完成，所有单测终端跑通后，回来把 `progress.md` 里对应任务勾上
4. 再开下一个模块

---

## M0 — 项目脚手架【子 Agent 提示词】

```
你是一个 Python 项目初始化 Agent。请严格按照以下要求搭建 DailyTechFlow 项目脚手架，不要添加任何未要求的内容。

【项目路径】
I:\AI\DailyTechFlow\

【任务清单】
按顺序完成以下任务，每完成一项在终端验证后再进行下一项：

1. 创建以下目录结构（已存在的跳过）：
   - src\
   - templates\
   - output\
   - logs\
   - tests\

2. 创建 requirements.txt，内容如下（精确版本）：
   google-generativeai>=0.8.0
   openai>=1.0.0
   edge-tts>=6.1.9
   requests>=2.31.0
   pyyaml>=6.0.1
   pytest>=8.0.0

3. 创建 config.yaml，内容如下（占位符，不填真实 key）：
   tavily:
     api_key: "YOUR_TAVILY_API_KEY"
   brave:
     api_key: "YOUR_BRAVE_API_KEY"
   gemini:
     api_key: "YOUR_GEMINI_API_KEY"
     model: "gemini-2.0-flash"
   gpt_image:
     api_key: "YOUR_OPENAI_API_KEY"
   wechat:
     app_id: "YOUR_WECHAT_APP_ID"
     app_secret: "YOUR_WECHAT_APP_SECRET"
     auto_publish: false
   output_base: "I:/AI/DailyTechFlow/output"

4. 创建 .gitignore，排除：
   config.yaml
   output/
   logs/
   __pycache__/
   *.pyc
   .env

5. 创建 src\__init__.py（空文件）
   创建 tests\__init__.py（空文件）

6. 在终端运行以下命令验证 Python 环境：
   python --version
   确认版本 >= 3.10，否则报错提示用户升级。

7. 创建 tests\test_scaffold.py，内容为：
   - 测试 src/ 目录存在
   - 测试 templates/ 目录存在
   - 测试 output/ 目录存在
   - 测试 logs/ 目录存在
   - 测试 config.yaml 存在
   - 测试 requirements.txt 存在

8. 在终端运行 pytest tests\test_scaffold.py -v，必须全部通过，否则修复后重跑。

【完成标准】
pytest 输出显示全部 PASSED，无任何 FAILED 或 ERROR。

【禁止事项】
- 不要安装任何包（用户自行 pip install）
- 不要创建 src\ 下的任何业务模块（那是 M1-M6 的任务）
- 不要修改 docs\ 下的任何文档
```

---

## M1 — 新闻抓取【子 Agent 提示词】

```
你是一个 Python 模块开发 Agent。请实现 DailyTechFlow 项目的新闻抓取模块。

【项目路径】
I:\AI\DailyTechFlow\

【前置条件】
- src\ 目录已存在（M0 已完成）
- config.yaml 已存在

【任务】
实现 src\news_fetcher.py，要求：

1. 对外接口：def run(date_str: str, config: dict) -> bool
2. 逻辑：
   - 用 Tavily API 搜索 "top tech news today"，取前 3 条
   - 如果 Tavily 失败，自动切换 Brave Search API 重试
   - 对结果按 URL 去重
   - 将结果写入 output/{date_str}/news_raw.json
   - 写入前自动创建目录（如不存在）
3. news_raw.json 格式：
   [{"title": "...", "summary": "...", "url": "...", "source": "..."}]
4. 任何异常抛出，不在模块内 catch（由 main.py 统一处理）

实现 tests\test_news_fetcher.py：
- mock Tavily API 返回正常数据，验证 JSON 写入正确
- mock Tavily API 抛出异常，验证自动切换 Brave Search
- mock 两个 API 都失败，验证抛出异常

在终端运行 pytest tests\test_news_fetcher.py -v，必须全部通过。

【禁止事项】
- 不要修改其他模块
- 不要处理超过 3 条新闻
- 函数内不要 print，用 logging
```

---

## M2 — 内容生成【子 Agent 提示词】

```
你是一个 Python 模块开发 Agent。请实现 DailyTechFlow 项目的内容生成模块。

【项目路径】
I:\AI\DailyTechFlow\

【前置条件】
- output/{date_str}/news_raw.json 已存在（M1 已完成）

【任务】
实现 src\content_generator.py，要求：

1. 对外接口：def run(date_str: str, config: dict) -> bool
2. 读取 output/{date_str}/news_raw.json
3. 调用 Gemini API（gemini-2.0-flash）生成：
   a. 中文公众号文章（800~1000字，含标题、正文、结尾引流到个人工具）→ article_zh.md
   b. 英文社交媒体文章（300~500字，适合 X/Twitter 风格）→ article_en.md
   c. 中文视频分镜脚本（3段 JSON）→ script_zh.json
   d. 英文视频分镜脚本（3段 JSON）→ script_en.json
4. script JSON 格式：
   [{"segment": 1, "headline": "...", "narration": "旁白文本30~40字", "visual_desc": "..."}]
5. 所有文件写入 output/{date_str}/

实现 tests\test_content_generator.py（mock Gemini API）。
运行 pytest tests\test_content_generator.py -v，全部通过。
```

---

## M3 — 图片生成【子 Agent 提示词】

```
你是一个 Python 模块开发 Agent。请实现 DailyTechFlow 项目的封面图生成模块。

【项目路径】
I:\AI\DailyTechFlow\

【前置条件】
- output/{date_str}/article_zh.md 已存在
- output/{date_str}/article_en.md 已存在

【任务】
实现 src\image_generator.py，要求：

1. 对外接口：def run(date_str: str, config: dict) -> bool
2. 从 article_zh.md 提取第一行标题（去掉 # 前缀）
3. 从 article_en.md 提取第一行标题
4. 调用 OpenAI GPT-Image-2 API 生成 1280x720 封面图：
   - 中文封面：科技风格，简洁，深色背景，包含中文标题关键词
   - 英文封面：同风格，包含英文标题关键词
5. 保存 cover_zh.png 和 cover_en.png 到 output/{date_str}/

实现 tests\test_image_generator.py（mock OpenAI API）。
运行 pytest tests\test_image_generator.py -v，全部通过。
```

---

## M4 — 语音生成【子 Agent 提示词】

```
你是一个 Python 模块开发 Agent。请实现 DailyTechFlow 项目的语音生成模块。

【项目路径】
I:\AI\DailyTechFlow\

【前置条件】
- output/{date_str}/script_zh.json 已存在
- output/{date_str}/script_en.json 已存在

【任务】
实现 src\voice_generator.py，要求：

1. 对外接口：def run(date_str: str, config: dict) -> bool
2. 读取 script_zh.json，提取每段 narration 字段
3. 用 edge-tts（zh-CN-XiaoxiaoNeural）合成中文语音，段落间插入 0.8s 停顿
4. 读取 script_en.json，提取每段 narration 字段
5. 用 edge-tts（en-US-JennyNeural）合成英文语音，段落间插入 0.8s 停顿
6. 保存 voiceover_zh.mp3 和 voiceover_en.mp3 到 output/{date_str}/

实现 tests\test_voice_generator.py（mock edge-tts）。
运行 pytest tests\test_voice_generator.py -v，全部通过。
```

---

## M5 — 视频合成【子 Agent 提示词】

```
你是一个 Python 模块开发 Agent。请实现 DailyTechFlow 项目的视频合成模块。

【项目路径】
I:\AI\DailyTechFlow\

【前置条件】
- output/{date_str}/script_zh.json、script_en.json 已存在
- output/{date_str}/cover_zh.png、cover_en.png 已存在
- output/{date_str}/voiceover_zh.mp3、voiceover_en.mp3 已存在
- templates\hyperframes_template.html 需要在本模块中创建

【任务】
1. 创建 templates\hyperframes_template.html：
   - 片头 5s：节目名称"DailyTechFlow"动画
   - 3段新闻：动态背景 + 标题文字动画 + 旁白音频同步
   - 片尾 10s：引流信息
   - 使用 Hyperframes HTML 格式（参考 hyperframes skill）

2. 实现 src\video_synthesizer.py：
   - 对外接口：def run(date_str: str, config: dict) -> bool
   - 将 script JSON + 封面图路径填充进 HTML 模板，生成当日 HTML
   - 调用 hyperframes render CLI 输出 video_zh.mp4 和 video_en.mp4
   - 验证输出文件存在且大小 > 0

实现 tests\test_video_synthesizer.py（mock CLI 调用）。
运行 pytest tests\test_video_synthesizer.py -v，全部通过。
```

---

## M6 — 发布【子 Agent 提示词】

```
你是一个 Python 模块开发 Agent。请实现 DailyTechFlow 项目的微信公众号发布模块。

【项目路径】
I:\AI\DailyTechFlow\

【前置条件】
- output/{date_str}/article_zh.md 已存在
- output/{date_str}/cover_zh.png 已存在

【任务】
实现 src\publisher.py，要求：

1. 对外接口：def run(date_str: str, config: dict) -> bool
2. 获取微信 access_token（有效期 2h，本地缓存到 logs/wechat_token.json）
3. 上传 cover_zh.png 为永久素材，获取 media_id
4. 将 article_zh.md 转换为微信富文本 HTML（标题变 <h2>，段落变 <p>）
5. 调用微信草稿 API 创建图文草稿
6. 若 config["wechat"]["auto_publish"] == true，调用群发 API 发布
7. 返回草稿 media_id 并写入 run.log

实现 tests\test_publisher.py（mock 微信 API）。
运行 pytest tests\test_publisher.py -v，全部通过。
```

---

## M7 — 主编排器【子 Agent 提示词】

```
你是一个 Python 模块开发 Agent。请实现 DailyTechFlow 项目的主编排器和任务调度脚本。

【项目路径】
I:\AI\DailyTechFlow\

【前置条件】
M0~M6 全部完成，src\ 下 6 个模块均已实现并通过单测。

【任务】
1. 实现 main.py：
   - 读取 config.yaml
   - 获取今日日期字符串（YYYY-MM-DD）
   - 创建 output/{date_str}/ 目录
   - 按序调用 M1~M6 的 run() 函数
   - 每个模块用 try/except 包裹，失败时写 run.log 并继续
   - 全部完成后打印运行摘要（各模块耗时、成功/失败）

2. 创建 setup_scheduler.bat：
   - 使用 schtasks 命令注册 Windows 任务计划
   - 每天 03:30 运行 python main.py
   - 工作目录设为 I:\AI\DailyTechFlow\

3. 端到端冒烟测试：
   - 用真实 API key（用户手动填入 config.yaml 后）运行 python main.py
   - 验证 output/{date_str}/ 下 8 个产物文件全部生成
```
