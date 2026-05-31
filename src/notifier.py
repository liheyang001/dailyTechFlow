"""M5 推送模块：把当天生成的文章邮到你手机，方便起床躺床上审核。

个人订阅号没有 API 发布权限，所以这里只负责「推送成品供审核」，不负责发布。
邮件正文直接放文章 HTML，手机邮件客户端能预览排版；合格了你再到
「订阅号助手」App 手动发布。

约定 run(date_str, config) -> bool。只读当天 output 目录。
邮箱未配置（password 为空）时优雅跳过，不报错、不中断流水线。
"""
import base64
import os
import re
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _extract_title(html: str, fallback: str) -> str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip() or fallback
    return fallback


def _cover_block(cover_path: str) -> str:
    """把封面图内联进邮件顶部（data URI），手机一开就看到封面。"""
    if not (cover_path and os.path.exists(cover_path)):
        return ""
    with open(cover_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return (
        f'<img src="data:image/png;base64,{b64}" '
        'style="width:100%;max-width:600px;display:block;margin:0 auto 16px"/>'
    )


def _build_message(ec: dict, date_str: str, html: str, title: str,
                   cover_path: str = "") -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["From"] = ec["sender"]
    msg["To"] = ec["recipient"]
    msg["Subject"] = f"[DailyTechFlow] 今日文章待审 · {date_str}｜{title}"
    plain = (
        f"今日文章已生成：{title}\n\n"
        "在手机上打开本邮件可直接预览封面和排版。\n"
        "觉得合格，就到「订阅号助手」App 发布。\n\n— DailyTechFlow 自动推送"
    )
    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(_cover_block(cover_path) + html, "html", "utf-8"))  # 优先显示 HTML
    return msg


def _send(ec: dict, msg: MIMEMultipart) -> None:
    ctx = ssl.create_default_context()
    with smtplib.SMTP(ec["smtp_host"], ec["smtp_port"]) as server:
        server.starttls(context=ctx)
        server.login(ec["sender"], ec["password"])
        server.send_message(msg)


def run(date_str: str, config: dict) -> bool:
    ec = config.get("email", {})
    article_path = os.path.join(config["output_base"], date_str, "wechat_article.html")

    if not os.path.exists(article_path):
        print("[notifier] 没有 wechat_article.html，本次无文章可推送，跳过")
        return False

    if not (ec.get("password") and ec.get("sender") and ec.get("recipient")):
        print("[notifier] 邮件未配置（缺 password/sender/recipient），跳过推送")
        return True

    with open(article_path, encoding="utf-8") as f:
        html = f.read()
    title = _extract_title(html, date_str)
    cover_path = os.path.join(config["output_base"], date_str, "cover.png")

    try:
        _send(ec, _build_message(ec, date_str, html, title, cover_path))
        print(f"[notifier] 今日文章已邮至 {ec['recipient']}：{title}")
    except Exception as e:
        print(f"[notifier] 邮件发送失败：{e}")
        return False

    return True
