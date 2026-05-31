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
