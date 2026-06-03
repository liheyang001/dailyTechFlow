"""M8 反馈学习模块。

闭环：发布的文章拿到阅读+评论数据 → 打分排名 → 让 Claude 总结「什么样的文章受欢迎」
写进 feedback/lessons.md → selector / article_writer 每天把它注入提示词，越写越准。

数据采集是可切换的适配器（config['feedback']['source']）：
  - manual : 读 output/<date>/metrics.json（你从公众号后台抄数字填进去）。今天即可用、可测。
  - wechat : 调微信数据接口自动拉。【未验证·休眠】需已认证账号 + 数据统计权限 + config.wechat
             凭据齐全，缺一不可。凭据补齐前请保持 source=manual。

metrics.json 格式（手动填写）：
    {"reads": 1234, "comments": 12, "likes": 30, "shares": 5}
注：likes/shares（点赞、转发）微信无公开计数接口、自动 wechat 采集拉不到，记 0；
    但手动模式下你能从后台抄进来，会一并纳入打分。旧文件没这两字段则默认 0。

约定 run(date_str, config) -> bool。
本模块跨天读 output/ 并写 feedback/——已获用户批准突破「模块不跨目录」规则，
因为学习系统天生需要跨天聚合，不跨天就学不到东西。
"""
import json
import os
import re
import urllib.request
from datetime import date, timedelta

import anthropic

FEEDBACK_DIR = "feedback"
HISTORY_FILE = "history.jsonl"
LESSONS_FILE = "lessons.md"
LESSONS_PATH = os.path.join(FEEDBACK_DIR, LESSONS_FILE)

_WECHAT_API = "https://api.weixin.qq.com"


def _score(reads: int, comments: int, comment_weight: float,
           likes: int = 0, shares: int = 0,
           like_weight: float = 0.0, share_weight: float = 0.0) -> float:
    """得分 = 阅读 + 评论×权重 + 点赞×权重 + 转发×权重。

    高成本互动比阅读稀有得多，权重把它们放大成可比的量级。成本越高、越能代表真实
    认可的信号权重越大：转发（要署名转给别人）> 评论（要打字）> 点赞（一键）> 阅读。
    """
    return (reads + comments * comment_weight
            + likes * like_weight + shares * share_weight)


def _published_title(output_base: str, date_str: str) -> str:
    """从当天 wechat_article.html 的 <h1> 取真正发出去的中文标题；取不到返回空串。

    学习要学读者真正看到、决定点不点的那个中文标题，而非 pick.json 里的英文源标题
    ——标题正是阅读量的主要胜负手，学错对象等于白学。
    """
    p = os.path.join(output_base, date_str, "wechat_article.html")
    if not os.path.exists(p):
        return ""
    try:
        html = open(p, encoding="utf-8").read()
    except Exception:
        return ""
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    return re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""


def read_lessons() -> str:
    """读已沉淀的经验笔记；没有就返回空串。供 selector/article_writer 注入提示词。"""
    if not os.path.exists(LESSONS_PATH):
        return ""
    with open(LESSONS_PATH, encoding="utf-8") as f:
        return f.read().strip()


