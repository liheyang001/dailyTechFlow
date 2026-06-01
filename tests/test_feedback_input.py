"""feedback_input CLI 单测。

用临时 config + 临时 output 目录，不碰真实数据。
运行：python tests/test_feedback_input.py
"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import feedback_input as fi


def _setup(base, date_str, make_pick=True):
    """造一个临时 config.yaml + output/<date> 目录，返回 config 路径。"""
    out = os.path.join(base, "output")
    day = os.path.join(out, date_str)
    os.makedirs(day, exist_ok=True)
    if make_pick:
        with open(os.path.join(day, "pick.json"), "w", encoding="utf-8") as f:
            json.dump({"title": "T"}, f)
    cfg = os.path.join(base, "config.yaml")
    with open(cfg, "w", encoding="utf-8") as f:
        f.write(f'output_base: "{out.replace(os.sep, "/")}"\n')  # 正斜杠，避免 YAML 反斜杠转义
    return cfg, out


def test_writes_metrics_json():
    with tempfile.TemporaryDirectory() as base:
        cfg, out = _setup(base, "2026-05-20")
        rc = fi.main(["1500", "8", "2026-05-20"], config_path=cfg)
        assert rc == 0
        m = json.load(open(os.path.join(out, "2026-05-20", "metrics.json"), encoding="utf-8"))
        assert m == {"reads": 1500, "comments": 8, "likes": 0, "shares": 0}


def test_writes_likes_and_shares():
    with tempfile.TemporaryDirectory() as base:
        cfg, out = _setup(base, "2026-05-20")
        rc = fi.main(["1500", "8", "2026-05-20", "--likes", "30", "--shares", "5"],
                     config_path=cfg)
        assert rc == 0
        m = json.load(open(os.path.join(out, "2026-05-20", "metrics.json"), encoding="utf-8"))
        assert m == {"reads": 1500, "comments": 8, "likes": 30, "shares": 5}


def test_negative_rejected():
    with tempfile.TemporaryDirectory() as base:
        cfg, _ = _setup(base, "2026-05-20")
        try:
            fi.main(["-5", "1", "2026-05-20"], config_path=cfg)
            assert False, "负数应被拒绝"
        except SystemExit as e:
            assert e.code != 0


def test_bad_date_rejected():
    with tempfile.TemporaryDirectory() as base:
        cfg, _ = _setup(base, "2026-05-20")
        try:
            fi.main(["100", "1", "not-a-date"], config_path=cfg)
            assert False, "非法日期应被拒绝"
        except SystemExit as e:
            assert e.code != 0


def test_missing_day_dir_errors():
    with tempfile.TemporaryDirectory() as base:
        cfg, _ = _setup(base, "2026-05-20")
        try:
            fi.main(["100", "1", "2026-01-01"], config_path=cfg)  # 这天目录不存在
            assert False, "目录不存在应报错"
        except FileNotFoundError:
            pass


def test_missing_pick_still_writes():
    """目录在但没 pick.json：警告但仍写入（用户可能知道自己在干嘛）。"""
    with tempfile.TemporaryDirectory() as base:
        cfg, out = _setup(base, "2026-05-20", make_pick=False)
        rc = fi.main(["100", "1", "2026-05-20"], config_path=cfg)
        assert rc == 0
        assert os.path.exists(os.path.join(out, "2026-05-20", "metrics.json"))


def _run():
    fns = [(n, f) for n, f in globals().items()
           if n.startswith("test_") and callable(f)]
    passed = 0
    for name, fn in fns:
        fn()
        print(f"  PASS {name}")
        passed += 1
    print(f"\n{passed}/{len(fns)} passed")
    return passed == len(fns)


if __name__ == "__main__":
    sys.exit(0 if _run() else 1)
