import json
import os
import re

import anthropic


def _candidates(items: list) -> str:
    lines = []
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. 标题：{it['title']}")
        lines.append(f"   摘要：{it['summary']}")
        lines.append(f"   来源：{it['source']}")
        lines.append("")
    return "\n".join(lines)


def _parse_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?\s*", "", text)
    text = re.sub(r"```\s*$", "", text.strip())
    return json.loads(text.strip())


def run(date_str: str, config: dict) -> bool:
    output_dir = os.path.join(config["output_base"], date_str)
    news_path = os.path.join(output_dir, "news_raw.json")

    if not os.path.exists(news_path):
        raise FileNotFoundError(f"news_raw.json not found: {news_path}")

    with open(news_path, encoding="utf-8") as f:
        items = json.load(f)

    if not items:
        print("[selector] 没有候选新闻")
        return False

    client = anthropic.Anthropic(api_key=config["anthropic"]["api_key"])
    prompt = f"""你是科技公众号主编。下面是今天抓到的若干条科技新闻，请挑出**最值得写成深度文章**的一条。

挑选标准（按重要性排序）：
1. 【最重要】内容爆款力——话题性强、有冲击力、能引发讨论和传播，读者一看就想点进来。内容本身够不够"爆"是第一位的；内容不行，数据再好也没人看。
2. 行业影响力——能改变行业格局、影响很多人，技术/产品从业者真正关心。
3. 数据（加分项）——若几条都够爆，优先选自带可对比数字（融资/估值/跑分/份额/增长率等）、能做出数据对比图的那条。但这只是加分，绝不为了数据牺牲内容质量。

候选新闻：
{_candidates(items)}

只输出 JSON，不要任何其他内容：
{{"index": 选中的序号(从1开始的整数), "reason": "为什么选它，一句话"}}"""

    resp = client.messages.create(
        model=config["anthropic"]["model"],
        max_tokens=300,
        messages=[{"role": "user", "content": prompt}],
    )
    data = _parse_json(resp.content[0].text)

    idx = int(data["index"]) - 1
    if idx < 0 or idx >= len(items):
        print(f"[selector] 模型返回的序号越界：{data['index']}，回退到第 1 条")
        idx = 0

    pick = dict(items[idx])
    pick["reason"] = data.get("reason", "")

    with open(os.path.join(output_dir, "pick.json"), "w", encoding="utf-8") as f:
        json.dump(pick, f, ensure_ascii=False, indent=2)

    print(f"[selector] 选中第 {idx + 1} 条：{pick['title']}")
    print(f"[selector] 理由：{pick['reason']}")
    return True
