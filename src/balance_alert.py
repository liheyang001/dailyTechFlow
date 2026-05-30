import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic


def _send_email(ec: dict) -> None:
    msg = MIMEMultipart()
    msg["From"]    = ec["sender"]
    msg["To"]      = ec["recipient"]
    msg["Subject"] = "[DailyTechFlow] Claude API 余额不足，流水线即将中断"
    msg.attach(MIMEText(
        "您好，\n\n"
        "DailyTechFlow 检测到 Claude API 余额已不足，下次运行将无法生成内容。\n\n"
        "请前往 https://console.anthropic.com 充值。\n\n"
        "— DailyTechFlow 自动提醒",
        "plain", "utf-8",
    ))
    ctx = ssl.create_default_context()
    with smtplib.SMTP(ec["smtp_host"], ec["smtp_port"]) as server:
        server.starttls(context=ctx)
        server.login(ec["sender"], ec["password"])
        server.send_message(msg)


def run(date_str: str, config: dict) -> bool:
    ac = config.get("anthropic", {})
    ec = config.get("email", {})

    if not ac.get("api_key") or not ec.get("password"):
        print("[balance_alert] 未配置 Claude API key 或邮件密码，跳过")
        return True

    try:
        client = anthropic.Anthropic(api_key=ac["api_key"])
        client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1,
            messages=[{"role": "user", "content": "hi"}],
        )
        print("[balance_alert] Claude API 余额正常")
    except anthropic.APIStatusError as e:
        msg = str(e).lower()
        if "credit" in msg or "balance" in msg:
            print("[balance_alert] 余额不足，发送邮件...")
            try:
                _send_email(ec)
                print("[balance_alert] 邮件已发送至", ec["recipient"])
            except Exception as mail_err:
                print(f"[balance_alert] 邮件发送失败：{mail_err}")
        else:
            print(f"[balance_alert] API 错误（非余额问题）：{e}")
    except Exception as e:
        print(f"[balance_alert] 检查失败（网络或配置问题）：{e}")

    return True
