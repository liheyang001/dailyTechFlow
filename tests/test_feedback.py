"""feedback 模块单测。

纯逻辑 + tmp 目录聚合 + mock 掉 Claude 调用，不打真实 API。
运行：python tests/test_feedback.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from src import feedback


@pytest.fixture
def tmp_lessons_dir(monkeypatch, tmp_path):
    """切到 tmp 工作目录并建好 feedback/，让 _distill/read_lessons 读写隔离的 lessons.md，不污染项目。"""
    monkeypatch.chdir(tmp_path)
    os.makedirs(feedback.FEEDBACK_DIR, exist_ok=True)
    return str(tmp_path)


def _make_day(base, date_str, title, reason, reads=None, comments=None,
              likes=None, shares=None):
    """在 tmp output_base 下造一天的 pick.json（+可选 metrics.json）。"""
    day = os.path.join(base, date_str)
    os.makedirs(day, exist_ok=True)
    with open(os.path.join(day, "pick.json"), "w", encoding="utf-8") as f:
        json.dump({"title": title, "reason": reason}, f, ensure_ascii=False)
    if reads is not None:
        m = {"reads": reads, "comments": comments}
        if likes is not None:
            m["likes"] = likes
        if shares is not None:
            m["shares"] = shares
        with open(os.path.join(day, "metrics.json"), "w", encoding="utf-8") as f:
            json.dump(m, f, ensure_ascii=False)


def test_score_weights_comments():
    """评论按权重放大；得分应高于纯阅读。"""
    assert feedback._score(100, 0, 50) == 100
    assert feedback._score(100, 2, 50) == 200


def test_score_weights_likes_and_shares():
    """点赞、转发按各自权重计入得分。"""
    # 阅读100 + 评论1×50 + 点赞2×20 + 转发1×100 = 290
    assert feedback._score(100, 1, 50, likes=2, shares=1,
                           like_weight=20, share_weight=100) == 290
    # 不传点赞/转发时退回旧行为
    assert feedback._score(100, 1, 50) == 150


def test_collect_manual_reads_metrics():
    with tempfile.TemporaryDirectory() as base:
        _make_day(base, "2026-05-20", "T", "r", reads=888, comments=3,
                  likes=10, shares=2)
        cfg = {"output_base": base}
        m = feedback.collect_manual("2026-05-20", cfg)
        assert m == {"reads": 888, "comments": 3, "likes": 10, "shares": 2}


def test_collect_manual_defaults_missing_likes_shares_to_zero():
    """旧 metrics.json 没有 likes/shares 字段时默认 0，向后兼容。"""
    with tempfile.TemporaryDirectory() as base:
        _make_day(base, "2026-05-20", "T", "r", reads=500, comments=1)
        m = feedback.collect_manual("2026-05-20", {"output_base": base})
        assert m == {"reads": 500, "comments": 1, "likes": 0, "shares": 0}


def test_collect_manual_missing_returns_none():
    with tempfile.TemporaryDirectory() as base:
        _make_day(base, "2026-05-20", "T", "r")  # 没填 metrics.json
        assert feedback.collect_manual("2026-05-20", {"output_base": base}) is None


def test_aggregate_skips_days_without_metrics_and_sorts_by_score():
    with tempfile.TemporaryDirectory() as base:
        _make_day(base, "2026-05-28", "低分文", "角度A", reads=100, comments=0)   # 100
        _make_day(base, "2026-05-29", "高分文", "角度B", reads=200, comments=5)   # 450
        _make_day(base, "2026-05-30", "没数据", "角度C")                          # 跳过
        cfg = {"output_base": base}
        recs = feedback._aggregate("2026-05-31", cfg, lookback=30,
                                   comment_weight=50, source="manual")
        assert len(recs) == 2  # 没数据那天被跳过
        assert recs[0]["title"] == "高分文" and recs[0]["score"] == 450
        assert recs[1]["title"] == "低分文" and recs[1]["score"] == 100
        assert recs[0]["angle"] == "角度B"


def test_aggregate_counts_likes_and_shares():
    """点赞/转发参与打分，能把低阅读但高转发的文章排到前面。"""
    with tempfile.TemporaryDirectory() as base:
        # 阅读高但无互动：300
        _make_day(base, "2026-05-28", "纯阅读", "角度A", reads=300, comments=0)
        # 阅读低但转发多：50 + 3×100 = 350
        _make_day(base, "2026-05-29", "高转发", "角度B", reads=50, comments=0,
                  likes=0, shares=3)
        recs = feedback._aggregate("2026-05-31", {"output_base": base}, lookback=30,
                                   comment_weight=50, source="manual",
                                   like_weight=20, share_weight=100)
        assert recs[0]["title"] == "高转发" and recs[0]["score"] == 350
        assert recs[0]["shares"] == 3
        assert recs[1]["title"] == "纯阅读" and recs[1]["score"] == 300


def test_distill_writes_lessons_with_mocked_claude(monkeypatch, tmp_lessons_dir):
    """_distill 应把 Claude 返回写进 lessons.md，且不真的打 API。"""
    class _FakeMsg:
        text = "【选题方向】\n- 融资类更火\n【写作建议】\n- 标题带数字"

    class _FakeResp:
        content = [_FakeMsg()]

    class _FakeClient:
        def __init__(self, *a, **k):
            self.messages = self

        def create(self, *a, **k):
            return _FakeResp()

    monkeypatch.setattr(feedback.anthropic, "Anthropic", _FakeClient)
    records = [{"date": "2026-05-29", "title": "高分文", "angle": "融资",
                "reads": 200, "comments": 5, "score": 450}]
    cfg = {"anthropic": {"api_key": "x", "model": "m"}}
    feedback._distill(records, cfg)
    assert os.path.exists(feedback.LESSONS_PATH)
    content = open(feedback.LESSONS_PATH, encoding="utf-8").read()
    assert "融资类更火" in content
    assert "基于 1 篇" in content


def test_read_lessons_empty_when_absent(tmp_lessons_dir):
    assert feedback.read_lessons() == ""


# ---- 极简 pytest 替身：支持 monkeypatch 与 tmp_lessons_dir 两个 fixture ----
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
        params = inspect.signature(fn).parameters
        kwargs, mp, cwd = {}, None, os.getcwd()
        tmp = None
        if "monkeypatch" in params:
            mp = _MonkeyPatch()
            kwargs["monkeypatch"] = mp
        if "tmp_lessons_dir" in params:
            tmp = tempfile.TemporaryDirectory()
            os.chdir(tmp.name)  # FEEDBACK_DIR 是相对路径，切到 tmp 避免污染项目
            os.makedirs(feedback.FEEDBACK_DIR, exist_ok=True)
            kwargs["tmp_lessons_dir"] = tmp.name
        try:
            fn(**kwargs)
            print(f"  PASS {name}")
            passed += 1
        finally:
            if mp:
                mp.undo()
            os.chdir(cwd)
            if tmp:
                tmp.cleanup()
    print(f"\n{passed}/{len(fns)} passed")
    return passed == len(fns)


if __name__ == "__main__":
    sys.exit(0 if _run() else 1)
