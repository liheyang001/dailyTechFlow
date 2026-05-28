import os

from huggingface_hub import InferenceClient

_MODEL = "black-forest-labs/FLUX.1-dev"


def _extract_title(md_path: str) -> str:
    with open(md_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip()
    raise ValueError(f"No H1 title found in {md_path}")


def _build_prompt(title: str, lang: str) -> str:
    # Title is intentionally excluded — AI cannot render text reliably.
    # Text overlay happens in M5 video synthesis.
    if lang == "zh":
        return (
            "tech news broadcast background, 16:9 landscape, deep navy blue, "
            "glowing circuit board patterns, data streams, floating holographic chips, "
            "soft cyan and blue light rays, clean empty center space for text overlay, "
            "no text, no letters, no words, no faces, no logos, "
            "professional broadcast quality, cinematic"
        )
    return (
        "tech news broadcast background, 16:9 landscape, deep space dark background, "
        "glowing network nodes, fiber optic light trails, abstract digital grid, "
        "gold and white light accents, clean empty center space for text overlay, "
        "no text, no letters, no words, no faces, no logos, "
        "professional broadcast quality, cinematic"
    )


def _generate_image(prompt: str, api_key: str, out_path: str) -> None:
    client = InferenceClient(api_key=api_key)
    image = client.text_to_image(prompt, model=_MODEL, width=1280, height=720)
    image.save(out_path)


def run(date_str: str, config: dict) -> bool:
    output_dir = os.path.join(config["output_base"], date_str)

    zh_article = os.path.join(output_dir, "article_zh.md")
    en_article = os.path.join(output_dir, "article_en.md")

    if not os.path.exists(zh_article):
        raise FileNotFoundError(f"Missing: {zh_article}")
    if not os.path.exists(en_article):
        raise FileNotFoundError(f"Missing: {en_article}")

    title_zh = _extract_title(zh_article)
    title_en = _extract_title(en_article)
    api_key = config["huggingface"]["api_key"]

    tasks = [
        (title_zh, "zh", os.path.join(output_dir, "cover_zh.png")),
        (title_en, "en", os.path.join(output_dir, "cover_en.png")),
    ]

    try:
        for title, lang, out_path in tasks:
            print(f"[image_generator] Generating {lang} cover for: {title[:50]}...")
            _generate_image(_build_prompt(title, lang), api_key, out_path)

    except Exception as e:
        print(f"[image_generator] Error: {e}")
        return False

    print(f"[image_generator] cover_zh.png, cover_en.png saved to {output_dir}")
    return True
