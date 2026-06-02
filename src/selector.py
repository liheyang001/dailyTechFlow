import json
import os
import re
from datetime import date, timedelta

import anthropic


def _candidates(items: list) -> str:
    lines = []
    for i, it in enumerate(items, 1):
        lines.append(f"{i}. 标题：{it['title']}")
        lines.append(f"   摘要：{it['summary']}")
        lines.append(f"   来源：{it['source']}")
        lines.append("")
    return "\n".join(lines)


def _recent_titles(output_base: str, date_str: str, days: int = 7) -> list:
    """读取最近 days 天已写过的选题标题，用于避免连续撞题。"""
    try:
        base = date.fromisoformat(date_str)
    except ValueError:
        return []
    titles = []
    for i in range(1, days + 1):
        d = (base - timedelta(days=i)).isoformat()
        p = os.path.join(output_base, d, "pick.json")
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as f:
                    t = json.load(f).get("title", "")
                if t:
                    titles.append(t)
            except Exception:
                pass
    return titles


def _parse_json(text: str) -> dict:
    """解析模型返回的 {"index", "reason"}。

    优先标准 JSON；失败则正则兜底——reason 是一句话、常含未转义的引号，
    会让 json.loads 崩（线上连续两天栽在这），但 index 是整数、最关键，
    必须拿到：拿到就能选出文章、链路不断；reason 只是附注，尽力抽。
    """
    cleaned = re.sub(r"```(?:json)?\s*", "", text)
    cleaned = re.sub(r"```\s*$", "", cleaned.strip()).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    m = re.search(r'"index"\s*:\s*(\d+)', cleaned)
    if not m:
        raise ValueError(f"模型输出里找不到 index：{cleaned[:200]}")
    data = {"index": int(m.group(1)), "reason": ""}
    rm = re.search(r'"reason"\s*:\s*"(.*)"', cleaned, re.S)
    if rm:
        data["reason"] = rm.group(1).strip()
    return data


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

    recent = _recent_titles(config["output_base"], date_str)
    avoid_block = ""
    if recent:
        avoid_block = (
            "\n\n【最近几天已经写过的主题——请避开，不要再选同一主题或同一事件】\n"
            + "\n".join(f"- {t}" for t in recent)
        )

    # 注入 feedback 模块沉淀的经验：什么样的选题过往阅读/评论表现好
    lessons_block = ""
    lessons_path = os.path.join("feedback", "lessons.md")
    if os.path.exists(lessons_path):
        with open(lessons_path, encoding="utf-8") as f:
            lessons = f.read().strip()
        if lessons:
            lessons_block = (
                "\n\n【历史经验——根据过往文章真实阅读/评论总结，选题时务必参考】\n" + lessons
            )

    client = anthropic.Anthropic(api_key=config["anthropic"]["api_key"])
    prompt = f"""你是科技公众号主编。下面是今天抓到的若干条科技新闻，请挑出**最值得写成深度文章**的一条。

挑选标准（按重要性排序）：
1. 【最重要】内容爆款力——话题性强、有冲击力、能引发讨论和传播，读者一看就想点进来。内容本身够不够"爆"是第一位的；内容不行，数据再好也没人看。
2. 不要重复——避开最近几天已经写过的主题/事件（见下方清单），保持每天选题新鲜。哪怕某条很爆，但和近期写过的是同一件事，也要换一条。
3. 行业影响力——能改变行业格局、影响很多人，技术/产品从业者真正关心。
4. 数据（加分项）——若几条都够爆，优先选自带可对比数字（融资/估值/跑分/份额/增长率等）、能做出数据对比图的那条。但这只是加分，绝不为了数据牺牲内容质量。

候选新闻：
{_candidates(items)}{avoid_block}{lessons_block}

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
