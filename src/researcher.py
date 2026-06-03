import json
import os
import re
from urllib.parse import urlparse

import requests


def _domain(url: str) -> str:
    try:
        return urlparse(url or "").hostname or ""
    except Exception:
        return ""


def _extract(url: str, api_key: str) -> str:
    """抓取选中新闻的原文全文（付费墙站点可能失败）。"""
    resp = requests.post(
        "https://api.tavily.com/extract",
        json={"api_key": api_key, "urls": [url]},
        timeout=30,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return results[0].get("raw_content", "") if results else ""


def _search_fulltext(query: str, api_key: str, max_results: int = 6) -> list:
    """对选题做深度搜索，聚合多个来源的正文——绕开单一付费墙，凑齐可交叉核对的数据。"""
    resp = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": api_key,
            "query": query,
            "search_depth": "advanced",
            "include_raw_content": True,
            "max_results": max_results,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def _clean(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", (text or "").strip())


def run(date_str: str, config: dict) -> bool:
    output_dir = os.path.join(config["output_base"], date_str)
    pick_path = os.path.join(output_dir, "pick.json")

    if not os.path.exists(pick_path):
        raise FileNotFoundError(f"pick.json not found: {pick_path}")

    with open(pick_path, encoding="utf-8") as f:
        pick = json.load(f)

    api_key = config["tavily"]["api_key"]

    # 1) 原文全文（付费墙/反爬时可能为空，靠下方多源兜底）
    raw = ""
    try:
        raw = _extract(pick["url"], api_key)
        print(f"[researcher] 原文全文 {len(raw)} 字符")
    except Exception as e:
        print(f"[researcher] 原文抓取失败：{e}")

    # 2) 多源深度搜索：聚合多篇报道的正文，交叉核对、提取可对比数字
    sources = []
    try:
        sources = _search_fulltext(pick["title"], api_key)
        # 剔除与选中文章同域名的来源：否则选了 PitchBook 又只搜回 PitchBook，
        # 多源退化成单一信源的回声室，凑不出真正可交叉核对的不同视角
        pick_dom = _domain(pick["url"])
        sources = [s for s in sources
                   if _domain(s.get("url", "")) and _domain(s.get("url", "")) != pick_dom]
        print(f"[researcher] 多源报道 {len(sources)} 篇（已去同域名回声）")
    except Exception as e:
        print(f"[researcher] 多源搜索失败：{e}")

    lines = [
        f"# 选题：{pick['title']}",
        "",
        f"- 来源：{pick['source']}",
        f"- 链接：{pick['url']}",
        f"- 入选理由：{pick.get('reason', '')}",
        "",
        "## 原文摘要",
        _clean(pick.get("summary", "")),
        "",
        "## 原文全文",
        _clean(raw)[:6000] if raw else "（原文抓取失败，见下方多源报道）",
        "",
        "## 多源详细报道（用于交叉核对数据、提取可对比数字）",
    ]
    if sources:
        for s in sources:
            lines.append(f"### {s.get('title', '')}")
            lines.append(f"来源：{s.get('url', '')}")
            content = _clean(s.get("content", ""))
            raw_c = _clean(s.get("raw_content", ""))[:2500]
            if content:
                lines.append(content)
            if raw_c:
                lines.append("")
                lines.append(raw_c)
            lines.append("")
    else:
        lines.append("（无）")

    research_path = os.path.join(output_dir, "research.md")
    with open(research_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[researcher] research.md 已保存到 {output_dir}")
    return True
