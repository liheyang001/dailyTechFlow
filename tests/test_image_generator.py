import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.image_generator import run, _extract_title, _build_prompt, _generate_image


def _make_output_dir(tmp: str) -> str:
    date_dir = os.path.join(tmp, "2026-05-27")
    os.makedirs(date_dir, exist_ok=True)
    Path(os.path.join(date_dir, "article_zh.md")).write_text(
        "# 科技大变革今日速览\n\n正文内容", encoding="utf-8"
    )
    Path(os.path.join(date_dir, "article_en.md")).write_text(
        "# Tech Revolution Daily\n\nBody content", encoding="utf-8"
    )
    return date_dir


def _make_config(output_base: str) -> dict:
    return {"output_base": output_base, "huggingface": {"api_key": "test-hf-key"}}


class TestExtractTitle(unittest.TestCase):
    def test_extracts_h1(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("# My Title\n\nSome content\n")
            tmp = f.name
        try:
            self.assertEqual(_extract_title(tmp), "My Title")
        finally:
            os.unlink(tmp)

    def test_ignores_non_h1(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("## Secondary\n# Primary\n")
            tmp = f.name
        try:
            self.assertEqual(_extract_title(tmp), "Primary")
        finally:
            os.unlink(tmp)

    def test_no_title_raises(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("No title here\n")
            tmp = f.name
        try:
            with self.assertRaises(ValueError):
                _extract_title(tmp)
        finally:
            os.unlink(tmp)


class TestBuildPrompt(unittest.TestCase):
    def test_zh_contains_title(self):
        self.assertIn("AI大变革", _build_prompt("AI大变革", "zh"))

    def test_en_contains_title(self):
        self.assertIn("Tech Revolution", _build_prompt("Tech Revolution", "en"))

    def test_zh_and_en_differ(self):
        self.assertNotEqual(_build_prompt("X", "zh"), _build_prompt("X", "en"))


class TestGenerateImage(unittest.TestCase):
    @patch("src.image_generator.InferenceClient")
    def test_saves_image(self, mock_cls):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_image = MagicMock()
        mock_client.text_to_image.return_value = mock_image

        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out.png")
            _generate_image("a circuit board", "hf_test", out)
            mock_client.text_to_image.assert_called_once_with(
                "a circuit board", model="black-forest-labs/FLUX.1-schnell",
                width=1280, height=720
            )
            mock_image.save.assert_called_once_with(out)

    @patch("src.image_generator.InferenceClient")
    def test_uses_api_key(self, mock_cls):
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.text_to_image.return_value = MagicMock()

        with tempfile.TemporaryDirectory() as tmp:
            _generate_image("test", "hf_mytoken", os.path.join(tmp, "x.png"))
            mock_cls.assert_called_once_with(api_key="hf_mytoken")


class TestRun(unittest.TestCase):
    @patch("src.image_generator._generate_image")
    def test_success_saves_both_covers(self, mock_gen):
        with tempfile.TemporaryDirectory() as tmp:
            date_dir = _make_output_dir(tmp)
            result = run("2026-05-27", _make_config(tmp))

            self.assertTrue(result)
            self.assertEqual(mock_gen.call_count, 2)
            # verify both output paths
            calls = [c[0][2] for c in mock_gen.call_args_list]
            self.assertTrue(any("cover_zh.png" in p for p in calls))
            self.assertTrue(any("cover_en.png" in p for p in calls))

    @patch("src.image_generator._generate_image")
    def test_api_key_passed_through(self, mock_gen):
        with tempfile.TemporaryDirectory() as tmp:
            _make_output_dir(tmp)
            run("2026-05-27", _make_config(tmp))
            key_used = mock_gen.call_args_list[0][0][1]
            self.assertEqual(key_used, "test-hf-key")

    def test_missing_zh_article_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                run("2026-05-27", _make_config(tmp))

    def test_missing_en_article_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            date_dir = os.path.join(tmp, "2026-05-27")
            os.makedirs(date_dir)
            Path(os.path.join(date_dir, "article_zh.md")).write_text("# Title\n", encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                run("2026-05-27", _make_config(tmp))

    @patch("src.image_generator._generate_image")
    def test_api_error_returns_false(self, mock_gen):
        mock_gen.side_effect = Exception("connection timeout")
        with tempfile.TemporaryDirectory() as tmp:
            _make_output_dir(tmp)
            result = run("2026-05-27", _make_config(tmp))
            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
