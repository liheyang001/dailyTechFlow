import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.publisher import (
    run,
    _get_access_token,
    _upload_thumb,
    _md_to_wechat_html,
    _extract_title,
    _extract_digest,
    _create_draft,
    _publish_draft,
)


def _urlopen_mock(response_data: dict):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_data).encode("utf-8")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def _make_output(tmp: str, date_str: str = "2026-05-28") -> str:
    date_dir = os.path.join(tmp, date_str)
    os.makedirs(date_dir, exist_ok=True)
    Path(os.path.join(date_dir, "article_zh.md")).write_text(
        "# 每日科技速递\n\n今天三条科技新闻值得关注。\n\n## 新闻一\n\n**重要进展**",
        encoding="utf-8",
    )
    Path(os.path.join(date_dir, "cover_zh.png")).write_bytes(b"\x89PNG\r\n\x1a\n")
    return date_dir


def _make_config(output_base: str, auto_publish: bool = False) -> dict:
    return {
        "output_base": output_base,
        "wechat": {
            "app_id": "wx_test_appid",
            "app_secret": "test_secret",
            "auto_publish": auto_publish,
        },
    }


# ---------------------------------------------------------------------------
# _get_access_token
# ---------------------------------------------------------------------------

class TestGetAccessToken(unittest.TestCase):
    @patch("src.publisher.urllib.request.urlopen")
    def test_returns_token(self, mock_urlopen):
        mock_urlopen.return_value = _urlopen_mock({"access_token": "TOKEN123", "expires_in": 7200})
        token = _get_access_token("app1", "secret1")
        self.assertEqual(token, "TOKEN123")

    @patch("src.publisher.urllib.request.urlopen")
    def test_missing_token_raises(self, mock_urlopen):
        mock_urlopen.return_value = _urlopen_mock({"errcode": 40013, "errmsg": "invalid appid"})
        with self.assertRaises(RuntimeError):
            _get_access_token("bad_app", "bad_secret")


# ---------------------------------------------------------------------------
# _upload_thumb
# ---------------------------------------------------------------------------

class TestUploadThumb(unittest.TestCase):
    @patch("src.publisher.urllib.request.urlopen")
    def test_returns_media_id(self, mock_urlopen):
        mock_urlopen.return_value = _urlopen_mock({"media_id": "MEDIA_001", "url": "http://x"})
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG\r\n\x1a\n")
            tmp = f.name
        try:
            media_id = _upload_thumb("TOKEN", tmp)
            self.assertEqual(media_id, "MEDIA_001")
        finally:
            os.unlink(tmp)

    @patch("src.publisher.urllib.request.urlopen")
    def test_upload_error_raises(self, mock_urlopen):
        mock_urlopen.return_value = _urlopen_mock({"errcode": 40007, "errmsg": "invalid media_id"})
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG")
            tmp = f.name
        try:
            with self.assertRaises(RuntimeError):
                _upload_thumb("TOKEN", tmp)
        finally:
            os.unlink(tmp)


# ---------------------------------------------------------------------------
# _md_to_wechat_html
# ---------------------------------------------------------------------------

class TestMdToWechatHtml(unittest.TestCase):
    def test_h1_centered(self):
        html = _md_to_wechat_html("# 标题")
        self.assertIn('<h1 style="text-align:center">标题</h1>', html)

    def test_h2(self):
        html = _md_to_wechat_html("## 子标题")
        self.assertIn("<h2>子标题</h2>", html)

    def test_h3(self):
        html = _md_to_wechat_html("### 三级标题")
        self.assertIn("<h3>三级标题</h3>", html)

    def test_paragraph(self):
        html = _md_to_wechat_html("普通段落文字")
        self.assertIn("<p>普通段落文字</p>", html)

    def test_bold(self):
        html = _md_to_wechat_html("**重要**内容")
        self.assertIn("<strong>重要</strong>", html)

    def test_italic(self):
        html = _md_to_wechat_html("*斜体*文字")
        self.assertIn("<em>斜体</em>", html)

    def test_empty_lines_skipped(self):
        html = _md_to_wechat_html("行一\n\n\n行二")
        self.assertEqual(html.count("<p>"), 2)

    def test_full_article(self):
        md = "# 标题\n\n正文段落。\n\n## 小节\n\n**重点**文字"
        html = _md_to_wechat_html(md)
        self.assertIn('<h1 style="text-align:center">标题</h1>', html)
        self.assertIn("<h2>小节</h2>", html)
        self.assertIn("<strong>重点</strong>", html)


# ---------------------------------------------------------------------------
# _extract_title / _extract_digest
# ---------------------------------------------------------------------------

class TestExtractTitle(unittest.TestCase):
    def test_extracts_h1(self):
        self.assertEqual(_extract_title("# 每日科技速递\n\n段落"), "每日科技速递")

    def test_skips_h2(self):
        self.assertEqual(_extract_title("## 子标题\n段落"), "每日科技速递")

    def test_fallback_when_no_h1(self):
        self.assertEqual(_extract_title("没有标题的文本"), "每日科技速递")


class TestExtractDigest(unittest.TestCase):
    def test_extracts_first_paragraph(self):
        md = "# 标题\n\n第一段摘要文字。\n\n第二段"
        self.assertEqual(_extract_digest(md), "第一段摘要文字。")

    def test_truncates_at_max_len(self):
        md = "# 标题\n\n" + "很" * 200
        digest = _extract_digest(md, max_len=120)
        self.assertEqual(len(digest), 120)

    def test_empty_article(self):
        self.assertEqual(_extract_digest(""), "")


