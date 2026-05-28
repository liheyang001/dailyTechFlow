import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

_WECHAT_API = "https://api.weixin.qq.com"


def _get_access_token(app_id: str, app_secret: str) -> str:
    url = (
        f"{_WECHAT_API}/cgi-bin/token"
        f"?grant_type=client_credential&appid={app_id}&secret={app_secret}"
    )
    with urllib.request.urlopen(url) as resp:
        data = json.loads(resp.read())
    if "access_token" not in data:
        raise RuntimeError(f"WeChat token error: {data.get('errmsg', data)}")
    return data["access_token"]


def _upload_thumb(access_token: str, image_path: str) -> str:
    url = (
        f"{_WECHAT_API}/cgi-bin/material/add_material"
        f"?access_token={access_token}&type=thumb"
    )
    boundary = "DailyTechFlowBoundary"
    filename = os.path.basename(image_path)
    with open(image_path, "rb") as f:
        image_data = f.read()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="media"; filename="{filename}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode("utf-8") + image_data + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = urllib.request.Request(url, data=body)
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    if "media_id" not in data:
        raise RuntimeError(f"WeChat upload error: {data.get('errmsg', data)}")
    return data["media_id"]


def _md_to_wechat_html(md_text: str) -> str:
    lines = md_text.strip().split("\n")
    html_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("### "):
            html_lines.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("# "):
            html_lines.append(f'<h1 style="text-align:center">{line[2:]}</h1>')
        else:
            line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", line)
            line = re.sub(r"\*(.+?)\*", r"<em>\1</em>", line)
            html_lines.append(f"<p>{line}</p>")
    return "\n".join(html_lines)


def _extract_title(md_text: str) -> str:
    for line in md_text.splitlines():
        line = line.strip()
        if line.startswith("# ") and not line.startswith("## "):
            return line[2:]
    return "每日科技速递"


def _extract_digest(md_text: str, max_len: int = 120) -> str:
    for line in md_text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            return line[:max_len]
    return ""


def _create_draft(access_token: str, title: str, content_html: str,
                  thumb_media_id: str, digest: str) -> str:
    url = f"{_WECHAT_API}/cgi-bin/draft/add?access_token={access_token}"
    payload = {
        "articles": [{
            "title": title,
            "content": content_html,
            "thumb_media_id": thumb_media_id,
            "digest": digest,
            "need_open_comment": 0,
            "only_fans_can_comment": 0,
        }]
    }
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    if "media_id" not in data:
        raise RuntimeError(f"WeChat draft error: {data.get('errmsg', data)}")
    return data["media_id"]


def _publish_draft(access_token: str, media_id: str) -> str:
    url = f"{_WECHAT_API}/cgi-bin/freepublish/submit?access_token={access_token}"
    payload = {"media_id": media_id}
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json; charset=utf-8")
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    if data.get("errcode", 0) != 0:
        raise RuntimeError(f"WeChat publish error: {data.get('errmsg', data)}")
    return data.get("publish_id", "")


def run(date_str: str, config: dict) -> bool:
    wechat = config.get("wechat", {})
    app_id = wechat.get("app_id", "")
    app_secret = wechat.get("app_secret", "")
    auto_publish = wechat.get("auto_publish", False)

    if not app_id or not app_secret:
        raise ValueError("WeChat app_id and app_secret are required in config.yaml")

    output_dir = os.path.join(config["output_base"], date_str)
    article_path = os.path.join(output_dir, "article_zh.md")
    cover_path = os.path.join(output_dir, "cover_zh.png")

    if not os.path.exists(article_path):
        raise FileNotFoundError(f"Missing: {article_path}")
    if not os.path.exists(cover_path):
        raise FileNotFoundError(f"Missing: {cover_path}")

    try:
        with open(article_path, encoding="utf-8") as f:
            md_text = f.read()

        print("[publisher] Getting WeChat access_token...")
        token = _get_access_token(app_id, app_secret)

        print("[publisher] Uploading cover image...")
        thumb_media_id = _upload_thumb(token, cover_path)

        title = _extract_title(md_text)
        digest = _extract_digest(md_text)
        content_html = _md_to_wechat_html(md_text)

        print(f"[publisher] Creating draft: {title}")
        draft_media_id = _create_draft(token, title, content_html, thumb_media_id, digest)
        print(f"[publisher] Draft created: {draft_media_id}")

        if auto_publish:
            print("[publisher] Publishing draft...")
            publish_id = _publish_draft(token, draft_media_id)
            print(f"[publisher] Published: publish_id={publish_id}")
        else:
            print("[publisher] Draft saved (auto_publish=false)")

    except Exception as e:
        print(f"[publisher] Error: {e}")
        return False

    return True
