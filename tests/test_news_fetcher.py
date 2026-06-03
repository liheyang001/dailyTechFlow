import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import datetime

from src.news_fetcher import (
    run, _fetch_tavily, _fetch_brave, _deduplicate, _cap_per_domain,
    _pick_query, _QUERIES,
)


def _make_config(output_base: str) -> dict:
    return {
        "tavily": {"api_key": "test-tavily"},
        "brave": {"api_key": "test-brave"},
        "output_base": output_base,
    }


TAVILY_RAW = {
    "results": [
        {"title": "News A", "content": "Summary A", "url": "https://example.com/a"},
        {"title": "News B", "content": "Summary B", "url": "https://example.com/b"},
        {"title": "News C", "content": "Summary C", "url": "https://example.com/c"},
        {"title": "News D", "content": "Summary D", "url": "https://example.com/a"},  # duplicate
    ]
}

BRAVE_RAW = {
    "web": {
        "results": [
            {"title": "Brave A", "description": "Desc A", "url": "https://brave.com/a", "meta_url": {"hostname": "brave.com"}},
            {"title": "Brave B", "description": "Desc B", "url": "https://brave.com/b", "meta_url": {"hostname": "brave.com"}},
        ]
    }
}


class TestDeduplicate(unittest.TestCase):
    def test_removes_duplicate_urls(self):
        items = [
            {"url": "https://a.com", "title": "A"},
            {"url": "https://b.com", "title": "B"},
            {"url": "https://a.com", "title": "A2"},
        ]
        result = _deduplicate(items)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["title"], "A")

    def test_empty_input(self):
        self.assertEqual(_deduplicate([]), [])


