import logging
import os
import sys
import time
from datetime import date

import yaml

from src import (
    article_writer,
    balance_alert,
    news_fetcher,
    researcher,
    selector,
)

# 每日精品图文流水线：抓新闻 → 挑最有影响力的一条 → 深抓资料 → 写成公众号文章
# 视频相关模块（image_generator / voice_generator / video_synthesizer / publisher）
# 暂从流水线移除，文件保留，待图文稳定后再启用。
MODULES = [
    ("M1 news_fetcher",   news_fetcher),
    ("M2 selector",       selector),
    ("M3 researcher",     researcher),
    ("M4 article_writer", article_writer),
    ("M7 balance_alert",  balance_alert),
]


def _load_config(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _setup_logging(date_str: str, config: dict) -> logging.Logger:
    output_base = config.get("output_base", "output")
    day_dir = os.path.join(output_base, date_str)
    os.makedirs(day_dir, exist_ok=True)
    os.makedirs("logs", exist_ok=True)

    run_log = os.path.join(day_dir, "run.log")
    backup_log = os.path.join("logs", f"{date_str}.log")

    logger = logging.getLogger(f"main.{date_str}")
    logger.setLevel(logging.INFO)
    # 清除上一次运行残留的 handlers
    logger.handlers.clear()
    logger.propagate = False

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    for path in (run_log, backup_log):
        h = logging.FileHandler(path, encoding="utf-8")
        h.setFormatter(fmt)
        logger.addHandler(h)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger


def run(date_str: str | None = None) -> dict:
    if date_str is None:
        date_str = date.today().isoformat()

    config = _load_config()
    logger = _setup_logging(date_str, config)

    logger.info("=" * 60)
    logger.info(f"DailyTechFlow 开始运行，日期：{date_str}")
    logger.info("=" * 60)

    results = {}
    timings = {}
    pipeline_start = time.monotonic()

    for name, module in MODULES:
        logger.info(f"--- {name} 开始 ---")
        t0 = time.monotonic()
        try:
            ok = module.run(date_str, config)
            elapsed = time.monotonic() - t0
            timings[name] = elapsed
            results[name] = "ok" if ok else "failed"
            if ok:
                logger.info(f"{name} 完成（{elapsed:.1f}s）")
            else:
                logger.warning(f"{name} 返回 False（{elapsed:.1f}s），继续下一模块")
        except Exception as exc:
            elapsed = time.monotonic() - t0
            timings[name] = elapsed
            results[name] = f"error: {exc}"
            logger.error(f"{name} 异常（{elapsed:.1f}s）：{exc}", exc_info=True)
            logger.warning(f"{name} 失败，继续执行后续模块")

    total = time.monotonic() - pipeline_start
    logger.info("=" * 60)
    logger.info(f"运行结束，总耗时 {total:.1f}s，汇总：")
    for name, status in results.items():
        logger.info(f"  {name}: {status}（{timings[name]:.1f}s）")
    logger.info("=" * 60)

    return results


if __name__ == "__main__":
    date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    run(date_arg)
