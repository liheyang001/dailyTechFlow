import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.news_fetcher import run, _fetch_tavily, _fetch_brave, _deduplicate


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
        mock_resp = MagicMock()
        mock_resp.json.return_value = TAVILY_RAW
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
        many_results = [
            {"title": f"News {i}", "content": f"Summary {i}", "url": f"https://example.com/{i}"}
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


if __name__ == "__main__":
    unittest.main()
