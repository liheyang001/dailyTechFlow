import json
import os
from datetime import date

import requests
from urllib.parse import urlparse

# 科技主题按天轮换，避免天天用同一个搜索词、候选池又窄又偏。
# 都是科技类，只是换角度：去掉旧 query 里那个总把风投/估值数据源（如 PitchBook）
# 顶上来的 "startup" 偏向，融资只占其中一格，不再天天主导。
_QUERIES = [
    "latest AI model releases and research breakthroughs",
    "new open-source AI tools and developer frameworks",
    "AI chips, GPUs and semiconductor industry news",
    "AI products and real-world enterprise applications",
    "big tech platform, software and developer news",
    "robotics, autonomous vehicles and embodied AI",
    "AI policy, regulation, safety and security news",
    "AI startup funding and venture capital deals",
]


def _pick_query(date_str: str) -> str:
    """按日期轮换查询词，覆盖率随天数铺开；同一天结果确定、可测。"""
    try:
        n = date.fromisoformat(date_str).toordinal()
    except ValueError:
        n = 0
    return _QUERIES[n % len(_QUERIES)]


def _domain(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except Exception:
        return ""


def _is_article(url: str) -> bool:
    """过滤掉栏目首页/聚合页，只保留具体文章。

    具体文章 URL 通常路径较深、末段是带连字符的 slug，例如
    /technology/anthropic-valuation-surges-...；而 /technology 这种
    栏目首页抓回来全是导航菜单，没有正文。
    """
    path = urlparse(url).path.strip("/")
    if not path:
        return False  # 根域名
    segs = path.split("/")
    last = segs[-1]
    return len(segs) >= 2 and ("-" in last or len(last) > 24)


def _fetch_tavily(config: dict, query: str = "") -> list:
    api_key = config["tavily"]["api_key"]
    resp = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": api_key,
            "query": query or _QUERIES[0],
            "topic": "news",          # 拿具体新闻文章，而非栏目聚合页
            "search_depth": "advanced",
            "days": 3,                 # 最近 3 天
            "max_results": 15,
        },
        timeout=20,
    )
    resp.raise_for_status()
    items = []
    for r in resp.json().get("results", []):
        url = r.get("url", "")
        if url:
            items.append({
                "title": r.get("title", ""),
                "summary": r.get("content", ""),
                "url": url,
                "source": _domain(url),
            })
    return items


def _fetch_brave(config: dict, query: str = "") -> list:
    api_key = config["brave"]["api_key"]
    resp = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
        params={"q": query or _QUERIES[0], "count": 10},
        timeout=15,
    )
    resp.raise_for_status()
    items = []
    for r in resp.json().get("web", {}).get("results", []):
        url = r.get("url", "")
        if url:
            items.append({
                "title": r.get("title", ""),
                "summary": r.get("description", ""),
                "url": url,
                "source": r.get("meta_url", {}).get("hostname", _domain(url)),
            })
    return items


def _deduplicate(items: list) -> list:
    seen = set()
    result = []
    for item in items:
        if item["url"] not in seen:
            seen.add(item["url"])
            result.append(item)
    return result


def _cap_per_domain(items: list, n: int = 2) -> list:
    """同一来源最多保留 n 条，防止单一信源（如 PitchBook）霸占候选池。"""
    count: dict = {}
    result = []
    for item in items:
        dom = item.get("source") or _domain(item.get("url", ""))
        if count.get(dom, 0) < n:
            count[dom] = count.get(dom, 0) + 1
            result.append(item)
    return result


def run(date_str: str, config: dict) -> bool:
    output_dir = os.path.join(config["output_base"], date_str)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "news_raw.json")

    query = _pick_query(date_str)
    try:
        items = _fetch_tavily(config, query)
    except Exception as e:
        print(f"[news_fetcher] Tavily failed: {e}, falling back to Brave")
        try:
            items = _fetch_brave(config, query)
        except Exception as e2:
            print(f"[news_fetcher] Brave also failed: {e2}")
            return False

    print(f"[news_fetcher] 今日查询词：{query}")
    items = _deduplicate(items)
    articles = [it for it in items if _is_article(it["url"])]
    # 过滤后若太少，退回未过滤结果兜底，避免空手；再按来源限流去掉单一信源霸榜
    items = _cap_per_domain(articles or items)[:8]
    if not items:
        print("[news_fetcher] No results found")
        return False
    print(f"[news_fetcher] 过滤聚合页：{len(articles)} 篇具体文章")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print(f"[news_fetcher] Saved {len(items)} items to {output_path}")
    return True
