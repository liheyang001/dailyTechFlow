"""notifier 模块单测。mock 掉 SMTP，不发真邮件。

运行：python tests/test_notifier.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import notifier

_EC = {"smtp_host": "h", "smtp_port": 587, "sender": "a@x.com",
       "recipient": "b@x.com", "password": "pw"}


def _make_article(base, date_str, html='<h1 class="title">今日大新闻</h1><p>正文</p>'):
    day = os.path.join(base, date_str)
    os.makedirs(day, exist_ok=True)
    with open(os.path.join(day, "wechat_article.html"), "w", encoding="utf-8") as f:
        f.write(html)


def test_extract_title():
    assert notifier._extract_title('<h1 class="t">标题A</h1>', "fb") == "标题A"
    assert notifier._extract_title("<p>无h1</p>", "fb") == "fb"


def test_cover_block_empty_when_missing():
    assert notifier._cover_block("") == ""
    assert notifier._cover_block("/no/such/cover.png") == ""


def test_cover_block_inlines_existing_image():
    with tempfile.TemporaryDirectory() as base:
        p = os.path.join(base, "cover.png")
        with open(p, "wb") as f:
            f.write(b"\x89PNG\r\n fake")
        block = notifier._cover_block(p)
        assert block.startswith('<img src="data:image/png;base64,')


def test_article_text_strips_tags():
    txt = notifier._article_text('<body><h1>标题</h1><p>第一段</p><p>第二段</p></body>')
    assert "标题" in txt and "第一段" in txt and "第二段" in txt
    assert "<" not in txt  # 标签都去掉了


def test_build_message_attaches_full_html_and_keeps_body_light():
    """完整带封面 HTML 进附件；正文不内嵌大图（杜绝 Gmail 截断）。"""
    with tempfile.TemporaryDirectory() as base:
        cover = os.path.join(base, "cover.png")
        with open(cover, "wb") as f:
            f.write(b"\x89PNG\r\n fake")
        html = ('<!DOCTYPE html><html><head><meta charset="UTF-8">'
                '<title>标题X</title></head><body>'
                '<h1>标题X</h1><p>正文段落</p></body></html>')
        msg = notifier._build_message(_EC, "2026-05-20", html, "标题X", cover)

        atts = [p for p in msg.walk() if p.get_content_disposition() == "attachment"]
        names = [a.get_filename() for a in atts]
        assert "cover.png" in names                       # 封面 PNG 作为独立附件
        html_atts = [a for a in atts if a.get_filename().endswith(".html")]
        assert len(html_atts) == 1
        # 封面附件是真实 PNG 字节
        png = [a for a in atts if a.get_filename() == "cover.png"][0]
        assert png.get_payload(decode=True).startswith(b"\x89PNG")
        payload = html_atts[0].get_payload(decode=True).decode("utf-8")
        assert "正文段落" in payload                       # 文章在附件
        assert "data:image/png;base64," in payload         # 封面也在附件
        # 关键：<meta charset> 必须排在巨大的 base64 封面之前，
        # 否则被挤出浏览器前 1024 字节嗅探窗口 → 中文乱码
        assert payload.index("charset") < payload.index("base64,")

        body_parts = [p.get_payload(decode=True).decode("utf-8") for p in msg.walk()
                      if p.get_content_type() in ("text/plain", "text/html")
                      and p.get_content_disposition() != "attachment"]
        assert any("正文段落" in b for b in body_parts)      # 正文有文字预览
        assert all("base64," not in b for b in body_parts)  # 正文无大图


def test_missing_article_returns_false():
    with tempfile.TemporaryDirectory() as base:
        cfg = {"output_base": base, "email": _EC}
        assert notifier.run("2026-05-20", cfg) is False


def test_no_password_skips_gracefully():
    with tempfile.TemporaryDirectory() as base:
        _make_article(base, "2026-05-20")
        ec = dict(_EC, password="")  # 没配密码
        cfg = {"output_base": base, "email": ec}
        assert notifier.run("2026-05-20", cfg) is True  # 跳过但不报错


def test_sends_when_configured(monkeypatch):
    sent = {}

    class _FakeSMTP:
        def __init__(self, host, port):
            sent["host"], sent["port"] = host, port

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context=None):
            pass

        def login(self, u, p):
            sent["login"] = (u, p)

        def send_message(self, msg):
            sent["subject"] = msg["Subject"]
            sent["to"] = msg["To"]

    monkeypatch.setattr(notifier.smtplib, "SMTP", _FakeSMTP)
    with tempfile.TemporaryDirectory() as base:
        _make_article(base, "2026-05-20")
        cfg = {"output_base": base, "email": _EC}
        assert notifier.run("2026-05-20", cfg) is True
    assert sent["login"] == ("a@x.com", "pw")
    assert sent["to"] == "b@x.com"
    assert "今日大新闻" in sent["subject"]


def test_send_failure_writes_fallback_note(monkeypatch):
    """邮件发送失败时落地一张便条（错误 + 成品位置），不丢成品，返回 False。"""
    class _BoomSMTP:
        def __init__(self, *a):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context=None):
            pass

        def login(self, u, p):
            pass

        def send_message(self, msg):
            raise RuntimeError("smtp boom")

    monkeypatch.setattr(notifier.smtplib, "SMTP", _BoomSMTP)
    with tempfile.TemporaryDirectory() as base:
        _make_article(base, "2026-05-20")
        cfg = {"output_base": base, "email": _EC}
        assert notifier.run("2026-05-20", cfg) is False
        note = os.path.join(base, "2026-05-20", "EMAIL_FAILED.md")
        assert os.path.exists(note)
        content = open(note, encoding="utf-8").read()
        assert "smtp boom" in content
        assert "wechat_article.html" in content


# ---- 极简 pytest 替身（支持 monkeypatch fixture）----
class _MonkeyPatch:
    def __init__(self):
        self._undo = []

    def setattr(self, obj, name, value):
        self._undo.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def undo(self):
        for obj, name, old in reversed(self._undo):
            setattr(obj, name, old)


def _run():
    import inspect
    fns = [(n, f) for n, f in globals().items()
           if n.startswith("test_") and callable(f)]
    passed = 0
    for name, fn in fns:
        mp = None
        if "monkeypatch" in inspect.signature(fn).parameters:
            mp = _MonkeyPatch()
        try:
            fn(mp) if mp else fn()
            print(f"  PASS {name}")
            passed += 1
        finally:
            if mp:
                mp.undo()
    print(f"\n{passed}/{len(fns)} passed")
    return passed == len(fns)


if __name__ == "__main__":
    sys.exit(0 if _run() else 1)
