import json
import os
import requests
from urllib.parse import urlparse


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


def _fetch_tavily(config: dict) -> list:
    api_key = config["tavily"]["api_key"]
    resp = requests.post(
        "https://api.tavily.com/search",
        json={
            "api_key": api_key,
            "query": "latest AI, startup and big tech news",
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


def _fetch_brave(config: dict) -> list:
    api_key = config["brave"]["api_key"]
    resp = requests.get(
        "https://api.search.brave.com/res/v1/web/search",
        headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
        params={"q": "tech news today", "count": 10},
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


def run(date_str: str, config: dict) -> bool:
    output_dir = os.path.join(config["output_base"], date_str)
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "news_raw.json")

    try:
        items = _fetch_tavily(config)
    except Exception as e:
        print(f"[news_fetcher] Tavily failed: {e}, falling back to Brave")
        try:
            items = _fetch_brave(config)
        except Exception as e2:
            print(f"[news_fetcher] Brave also failed: {e2}")
            return False

    items = _deduplicate(items)
    articles = [it for it in items if _is_article(it["url"])]
    # 过滤后若太少，退回未过滤结果兜底，避免空手
    items = (articles or items)[:8]
    if not items:
        print("[news_fetcher] No results found")
        return False
    print(f"[news_fetcher] 过滤聚合页：{len(articles)} 篇具体文章")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print(f"[news_fetcher] Saved {len(items)} items to {output_path}")
    return True
