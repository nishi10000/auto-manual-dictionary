from pathlib import Path

from auto_manual_dict.html_extract import extract_html

FIXTURES = Path(__file__).parent / "fixtures"


def test_extracts_title_headings_blocks_tables_images_and_safety_blocks():
    result = extract_html((FIXTURES / "ja" / "engine_no_start.html").read_text(encoding="utf-8"))

    assert result.title == "エンジン始動不良"
    assert "エンジン始動不良" in result.headings
    assert any(block.block_type == "paragraph" and "P0A80" in block.text for block in result.blocks)
    assert any(block.block_type == "caution" and "12 V" in block.text for block in result.blocks)
    assert any(block.block_type == "table_row" and "304 kPa" in block.text for block in result.blocks)
    assert "images/engine_start.png" in result.images


def test_extract_ignores_script_and_style_text():
    html = """<html><head><style>.secret{}</style><script>alert('secret')</script><title>T</title></head><body><h1>Visible</h1><p>Body</p></body></html>"""
    result = extract_html(html)
    all_text = " ".join(block.text for block in result.blocks)
    assert "secret" not in all_text
    assert "alert" not in all_text
    assert "Body" in all_text
