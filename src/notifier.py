"""M5 推送模块：把当天生成的文章邮到你手机，方便起床躺床上审核。

个人订阅号没有 API 发布权限，所以这里只负责「推送成品供审核」，不负责发布。
邮件正文直接放内联版完整文章 HTML——内联样式无 <style> 块（Gmail 不会删）、
不含封面 base64（不超 Gmail 102KB 截断线），Gmail 直接打开即排版好的文章，
无需点开附件。封面 cover.png 单独作附件，可保存用作微信封面。
合格了你再到「订阅号助手」App 手动发布。

约定 run(date_str, config) -> bool。只读当天 output 目录。
邮箱未配置（password 为空）时优雅跳过，不报错、不中断流水线。
"""
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


def _article_text(html: str) -> str:
    """把文章 HTML 转成可读纯文本，作邮件 plain 兜底（客户端不支持 HTML 时仍可读）。"""
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


_FOOTER = ("发布方法：用浏览器打开附件 HTML（会渲染成排版页面）→ 在页面里全选复制 → "
           "粘进公众号后台/排版工具，排版即保留。"
           "关键：复制渲染后的页面，不是复制源码（粘源码只会显示代码、不渲染）。"
           "封面 cover.png 也在附件。")


def _preview_html(title: str, text: str) -> str:
    """邮件正文轻量预览：标题 + 引导语 + 纯文本正文。完整带样式文章看附件。"""
    paras = "".join(f'<p style="margin:0 0 10px;line-height:1.7">{escape(p)}</p>'
                    for p in text.split("\n") if p.strip())
    return (
        '<div style="max-width:600px;margin:0 auto;color:#1f1b16;font-size:15px;'
        'font-family:-apple-system,Segoe UI,Roboto,sans-serif">'
        f'<h2 style="font-size:20px;line-height:1.4;margin:0 0 6px">{escape(title)}</h2>'
        '<p style="color:#8a8170;font-size:13px;margin:0 0 16px">'
        '完整排版见附件 HTML，手机点开附件查看；以下仅纯文本预览：</p>'
        f'{paras}</div>'
    )


def _build_message(ec: dict, date_str: str, html: str, title: str,
                   cover_path: str = "") -> MIMEMultipart:
    msg = MIMEMultipart("mixed")
    msg["From"] = ec["sender"]
    msg["To"] = ec["recipient"]
    msg["Subject"] = f"[DailyTechFlow] 今日文章待审 · {date_str}｜{title}"

    # 正文：轻量预览（纯文本 + 简短 html）；完整带样式文章放附件供手机点开渲染。
    text = _article_text(html)
    body = MIMEMultipart("alternative")
    body.attach(MIMEText(f"{title}\n\n{text}\n\n—— {_FOOTER}", "plain", "utf-8"))
    body.attach(MIMEText(_preview_html(title, text), "html", "utf-8"))
    msg.attach(body)

    # 封面 PNG 作为附件，可保存用作微信文章封面
    if cover_path and os.path.exists(cover_path):
        with open(cover_path, "rb") as f:
            img = MIMEImage(f.read(), "png")  # 显式 png，不依赖类型猜测
        img.add_header("Content-Disposition", "attachment", filename="cover.png")
        msg.attach(img)

    # 文章 HTML 附件：浏览器打开会 render 成排版页面，在页面里全选复制即得富文本，
    # 粘进公众号后台/排版工具就保留排版——这是 6/2 验证过的发布路径。
    # 关键：复制的是渲染后的页面，不是源码；粘源码进编辑器只会显示代码、不渲染。
    att = MIMEText(html, "html", "utf-8")
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
