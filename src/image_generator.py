"""M4.5 封面生成：AI 画背景插画 + 代码精确叠中文，做微信公众号封面。

为什么分两层：gemini-2.5-flash-image 画插画很强，但直接渲染中文常出错别字，
每天自动发不可控。所以让 AI 只画无字背景，标题/分类/数据用 PIL + 雅黑精确叠上，
零错字、每天从文章自动提炼，完全可控。

流程：Claude 从文章提炼封面文案 → Gemini 出纯背景 → PIL 叠字 → cover.png。
约定 run(date_str, config) -> bool，只读写当天 output 目录。
"""
import json
import os
import re

import anthropic
from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont

_IMG_MODEL = "gemini-2.5-flash-image"
_FONT_BD = "C:/Windows/Fonts/msyhbd.ttc"   # 微软雅黑 粗
_FONT_RG = "C:/Windows/Fonts/msyh.ttc"     # 微软雅黑 常规
W, H = 1600, 680                            # 2.35:1 微信封面比例

_ORANGE = (232, 98, 42)
_DARK = (38, 36, 34)
_GREY = (96, 86, 78)


def _article_text(html: str) -> tuple:
    """从 wechat_article.html 提取标题 + 正文纯文本（喂给 Claude 提炼用）。"""
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    title = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S)
    body = re.sub(r"<[^>]+>", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    return title, body[:2500]


def _parse_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text.strip())
    return json.loads(text.strip())


def _distill_copy(client, model: str, title: str, body: str) -> dict:
    prompt = f"""你是公众号封面文案设计师。根据下面的文章，提炼一张封面要放的文字（要够吸睛）。

文章标题：{title}
文章正文：{body}

只输出 JSON，字数务必严格遵守（封面空间有限，超长会排不下）：
{{
  "category": "分类标签，如 产业 · 风险投资 / AI · 模型发布，≤8字",
  "title": "封面主标题，4-9字，有冲击力，可以不同于文章长标题",
  "data": "一行核心信息，≤18字。优先用文章里真实的醒目数字（如 Q1融资$21亿超越晚期）；没有醒目数字就写一句最有冲击力的结论。绝不编造数字。",
  "tagline_en": "一句英文标语，大写，≤28字符",
  "hook": "一句中文钩子，≤16字",
  "scene": "给背景插画的英文视觉关键词，3-6个词，如 rocket launching upward, growth, finance charts"
}}"""
    resp = client.messages.create(
        model=model, max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return _parse_json(resp.content[0].text)


def _gen_background(api_key: str, scene: str, out_path: str) -> None:
    prompt = (
        "Wide 2.35:1 WeChat article cover BACKGROUND illustration, editorial tech-magazine style. "
        "Diagonal split: LEFT 45% is a clean warm cream-beige flat area kept MOSTLY EMPTY for text, "
        "RIGHT side dark charcoal with the illustration. "
        f"Illustration theme: {scene}. "
        "Color palette: warm orange, copper, cream, charcoal grey. Clean, balanced, high quality. "
        "ABSOLUTELY NO TEXT, NO LETTERS, NO WORDS, NO NUMBERS anywhere in the image."
    )
    client = genai.Client(api_key=api_key)
    resp = client.models.generate_content(
        model=_IMG_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=types.ImageConfig(aspect_ratio="21:9"),
        ),
    )
    for part in resp.parts:
        if getattr(part, "inline_data", None) is not None:
            part.as_image().save(out_path)
            return
    raise RuntimeError("Gemini 未返回图片数据")


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def _fit_size(draw, text: str, font_path: str, max_w: int, start: int, low: int = 40) -> int:
    """从 start 往下找能塞进 max_w 的字号，避免文字溢出封面。"""
    size = start
    while size > low:
        if draw.textlength(text, font=_font(font_path, size)) <= max_w:
            break
        size -= 4
    return size


def _compose(bg_path: str, copy: dict, out_path: str) -> None:
    base = Image.open(bg_path).convert("RGB").resize((W, H))

    # 左侧文字区叠半透明奶白衬底，兜底深色字可读性（不依赖 AI 背景精确留白）
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([0, 0, 760, H], fill=(245, 241, 234, 150))
    base = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
    d = ImageDraw.Draw(base)

    LX = 64  # 左边距

    # 分类标签：橙色圆角块
    cat = copy.get("category", "")
    if cat:
        cf = _font(_FONT_BD, 34)
        cw = d.textlength(cat, font=cf)
        d.rounded_rectangle([LX, 48, LX + cw + 44, 102], radius=10, fill=_ORANGE)
        d.text((LX + 22, 58), cat, font=cf, fill=(255, 255, 255))

    # 主标题：自适应字号
    title = copy.get("title", "")
    ts = _fit_size(d, title, _FONT_BD, 660, 104, 60)
    d.text((LX, 150), title, font=_font(_FONT_BD, ts), fill=_DARK)

    # 核心数据行
    data = copy.get("data", "")
    ds = _fit_size(d, data, _FONT_RG, 670, 46, 28)
    d.text((LX + 2, 150 + ts + 30), data, font=_font(_FONT_RG, ds), fill=_GREY)

    # 英文标语（橙）+ 中文钩子（深灰）
    d.text((LX + 2, 470), copy.get("tagline_en", ""), font=_font(_FONT_BD, 40), fill=_ORANGE)
    d.text((LX + 2, 530), copy.get("hook", ""), font=_font(_FONT_RG, 32), fill=_GREY)

    base.save(out_path)


def run(date_str: str, config: dict) -> bool:
    output_dir = os.path.join(config["output_base"], date_str)
    article_path = os.path.join(output_dir, "wechat_article.html")

    if not os.path.exists(article_path):
        raise FileNotFoundError(f"Missing: {article_path}")

    try:
        with open(article_path, encoding="utf-8") as f:
            title, body = _article_text(f.read())

        client = anthropic.Anthropic(api_key=config["anthropic"]["api_key"])
        copy = _distill_copy(client, config["anthropic"]["model"], title, body)
        print(f"[image_generator] 封面文案：{copy.get('title')} / {copy.get('data')}")

        bg_path = os.path.join(output_dir, "_cover_bg.png")
        _gen_background(config["gemini"]["api_key"], copy.get("scene", "abstract tech"), bg_path)

        cover_path = os.path.join(output_dir, "cover.png")
        _compose(bg_path, copy, cover_path)
        print(f"[image_generator] 封面已生成：{cover_path}")

    except Exception as e:
        print(f"[image_generator] 出错：{e}")
        return False

    return True
