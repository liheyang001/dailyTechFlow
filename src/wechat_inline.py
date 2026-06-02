"""把 class 化的文章 HTML 转成「微信公众号安全」的全内联样式 HTML。

为什么需要：微信编辑器（和邮件、绝大多数富文本粘贴）会删掉 <style> 块、class、
CSS 变量、伪元素(::before)、伪类(:nth-child)，还**不认 flexbox**。本模块用一份
确定性的「class → 内联样式」表，把样式直接写到每个元素的 style 属性上，并把
flex 布局改写成 inline-block / 块级堆叠等微信支持的写法。颜色变量在表里已解析成
具体色值。这样产出的 HTML 粘进微信能保留排版。

单一入口：inline(html) -> str。纯字符串/正则处理，不依赖第三方库。
设计取舍：大模型仍按 class 产出内容（简短可靠），样式由本表统一决定。
"""
import re

# 设计系统色值（原模板 :root 变量解析后的具体值）
_CREAM, _INK, _BODY = "#F5F1EA", "#1F1B16", "#3a342c"
_MUTED, _CLAY, _CLAY_SOFT = "#8a8170", "#D97757", "#FBEAE2"
_LINE, _CARD = "#E3DBCD", "#FFFFFF"

# 元素默认样式（按标签名套，不管有没有 class）
TAG_STYLES = {
    # 字体名用单引号：整段 style 由 inline() 写进 style="..." 双引号里，
    # 字体名再用双引号会提前闭合 style 属性、冲垮整个 body 标签。
    "body": f"margin:0;background:#E9E2D6;color:{_BODY};line-height:1.9;"
            "font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;",
    "h1": f"font-size:30px;line-height:1.32;color:{_INK};font-weight:800;margin:18px 0 14px;",
    "h2": f"font-size:21px;color:{_INK};font-weight:800;margin:42px 0 6px;",
    "p": "font-size:16px;margin:14px 0;",
    "table": f"width:100%;border-collapse:collapse;margin:8px 0;font-size:14.5px;background:{_CARD};",
    "th": f"padding:13px 14px;text-align:left;border-bottom:1px solid {_LINE};"
          f"background:{_INK};color:{_CREAM};font-weight:700;font-size:13.5px;",
    "td": f"padding:13px 14px;text-align:left;border-bottom:1px solid {_LINE};",
    "code": f"background:#efe7d8;padding:2px 7px;border-radius:5px;font-size:13px;color:#6b3a28;",
    "figure": "margin:26px 0;",
    "figcaption": f"font-size:12.5px;color:{_MUTED};text-align:center;margin-top:9px;",
}

