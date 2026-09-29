"""SlotWidget — 單一部位格的唯讀顯示(T5) + 訊號骨架(T6接互動)。

版面: 第一列
[部位標籤 fixed 70px][精煉 +N][階級][裝備名 stretch][chips…靠右],
高度28px, 字級12px。chips若在第一列會被擠到截字(2026-09-08驗收裁決), 就整組
搬到第二列靠右排(格高變成28+24), 塞得下就收回第一列 — 判斷在_relayout_chips,
set_config與resizeEvent都會重算。20格 + 3個section標題(各18px)單列時約690px。

chips規則(T5只畫, T6接點擊事件):
    一般裝備(GENERAL_SLOTS): 卡片chip(chip_card) x len(cards), 若插槽數(由
        session.slot_count_of查item的slot_count, 查無資料視為0)大於已插卡片數,
        補一顆「+ 卡片」(chip_add); 附魔chip(chip_enchant) x 已選(非None)的
        enchants項, 若附魔池槽位數(session.enchant_pools)大於已選數,
        補一顆「+ 附魔」(chip_add)。
    服飾(COSTUME_SLOTS): 服飾本體沒有任何效果, 不顯示、不可選; item_id直接存
        服飾強化石(與CLI配裝檔一致), 點格子開的是強化石清單, 沒有任何chip。
        服飾格沒有精煉/附魔的概念, refine_label永不顯示。
    影子裝備(SHADOW_SLOTS): 沒有任何chip(spec: 只有基本裝備, 無卡片/附魔欄位)。

grade_label只有GENERAL_SLOTS的格才顯示(服飾/影子裝備沒有升階概念); grade
為"none"時同樣不顯示(沒升階=不畫這個標籤, 不是畫一個空字)。

套裝(2026-09-29驗收裁決): 懸停裝備名只看本體的套裝、懸停卡片chip只看那張卡的
套裝(combo_hovered帶item_id, 離開帶None), 格子其他地方不觸發高亮 — 本體與卡片
的套裝混在一起亮會看不出哪格跟哪個套裝走。成立的套裝另列在各自tooltip最上方。
"""
import html

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QToolButton, QVBoxLayout, QWidget

from app.gui.item_text import description_to_html

SLOT_LABELS: dict[str, str] = {
    "head_top": "上段頭飾",
    "head_mid": "中段頭飾",
    "head_low": "下段頭飾",
    "armor": "鎧甲",
    "weapon": "武器",
    "shield": "盾牌",
    "garment": "披肩",
    "shoes": "鞋子",
    "acc_r": "飾品(右)",
    "acc_l": "飾品(左)",
    "costume_top": "服飾上段",
    "costume_mid": "服飾中段",
    "costume_low": "服飾下段",
    "costume_garment": "服飾背飾",
    "shadow_armor": "影子鎧甲",
    "shadow_gauntlet": "影子手套",
    "shadow_shield": "影子盾牌",
    "shadow_shoes": "影子鞋子",
    "shadow_earring": "影子耳環",
    "shadow_pendant": "影子墜飾",
}

SLOT_SECTIONS: list[tuple[str, list[str]]] = [
    ("一般裝備", ["head_top", "head_mid", "head_low", "armor", "weapon", "shield", "garment", "shoes", "acc_r", "acc_l"]),
    ("服飾", ["costume_top", "costume_mid", "costume_low", "costume_garment"]),
    ("影子裝備", ["shadow_armor", "shadow_gauntlet", "shadow_shield", "shadow_shoes", "shadow_earring", "shadow_pendant"]),
]
GENERAL_SLOTS = SLOT_SECTIONS[0][1]
COSTUME_SLOTS = SLOT_SECTIONS[1][1]
SHADOW_SLOTS = SLOT_SECTIONS[2][1]

_UNEQUIPPED_TEXT = "— 未裝備(點擊選擇)"
_COST_TARGETS_MARKER = " $"
_ADD_CARD_TEXT = "+ 卡片"
_ADD_ENCHANT_TEXT = "+ 附魔"
_GRADE_LETTERS = {"D": "D", "C": "C", "B": "B", "A": "A"}

_SLOT_HEIGHT = 28
_CHIP_ROW_HEIGHT = 24
_LABEL_WIDTH = 70

