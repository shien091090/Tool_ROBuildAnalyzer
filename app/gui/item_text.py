"""道具敘述→HTML轉換(純python, 不import Qt) — picker對話框tooltip共用。

RO道具敘述習慣用^RRGGBB切換文字顏色、^000000代表切回預設色(視為關閉span
回到QToolTip的預設字色, 不硬畫成黑字; tooltip底色見theme.TOOLTIP_BG, 與遊戲內
淺色道具視窗一致, 色碼才會照原意呈現) — 這裡只做這一種標記語言到
HTML的最小轉換, 換行轉<br>, 其餘文字一律html.escape避免敘述裡剛好出現
<...>被瀏覽器/QLabel richtext當成標籤解讀。
"""
import html
import re

_RE_COLOR = re.compile(r"\^([0-9A-Fa-f]{6})")


def description_to_html(description: str | None) -> str:
    if not description:
        return ""
    out = []
    open_span = False
    pos = 0
    for m in _RE_COLOR.finditer(description):
        out.append(html.escape(description[pos:m.start()]))
        if open_span:
            out.append("</span>")
            open_span = False
        code = m.group(1).lower()
        if code != "000000":
            out.append(f'<span style="color:#{code}">')
            open_span = True
        pos = m.end()
    out.append(html.escape(description[pos:]))
    if open_span:
        out.append("</span>")
    return "".join(out).replace("\n", "<br>")
