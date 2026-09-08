from app.gui.item_text import description_to_html


def test_color_codes_become_spans_and_newlines_break():
    html = description_to_html("MHP+1\n系列 : ^777777鎧甲^000000 <x>")
    assert "<br>" in html
    assert '<span style="color:#777777">鎧甲</span>' in html
    assert "&lt;x&gt;" in html


def test_none_is_empty():
    assert description_to_html(None) == ""


def test_tooltip_style_uses_light_background_with_dark_text():
    # tooltip底/字必須分開定義且對比足夠, 否則系統淺底套到全域淺字會讀不到
    from app.gui import theme
    assert "QToolTip" in theme.QSS
    assert theme.TOOLTIP_BG in theme.QSS and theme.TOOLTIP_TEXT in theme.QSS
    assert theme.TOOLTIP_TEXT != theme.TEXT
