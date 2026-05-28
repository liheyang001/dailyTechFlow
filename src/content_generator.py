import json
import os
import re

from google import genai


def _news_context(items: list) -> str:
    lines = []
    for i, item in enumerate(items, 1):
        lines.append(f"{i}. 标题：{item['title']}")
        lines.append(f"   摘要：{item['summary']}")
        lines.append(f"   来源：{item['source']}")
        lines.append("")
    return "\n".join(lines)


def _call(client, model_name: str, prompt: str) -> str:
    response = client.models.generate_content(model=model_name, contents=prompt)
    return response.text.strip()


def _parse_json(text: str) -> list:
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text.strip())
    return json.loads(text.strip())


def run(date_str: str, config: dict) -> bool:
    output_dir = os.path.join(config["output_base"], date_str)
    news_path = os.path.join(output_dir, "news_raw.json")

    if not os.path.exists(news_path):
        raise FileNotFoundError(f"news_raw.json not found: {news_path}")

    with open(news_path, encoding="utf-8") as f:
        news_items = json.load(f)

    client = genai.Client(api_key=config["gemini"]["api_key"])
    model_name = config["gemini"]["model"]
    ctx = _news_context(news_items)

    zh_article_prompt = f"""你是一位科技新闻公众号编辑。根据以下 3 条科技新闻，撰写一篇微信公众号文章。

要求：
- 字数 800~1000 字
- 结构：标题（以 # 开头）、正文（分段叙述每条新闻）、结尾引流（鼓励关注 DailyTechFlow）
- 语言：中文，通俗易懂，有科技感
- 忠实于新闻内容，不要过度发挥

今日新闻：
{ctx}
直接输出 Markdown 格式文章，不要额外说明。"""

    en_article_prompt = f"""You are a tech journalist writing for X (Twitter). Based on these 3 tech news items, write an engaging English article for social media.

Requirements:
- Length: 300~500 words
- Style: Concise, engaging, suitable for X/Twitter audience
- Structure: Hook opening, one paragraph per news item, brief conclusion
- Format: Markdown with a # Title at the top

Today's news:
{ctx}
Output the Markdown article directly, no extra commentary."""

    zh_script_prompt = f"""根据以下 3 条科技新闻，为短视频生成中文分镜脚本，每条新闻对应一段。

严格输出 JSON 数组，格式：
[
  {{
    "segment": 1,
    "headline": "简短标题（10字以内）",
    "narration": "旁白文本（30~40字，口语化，适合 TTS 朗读）",
    "visual_desc": "画面描述（20字以内）"
  }}
]

今日新闻：
{ctx}
只输出 JSON，不要其他内容。"""

    en_script_prompt = f"""Based on these 3 tech news items, generate an English video storyboard, one segment per news item.

Output a strict JSON array:
[
  {{
    "segment": 1,
    "headline": "Short title (under 8 words)",
    "narration": "Narration (30-50 words, conversational, suitable for TTS)",
    "visual_desc": "Visual description (under 15 words)"
  }}
]

Today's news:
{ctx}
Output only JSON, no other content."""

    try:
        print("[content_generator] Generating Chinese article...")
        article_zh = _call(client, model_name, zh_article_prompt)

        print("[content_generator] Generating English article...")
        article_en = _call(client, model_name, en_article_prompt)

        print("[content_generator] Generating Chinese script...")
        script_zh = _parse_json(_call(client, model_name, zh_script_prompt))

        print("[content_generator] Generating English script...")
        script_en = _parse_json(_call(client, model_name, en_script_prompt))

    except Exception as e:
        print(f"[content_generator] Error: {e}")
        return False

    with open(os.path.join(output_dir, "article_zh.md"), "w", encoding="utf-8") as f:
        f.write(article_zh)

    with open(os.path.join(output_dir, "article_en.md"), "w", encoding="utf-8") as f:
        f.write(article_en)

    with open(os.path.join(output_dir, "script_zh.json"), "w", encoding="utf-8") as f:
        json.dump(script_zh, f, ensure_ascii=False, indent=2)

    with open(os.path.join(output_dir, "script_en.json"), "w", encoding="utf-8") as f:
        json.dump(script_en, f, ensure_ascii=False, indent=2)

    print(f"[content_generator] 4 files saved to {output_dir}")
    return True
