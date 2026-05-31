#!/usr/bin/env python
"""给某天的文章手动填阅读/评论数，写进 output/<date>/metrics.json。

feedback 模块会读这个文件来打分、沉淀经验。点赞/在看微信无公开接口，不填。

用法：
    python feedback_input.py <阅读数> <评论数> [日期YYYY-MM-DD]
例：
    python feedback_input.py 1500 8              # 填今天的文章
    python feedback_input.py 1500 8 2026-05-29   # 填指定某天
"""
import argparse
import json
import os
import sys
from datetime import date as _date

import yaml


def _valid_date(s: str) -> str:
    _date.fromisoformat(s)  # 格式非法会抛 ValueError，交给 argparse 报错
    return s


def write_metrics(output_base: str, date_str: str, reads: int, comments: int) -> str:
    """写 metrics.json，返回路径。目录不存在（那天没跑过流水线）则报错。"""
    day_dir = os.path.join(output_base, date_str)
    if not os.path.isdir(day_dir):
        raise FileNotFoundError(f"目录不存在：{day_dir}（{date_str} 这天没跑过流水线？日期填错了？）")
    path = os.path.join(day_dir, "metrics.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"reads": reads, "comments": comments}, f, ensure_ascii=False, indent=2)
    return path


def main(argv=None, config_path: str = "config.yaml") -> int:
    p = argparse.ArgumentParser(description="给某天文章手动填阅读/评论数")
    p.add_argument("reads", type=int, help="阅读数")
    p.add_argument("comments", type=int, help="评论数")
    p.add_argument("date", nargs="?", default=_date.today().isoformat(),
                   type=_valid_date, help="日期 YYYY-MM-DD，默认今天")
    args = p.parse_args(argv)

    if args.reads < 0 or args.comments < 0:
        p.error("阅读数和评论数不能为负")

    with open(config_path, encoding="utf-8") as f:
        output_base = yaml.safe_load(f)["output_base"]

    if not os.path.exists(os.path.join(output_base, args.date, "pick.json")):
        print(f"[警告] {args.date} 没有 pick.json，这天可能没发文章。仍按你的输入写入。")

    path = write_metrics(output_base, args.date, args.reads, args.comments)
    print(f"已写入 {path}：阅读 {args.reads}，评论 {args.comments}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
