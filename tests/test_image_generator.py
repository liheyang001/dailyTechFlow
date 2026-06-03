"""image_generator 单测：纯逻辑 + 叠字合成（用假背景图，不调 API）。

运行：python tests/test_image_generator.py
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

from src.image_generator import (
    W, H, _article_text, _article_category, _parse_json, _compose,
)


class TestArticleText(unittest.TestCase):
    def test_extracts_title_and_strips_tags(self):
        html = '<h1 class="t">今日大新闻</h1><style>.x{color:red}</style><p>正文<b>内容</b></p>'
        title, body = _article_text(html)
        self.assertEqual(title, "今日大新闻")
        self.assertIn("正文内容", body.replace(" ", ""))
        self.assertNotIn("<", body)
        self.assertNotIn("color:red", body)  # style 块被剔除

    def test_no_title_returns_empty(self):
        title, _ = _article_text("<p>无标题</p>")
        self.assertEqual(title, "")


class TestArticleCategory(unittest.TestCase):
    def test_extracts_kicker_category(self):
        html = '<span class="kicker">AI · 行业观察</span><h1>标题</h1>'
        self.assertEqual(_article_category(html), "AI · 行业观察")

    def test_missing_kicker_returns_empty(self):
        self.assertEqual(_article_category("<h1>标题</h1>"), "")


class TestParseJson(unittest.TestCase):
    def test_strips_code_fence(self):
        self.assertEqual(_parse_json('```json\n{"a": 1}\n```'), {"a": 1})


class TestCompose(unittest.TestCase):
    _COPY = {"category": "产业 · 风险投资", "title": "早期吃掉晚期",
             "data": "Q1融资$21亿 反超晚期", "tagline_en": "EARLY BEATS LATE",
             "hook": "B轮即独角兽"}

    def test_creates_cover_with_wechat_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            bg = os.path.join(tmp, "bg.png")
            Image.new("RGB", (800, 340), (200, 200, 200)).save(bg)
            out = os.path.join(tmp, "cover.png")
            _compose(bg, self._COPY, out)
            self.assertTrue(os.path.exists(out))
            self.assertEqual(Image.open(out).size, (W, H))

    def test_long_title_does_not_crash(self):
        """超长标题应被自适应字号塞下，不抛异常。"""
        with tempfile.TemporaryDirectory() as tmp:
            bg = os.path.join(tmp, "bg.png")
            Image.new("RGB", (W, H), (220, 220, 220)).save(bg)
            copy = dict(self._COPY, title="一个非常非常非常长的封面主标题远超宽度限制")
            out = os.path.join(tmp, "c.png")
            _compose(bg, copy, out)
            self.assertTrue(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
