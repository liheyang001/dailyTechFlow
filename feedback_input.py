#!/usr/bin/env python
"""给某天的文章手动填阅读/评论/点赞/转发数，写进 output/<date>/metrics.json。

feedback 模块会读这个文件来打分、沉淀经验。点赞/转发微信无自动接口，
但你能从后台抄数字，用 --likes/--shares 填进来一并纳入打分；不填默认 0。

用法：
    python feedback_input.py <阅读数> <评论数> [日期YYYY-MM-DD] [--likes N] [--shares N]
例：
    python feedback_input.py 1500 8                        # 填今天，点赞/转发记 0
    python feedback_input.py 1500 8 2026-05-29             # 填指定某天
    python feedback_input.py 1500 8 --likes 30 --shares 5  # 带点赞/转发
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


def write_metrics(output_base: str, date_str: str, reads: int, comments: int,
                  likes: int = 0, shares: int = 0) -> str:
    """写 metrics.json，返回路径。目录不存在（那天没跑过流水线）则报错。"""
    day_dir = os.path.join(output_base, date_str)
    if not os.path.isdir(day_dir):
        raise FileNotFoundError(f"目录不存在：{day_dir}（{date_str} 这天没跑过流水线？日期填错了？）")
    path = os.path.join(day_dir, "metrics.json")
    data = {"reads": reads, "comments": comments, "likes": likes, "shares": shares}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def main(argv=None, config_path: str = "config.yaml") -> int:
    p = argparse.ArgumentParser(description="给某天文章手动填阅读/评论数")
    p.add_argument("reads", type=int, help="阅读数")
    p.add_argument("comments", type=int, help="评论数")
    p.add_argument("date", nargs="?", default=_date.today().isoformat(),
                   type=_valid_date, help="日期 YYYY-MM-DD，默认今天")
    p.add_argument("--likes", type=int, default=0, help="点赞数（可选，默认 0）")
    p.add_argument("--shares", type=int, default=0, help="转发/分享数（可选，默认 0）")
    args = p.parse_args(argv)

    if min(args.reads, args.comments, args.likes, args.shares) < 0:
        p.error("阅读/评论/点赞/转发数都不能为负")

    with open(config_path, encoding="utf-8") as f:
        output_base = yaml.safe_load(f)["output_base"]

    if not os.path.exists(os.path.join(output_base, args.date, "pick.json")):
        print(f"[警告] {args.date} 没有 pick.json，这天可能没发文章。仍按你的输入写入。")

    path = write_metrics(output_base, args.date, args.reads, args.comments,
                         args.likes, args.shares)
    print(f"已写入 {path}：阅读 {args.reads}，评论 {args.comments}，"
          f"点赞 {args.likes}，转发 {args.shares}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
