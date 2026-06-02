"""wechat_inline 单测：验证 class → 内联样式、剥离 <style>、合并优先级、微信安全。

运行：python tests/test_wechat_inline.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import wechat_inline as wi


def test_strips_style_block():
    out = wi.inline("<style>.x{color:red}</style><p>hi</p>")
    assert "<style" not in out and "color:red" not in out
    assert "<p" in out and "hi" in out


def test_class_becomes_inline_and_removed():
    out = wi.inline('<div class="keybox">x</div>')
    assert 'class=' not in out          # class 去掉
    assert 'style="' in out
    assert "border-radius:14px" in out  # keybox 的样式被内联


def test_no_flex_in_output():
    """微信不认 flex：任何 class 都不能内联出 display:flex。"""
    html = ('<h2><span class="num">1</span>标题</h2>'
            '<div class="bar-row"><span class="bar-label">A</span>'
            '<span class="bar"><span class="bar-fill" style="width:80%">8</span></span></div>')
    out = wi.inline(html)
    assert "flex" not in out


def test_preserves_existing_inline_style_width():
    """条形图的 width 是元素自带 inline，必须保留并优先。"""
    out = wi.inline('<span class="bar-fill" style="width:80%">8</span>')
    assert "width:80%" in out
    assert f"background:{wi._CLAY}" in out  # class 样式也在


def test_combined_classes_merge():
    """bar-fill alt：两个 class 的样式都要在，alt 的深色覆盖。"""
    out = wi.inline('<span class="bar-fill alt" style="width:50%">5</span>')
    assert "width:50%" in out
    assert wi._INK in out  # alt 把背景改成深色


def test_element_default_applied_to_bare_tag():
    out = wi.inline("<p>正文</p>")
    assert "font-size:16px" in out


def test_resolves_color_vars():
    """输出里不能残留 CSS 变量。"""
    out = wi.inline('<span class="kicker">AI</span>')
    assert "var(" not in out
    assert wi._CLAY in out


def test_keeps_other_attributes():
    out = wi.inline('<td colspan="2" class="up">9↑</td>')
    assert 'colspan="2"' in out
    assert "class=" not in out
    assert f"color:{wi._CLAY}" in out


def test_full_document_roundtrip():
    """整篇（模板风格）跑一遍不报错、关键结构在、无 <style>/flex/var。"""
    html = (
        '<!DOCTYPE html><html><head><meta charset="UTF-8">'
        '<style>.wrap{display:flex;color:var(--clay)}</style></head>'
        '<body><div class="wrap"><div class="inner">'
        '<span class="kicker">AI · 模型</span><h1>标题</h1>'
        '<div class="lead">导语 <b>关键词</b></div>'
        '<h2><span class="num">1</span>章节</h2><p>正文</p>'
        '<div class="ending"><p class="big">总结</p><p>补充</p></div>'
        '</div></div></body></html>')
    out = wi.inline(html)
    assert "<style" not in out
    assert "flex" not in out and "var(" not in out
    assert "标题" in out and "章节" in out and "总结" in out
    assert 'charset="UTF-8"' in out  # meta 保留


def test_body_style_not_broken_by_inner_quotes():
    """body 字体名必须用单引号——style 由 inline 写进 style="..." 双引号里，
    字体名再用双引号会提前闭合属性、冲垮 body 标签（线上邮件附件就栽在这）。"""
    out = wi.inline("<body><p>x</p></body>")
    m = re.search(r"<body\b[^>]*>", out)
    assert m, "body 标签应存在"
    tag = m.group(0)
    assert '"PingFang' not in tag        # 不能有双引号字体名
    assert "'PingFang SC'" in tag        # 改用单引号
    assert tag.count('"') == 2           # 只剩外层那一对 style="..."


def _run():
    fns = [(n, f) for n, f in globals().items() if n.startswith("test_") and callable(f)]
    passed = 0
    for name, fn in fns:
        fn()
        print(f"  PASS {name}")
        passed += 1
    print(f"\n{passed}/{len(fns)} passed")
    return passed == len(fns)


if __name__ == "__main__":
    sys.exit(0 if _run() else 1)
