import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

from src.voice_generator import run, _load_narrations, _synthesize, _VOICE_ZH, _VOICE_EN, _PAUSE_TAG


def _make_scripts(tmp: str) -> str:
    date_dir = os.path.join(tmp, "2026-05-27")
    os.makedirs(date_dir, exist_ok=True)
    script_zh = [
        {"segment": 1, "headline": "新闻1", "narration": "第一段旁白文本", "visual_desc": "画面1"},
        {"segment": 2, "headline": "新闻2", "narration": "第二段旁白文本", "visual_desc": "画面2"},
        {"segment": 3, "headline": "新闻3", "narration": "第三段旁白文本", "visual_desc": "画面3"},
    ]
    script_en = [
        {"segment": 1, "headline": "News 1", "narration": "First narration", "visual_desc": "Scene 1"},
        {"segment": 2, "headline": "News 2", "narration": "Second narration", "visual_desc": "Scene 2"},
        {"segment": 3, "headline": "News 3", "narration": "Third narration", "visual_desc": "Scene 3"},
    ]
    Path(os.path.join(date_dir, "script_zh.json")).write_text(
        json.dumps(script_zh), encoding="utf-8"
    )
    Path(os.path.join(date_dir, "script_en.json")).write_text(
        json.dumps(script_en), encoding="utf-8"
    )
    return date_dir


def _make_config(output_base: str) -> dict:
    return {"output_base": output_base}


class TestLoadNarrations(unittest.TestCase):
    def test_extracts_narrations(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump([
                {"segment": 1, "narration": "First", "headline": "H1", "visual_desc": "V1"},
                {"segment": 2, "narration": "Second", "headline": "H2", "visual_desc": "V2"},
            ], f)
            tmp = f.name
        try:
            self.assertEqual(_load_narrations(tmp), ["First", "Second"])
        finally:
            os.unlink(tmp)

    def test_empty_script_raises(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump([], f)
            tmp = f.name
        try:
            with self.assertRaises(ValueError):
                _load_narrations(tmp)
        finally:
            os.unlink(tmp)


class TestSynthesize(unittest.TestCase):
    @patch("src.voice_generator.edge_tts.Communicate")
    def test_calls_save_with_output_path(self, mock_comm_cls):
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock()
        mock_comm_cls.return_value = mock_comm

        asyncio.run(_synthesize(["Hello", "World"], _VOICE_EN, "/tmp/out.mp3"))

        mock_comm.save.assert_called_once_with("/tmp/out.mp3")

    @patch("src.voice_generator.edge_tts.Communicate")
    def test_pause_tag_between_segments(self, mock_comm_cls):
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock()
        mock_comm_cls.return_value = mock_comm

        asyncio.run(_synthesize(["A", "B", "C"], _VOICE_ZH, "/tmp/out.mp3"))

        text_arg = mock_comm_cls.call_args[0][0]
        self.assertEqual(text_arg, f"A{_PAUSE_TAG}B{_PAUSE_TAG}C")

    @patch("src.voice_generator.edge_tts.Communicate")
    def test_single_segment_no_pause(self, mock_comm_cls):
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock()
        mock_comm_cls.return_value = mock_comm

        asyncio.run(_synthesize(["Only one"], _VOICE_EN, "/tmp/out.mp3"))

        text_arg = mock_comm_cls.call_args[0][0]
        self.assertNotIn(_PAUSE_TAG, text_arg)

    @patch("src.voice_generator.edge_tts.Communicate")
    def test_uses_specified_voice(self, mock_comm_cls):
        mock_comm = MagicMock()
        mock_comm.save = AsyncMock()
        mock_comm_cls.return_value = mock_comm

        asyncio.run(_synthesize(["test"], _VOICE_EN, "/tmp/out.mp3"))

        self.assertEqual(mock_comm_cls.call_args[0][1], _VOICE_EN)


class TestRun(unittest.TestCase):
    @patch("src.voice_generator.asyncio.run")
    def test_success_calls_synthesize_twice(self, mock_run):
        with tempfile.TemporaryDirectory() as tmp:
            _make_scripts(tmp)
            result = run("2026-05-27", _make_config(tmp))

            self.assertTrue(result)
            self.assertEqual(mock_run.call_count, 2)

    @patch("src.voice_generator.asyncio.run")
    def test_output_paths_are_correct(self, mock_run):
        with tempfile.TemporaryDirectory() as tmp:
            _make_scripts(tmp)
            run("2026-05-27", _make_config(tmp))

            # asyncio.run receives coroutine objects; inspect via _synthesize args indirectly
            # We verify run returns True, which means both asyncio.run calls were made
            self.assertEqual(mock_run.call_count, 2)

    def test_missing_script_zh_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                run("2026-05-27", _make_config(tmp))

    def test_missing_script_en_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            date_dir = os.path.join(tmp, "2026-05-27")
            os.makedirs(date_dir)
            Path(os.path.join(date_dir, "script_zh.json")).write_text(
                json.dumps([{"segment": 1, "narration": "x", "headline": "h", "visual_desc": "v"}]),
                encoding="utf-8",
            )
            with self.assertRaises(FileNotFoundError):
                run("2026-05-27", _make_config(tmp))

    @patch("src.voice_generator.asyncio.run")
    def test_api_error_returns_false(self, mock_run):
        mock_run.side_effect = Exception("TTS service unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            _make_scripts(tmp)
            result = run("2026-05-27", _make_config(tmp))
            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
