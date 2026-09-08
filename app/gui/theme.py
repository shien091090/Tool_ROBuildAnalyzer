"""GUI色票與QSS — spec mockup配色, 純樣式無邏輯。

色票(給其他gui模組直接import使用, 避免各檔各自複製hex碼):
    bg #14161c / panel #1c1f27 / raised #242833 / line #333845 / text #e2e6ef /
    muted #8b93a5 / dim #5c6373 / gold #d9a84e / combo #4ec9b0 / good #6fbf73 /
    bad #d97c7c / warn #d9b84e; tooltip獨立淺底 tooltip_bg #f4f1e8 / tooltip_text #1c1f27。

chip樣式一律以QToolButton的objectName區分(見slot_widget.py建立時setObjectName):
    chip_card(卡片) / chip_enchant(附魔) / chip_stone(強化石, 服飾格用) /
    chip_add(「+ 卡片」/「+ 附魔」/「+ 強化石」等待新增按鈕, 虛線框)。

高亮邊框(套裝提示用, T6接): SlotWidget呼叫setProperty("highlight", True/False)後
須自行style().unpolish()+polish()才能讓下面的[highlight="true"]選擇器套用
(Qt動態屬性選擇器不會自動重新計算樣式)。
"""
from PySide6.QtWidgets import QApplication

BG = "#14161c"
PANEL = "#1c1f27"
RAISED = "#242833"
LINE = "#333845"
TEXT = "#e2e6ef"
MUTED = "#8b93a5"
DIM = "#5c6373"
GOLD = "#d9a84e"
COMBO = "#4ec9b0"
GOOD = "#6fbf73"
BAD = "#d97c7c"
WARN = "#d9b84e"
# tooltip獨立用淺底深字: RO敘述的^RRGGBB色碼是針對遊戲內淺色道具視窗設計的, 走深底會讓
# ^0000FF等深色碼看不見; 不定義QToolTip時Qt會用系統淺底卻套到上面`*`的淺字, 兩者相近讀不到
TOOLTIP_BG = "#f4f1e8"
TOOLTIP_TEXT = "#1c1f27"
TOOLTIP_LINE = "#b8b2a3"

QSS = f"""
* {{
    font-family: "Microsoft JhengHei";
    font-size: 12px;
    color: {TEXT};
}}
QMainWindow, QWidget {{
    background: {BG};
}}
QFrame#BuildPanel, QFrame#SlotWidget {{
    background: {PANEL};
    border: 1px solid {LINE};
}}
QFrame#SlotWidget {{
    border: none;
    border-bottom: 1px solid {LINE};
}}
QFrame#SlotWidget[highlight="true"] {{
    border: 1px solid {COMBO};
    background: #1d2a28;
}}
QLabel {{
    color: {TEXT};
}}
QLabel[muted="true"] {{
    color: {MUTED};
}}
QLabel[dim="true"] {{
    color: {DIM};
}}
QTabWidget::pane {{
    border: 1px solid {LINE};
    background: {PANEL};
}}
QTabBar::tab {{
    background: {RAISED};
    color: {MUTED};
    padding: 4px 12px;
    border: 1px solid {LINE};
}}
QTabBar::tab:selected {{
    background: {PANEL};
    color: {TEXT};
}}
QComboBox {{
    background: {RAISED};
    border: 1px solid {LINE};
    color: {COMBO};
    padding: 2px 6px;
}}
QPushButton {{
    background: {RAISED};
    border: 1px solid {LINE};
    padding: 3px 10px;
}}
QPushButton:hover {{
    border-color: {COMBO};
}}
QToolTip {{
    background: {TOOLTIP_BG};
    color: {TOOLTIP_TEXT};
    border: 1px solid {TOOLTIP_LINE};
    padding: 4px 6px;
}}
QToolButton {{
    border-radius: 3px;
    padding: 1px 6px;
}}
QToolButton#chip_card {{
    background: #1a2030;
    border: 1px solid #2c3850;
    color: #a8c0e0;
}}
QToolButton#chip_enchant {{
    background: #241f30;
    border: 1px solid #453860;
    color: #c8b4e8;
}}
QToolButton#chip_stone {{
    background: #2b2418;
    border: 1px solid #4d3f22;
    color: #dcc084;
}}
QToolButton#chip_add {{
    background: transparent;
    border: 1px dashed {LINE};
    color: {DIM};
}}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyleSheet(QSS)
