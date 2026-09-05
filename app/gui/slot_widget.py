"""SlotWidget — 單一部位格的唯讀顯示(T5) + 訊號骨架(T6接互動)。

版面(spec brief §版面對策, 硬性約束): 單列
[部位標籤 fixed 70px][精煉 +N][階級][裝備名 stretch][chips…靠右不換行],
固定高度28px, 字級12px。20格 + 3個section標題(各18px)全部疊起來約690px,
在1920x1080下兩個BuildPanel並排仍可完整顯示、無需捲動(spec §9)。

chips規則(T5只畫, T6接點擊事件):
    一般裝備(GENERAL_SLOTS): 卡片chip(chip_card) x len(cards), 若插槽數(由
        session.catalog查item的slot_count, 查無資料視為0)大於已插卡片數,
        補一顆「+ 卡片」(chip_add); 附魔chip(chip_enchant) x 已選(非None)的
        enchants項, 若附魔池槽位數(session.enchant_pools)大於已選數,
        補一顆「+ 附魔」(chip_add)。
    服飾(COSTUME_SLOTS): cards[0]存在 → 一顆強化石chip(chip_stone), 否則
        補一顆「+ 強化石」(chip_add)。服飾格沒有精煉/附魔的概念, refine_label
        永不顯示。
    影子裝備(SHADOW_SLOTS): 沒有任何chip(spec: 只有基本裝備, 無卡片/附魔欄位)。

grade_label只有GENERAL_SLOTS的格才顯示(服飾/影子裝備沒有升階概念); grade
為"none"時同樣不顯示(沒升階=不畫這個標籤, 不是畫一個空字)。
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QWidget

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
_GRADE_LETTERS = {"D": "D", "C": "C", "B": "B", "A": "A"}

_SLOT_HEIGHT = 28
_LABEL_WIDTH = 70


def _make_chip(text: str, object_name: str) -> QToolButton:
    btn = QToolButton()
    btn.setText(text)
    btn.setObjectName(object_name)
    btn.setAutoRaise(False)
    return btn


class SlotWidget(QFrame):
    item_clicked = Signal()
    refine_clicked = Signal()
    grade_clicked = Signal()
    card_clicked = Signal(int)
    enchant_clicked = Signal(int)
    stone_clicked = Signal()
    add_card_clicked = Signal()
    add_enchant_clicked = Signal()
    add_stone_clicked = Signal()
    clear_requested = Signal()
    cost_targets_requested = Signal()
    hovered = Signal(bool)

    def __init__(self, slot_key: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.slot_key = slot_key
        self.setObjectName("SlotWidget")
        self.setFixedHeight(_SLOT_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(6)

        self.slot_label = QLabel(SLOT_LABELS[slot_key])
        self.slot_label.setFixedWidth(_LABEL_WIDTH)
        self.slot_label.setProperty("muted", True)
        layout.addWidget(self.slot_label)

        self.refine_label = QLabel("")
        self.refine_label.setVisible(False)
        layout.addWidget(self.refine_label)

        self.grade_label = QLabel("")
        self.grade_label.setVisible(False)
        layout.addWidget(self.grade_label)

        self.name_label = QLabel(_UNEQUIPPED_TEXT)
        layout.addWidget(self.name_label, 1)

        self._chips_widget = QWidget()
        self._chips_layout = QHBoxLayout(self._chips_widget)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(4)
        layout.addWidget(self._chips_widget, 0, Qt.AlignRight)

        self._cfg = None

    def _clear_chips(self) -> None:
        while self._chips_layout.count():
            item = self._chips_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _add_chip(self, text: str, object_name: str) -> None:
        self._chips_layout.addWidget(_make_chip(text, object_name))

    def set_config(self, cfg, session) -> None:
        self._cfg = cfg
        self._clear_chips()

        if cfg is None:
            self.name_label.setText(_UNEQUIPPED_TEXT)
            self.name_label.setProperty("dim", True)
            self.refine_label.setVisible(False)
            self.grade_label.setVisible(False)
            return

        self.name_label.setProperty("dim", False)
        self.name_label.setText(session.item_display(cfg.item_id))

        is_costume = self.slot_key in COSTUME_SLOTS
        is_general = self.slot_key in GENERAL_SLOTS

        if not is_costume and cfg.refine > 0:
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
        elif is_costume:
            self._fill_costume_chips(cfg, session)
        # SHADOW_SLOTS: 無chips

    def _fill_general_chips(self, cfg, session) -> None:
        for card_id in cfg.cards:
            self._add_chip(session.item_display(card_id), "chip_card")
        entry = session.catalog.get(cfg.item_id)
        slot_count = entry.slot_count if entry is not None else 0
        if slot_count > len(cfg.cards):
            self._add_chip("+ 卡片", "chip_add")

        pools = session.enchant_pools(cfg.item_id)
        filled = 0
        for option in cfg.enchants:
            if option is not None:
                filled += 1
                self._add_chip(session.option_display(option), "chip_enchant")
        if len(pools) > filled:
            self._add_chip("+ 附魔", "chip_add")

    def _fill_costume_chips(self, cfg, session) -> None:
        if cfg.cards and cfg.cards[0] is not None:
            self._add_chip(session.item_display(cfg.cards[0]), "chip_stone")
        else:
            self._add_chip("+ 強化石", "chip_add")

    def set_highlight(self, on: bool) -> None:
        self.setProperty("highlight", on)
        self.style().unpolish(self)
        self.style().polish(self)

    def chip_buttons(self) -> list[QToolButton]:
        return [self._chips_layout.itemAt(i).widget() for i in range(self._chips_layout.count())]

    def enterEvent(self, event) -> None:
        self.hovered.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.hovered.emit(False)
        super().leaveEvent(event)
