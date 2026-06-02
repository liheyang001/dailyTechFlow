"""selector 查重逻辑单测（纯函数，不打 API）。

运行：python tests/test_selector.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.selector import _recent_picks


def _make_pick(base, date_str, title, reason):
    day = os.path.join(base, date_str)
    os.makedirs(day, exist_ok=True)
    with open(os.path.join(day, "pick.json"), "w", encoding="utf-8") as f:
        json.dump({"title": title, "reason": reason}, f, ensure_ascii=False)


def test_recent_picks_collects_title_and_reason():
    """查重要带上角度，模型才能从内核判断撞题（仅标题字面查不出同主题）。"""
    with tempfile.TemporaryDirectory() as base:
        _make_pick(base, "2026-06-02", "220 独角兽出局", "AI资本集中")
        _make_pick(base, "2026-06-01", "裁掉22%换AI", "AI裁员")
        picks = _recent_picks(base, "2026-06-03", days=7)
        titles = [p["title"] for p in picks]
        assert "220 独角兽出局" in titles and "裁掉22%换AI" in titles
        assert any(p["reason"] == "AI资本集中" for p in picks)


def test_recent_picks_skips_missing_days():
    with tempfile.TemporaryDirectory() as base:
        _make_pick(base, "2026-06-02", "T", "r")  # 只有 6/2 有
        picks = _recent_picks(base, "2026-06-03", days=3)
        assert len(picks) == 1
        assert picks[0] == {"title": "T", "reason": "r"}


def test_recent_picks_excludes_today_itself():
    """只回看过去的天，不含当天（range 从 1 开始）。"""
    with tempfile.TemporaryDirectory() as base:
        _make_pick(base, "2026-06-03", "今天的", "x")
        assert _recent_picks(base, "2026-06-03", days=7) == []


def test_recent_picks_bad_date_returns_empty():
    assert _recent_picks("/nope", "not-a-date") == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")
