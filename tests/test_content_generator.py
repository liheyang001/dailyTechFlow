import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.content_generator import run, _parse_json


MOCK_NEWS = [
    {"title": "News A", "summary": "Summary A", "url": "https://a.com", "source": "a.com"},
    {"title": "News B", "summary": "Summary B", "url": "https://b.com", "source": "b.com"},
    {"title": "News C", "summary": "Summary C", "url": "https://c.com", "source": "c.com"},
]

MOCK_ZH_SCRIPT = [
    {"segment": 1, "headline": "标题一", "narration": "旁白一内容", "visual_desc": "科技背景"},
    {"segment": 2, "headline": "标题二", "narration": "旁白二内容", "visual_desc": "数据图表"},
    {"segment": 3, "headline": "标题三", "narration": "旁白三内容", "visual_desc": "未来城市"},
]

MOCK_EN_SCRIPT = [
    {"segment": 1, "headline": "Title One", "narration": "Narration one.", "visual_desc": "Tech background"},
    {"segment": 2, "headline": "Title Two", "narration": "Narration two.", "visual_desc": "Data charts"},
    {"segment": 3, "headline": "Title Three", "narration": "Narration three.", "visual_desc": "Futuristic city"},
]


def _make_config(output_base: str) -> dict:
    return {
        "gemini": {"api_key": "test-key", "model": "gemini-2.0-flash"},
        "output_base": output_base,
    }


def _write_news(date_dir: str):
    os.makedirs(date_dir, exist_ok=True)
    with open(os.path.join(date_dir, "news_raw.json"), "w", encoding="utf-8") as f:
        json.dump(MOCK_NEWS, f)


class TestParseJson(unittest.TestCase):
    def test_plain_json(self):
        data = _parse_json(json.dumps(MOCK_ZH_SCRIPT))
        self.assertEqual(len(data), 3)

    def test_strips_markdown_code_block(self):
        text = "```json\n" + json.dumps(MOCK_ZH_SCRIPT) + "\n```"
        data = _parse_json(text)
        self.assertEqual(len(data), 3)

    def test_strips_code_block_no_lang(self):
        text = "```\n" + json.dumps(MOCK_ZH_SCRIPT) + "\n```"
        data = _parse_json(text)
        self.assertEqual(len(data), 3)


class TestRun(unittest.TestCase):

    def _mock_responses(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.models.generate_content.side_effect = [
            MagicMock(text="# 中文标题\n正文内容正文内容正文内容"),
            MagicMock(text="# English Title\nContent content content"),
            MagicMock(text=json.dumps(MOCK_ZH_SCRIPT)),
            MagicMock(text=json.dumps(MOCK_EN_SCRIPT)),
        ]
        return mock_client

    @patch("src.content_generator.genai.Client")
    def test_success_saves_all_four_files(self, mock_client_class):
        self._mock_responses(mock_client_class)
        with tempfile.TemporaryDirectory() as tmp:
            date_dir = os.path.join(tmp, "2026-05-27")
            _write_news(date_dir)
            result = run("2026-05-27", _make_config(tmp))
            self.assertTrue(result)
            for fname in ["article_zh.md", "article_en.md", "script_zh.json", "script_en.json"]:
                self.assertTrue(os.path.exists(os.path.join(date_dir, fname)), f"Missing: {fname}")

    @patch("src.content_generator.genai.Client")
    def test_script_json_structure(self, mock_client_class):
        self._mock_responses(mock_client_class)
        with tempfile.TemporaryDirectory() as tmp:
            date_dir = os.path.join(tmp, "2026-05-27")
            _write_news(date_dir)
            run("2026-05-27", _make_config(tmp))
            with open(os.path.join(date_dir, "script_zh.json"), encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(len(data), 3)
            for seg in data:
                for key in ("segment", "headline", "narration", "visual_desc"):
                    self.assertIn(key, seg)

    def test_missing_news_file_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                run("2026-05-27", _make_config(tmp))

    @patch("src.content_generator.genai.Client")
    def test_api_error_returns_false(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.models.generate_content.side_effect = Exception("API quota exceeded")
        with tempfile.TemporaryDirectory() as tmp:
            date_dir = os.path.join(tmp, "2026-05-27")
            _write_news(date_dir)
            result = run("2026-05-27", _make_config(tmp))
        self.assertFalse(result)

    @patch("src.content_generator.genai.Client")
    def test_script_json_with_markdown_wrapper(self, mock_client_class):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        mock_client.models.generate_content.side_effect = [
            MagicMock(text="# 中文标题\n正文"),
            MagicMock(text="# English Title\nContent"),
            MagicMock(text="```json\n" + json.dumps(MOCK_ZH_SCRIPT) + "\n```"),
            MagicMock(text="```\n" + json.dumps(MOCK_EN_SCRIPT) + "\n```"),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            date_dir = os.path.join(tmp, "2026-05-27")
            _write_news(date_dir)
            result = run("2026-05-27", _make_config(tmp))
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