# class → 内联样式（已去 flex / 伪元素 / 变量）
CLASS_STYLES = {
    "wrap": f"max-width:678px;margin:0 auto;background:{_CREAM};padding:0 0 64px;box-sizing:border-box;",
    "inner": "padding:0 26px;box-sizing:border-box;",
    "topbar": f"height:6px;background:{_CLAY};",
    "kicker": f"display:inline-block;margin:30px 0 0;background:{_CLAY};color:#fff;font-size:13px;"
              "font-weight:800;letter-spacing:.08em;padding:6px 14px;border-radius:4px;",
    "meta": f"font-size:13px;color:{_MUTED};margin-bottom:22px;",
    "dot": f"display:inline-block;width:4px;height:4px;border-radius:50%;background:{_MUTED};"
           "margin:0 8px;vertical-align:middle;",
    "lead": f"background:{_CLAY_SOFT};border-left:4px solid {_CLAY};padding:16px 18px;"
            "border-radius:0 8px 8px 0;font-size:15.5px;color:#6b3a28;margin:0 0 26px;box-sizing:border-box;",
    # h2 编号徽章：flex 改 inline-block + line-height 居中
    "num": f"display:inline-block;width:30px;height:30px;line-height:30px;border-radius:8px;"
           f"background:{_INK};color:{_CREAM};font-size:15px;text-align:center;font-weight:800;"
           "vertical-align:middle;margin-right:11px;",
    "sub": f"font-size:13px;color:{_CLAY};font-weight:700;margin:0 0 14px 41px;letter-spacing:.04em;",
    "keybox": f"background:{_CARD};border:1px solid {_LINE};border-radius:14px;padding:6px 20px 14px;"
              "margin:6px 0 8px;box-sizing:border-box;",
    "kli": f"padding:13px 0;border-bottom:1px dashed {_LINE};",
    # 要点编号圆点：flex 改 inline-block
    "tick": f"display:inline-block;width:22px;height:22px;line-height:22px;border-radius:50%;"
            f"background:{_CLAY};color:#fff;font-size:13px;font-weight:800;text-align:center;"
            "margin-right:13px;vertical-align:top;",
    "kt": "",
    "partner": f"background:{_CARD};border:1px solid {_LINE};border-radius:12px;padding:4px 18px;margin:14px 0;",
    "pli": f"padding:12px 0;border-bottom:1px solid {_LINE};font-size:14.5px;",
    "pname": f"color:{_CLAY};font-weight:800;",
    # 大字引用：去掉 ::before 大引号，改用上下细线装饰
    "quote": f"font-size:18px;line-height:1.7;color:{_INK};font-weight:700;text-align:center;"
             f"margin:30px 18px;border-top:1px solid {_LINE};border-bottom:1px solid {_LINE};padding:18px 0;",
    "feat": f"background:{_CARD};border:1px solid {_LINE};border-left:4px solid {_CLAY};"
            "border-radius:0 12px 12px 0;padding:15px 18px;margin:14px 0;box-sizing:border-box;",
    "tag": f"display:inline-block;background:{_CLAY_SOFT};color:{_CLAY};font-size:11px;font-weight:800;"
           "padding:3px 9px;border-radius:20px;margin-left:6px;vertical-align:middle;",
    # 价格卡片：flex 横排改竖排堆叠
    "price": "margin:16px 0;",
    "pc": f"background:{_CARD};border:1px solid {_LINE};border-radius:14px;padding:16px 18px;"
          "margin:10px 0;box-sizing:border-box;",
    "lab": f"font-size:13px;color:{_MUTED};font-weight:700;",
    "val": f"font-size:15px;color:{_INK};font-weight:800;margin-top:6px;line-height:1.6;",
    "divider": f"text-align:center;color:{_CLAY};letter-spacing:.6em;margin:38px 0 30px;font-size:13px;",
    "ending": f"background:{_INK};color:{_CREAM};border-radius:16px;padding:24px 22px;margin:30px 0 10px;"
              "box-sizing:border-box;",
    "big": "font-size:19px;font-weight:800;color:#fff;line-height:1.6;",
    "src": f"font-size:12px;color:{_MUTED};text-align:center;margin-top:26px;",
    "chart": f"background:{_CARD};border:1px solid {_LINE};border-radius:14px;padding:18px 20px;"
             "margin:18px 0;box-sizing:border-box;",
    "chart-title": f"font-size:14.5px;font-weight:800;color:{_INK};margin-bottom:14px;",
    # 条形图：flex 改 label 块级 + bar 块级堆叠
    "bar-row": "margin:10px 0;",
    "bar-label": f"display:block;font-size:13px;color:{_BODY};font-weight:700;margin-bottom:4px;",
    "bar": "display:block;background:#F0E9DC;border-radius:6px;overflow:hidden;height:26px;",
    "bar-fill": f"display:block;background:{_CLAY};height:26px;border-radius:6px;color:#fff;font-size:12.5px;"
                "font-weight:800;text-align:right;padding-right:10px;line-height:26px;white-space:nowrap;"
                "box-sizing:border-box;",
    "alt": f"background:{_INK};",          # 与 bar-fill 组合：对比项用深色
    "up": f"color:{_CLAY};font-weight:800;",  # 与 td 组合：表格数字高亮
    "chart-src": f"font-size:11.5px;color:{_MUTED};margin-top:12px;text-align:right;",
}

_TAG_RE = re.compile(r"<([a-zA-Z][a-zA-Z0-9]*)((?:[^>\"']|\"[^\"]*\"|'[^']*')*?)(/?)>")
_ATTR_RE = re.compile(r"""(\w[\w-]*)\s*=\s*("(?:[^"]*)"|'(?:[^']*)'|[^\s>]+)""")


def _attr_value(raw: str) -> str:
    return raw[1:-1] if raw and raw[0] in "\"'" else raw


def _compute_style(tag: str, classes: list, existing_style: str) -> str:
    """合并：元素默认 → 各 class 样式 → 元素自带 inline（后者优先，故放最后）。"""
    parts = []
    if tag in TAG_STYLES:
        parts.append(TAG_STYLES[tag])
    for c in classes:
        if c in CLASS_STYLES and CLASS_STYLES[c]:
            parts.append(CLASS_STYLES[c])
    if existing_style:
        s = existing_style.strip()
        parts.append(s if s.endswith(";") else s + ";")
    return "".join(parts)


def _rewrite_tag(m: re.Match) -> str:
    tag, attr_str, closing = m.group(1), m.group(2), m.group(3)
    if tag.lower() in ("style", "script"):
        return m.group(0)  # 整块在 inline() 里单独剥离，这里不碰

    classes, existing_style, others = [], "", []
    for am in _ATTR_RE.finditer(attr_str):
        name, val = am.group(1).lower(), _attr_value(am.group(2))
        if name == "class":
            classes = val.split()
        elif name == "style":
            existing_style = val
        else:
            others.append(f'{am.group(1)}={am.group(2)}')

    style = _compute_style(tag, classes, existing_style)
    rebuilt = "<" + tag
    if others:
        rebuilt += " " + " ".join(others)
    if style:
        rebuilt += f' style="{style}"'
    rebuilt += "/>" if closing else ">"
    return rebuilt


def inline(html: str) -> str:
    """剥离 <style> 块，把所有 class/元素样式写成内联 style，返回微信安全的 HTML。"""
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.S | re.I)
    return _TAG_RE.sub(_rewrite_tag, html)