_MENU_REFINE_TEXT = "設定精煉…"
_MENU_GRADE_TEXT = "設定階級…"
_MENU_CLEAR_TEXT = "清空此格"
_MENU_COST_TARGETS_TEXT = "成本設定…"
_COMBO_HEADER = "成立套裝"


def _make_chip(text: str, object_name: str) -> QToolButton:
    btn = QToolButton()
    btn.setText(text)
    btn.setObjectName(object_name)
    btn.setAutoRaise(False)
    return btn


class _ClickableLabel(QLabel):
    """一般QLabel沒有點擊訊號 — 包一層在mousePressEvent補emit, 讓name_label/
    refine_label/grade_label各自能連到SlotWidget對應的*_clicked訊號。"""
    clicked = Signal()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        event.accept()  # 吞掉, 不讓事件穿透到SlotWidget(曾因此選完裝備又跳精煉視窗)


def _repolish(widget) -> None:
    """QSS的動態屬性選擇器(如[dim="true"]/[highlight="true"])不會在setProperty
    後自動重新計算樣式, 必須手動unpolish+polish才會生效 — 抽成共用helper,
    避免set_config的dim切換與set_highlight各自重複這兩行。
    """
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def _tooltip_html(combo_lines: list[str], desc_html: str) -> str:
    """套裝段放最上面(道具敘述常很長, 放後面會被擠到看不見), 與敘述以<hr>分隔。"""
    if not combo_lines:
        return desc_html
    items = "<br>".join(f"・{html.escape(line)}" for line in combo_lines)
    combo_html = f"<b>{_COMBO_HEADER}</b><br>{items}"
    return f"{combo_html}<hr>{desc_html}" if desc_html else combo_html


class _HoverWatcher(QObject):
    """裝在name_label/卡片chip上, Enter/Leave轉成callback(item_id或None)。"""

    def __init__(self, parent: QObject, item_id: int, callback):
        super().__init__(parent)
        self._item_id = item_id
        self._callback = callback

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.Enter:
            self._callback(self._item_id)
        elif event.type() == QEvent.Type.Leave:
            self._callback(None)
        return False


