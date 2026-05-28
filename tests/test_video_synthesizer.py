import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.video_synthesizer import (
    run,
    _estimate_seg_dur,
    _compute_timing,
    _fill_template,
    _render_video,
    _INTRO_DUR,
    _OUTRO_DUR,
    _PAUSE,
    _SEG_BUFFER,
    _CHARS_PER_SEC_ZH,
    _WORDS_PER_SEC_EN,
)

_TEMPLATE = (
    "dur={{TOTAL_DURATION}} audio={{AUDIO_DURATION}} voice={{VOICEOVER_PATH}} "
    "lang={{LANG}} label={{LANG_LABEL}} date={{DATE_STR}} cover={{COVER_IMAGE_PATH}} "
    "h1={{HEADLINE_1}} h2={{HEADLINE_2}} h3={{HEADLINE_3}} "
    "n1={{NARRATION_1}} n2={{NARRATION_2}} n3={{NARRATION_3}} "
    "s1={{SEG1_START}} s2={{SEG2_START}} s3={{SEG3_START}} "
    "outro={{OUTRO_START}} cta={{CTA_TEXT}} ol={{OUTRO_LABEL}}"
)

_SEGMENTS_ZH = [
    {"segment": 1, "headline": "新闻一", "narration": "这是第一段旁白文本内容", "visual_desc": "画面1"},
    {"segment": 2, "headline": "新闻二", "narration": "这是第二段旁白文字", "visual_desc": "画面2"},
    {"segment": 3, "headline": "新闻三", "narration": "这是第三段旁白", "visual_desc": "画面3"},
]
_SEGMENTS_EN = [
    {"segment": 1, "headline": "News One", "narration": "This is the first narration text here", "visual_desc": "Scene 1"},
    {"segment": 2, "headline": "News Two", "narration": "Second narration piece goes here now", "visual_desc": "Scene 2"},
    {"segment": 3, "headline": "News Three", "narration": "Third and final narration segment", "visual_desc": "Scene 3"},
]


def _make_output_dir(tmp: str, segments_zh=None, segments_en=None) -> str:
    date_dir = os.path.join(tmp, "2026-05-27")
    os.makedirs(date_dir, exist_ok=True)
    segs_zh = segments_zh or _SEGMENTS_ZH
    segs_en = segments_en or _SEGMENTS_EN
    Path(os.path.join(date_dir, "script_zh.json")).write_text(
        json.dumps(segs_zh), encoding="utf-8"
    )
    Path(os.path.join(date_dir, "script_en.json")).write_text(
        json.dumps(segs_en), encoding="utf-8"
    )
    for fname in ["cover_zh.png", "cover_en.png", "voiceover_zh.mp3", "voiceover_en.mp3"]:
        Path(os.path.join(date_dir, fname)).write_bytes(b"dummy")
    return date_dir


def _make_config(output_base: str, template_path: str = "") -> dict:
    return {"output_base": output_base, "_template_path_override": template_path}


class TestEstimateSegDur(unittest.TestCase):
    def test_zh_uses_char_rate(self):
        narration = "十个中文字符测试用"  # 9 chars
        expected = len(narration) / _CHARS_PER_SEC_ZH + _SEG_BUFFER
        self.assertAlmostEqual(_estimate_seg_dur(narration, "zh"), expected, places=5)

    def test_en_uses_word_rate(self):
        narration = "five words right here"
        expected = 4 / _WORDS_PER_SEC_EN + _SEG_BUFFER
        self.assertAlmostEqual(_estimate_seg_dur(narration, "en"), expected, places=5)

    def test_zh_longer_narration_is_longer(self):
        short = _estimate_seg_dur("短", "zh")
        long_ = _estimate_seg_dur("这是一段很长很长的旁白文本内容", "zh")
        self.assertGreater(long_, short)

    def test_en_more_words_is_longer(self):
        few = _estimate_seg_dur("one two", "en")
        many = _estimate_seg_dur("one two three four five six seven eight", "en")
        self.assertGreater(many, few)


class TestComputeTiming(unittest.TestCase):
    def _narrations(self):
        return ["十个字的旁白文本内容是", "另一段旁白文本内容", "第三段旁白"]

    def test_first_seg_starts_at_intro_dur(self):
        timing = _compute_timing(self._narrations(), "zh")
        self.assertAlmostEqual(timing["seg_starts"][0], _INTRO_DUR, places=2)

    def test_seg_starts_increase_monotonically(self):
        timing = _compute_timing(self._narrations(), "zh")
        starts = timing["seg_starts"]
        self.assertLess(starts[0], starts[1])
        self.assertLess(starts[1], starts[2])

    def test_pause_between_segments(self):
        timing = _compute_timing(self._narrations(), "zh")
        starts = timing["seg_starts"]
        durs = timing["seg_durs"]
        gap = starts[1] - starts[0] - durs[0]
        self.assertAlmostEqual(gap, _PAUSE, places=2)

    def test_total_dur_includes_intro_and_outro(self):
        timing = _compute_timing(self._narrations(), "zh")
        self.assertGreater(timing["total_dur"], _INTRO_DUR + _OUTRO_DUR)

    def test_outro_start_plus_outro_equals_total(self):
        timing = _compute_timing(self._narrations(), "zh")
        self.assertAlmostEqual(timing["outro_start"] + _OUTRO_DUR, timing["total_dur"], places=2)

    def test_en_timing_computed(self):
        narrations = ["first narration text here", "second narration text", "third one"]
        timing = _compute_timing(narrations, "en")
        self.assertEqual(len(timing["seg_starts"]), 3)
        self.assertEqual(len(timing["seg_durs"]), 3)


