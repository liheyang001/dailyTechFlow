import os
import re

import anthropic

PROMPT_PATH = "prompts/wechat_writer.md"
TEMPLATE_PATH = "templates/wechat_article.html"


def _parse_sections(text: str) -> dict:
    """按 ###KEY### 分隔标记切分模型输出，避免大段 HTML 塞进 JSON 的转义问题。"""
    parts = re.split(r"###(\w+)###", text)
    result = {}
    for i in range(1, len(parts) - 1, 2):
        key = parts[i].strip().lower()
        result[key] = parts[i + 1].strip()
    return result


def run(date_str: str, config: dict) -> bool:
    output_dir = os.path.join(config["output_base"], date_str)
    research_path = os.path.join(output_dir, "research.md")

    if not os.path.exists(research_path):
        raise FileNotFoundError(f"research.md not found: {research_path}")

    with open(research_path, encoding="utf-8") as f:
        material = f.read()
    with open(PROMPT_PATH, encoding="utf-8") as f:
        writer_guide = f.read()
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()

    client = anthropic.Anthropic(api_key=config["anthropic"]["api_key"])

    user_prompt = f"""请根据下面的资料，写一篇微信公众号深度文章，严格遵守你的写作标准（篇幅、结构、数据、观点）。

【资料】
{material}

【输出格式】
严格按以下分隔标记输出，每个标记独占一行，标记之间填内容。不要输出任何额外说明：

###CATEGORY###
分类标签，如 AI · 模型发布 / 产品 · 融资 / 行业 · 政策
###TITLE###
主标题，不超过28字，有冲击力
###READ_TIME###
预计阅读分钟数，只填整数，如 7
###LEAD###
导语1-2句话，点出核心价值，可用 <b>关键词</b> 强调
###CONTENT###
正文 HTML 片段，使用写作标准里的组件：<h2><span class="num">N</span>标题</h2>、<div class="sub">副标题</div>、<p>、<div class="keybox">、<table>、<div class="quote">、<div class="feat">、<div class="ending">、结尾用 <p class="src">信息来源：…</p>。不要包含 h1 主标题、导语块、分类标签（它们由模板单独渲染）。

【强制要求】
1. 内容质量第一：标题和开头要有冲击力、让人想读下去，正文要有观点、有信息量。这是最重要的。
2. 数据图（有则做，无则不强求）：如果资料里有可横向对比的量化数据（多家公司/产品的数值、增长率、份额、价格等），就做一张数据条形图把它可视化：
   <div class="chart">
     <div class="chart-title">图表标题（带单位）</div>
     <div class="bar-row"><span class="bar-label">项名</span><span class="bar"><span class="bar-fill" style="width:100%">数值</span></span></div>
     <div class="bar-row"><span class="bar-label">项名</span><span class="bar"><span class="bar-fill alt" style="width:NN%">数值</span></span></div>
     <div class="chart-src">来源：XXX</div>
   </div>
   数值最大的一项 width 设 100%，其余按比例换算（例如 400/800≈50%，则 width:50%）。只把有确切数值的项放进图。
   如果这条新闻确实没有可量化对比的数据，就不要做图，更不能编数字凑图——把文章内容写扎实即可。
3. 数据真实性是铁律：每个数字都必须来自上方资料，绝不编造；每个关键数据都要标出处；图表和表格底部必须有「来源：…」。资料里没有的数字宁可不写。"""

    resp = client.messages.create(
        model=config["anthropic"]["model"],
        max_tokens=8000,
        system=writer_guide,
        messages=[{"role": "user", "content": user_prompt}],
    )
    data = _parse_sections(resp.content[0].text)

    required = {"category", "title", "lead", "content"}
    missing = required - data.keys()
    if missing:
        print(f"[article_writer] 模型输出缺少字段：{missing}")
        return False

    # 去掉模板里给人看的"组件清单"注释，保持产出干净
    html = re.sub(r"<!--\s*可用组件清单[\s\S]*?-->", "", template)
    replacements = {
        "{{CATEGORY}}": data.get("category", ""),
        "{{TITLE}}": data.get("title", ""),
        "{{DATE}}": f"{date_str.replace('-', '.')} 北京时间",
        "{{READ_TIME}}": data.get("read_time", ""),
        "{{LEAD}}": data.get("lead", ""),
        "{{CONTENT}}": data.get("content", ""),
    }
    for placeholder, value in replacements.items():
        html = html.replace(placeholder, value)

    out_path = os.path.join(output_dir, "wechat_article.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[article_writer] 文章已生成：{data.get('title', '')}")
    print(f"[article_writer] 保存到 {out_path}")
    return True
