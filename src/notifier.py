"""M5 推送模块：把当天生成的文章邮到你手机，方便起床躺床上审核。

个人订阅号没有 API 发布权限，所以这里只负责「推送成品供审核」，不负责发布。
邮件正文放可读的纯文本+轻量内联样式预览（邮件客户端会删掉 <style> 块、
不渲染内联大图，所以正文保持轻量、不塞封面，避免 Gmail 102KB 截断）；
完整带封面的文章 HTML 作为附件，手机点开即用浏览器渲染、排版 100% 还原。
合格了你再到「订阅号助手」App 手动发布。

约定 run(date_str, config) -> bool。只读当天 output 目录。
邮箱未配置（password 为空）时优雅跳过，不报错、不中断流水线。
"""
import base64
import os
import re
import smtplib
import ssl
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from html import escape, unescape


def _extract_title(html: str, fallback: str) -> str:
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip() or fallback
    return fallback


def _inject_cover(html: str, cover_path: str) -> str:
    """把封面插到 <body> 之后，而非文档最前——否则巨大的 base64 会把
    <meta charset> 挤出浏览器前 1024 字节的编码嗅探窗口，导致中文乱码。"""
    block = _cover_block(cover_path)
    if not block:
        return html
    m = re.search(r"<body[^>]*>", html, re.I)
    if m:
        return html[:m.end()] + block + html[m.end():]
    return block + html  # 没有 <body> 的兜底


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


def _article_text(html: str) -> str:
    """把文章 HTML 转成可读纯文本，供邮件正文快速审阅（精确排版看附件）。"""
    body = html[html.find("<body"):] if "<body" in html else html
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", body, flags=re.S | re.I)
    body = re.sub(r"<br\s*/?>", "\n", body, flags=re.I)
    body = re.sub(r"</(p|div|h[1-6]|li|tr|section)>", "\n", body, flags=re.I)
    text = unescape(re.sub(r"<[^>]+>", "", body))
    out: list[str] = []
    for ln in (l.strip() for l in text.splitlines()):
        if ln or (out and out[-1]):          # 收敛连续空行
            out.append(ln)
    return "\n".join(out).strip()


_FOOTER = ("完整排版（含封面）见附件 HTML，手机点开即用浏览器渲染。"
           "封面图 cover.png 也作为附件，可直接保存用作微信文章封面。"
           "审核合格后到「订阅号助手」App 发布。")


def _body_html(title: str, text: str) -> str:
    """轻量内联样式的正文 HTML——只用 inline style，邮件客户端不会删。"""
    paras = "".join(f'<p style="margin:0 0 12px;line-height:1.75">{escape(p)}</p>'
                    for p in text.split("\n") if p.strip())
    return (
        '<div style="max-width:600px;margin:0 auto;color:#1f1b16;font-size:16px;'
        'font-family:-apple-system,Segoe UI,Roboto,sans-serif">'
        f'<h1 style="font-size:22px;line-height:1.4;margin:0 0 16px">{escape(title)}</h1>'
        f'{paras}'
        '<p style="margin:24px 0 0;padding-top:12px;border-top:1px solid #e3dbcd;'
        f'color:#8a8170;font-size:14px">{escape(_FOOTER)}</p></div>'
    )


def _build_message(ec: dict, date_str: str, html: str, title: str,
                   cover_path: str = "") -> MIMEMultipart:
    msg = MIMEMultipart("mixed")
    msg["From"] = ec["sender"]
    msg["To"] = ec["recipient"]
    msg["Subject"] = f"[DailyTechFlow] 今日文章待审 · {date_str}｜{title}"

    # 正文：纯文本 + 轻量 HTML 预览（不内嵌大图，避免被邮件客户端截断）
    text = _article_text(html)
    body = MIMEMultipart("alternative")
    body.attach(MIMEText(f"{title}\n\n{text}\n\n—— {_FOOTER}", "plain", "utf-8"))
    body.attach(MIMEText(_body_html(title, text), "html", "utf-8"))
    msg.attach(body)

    # 附件1：封面 PNG（可直接保存、用作微信文章封面）
    if cover_path and os.path.exists(cover_path):
        with open(cover_path, "rb") as f:
            img = MIMEImage(f.read(), "png")  # 显式 png，不依赖类型猜测
        img.add_header("Content-Disposition", "attachment", filename="cover.png")
        msg.attach(img)

    # 附件2：自包含 HTML（封面内联 + 文章原排版），浏览器打开 100% 还原
    att = MIMEText(_inject_cover(html, cover_path), "html", "utf-8")
    att.add_header("Content-Disposition", "attachment",
                   filename=f"{date_str}_article.html")
    msg.attach(att)
    return msg


def _send(ec: dict, msg: MIMEMultipart) -> None:
    ctx = ssl.create_default_context()
    with smtplib.SMTP(ec["smtp_host"], ec["smtp_port"]) as server:
        server.starttls(context=ctx)
        server.login(ec["sender"], ec["password"])
        server.send_message(msg)


def _write_fallback(output_base: str, date_str: str, title: str,
                    error: str, cover_path: str = "") -> str:
    """邮件没发出去时，在当天目录留一张醒目便条：错误 + 成品位置，
    方便人工去 output 目录取文件手动发布。文章/封面本就已落盘，不会丢。"""
    day_dir = os.path.join(output_base, date_str)
    note = os.path.join(day_dir, "EMAIL_FAILED.md")
    lines = [
        f"# 邮件发送失败 · {date_str}",
        "",
        f"- 标题：{title}",
        f"- 错误：{error}",
        "",
        "邮件没发出，但成品都在本目录，可手动取用发布：",
        "- 文章：wechat_article.html（浏览器打开或粘进微信）",
    ]
    if cover_path and os.path.exists(cover_path):
        lines.append(f"- 封面：{os.path.basename(cover_path)}")
    with open(note, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[notifier] 已写失败便条供人工补发：{note}")
    return note


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
        _write_fallback(config["output_base"], date_str, title, str(e), cover_path)
        return False

    return True