class TestFillTemplate(unittest.TestCase):
    def _timing(self):
        return {
            "total_dur": 55.0,
            "audio_dur": 40.0,
            "seg_starts": [5.0, 18.0, 31.0],
            "seg_durs": [12.2, 12.2, 9.6],
            "outro_start": 45.0,
        }

    def test_all_placeholders_replaced(self):
        result = _fill_template(
            _TEMPLATE, _SEGMENTS_ZH,
            cover_path="cover_zh.png",
            voiceover_path="voiceover_zh.mp3",
            lang="zh",
            date_str="2026-05-27",
            timing=self._timing(),
        )
        self.assertNotIn("{{", result)
        self.assertNotIn("}}", result)

    def test_headlines_injected(self):
        result = _fill_template(
            _TEMPLATE, _SEGMENTS_ZH,
            cover_path="cover_zh.png",
            voiceover_path="voiceover_zh.mp3",
            lang="zh",
            date_str="2026-05-27",
            timing=self._timing(),
        )
        self.assertIn("新闻一", result)
        self.assertIn("新闻二", result)
        self.assertIn("新闻三", result)

    def test_narrations_injected(self):
        result = _fill_template(
            _TEMPLATE, _SEGMENTS_ZH,
            cover_path="cover_zh.png",
            voiceover_path="voiceover_zh.mp3",
            lang="zh",
            date_str="2026-05-27",
            timing=self._timing(),
        )
        self.assertIn(_SEGMENTS_ZH[0]["narration"], result)
        self.assertIn(_SEGMENTS_ZH[2]["narration"], result)

    def test_en_lang_label(self):
        result = _fill_template(
            _TEMPLATE, _SEGMENTS_EN,
            cover_path="cover_en.png",
            voiceover_path="voiceover_en.mp3",
            lang="en",
            date_str="2026-05-27",
            timing=self._timing(),
        )
        self.assertIn("Daily Tech Digest", result)

    def test_cover_path_injected(self):
        result = _fill_template(
            _TEMPLATE, _SEGMENTS_ZH,
            cover_path="cover_zh.png",
            voiceover_path="voiceover_zh.mp3",
            lang="zh",
            date_str="2026-05-27",
            timing=self._timing(),
        )
        self.assertIn("cover_zh.png", result)


class TestRenderVideo(unittest.TestCase):
    @patch("src.video_synthesizer.subprocess.run")
    def test_calls_hyperframes_render(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        with tempfile.TemporaryDirectory() as tmp:
            mp4 = os.path.join(tmp, "out.mp4")
            Path(mp4).write_bytes(b"fake mp4 data")
            _render_video(tmp, "video_zh.html", mp4)
        cmd = mock_run.call_args[0][0]
        self.assertEqual(cmd[0], "hyperframes")
        self.assertEqual(cmd[1], "render")
        self.assertIn("video_zh.html", cmd)
        self.assertIn(mp4, cmd)

    @patch("src.video_synthesizer.subprocess.run")
    def test_nonzero_returncode_raises(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stderr="error text")
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError) as ctx:
                _render_video(tmp, "video_zh.html", os.path.join(tmp, "out.mp4"))
            self.assertIn("render failed", str(ctx.exception))

    @patch("src.video_synthesizer.subprocess.run")
    def test_missing_output_file_raises(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        with tempfile.TemporaryDirectory() as tmp:
            mp4 = os.path.join(tmp, "nonexistent.mp4")
            with self.assertRaises(RuntimeError):
                _render_video(tmp, "video_zh.html", mp4)


class TestRun(unittest.TestCase):
    def _make_template_file(self, tmp: str) -> str:
        p = os.path.join(tmp, "hyperframes_template.html")
        Path(p).write_text(_TEMPLATE, encoding="utf-8")
        return p

    @patch("src.video_synthesizer._render_video")
    @patch("src.video_synthesizer.os.path.dirname")
    def test_success_returns_true(self, mock_dirname, mock_render):
        with tempfile.TemporaryDirectory() as tmp:
            _make_output_dir(tmp)
            tpl_dir = os.path.join(tmp, "templates")
            os.makedirs(tpl_dir)
            Path(os.path.join(tpl_dir, "hyperframes_template.html")).write_text(
                _TEMPLATE, encoding="utf-8"
            )
            mock_dirname.return_value = tmp
            result = run("2026-05-27", {"output_base": tmp})
            self.assertTrue(result)
            self.assertEqual(mock_render.call_count, 2)

    def test_missing_script_zh_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                run("2026-05-27", {"output_base": tmp})

    def test_missing_voiceover_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            date_dir = os.path.join(tmp, "2026-05-27")
            os.makedirs(date_dir)
            for fname in ["script_zh.json", "script_en.json"]:
                Path(os.path.join(date_dir, fname)).write_text(
                    json.dumps(_SEGMENTS_ZH), encoding="utf-8"
                )
            for fname in ["cover_zh.png", "cover_en.png"]:
                Path(os.path.join(date_dir, fname)).write_bytes(b"x")
            # voiceover files missing → should raise
            with self.assertRaises(FileNotFoundError):
                run("2026-05-27", {"output_base": tmp})

    @patch("src.video_synthesizer._render_video")
    @patch("src.video_synthesizer.os.path.dirname")
    def test_render_failure_returns_false(self, mock_dirname, mock_render):
        mock_render.side_effect = RuntimeError("hyperframes render failed")
        with tempfile.TemporaryDirectory() as tmp:
            _make_output_dir(tmp)
            tpl_dir = os.path.join(tmp, "templates")
            os.makedirs(tpl_dir)
            Path(os.path.join(tpl_dir, "hyperframes_template.html")).write_text(
                _TEMPLATE, encoding="utf-8"
            )
            mock_dirname.return_value = tmp
            result = run("2026-05-27", {"output_base": tmp})
            self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