class SlotWidget(QFrame):
    item_clicked = Signal()
    refine_clicked = Signal()
    grade_clicked = Signal()
    card_clicked = Signal(int)
    enchant_clicked = Signal(int)
    add_card_clicked = Signal()
    add_enchant_clicked = Signal()
    clear_requested = Signal()
    cost_targets_requested = Signal()
    combo_hovered = Signal(object)  # 懸停的item_id(本體或卡片), 離開時None

    def __init__(self, slot_key: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.slot_key = slot_key
        self.setObjectName("SlotWidget")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self._row1 = QWidget()
        self._row1.setFixedHeight(_SLOT_HEIGHT)
        layout = QHBoxLayout(self._row1)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)
        outer.addWidget(self._row1)
        self._row1_layout = layout

        self._row2 = QWidget()
        self._row2.setFixedHeight(_CHIP_ROW_HEIGHT)
        self._row2_layout = QHBoxLayout(self._row2)
        self._row2_layout.setContentsMargins(4, 0, 4, 2)
        self._row2_layout.setSpacing(6)
        self._row2_layout.addStretch(1)
        self._row2.setVisible(False)
        outer.addWidget(self._row2)

        self.slot_label = QLabel(SLOT_LABELS[slot_key])
        self.slot_label.setFixedWidth(_LABEL_WIDTH)
        self.slot_label.setProperty("muted", True)
        layout.addWidget(self.slot_label)

        self.refine_label = _ClickableLabel("")
        self.refine_label.setVisible(False)
        self.refine_label.clicked.connect(self.refine_clicked.emit)
        layout.addWidget(self.refine_label)

        self.grade_label = _ClickableLabel("")
        self.grade_label.setVisible(False)
        self.grade_label.clicked.connect(self.grade_clicked.emit)
        layout.addWidget(self.grade_label)

        self.name_label = _ClickableLabel(_UNEQUIPPED_TEXT)
        self.name_label.clicked.connect(self.item_clicked.emit)
        layout.addWidget(self.name_label, 1)

        self._chips_widget = QWidget()
        self._chips_layout = QHBoxLayout(self._chips_widget)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(4)
        layout.addWidget(self._chips_widget, 0, Qt.AlignRight)
        self._chips_on_second_row = False

        self._cfg = None
        self._desc_html = ""
        self._name_watcher: _HoverWatcher | None = None
        self._card_chips: list[QToolButton] = []

    @property
    def chips_on_second_row(self) -> bool:
        return self._chips_on_second_row

    def _chips_natural_width(self) -> int:
        n = self._chips_layout.count()
        if n == 0:
            return 0
        widths = sum(self._chips_layout.itemAt(i).widget().sizeHint().width() for i in range(n))
        return widths + self._chips_layout.spacing() * (n - 1)

    def _row1_available_for_chips(self) -> int:
        m = self._row1_layout.contentsMargins()
        used = m.left() + m.right() + self.slot_label.width()
        parts = 1  # slot_label
        for w in (self.refine_label, self.grade_label):
            if w.isVisibleTo(self):
                used += w.sizeHint().width()
                parts += 1
        used += self.name_label.sizeHint().width()
        parts += 1
        used += self._row1_layout.spacing() * parts  # 每個元件與chips之間的間距
        return self.width() - used

    def _relayout_chips(self) -> None:
        """chips在第一列塞不下(會被擠到截字)就整組搬到第二列, 塞得下就收回。"""
        need = self._chips_natural_width()
        overflow = need > 0 and need > self._row1_available_for_chips()
        if overflow == self._chips_on_second_row:
            return
        self._chips_on_second_row = overflow
        if overflow:
            self._row1_layout.removeWidget(self._chips_widget)
            self._row2_layout.addWidget(self._chips_widget, 0, Qt.AlignRight)
        else:
            self._row2_layout.removeWidget(self._chips_widget)
            self._row1_layout.addWidget(self._chips_widget, 0, Qt.AlignRight)
        self._row2.setVisible(overflow)
        self.updateGeometry()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._relayout_chips()

    def _clear_chips(self) -> None:
        while self._chips_layout.count():
            item = self._chips_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _add_chip(self, text: str, object_name: str, on_click=None) -> QToolButton:
        btn = _make_chip(text, object_name)
        if on_click is not None:
            btn.clicked.connect(on_click)
        self._chips_layout.addWidget(btn)
        return btn

    def _set_name_watcher(self, item_id: int | None) -> None:
        if self._name_watcher is not None:
            self.name_label.removeEventFilter(self._name_watcher)
            self._name_watcher.deleteLater()
            self._name_watcher = None
        if item_id is not None:
            self._name_watcher = _HoverWatcher(self, item_id, self.combo_hovered.emit)
            self.name_label.installEventFilter(self._name_watcher)

    def set_config(self, cfg, session) -> None:
        self._cfg = cfg
        self._clear_chips()
        self._card_chips = []
        self._desc_html = ""

        has_cost_targets = cfg is not None and cfg.cost_targets is not None
        self.slot_label.setText(SLOT_LABELS[self.slot_key] + (_COST_TARGETS_MARKER if has_cost_targets else ""))

        if cfg is None:
            self.name_label.setText(_UNEQUIPPED_TEXT)
            self.name_label.setToolTip("")
            self._set_name_watcher(None)
            self.name_label.setProperty("dim", True)
            _repolish(self.name_label)
            self.refine_label.setVisible(False)
            self.grade_label.setVisible(False)
            self._relayout_chips()
            return

        self.name_label.setProperty("dim", False)
        _repolish(self.name_label)
        is_costume = self.slot_key in COSTUME_SLOTS
        is_general = self.slot_key in GENERAL_SLOTS
        # 一般格裝備名帶「[N]」洞數後綴; 服飾(石頭)/影子裝備不可插卡, 不帶
        display = session.equipment_display(cfg.item_id) if is_general else session.item_display(cfg.item_id)
        self.name_label.setText(display)
        # 懸停裝備名顯示與選擇清單相同的敘述tooltip(2026-09-08驗收需求)
        self._desc_html = description_to_html(session.item_description(cfg.item_id))
        self.name_label.setToolTip(self._desc_html)
        self._set_name_watcher(cfg.item_id)

        if not is_costume:
            # controller ruling(fix round1第3點, 覆蓋brief規則2原本的"refine>0才
            # 顯示"): 已裝備的GENERAL/SHADOW格恆顯示精煉值(含+0), 否則使用者永遠
            # 沒有實際可點的目標能把精煉從0設起來。服飾格依然沒有精煉概念, 永不顯示。
            self.refine_label.setText(f"+{cfg.refine}")
            self.refine_label.setVisible(True)
        else:
            self.refine_label.setVisible(False)

        if is_general and cfg.grade in _GRADE_LETTERS:
            self.grade_label.setText(_GRADE_LETTERS[cfg.grade])
            self.grade_label.setVisible(True)
        else:
            self.grade_label.setVisible(False)

        if is_general:
            self._fill_general_chips(cfg, session)
        # COSTUME_SLOTS(item_id即強化石)/SHADOW_SLOTS: 無chips
        self._relayout_chips()

    def _fill_general_chips(self, cfg, session) -> None:
        for i, card_id in enumerate(cfg.cards):
            chip = self._add_chip(session.item_display(card_id), "chip_card",
                                  lambda _checked=False, i=i: self.card_clicked.emit(i))
            chip.installEventFilter(_HoverWatcher(chip, card_id, self.combo_hovered.emit))
            self._card_chips.append(chip)
        slot_count = session.slot_count_of(cfg.item_id)
        if slot_count > len(cfg.cards):
            self._add_chip(_ADD_CARD_TEXT, "chip_add", self.add_card_clicked.emit)

        pools = session.enchant_pools(cfg.item_id)
        filled = 0
        for i, option in enumerate(cfg.enchants):
            if option is not None:
                filled += 1
                self._add_chip(session.option_display(option), "chip_enchant",
                                lambda _checked=False, i=i: self.enchant_clicked.emit(i))
        if len(pools) > filled:
            self._add_chip(_ADD_ENCHANT_TEXT, "chip_add", self.add_enchant_clicked.emit)

    def set_combo_info(self, name_lines: list[str], card_lines: list[list[str]]) -> None:
        """在set_config之後呼叫: 把成立套裝列進裝備名/各卡片chip的tooltip。
        card_lines與cfg.cards同序; 套裝要看整套build, 所以由BuildPanel算好傳進來。"""
        if self._cfg is None:
            return
        self.name_label.setToolTip(_tooltip_html(name_lines, self._desc_html))
        for chip, lines in zip(self._card_chips, card_lines):
            chip.setToolTip(_tooltip_html(lines, ""))

    def set_highlight(self, on: bool) -> None:
        self.setProperty("highlight", on)
        _repolish(self)

    def chip_buttons(self) -> list[QToolButton]:
        return [self._chips_layout.itemAt(i).widget() for i in range(self._chips_layout.count())]

    def contextMenuEvent(self, event) -> None:
        """「設定精煉…」/「設定階級…」放在「清空此格」前面, 與點擊精煉/階級數字
        並列為僅有的兩個編輯入口(2026-09-08驗收裁決: 空白處點擊改精煉已拔掉,
        它會在選完裝備關閉清單後連跳精煉視窗) — 只在該格「已裝備且該slot類型
        支援」時才加進選單。
        """
        menu = QMenu(self)
        equipped = self._cfg is not None
        is_costume = self.slot_key in COSTUME_SLOTS
        is_general = self.slot_key in GENERAL_SLOTS
        refine_action = menu.addAction(_MENU_REFINE_TEXT) if equipped and not is_costume else None
        grade_action = menu.addAction(_MENU_GRADE_TEXT) if equipped and is_general else None
        clear_action = menu.addAction(_MENU_CLEAR_TEXT)
        cost_action = menu.addAction(_MENU_COST_TARGETS_TEXT)
        cost_action.setEnabled(equipped)  # 未裝備的格沒有item_id, 無從查refine_table/enchant_pools
        chosen = menu.exec(event.globalPos())
        if chosen is None:
            return
        if chosen is refine_action:
            self.refine_clicked.emit()
        elif chosen is grade_action:
            self.grade_clicked.emit()
        elif chosen is clear_action:
            self.clear_requested.emit()
        elif chosen is cost_action:
            self.cost_targets_requested.emit()
