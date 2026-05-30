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
1. 必须包含至少一张数据条形图，把核心数据对比可视化：
   <div class="chart">
     <div class="chart-title">图表标题（带单位）</div>
     <div class="bar-row"><span class="bar-label">项名</span><span class="bar"><span class="bar-fill" style="width:100%">数值</span></span></div>
     <div class="bar-row"><span class="bar-label">项名</span><span class="bar"><span class="bar-fill alt" style="width:NN%">数值</span></span></div>
     <div class="chart-src">来源：XXX</div>
   </div>
   其中数值最大的一项 width 设 100%，其余项按与最大值的比例换算百分比（例如 8000/9650≈83%，则 width:83%）。
   只把资料里有确切数值的项放进条形图；某项没有确切数字时，绝不硬编一个比例宽度——可改用其它有确切数据的维度作图，或只比较有数字的项（哪怕只有一两项）。
2. 数据真实性是铁律：每个数字都必须来自上方资料，绝不编造；每个关键数据都要标出处；图表和表格底部必须有「来源：…」。资料里没有的数字宁可不写。"""

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

    html = template
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
