import json
import os

import requests


def _extract(url: str, api_key: str) -> str:
    """抓取选中新闻的原文全文。"""
    resp = requests.post(
        "https://api.tavily.com/extract",
        json={"api_key": api_key, "urls": [url]},
        timeout=30,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return results[0].get("raw_content", "") if results else ""


def _related(query: str, api_key: str) -> list:
    """搜索相关报道，补充数据和角度。"""
    resp = requests.post(
        "https://api.tavily.com/search",
        json={"api_key": api_key, "query": query, "max_results": 4},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def run(date_str: str, config: dict) -> bool:
    output_dir = os.path.join(config["output_base"], date_str)
    pick_path = os.path.join(output_dir, "pick.json")

    if not os.path.exists(pick_path):
        raise FileNotFoundError(f"pick.json not found: {pick_path}")

    with open(pick_path, encoding="utf-8") as f:
        pick = json.load(f)

    api_key = config["tavily"]["api_key"]

    raw = ""
    try:
        raw = _extract(pick["url"], api_key)
        print(f"[researcher] 原文全文抓取成功，{len(raw)} 字符")
    except Exception as e:
        print(f"[researcher] 原文全文抓取失败（用摘要兜底）：{e}")

    related = []
    try:
        related = _related(pick["title"], api_key)
        # 去掉与原文同源的那条，避免重复
        related = [r for r in related if r.get("url") != pick["url"]][:3]
        print(f"[researcher] 找到 {len(related)} 条相关报道")
    except Exception as e:
        print(f"[researcher] 相关报道搜索失败：{e}")

    lines = [
        f"# 选题：{pick['title']}",
        "",
        f"- 来源：{pick['source']}",
        f"- 链接：{pick['url']}",
        f"- 入选理由：{pick.get('reason', '')}",
        "",
        "## 原文摘要",
        pick.get("summary", ""),
        "",
        "## 原文全文",
        raw[:8000] if raw else "（抓取失败，仅有上方摘要可用）",
        "",
        "## 相关报道",
    ]
    if related:
        for r in related:
            lines.append(f"### {r.get('title', '')}")
            lines.append(f"{r.get('url', '')}")
            lines.append(r.get("content", ""))
            lines.append("")
    else:
        lines.append("（无）")

    research_path = os.path.join(output_dir, "research.md")
    with open(research_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"[researcher] research.md 已保存到 {output_dir}")
    return True
