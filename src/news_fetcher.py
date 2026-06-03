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


# 读者定位：英文为主 + 补国内 AI 大事。每天在轮换的英文 query 之外，额外搜一条中文，
# 把国内大模型/科技公司的大新闻（字节、阿里、智谱、MiniMax、Kimi、DeepSeek 等）并入池。
_CN_QUERY = "中国 AI 大模型与科技公司最新重大新闻"

# 信源分层：一手官方 + 一线媒体 + 国内一线 → tier1（优先）；内容农场/聚合/社交 → tier3（降权）。
# 子串匹配域名；命中即归档，其余默认 tier2。给 selector 一个可信度信号，别拿二手转载当主稿。
_TIER1 = (
    "openai.com", "anthropic.com", "blog.google", "deepmind", "meta.com",
    "microsoft.com", "apple.com", "nvidia.com", "arxiv.org", "github.com",
    "huggingface.co", "reuters.com", "techcrunch.com", "theverge.com",
    "arstechnica.com", "wired.com", "bloomberg.com", "wsj.com", "ft.com",
    "nytimes.com", "technologyreview.com", "theinformation.com",
    "venturebeat.com", "axios.com", "cnbc.com",
    "36kr.com", "qbitai.com", "jiqizhixin.com", "ithome.com", "leiphone.com",
    "pingwest.com", "geekpark.net", "thepaper.cn", "sspai.com",
)
_TIER3 = (
    "blockchain.news", "tradersunion", "investordaily", "digitalapplied",
    "privatemarketsinsights", "towardsai", "wolfstreet", "benzinga",
    "seekingalpha", "fool.com", "linkedin.com", "instagram.com",
    "facebook.com", "twitter.com", "reddit.com", "medium.com",
    "substack.com", "yahoo.com", "msn.com", "news.google", "flipboard",
)


def _source_tier(domain: str) -> int:
    """信源可信度档：1 一手/权威、2 常规、3 二手转载/内容农场。"""
    d = (domain or "").lower()
    if any(k in d for k in _TIER1):
        return 1
    if any(k in d for k in _TIER3):
        return 3
    return 2


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

    # 补国内 AI 大事：额外一条中文搜索并入候选池。best-effort，失败不影响主流程
    try:
        cn = _fetch_tavily(config, _CN_QUERY)
        items += cn
        print(f"[news_fetcher] 国内补充 {len(cn)} 条")
    except Exception as e:
        print(f"[news_fetcher] 国内补充搜索失败（忽略）：{e}")

    print(f"[news_fetcher] 今日查询词：{query} ＋ 国内补充")
    items = _deduplicate(items)
    for it in items:
        it["tier"] = _source_tier(it["source"])
    # 过滤聚合页/栏目首页，只留具体文章；一手/权威源（tier1，含 36kr/量子位等国内一线，
    # URL 常是数字 ID，过不了英文 slug 规则）直接放行
    articles = [it for it in items if _is_article(it["url"]) or it["tier"] == 1]
    # 过滤后若太少则退回兜底；按 tier 排序让高质先进池，再限流去单一信源霸榜，截断到 8
    pool = articles or items
    pool.sort(key=lambda it: it["tier"])
    items = _cap_per_domain(pool)[:8]
    if not items:
        print("[news_fetcher] No results found")
        return False
    print(f"[news_fetcher] 过滤聚合页：{len(articles)} 篇具体文章")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    print(f"[news_fetcher] Saved {len(items)} items to {output_path}")
    return True