def collect_manual(date_str: str, config: dict) -> dict | None:
    """读当天目录里手动填的 metrics.json；没有就返回 None。"""
    p = os.path.join(config["output_base"], date_str, "metrics.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        m = json.load(f)
    return {
        "reads": int(m.get("reads", 0)),
        "comments": int(m.get("comments", 0)),
        "likes": int(m.get("likes", 0)),
        "shares": int(m.get("shares", 0)),
    }


def _wechat_token(app_id: str, app_secret: str) -> str:
    url = (
        f"{_WECHAT_API}/cgi-bin/token"
        f"?grant_type=client_credential&appid={app_id}&secret={app_secret}"
    )
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
    if "access_token" not in data:
        raise RuntimeError(f"WeChat token error: {data.get('errmsg', data)}")
    return data["access_token"]


def _wechat_post(path: str, token: str, payload: dict) -> dict:
    url = f"{_WECHAT_API}{path}?access_token={token}"
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def collect_wechat(date_str: str, config: dict) -> dict | None:
    """【未验证·休眠】用微信数据接口拉某天文章的阅读 + 评论，写进 metrics.json 再返回。

    字段依据微信官方文档（datacube/getarticletotal、comment/list），但当前账号无凭据，
    未经真实验证。阅读数取 int_page_read_count；评论数为 best-effort，拿不到记 0。
    按标题与当天 pick.json 匹配，不依赖 publish_id。
    """
    wechat = config.get("wechat", {})
    app_id, app_secret = wechat.get("app_id", ""), wechat.get("app_secret", "")
    if not app_id or not app_secret:
        raise RuntimeError("config.wechat 缺 app_id/app_secret，wechat 采集器无法工作")

    pick_p = os.path.join(config["output_base"], date_str, "pick.json")
    if not os.path.exists(pick_p):
        return None
    with open(pick_p, encoding="utf-8") as f:
        title = json.load(f).get("title", "")

    token = _wechat_token(app_id, app_secret)
    data = _wechat_post(
        "/datacube/getarticletotal", token,
        {"begin_date": date_str, "end_date": date_str},
    )
    reads, comments = 0, 0
    for art in data.get("list", []):
        details = art.get("details", [{}])
        d0 = details[0] if details else {}
        if art.get("title", "") == title or d0.get("title", "") == title:
            reads = int(d0.get("int_page_read_count", 0))
            try:  # 评论 best-effort：msgid 形如 "123_1"，拆出 msg_data_id 与 index
                msg_data_id, _, idx = str(art.get("msgid", "")).partition("_")
                c = _wechat_post(
                    "/cgi-bin/comment/list", token,
                    {"msg_data_id": int(msg_data_id), "index": max(int(idx or 1) - 1, 0),
                     "begin": 0, "count": 0, "type": 0},
                )
                comments = int(c.get("total", 0))
            except Exception:
                comments = 0
            break

    # 点赞/转发微信数据接口拿不到，记 0；手动模式才有这两个信号。
    metrics = {"reads": reads, "comments": comments, "likes": 0, "shares": 0}
    with open(os.path.join(config["output_base"], date_str, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    return metrics


_COLLECTORS = {"manual": collect_manual, "wechat": collect_wechat}


def _aggregate(date_str: str, config: dict, lookback: int,
               comment_weight: float, source: str,
               like_weight: float = 0.0, share_weight: float = 0.0) -> list:
    """回看 lookback 天，凑齐每篇文章的 选题 + 阅读/评论/点赞/转发，算分排名。"""
    out = config["output_base"]
    base = date.fromisoformat(date_str)
    records = []
    for i in range(lookback + 1):
        d = (base - timedelta(days=i)).isoformat()
        pick_p = os.path.join(out, d, "pick.json")
        if not os.path.exists(pick_p):
            continue
        metrics = collect_manual(d, config)
        if metrics is None and source == "wechat":
            try:
                metrics = collect_wechat(d, config)
            except Exception as e:
                print(f"[feedback] {d} 微信采集失败：{e}")
                metrics = None
        if metrics is None:
            continue
        with open(pick_p, encoding="utf-8") as f:
            pick = json.load(f)
        reads, comments = metrics["reads"], metrics["comments"]
        likes, shares = metrics.get("likes", 0), metrics.get("shares", 0)
        records.append({
            "date": d,
            "title": pick.get("title", ""),
            "headline": _published_title(out, d) or pick.get("title", ""),
            "angle": pick.get("reason", ""),
            "reads": reads,
            "comments": comments,
            "likes": likes,
            "shares": shares,
            "score": round(_score(reads, comments, comment_weight,
                                  likes, shares, like_weight, share_weight), 1),
        })
    records.sort(key=lambda r: r["score"], reverse=True)
    return records


def _write_history(records: list) -> None:
    path = os.path.join(FEEDBACK_DIR, HISTORY_FILE)
    with open(path, "w", encoding="utf-8") as f:
        for r in sorted(records, key=lambda x: x["date"]):
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _distill(records: list, config: dict) -> None:
    """把排名喂给 Claude，总结成给选题/写作用的经验清单，写进 lessons.md。"""
    top = records[:8]
    bottom = records[-5:] if len(records) > 13 else []
    def _fmt(tag, r):
        name = r.get("headline") or r.get("title", "")
        return (f"[{tag}] {r['score']}分 · 阅读{r['reads']} 评论{r['comments']} "
                f"点赞{r.get('likes', 0)} 转发{r.get('shares', 0)} · "
                f"{name} · 角度：{r['angle']}")
    lines = [_fmt("高分", r) for r in top]
    lines += [_fmt("低分", r) for r in bottom]
    table = "\n".join(lines)

    prompt = f"""你是公众号增长分析师。下面是历史文章的真实表现（按得分排序，
得分=阅读+评论×权重+点赞×权重+转发×权重，权重越大代表该互动越能反映真实认可）。
请总结出「什么样的选题和写法更受读者欢迎」，写成给选题编辑和写手看的经验清单。

{table}

要求：
- 只说数据里能看出的规律，不要泛泛而谈、不要编造数据没体现的结论。
- 分两部分：【选题方向】（什么主题/角度更火）和【写作建议】（标题、结构、风格倾向）。
- 每条一句话、可执行，总共不超过 12 条。
- 若样本太少看不出规律，就如实写「样本不足，暂无明显规律」，绝不硬编。
只输出经验清单正文，不要前言后语。"""

    client = anthropic.Anthropic(api_key=config["anthropic"]["api_key"])
    resp = client.messages.create(
        model=config["anthropic"]["model"],
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    header = (
        f"# 文章表现经验（自动沉淀，基于 {len(records)} 篇真实数据）\n\n"
        "> 由 feedback 模块根据阅读/评论自动生成，每次运行更新。"
        "selector 与 article_writer 会读取本文件注入提示词。\n\n"
    )
    with open(LESSONS_PATH, "w", encoding="utf-8") as f:
        f.write(header + text + "\n")
    print(f"[feedback] 经验已更新 → {LESSONS_PATH}（基于 {len(records)} 篇）")


def run(date_str: str, config: dict) -> bool:
    fb = config.get("feedback", {})
    source = fb.get("source", "manual")
    comment_weight = float(fb.get("comment_weight", 50))
    like_weight = float(fb.get("like_weight", 20))
    share_weight = float(fb.get("share_weight", 100))
    min_articles = int(fb.get("min_articles", 3))
    lookback = int(fb.get("lookback_days", 30))

    if source not in _COLLECTORS:
        print(f"[feedback] 未知 source={source}（仅支持 manual / wechat），跳过")
        return False

    os.makedirs(FEEDBACK_DIR, exist_ok=True)

    records = _aggregate(date_str, config, lookback, comment_weight, source,
                         like_weight, share_weight)
    _write_history(records)
    print(f"[feedback] 已聚合 {len(records)} 篇有数据文章 → {FEEDBACK_DIR}/{HISTORY_FILE}")

    if len(records) < min_articles:
        print(f"[feedback] 不足 {min_articles} 篇，暂不沉淀经验（继续积累中）")
        return True

    _distill(records, config)
    return True
