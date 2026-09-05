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
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QToolButton, QWidget

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
_ADD_CARD_TEXT = "+ 卡片"
_ADD_ENCHANT_TEXT = "+ 附魔"
_ADD_STONE_TEXT = "+ 強化石"
_GRADE_LETTERS = {"D": "D", "C": "C", "B": "B", "A": "A"}

_SLOT_HEIGHT = 28
_LABEL_WIDTH = 70

_MENU_REFINE_TEXT = "設定精煉…"
_MENU_GRADE_TEXT = "設定階級…"
_MENU_CLEAR_TEXT = "清空此格"
_MENU_COST_TARGETS_TEXT = "成本設定…"


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
        super().mousePressEvent(event)


def _repolish(widget) -> None:
    """QSS的動態屬性選擇器(如[dim="true"]/[highlight="true"])不會在setProperty
    後自動重新計算樣式, 必須手動unpolish+polish才會生效 — 抽成共用helper,
    避免set_config的dim切換與set_highlight各自重複這兩行。
    """
    widget.style().unpolish(widget)
    widget.style().polish(widget)


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

        self._cfg = None

    def _clear_chips(self) -> None:
        while self._chips_layout.count():
            item = self._chips_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _add_chip(self, text: str, object_name: str, on_click=None) -> None:
        btn = _make_chip(text, object_name)
        if on_click is not None:
            btn.clicked.connect(on_click)
        self._chips_layout.addWidget(btn)

    def set_config(self, cfg, session) -> None:
        self._cfg = cfg
        self._clear_chips()

        if cfg is None:
            self.name_label.setText(_UNEQUIPPED_TEXT)
            self.name_label.setProperty("dim", True)
            _repolish(self.name_label)
            self.refine_label.setVisible(False)
            self.grade_label.setVisible(False)
            return

        self.name_label.setProperty("dim", False)
        _repolish(self.name_label)
        self.name_label.setText(session.item_display(cfg.item_id))

        is_costume = self.slot_key in COSTUME_SLOTS
        is_general = self.slot_key in GENERAL_SLOTS

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
        elif is_costume:
            self._fill_costume_chips(cfg, session)
        # SHADOW_SLOTS: 無chips

    def _fill_general_chips(self, cfg, session) -> None:
        for i, card_id in enumerate(cfg.cards):
            self._add_chip(session.item_display(card_id), "chip_card",
                            lambda _checked=False, i=i: self.card_clicked.emit(i))
        entry = session.catalog.get(cfg.item_id)
        slot_count = entry.slot_count if entry is not None else 0
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

    def _fill_costume_chips(self, cfg, session) -> None:
        if cfg.cards and cfg.cards[0] is not None:
            self._add_chip(session.item_display(cfg.cards[0]), "chip_stone", self.stone_clicked.emit)
        else:
            self._add_chip(_ADD_STONE_TEXT, "chip_add", self.add_stone_clicked.emit)

    def set_highlight(self, on: bool) -> None:
        self.setProperty("highlight", on)
        _repolish(self)

    def chip_buttons(self) -> list[QToolButton]:
        return [self._chips_layout.itemAt(i).widget() for i in range(self._chips_layout.count())]

    def enterEvent(self, event) -> None:
        self.hovered.emit(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.hovered.emit(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        """點在name_label/refine_label/grade_label/chips以外的空白處(精煉編輯規則2
        「點refine_label或空白處的『精煉』」) — 這幾個子widget各自已在自己的
        mousePressEvent吃掉事件(不會傳到這裡), 所以真的落到這裡的一定是空白處。
        """
        if event.button() == Qt.MouseButton.LeftButton:
            self.refine_clicked.emit()
        super().mousePressEvent(event)

    def contextMenuEvent(self, event) -> None:
        """fix round1第3點: 「設定精煉…」/「設定階級…」補在「清空此格」前面,
        給已裝備格一個一定找得到的精煉/階級編輯入口(不用再賭blank-space
        click的窄邊margin) — 只在該格「已裝備且該slot類型支援」時才加進選單。
        """
        menu = QMenu(self)
        equipped = self._cfg is not None
        is_costume = self.slot_key in COSTUME_SLOTS
        is_general = self.slot_key in GENERAL_SLOTS
        refine_action = menu.addAction(_MENU_REFINE_TEXT) if equipped and not is_costume else None
        grade_action = menu.addAction(_MENU_GRADE_TEXT) if equipped and is_general else None
        clear_action = menu.addAction(_MENU_CLEAR_TEXT)
        cost_action = menu.addAction(_MENU_COST_TARGETS_TEXT)
        cost_action.setEnabled(False)  # T8接成本設定對話框, T6先放著disabled
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