# ---------------------------------------------------------------------------
# _create_draft
# ---------------------------------------------------------------------------

class TestCreateDraft(unittest.TestCase):
    @patch("src.publisher.urllib.request.urlopen")
    def test_returns_media_id(self, mock_urlopen):
        mock_urlopen.return_value = _urlopen_mock({"media_id": "DRAFT_001"})
        media_id = _create_draft("TOKEN", "标题", "<p>内容</p>", "THUMB_001", "摘要")
        self.assertEqual(media_id, "DRAFT_001")

    @patch("src.publisher.urllib.request.urlopen")
    def test_sends_correct_payload(self, mock_urlopen):
        mock_urlopen.return_value = _urlopen_mock({"media_id": "DRAFT_001"})
        _create_draft("TOKEN", "标题", "<p>内容</p>", "THUMB_001", "摘要")
        req = mock_urlopen.call_args[0][0]
        body = json.loads(req.data.decode("utf-8"))
        article = body["articles"][0]
        self.assertEqual(article["title"], "标题")
        self.assertEqual(article["thumb_media_id"], "THUMB_001")
        self.assertEqual(article["content"], "<p>内容</p>")

    @patch("src.publisher.urllib.request.urlopen")
    def test_draft_error_raises(self, mock_urlopen):
        mock_urlopen.return_value = _urlopen_mock({"errcode": 45009, "errmsg": "reach max api"})
        with self.assertRaises(RuntimeError):
            _create_draft("TOKEN", "标题", "<p>内容</p>", "THUMB_001", "摘要")


# ---------------------------------------------------------------------------
# _publish_draft
# ---------------------------------------------------------------------------

class TestPublishDraft(unittest.TestCase):
    @patch("src.publisher.urllib.request.urlopen")
    def test_returns_publish_id(self, mock_urlopen):
        mock_urlopen.return_value = _urlopen_mock({"errcode": 0, "publish_id": "PUB_001"})
        publish_id = _publish_draft("TOKEN", "DRAFT_001")
        self.assertEqual(publish_id, "PUB_001")

    @patch("src.publisher.urllib.request.urlopen")
    def test_publish_error_raises(self, mock_urlopen):
        mock_urlopen.return_value = _urlopen_mock({"errcode": 45009, "errmsg": "reach max api"})
        with self.assertRaises(RuntimeError):
            _publish_draft("TOKEN", "DRAFT_001")


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

class TestRun(unittest.TestCase):
    def test_missing_credentials_raises(self):
        config = {"output_base": "/tmp", "wechat": {"app_id": "", "app_secret": ""}}
        with self.assertRaises(ValueError):
            run("2026-05-28", config)

    def test_missing_article_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                run("2026-05-28", _make_config(tmp))

    def test_missing_cover_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            date_dir = os.path.join(tmp, "2026-05-28")
            os.makedirs(date_dir)
            Path(os.path.join(date_dir, "article_zh.md")).write_text("# 标题\n\n内容", encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                run("2026-05-28", _make_config(tmp))

    @patch("src.publisher._get_access_token", return_value="TOKEN")
    @patch("src.publisher._upload_thumb", return_value="THUMB_001")
    @patch("src.publisher._create_draft", return_value="DRAFT_001")
    def test_success_draft_mode(self, mock_draft, mock_upload, mock_token):
        with tempfile.TemporaryDirectory() as tmp:
            _make_output(tmp)
            result = run("2026-05-28", _make_config(tmp, auto_publish=False))
            self.assertTrue(result)
            mock_token.assert_called_once_with("wx_test_appid", "test_secret")
            mock_upload.assert_called_once()
            mock_draft.assert_called_once()

    @patch("src.publisher._get_access_token", return_value="TOKEN")
    @patch("src.publisher._upload_thumb", return_value="THUMB_001")
    @patch("src.publisher._create_draft", return_value="DRAFT_001")
    @patch("src.publisher._publish_draft", return_value="PUB_001")
    def test_success_auto_publish(self, mock_publish, mock_draft, mock_upload, mock_token):
        with tempfile.TemporaryDirectory() as tmp:
            _make_output(tmp)
            result = run("2026-05-28", _make_config(tmp, auto_publish=True))
            self.assertTrue(result)
            mock_publish.assert_called_once_with("TOKEN", "DRAFT_001")

    @patch("src.publisher._get_access_token", side_effect=RuntimeError("token failed"))
    def test_api_error_returns_false(self, mock_token):
        with tempfile.TemporaryDirectory() as tmp:
            _make_output(tmp)
            result = run("2026-05-28", _make_config(tmp))
            self.assertFalse(result)

    @patch("src.publisher._get_access_token", return_value="TOKEN")
    @patch("src.publisher._upload_thumb", side_effect=RuntimeError("upload failed"))
    def test_upload_error_returns_false(self, mock_upload, mock_token):
        with tempfile.TemporaryDirectory() as tmp:
            _make_output(tmp)
            result = run("2026-05-28", _make_config(tmp))
            self.assertFalse(result)

    @patch("src.publisher._get_access_token", return_value="TOKEN")
    @patch("src.publisher._upload_thumb", return_value="THUMB_001")
    @patch("src.publisher._create_draft", return_value="DRAFT_001")
    def test_draft_not_published_when_auto_publish_false(self, mock_draft, mock_upload, mock_token):
        with tempfile.TemporaryDirectory() as tmp:
            _make_output(tmp)
            with patch("src.publisher._publish_draft") as mock_publish:
                run("2026-05-28", _make_config(tmp, auto_publish=False))
                mock_publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
