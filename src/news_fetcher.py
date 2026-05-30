import json
import os
import requests
from urllib.parse import urlparse


def _domain(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except Exception:
        return ""


def _fetch_tavily(config: dict) -> list:
    api_key = config["tavily"]["api_key"]
    resp = requests.post(
        "https://api.tavily.com/search",
        json={"api_key": api_key, "query": "tech news today", "max_results": 10},
        timeout=15,
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

    items = _deduplicate(items)[:8]
    if not items:
        print("[news_fetcher] No results found")
        return False

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print(f"[news_fetcher] Saved {len(items)} items to {output_path}")
    return True