class TestFetchTavily(unittest.TestCase):
    @patch("src.news_fetcher.requests.post")
    def test_parses_results(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = TAVILY_RAW
        mock_post.return_value = mock_resp

        config = {"tavily": {"api_key": "k"}}
        items = _fetch_tavily(config)
        self.assertEqual(len(items), 4)
        self.assertEqual(items[0]["title"], "News A")
        self.assertEqual(items[0]["source"], "example.com")

    @patch("src.news_fetcher.requests.post")
    def test_raises_on_http_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("HTTP 401")
        mock_post.return_value = mock_resp
        with self.assertRaises(Exception):
            _fetch_tavily({"tavily": {"api_key": "bad"}})


class TestFetchBrave(unittest.TestCase):
    @patch("src.news_fetcher.requests.get")
    def test_parses_results(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.json.return_value = BRAVE_RAW
        mock_get.return_value = mock_resp

        config = {"brave": {"api_key": "k"}}
        items = _fetch_brave(config)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["source"], "brave.com")

    @patch("src.news_fetcher.requests.get")
    def test_raises_on_http_error(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = Exception("HTTP 403")
        mock_get.return_value = mock_resp
        with self.assertRaises(Exception):
            _fetch_brave({"brave": {"api_key": "bad"}})


class TestRun(unittest.TestCase):
    @patch("src.news_fetcher.requests.post")
    def test_tavily_success_saves_json(self, mock_post):
        # 3 个不同域名的具体文章 + 1 条重复 URL：去重成 3 条，均在限流/上限内
        raw = {"results": [
            {"title": "News A", "content": "S", "url": "https://a.com/tech/news-a"},
            {"title": "News B", "content": "S", "url": "https://b.com/tech/news-b"},
            {"title": "News C", "content": "S", "url": "https://c.com/tech/news-c"},
            {"title": "News D", "content": "S", "url": "https://a.com/tech/news-a"},  # dup
        ]}
        mock_resp = MagicMock()
        mock_resp.json.return_value = raw
        mock_post.return_value = mock_resp

        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(tmp)
            result = run("2026-05-27", config)
            self.assertTrue(result)
            out_file = os.path.join(tmp, "2026-05-27", "news_raw.json")
            with open(out_file, encoding="utf-8") as f:
                data = json.load(f)
        self.assertEqual(len(data), 3)  # 4 条去重成 3 条，均在上限 8 内
        for item in data:
            self.assertIn("title", item)
            self.assertIn("summary", item)
            self.assertIn("url", item)
            self.assertIn("source", item)

    @patch("src.news_fetcher.requests.get")
    @patch("src.news_fetcher.requests.post")
    def test_fallback_to_brave_on_tavily_failure(self, mock_post, mock_get):
        mock_post.return_value.raise_for_status.side_effect = Exception("Tavily down")

        mock_resp = MagicMock()
        mock_resp.json.return_value = BRAVE_RAW
        mock_get.return_value = mock_resp

        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(tmp)
            result = run("2026-05-27", config)
            self.assertTrue(result)
            out_file = os.path.join(tmp, "2026-05-27", "news_raw.json")
            with open(out_file, encoding="utf-8") as f:
                data = json.load(f)
        self.assertEqual(len(data), 2)

    @patch("src.news_fetcher.requests.get")
    @patch("src.news_fetcher.requests.post")
    def test_both_fail_returns_false(self, mock_post, mock_get):
        mock_post.return_value.raise_for_status.side_effect = Exception("Tavily down")
        mock_get.return_value.raise_for_status.side_effect = Exception("Brave down")

        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(tmp)
            result = run("2026-05-27", config)

        self.assertFalse(result)

    @patch("src.news_fetcher.requests.post")
    def test_caps_at_eight_items(self, mock_post):
        # 12 个不同域名的具体文章 → 限流不削，最终由总上限 8 截断
        many_results = [
            {"title": f"News {i}", "content": f"Summary {i}",
             "url": f"https://s{i}.com/tech/news-{i}"}
            for i in range(12)
        ]
        mock_post.return_value.json.return_value = {"results": many_results}

        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(tmp)
            run("2026-05-27", config)
            out_file = os.path.join(tmp, "2026-05-27", "news_raw.json")
            with open(out_file, encoding="utf-8") as f:
                data = json.load(f)

        self.assertEqual(len(data), 8)  # fetcher 放宽到上限 8 条，最终由 selector 挑 1 条

    @patch("src.news_fetcher.requests.post")
    def test_caps_per_domain(self, mock_post):
        # 6 篇同域名文章 → 限流到每域名最多 2 条，防止单一信源霸榜
        same = [
            {"title": f"News {i}", "content": f"S{i}",
             "url": f"https://same.com/tech/news-{i}"}
            for i in range(6)
        ]
        mock_post.return_value.json.return_value = {"results": same}

        with tempfile.TemporaryDirectory() as tmp:
            config = _make_config(tmp)
            run("2026-05-27", config)
            out_file = os.path.join(tmp, "2026-05-27", "news_raw.json")
            with open(out_file, encoding="utf-8") as f:
                data = json.load(f)

        self.assertEqual(len(data), 2)
        self.assertTrue(all(it["source"] == "same.com" for it in data))


class TestCapPerDomain(unittest.TestCase):
    def test_keeps_at_most_n_per_domain(self):
        items = [
            {"source": "x.com", "url": "https://x.com/1"},
            {"source": "x.com", "url": "https://x.com/2"},
            {"source": "x.com", "url": "https://x.com/3"},
            {"source": "y.com", "url": "https://y.com/1"},
        ]
        capped = _cap_per_domain(items, n=2)
        self.assertEqual(len(capped), 3)  # x 留 2、y 留 1
        self.assertEqual(sum(1 for i in capped if i["source"] == "x.com"), 2)


class TestPickQuery(unittest.TestCase):
    def test_deterministic_for_same_date(self):
        self.assertEqual(_pick_query("2026-06-01"), _pick_query("2026-06-01"))

    def test_rotation_covers_all_within_one_cycle(self):
        start = datetime.date(2026, 6, 1)
        days = [(start + datetime.timedelta(days=i)).isoformat()
                for i in range(len(_QUERIES))]
        self.assertEqual(len({_pick_query(d) for d in days}), len(_QUERIES))

    def test_bad_date_falls_back(self):
        self.assertIn(_pick_query("not-a-date"), _QUERIES)


if __name__ == "__main__":
    unittest.main()
