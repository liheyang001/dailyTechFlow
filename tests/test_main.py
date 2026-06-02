import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import main

DATE = "2099-01-01"

# 对齐 main.MODULES 的 8 模块图文流水线（视频链路已下线）
_MODULE_PATHS = [
    "src.news_fetcher.run",
    "src.selector.run",
    "src.researcher.run",
    "src.article_writer.run",
    "src.image_generator.run",
    "src.notifier.run",
    "src.balance_alert.run",
    "src.feedback.run",
]


def _patch_runs(side_effects: dict | None = None):
    """
    Patch all 8 module run() functions.
    side_effects: {short_name: exception_or_return_value}
      - If value is an Exception instance, it becomes side_effect.
      - Otherwise it becomes return_value.
    """
    side_effects = side_effects or {}

    class CM:
        def __enter__(self_):
            self_._patches = []
            self_.mocks = {}
            for path in _MODULE_PATHS:
                short = path.split(".")[1]  # e.g. "news_fetcher"
                p = patch(path)
                m = p.start()
                se = side_effects.get(short)
                if isinstance(se, BaseException):
                    m.side_effect = se
                elif se is not None:
                    m.return_value = se
                else:
                    m.return_value = True
                self_._patches.append(p)
                self_.mocks[short] = m
            return self_.mocks

        def __exit__(self_, *args):
            for p in self_._patches:
                p.stop()

    return CM()


def _mock_setup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        "output_base: output\ntavily:\n  api_key: ''\n"
        "anthropic:\n  api_key: ''\n  model: claude-x\n"
        "wechat:\n  app_id: ''\n  app_secret: ''\n  auto_publish: false\n"
    )


# ── 基础执行 ──────────────────────────────────────────────────────────────────

def test_all_modules_succeed(tmp_path, monkeypatch):
    _mock_setup(tmp_path, monkeypatch)
    with _patch_runs() as mocks:
        results = main.run(DATE)
    assert all(v == "ok" for v in results.values()), results
    for mod in mocks.values():
        mod.assert_called_once()
        assert mod.call_args[0][0] == DATE


def test_results_keys_order(tmp_path, monkeypatch):
    _mock_setup(tmp_path, monkeypatch)
    with _patch_runs():
        results = main.run(DATE)
    keys = list(results.keys())
    assert keys[0].startswith("M1")
    assert keys[-1].startswith("M8")


def test_eight_results_returned(tmp_path, monkeypatch):
    _mock_setup(tmp_path, monkeypatch)
    with _patch_runs():
        results = main.run(DATE)
    assert len(results) == 8


# ── 错误隔离 ──────────────────────────────────────────────────────────────────

def test_one_module_exception_does_not_abort(tmp_path, monkeypatch):
    _mock_setup(tmp_path, monkeypatch)
    with _patch_runs({"image_generator": RuntimeError("boom")}):
        results = main.run(DATE)
    m5_key = next(k for k in results if k.startswith("M5"))
    assert "error" in results[m5_key]
    # 后续 M6-M8 仍然执行
    for name in ["M6", "M7", "M8"]:
        key = next(k for k in results if k.startswith(name))
        assert results[key] == "ok", f"{key}: {results[key]}"


def test_module_returns_false_recorded(tmp_path, monkeypatch):
    _mock_setup(tmp_path, monkeypatch)
    with _patch_runs({"news_fetcher": False}):
        results = main.run(DATE)
    m1_key = next(k for k in results if k.startswith("M1"))
    assert results[m1_key] == "failed"


def test_false_module_does_not_abort_pipeline(tmp_path, monkeypatch):
    _mock_setup(tmp_path, monkeypatch)
    with _patch_runs({"selector": False}):
        results = main.run(DATE)
    assert len(results) == 8
    # M3-M8 仍然执行并返回 ok
    for name in ["M3", "M4", "M5", "M6", "M7", "M8"]:
        key = next(k for k in results if k.startswith(name))
        assert results[key] == "ok"


def test_all_modules_raise_still_returns_dict(tmp_path, monkeypatch):
    _mock_setup(tmp_path, monkeypatch)
    errors = {short: Exception("fail") for short in
              ["news_fetcher", "selector", "researcher", "article_writer",
               "image_generator", "notifier", "balance_alert", "feedback"]}
    with _patch_runs(errors):
        results = main.run(DATE)
    assert len(results) == 8
    assert all("error" in v for v in results.values()), results


def test_later_modules_run_after_early_failure(tmp_path, monkeypatch):
    _mock_setup(tmp_path, monkeypatch)
    with _patch_runs({"news_fetcher": RuntimeError("net error")}) as mocks:
        main.run(DATE)
    # M2-M8 全部被调用（早期失败不阻断后续）
    for name in ["selector", "researcher", "article_writer",
                 "image_generator", "notifier", "balance_alert", "feedback"]:
        mocks[name].assert_called_once()


# ── 日志文件 ──────────────────────────────────────────────────────────────────

def test_run_log_created(tmp_path, monkeypatch):
    _mock_setup(tmp_path, monkeypatch)
    with _patch_runs():
        main.run(DATE)
    log_path = tmp_path / "output" / DATE / "run.log"
    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "DailyTechFlow" in content


def test_backup_log_created(tmp_path, monkeypatch):
    _mock_setup(tmp_path, monkeypatch)
    with _patch_runs():
        main.run(DATE)
    backup = tmp_path / "logs" / f"{DATE}.log"
    assert backup.exists()


def test_output_dir_created(tmp_path, monkeypatch):
    _mock_setup(tmp_path, monkeypatch)
    with _patch_runs():
        main.run(DATE)
    assert (tmp_path / "output" / DATE).is_dir()


def test_error_logged_in_run_log(tmp_path, monkeypatch):
    _mock_setup(tmp_path, monkeypatch)
    with _patch_runs({"researcher": ValueError("bad research")}):
        main.run(DATE)
    content = (tmp_path / "output" / DATE / "run.log").read_text(encoding="utf-8")
    assert "bad research" in content


# ── 日期参数 ──────────────────────────────────────────────────────────────────

def test_custom_date_passed_to_modules(tmp_path, monkeypatch):
    _mock_setup(tmp_path, monkeypatch)
    custom = "2030-06-15"
    with _patch_runs() as mocks:
        main.run(custom)
    for mod in mocks.values():
        assert mod.call_args[0][0] == custom


def test_default_date_is_today(tmp_path, monkeypatch):
    _mock_setup(tmp_path, monkeypatch)
    from datetime import date
    today = date.today().isoformat()
    with _patch_runs() as mocks:
        main.run()
    for mod in mocks.values():
        assert mod.call_args[0][0] == today


def test_config_passed_to_modules(tmp_path, monkeypatch):
    _mock_setup(tmp_path, monkeypatch)
    with _patch_runs() as mocks:
        main.run(DATE)
    for mod in mocks.values():
        cfg = mod.call_args[0][1]
        assert isinstance(cfg, dict)
        assert "output_base" in cfg
