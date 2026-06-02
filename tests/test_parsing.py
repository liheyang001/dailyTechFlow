"""解析逻辑单测（纯函数，不依赖外部 API）。

运行：python tests/test_parsing.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.article_writer import _parse_sections
from src.selector import _parse_json


def test_parse_sections_handles_html_with_quotes_and_newlines():
    """CONTENT 含引号和换行的 HTML 不应破坏解析（之前用 JSON 会炸）。"""
    text = """###CATEGORY###
AI · 模型发布
###TITLE###
一个有"引号"的标题
###READ_TIME###
7
###LEAD###
导语 <b>强调</b>
###CONTENT###
<h2><span class="num">1</span>标题</h2>
<p>带"引号"和
换行的正文</p>"""
    data = _parse_sections(text)
    assert data["category"] == "AI · 模型发布"
    assert data["title"] == '一个有"引号"的标题'
    assert data["read_time"] == "7"
    assert data["lead"] == "导语 <b>强调</b>"
    assert '<span class="num">1</span>' in data["content"]
    assert "换行的正文" in data["content"]


def test_parse_sections_missing_field():
    """缺字段时只解析出已有的，不报错（由调用方校验必填）。"""
    data = _parse_sections("###TITLE###\n只有标题")
    assert data == {"title": "只有标题"}


def test_parse_json_strips_code_fence():
    """selector 的 JSON 解析应能剥掉 ```json 围栏。"""
    assert _parse_json('```json\n{"index": 2, "reason": "x"}\n```') == {"index": 2, "reason": "x"}
    assert _parse_json('{"index": 1, "reason": "y"}') == {"index": 1, "reason": "y"}


def test_parse_json_recovers_from_unescaped_quotes_in_reason():
    """reason 含未转义引号时仍兜底抽出 index（线上连续两天栽在这）。"""
    bad = '{"index": 3, "reason": "「220独角兽」这个"踢出局"标题极具冲击力"}'
    data = _parse_json(bad)
    assert data["index"] == 3
    assert "踢出局" in data["reason"]


def test_parse_json_raises_when_no_index():
    """连 index 都抽不到才报错，不静默吞掉坏输出。"""
    raised = False
    try:
        _parse_json("这根本不是 JSON")
    except Exception:
        raised = True
    assert raised


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} passed")
