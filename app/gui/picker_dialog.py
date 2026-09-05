"""PickerDialog — 部位過濾選擇清單(裝備/卡片/強化石/附魔共用一套UI, T6)。

四種挑選對象(equipment/card/stone/enchant)資料來源不同, 但呈現/互動規則一致:
兩欄tree(名稱, 機率)、搜尋框即時過濾、雙擊或Enter選取、底部顯示筆數與
「清除」(選取CLEAR哨兵, 呼叫端解讀成刪除該格內容)/「關閉(Esc)」按鈕。只有
equipment且傳入job_id時才建「僅顯示本職業可裝備」核取方塊(卡片/強化石/
附魔沒有職業限定資訊, 不建這個方塊)。

四個`_rows`static method只做「session資料→PickRow清單」的純轉換, 不碰Qt,
方便測試不開對話框就驗證資料是否正確; 四個`pick_*` static method才是
真的開對話框的呼叫端(build_panel的thin handler直接呼叫這幾個)。
"""
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from app.gui.item_text import description_to_html
from app.gui.slot_widget import SLOT_LABELS

CLEAR = object()  # 「清除」哨兵 — 使用者按「清除」選取的result, 呼叫端解讀成刪除該格內容

_TITLE_EQUIPMENT_FORMAT = "選擇裝備 — {}"
_TITLE_CARD_FORMAT = "選擇卡片 — {}"
_TITLE_STONE_FORMAT = "選擇強化石 — {}"
_TITLE_ENCHANT_FORMAT = "選擇附魔 — {} 第{}槽"
_NOTE_TEXT = "雙擊或按Enter選取, Esc關閉"
_JOB_FILTER_TEXT = "僅顯示本職業可裝備"
_SEARCH_PLACEHOLDER = "搜尋名稱…"
_COUNT_FORMAT = "{} 筆"
_CLEAR_TEXT = "清除"
_CLOSE_TEXT = "關閉(Esc)"


@dataclass(frozen=True)
class PickRow:
    key: object      # item_id(equipment/card/stone) 或 option internal_name(enchant)
    name: str
    rate_text: str
    tooltip_html: str


class PickerDialog(QDialog):
    def __init__(self, parent, session, title: str, note: str, rows: list[PickRow], job_filter=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self._session = session
        self._job_filter = job_filter
        self._all_rows: list[PickRow] = list(rows)
        self.result = None

        layout = QVBoxLayout(self)
        if note:
            note_label = QLabel(note)
            note_label.setProperty("muted", True)
            layout.addWidget(note_label)

        top_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(_SEARCH_PLACEHOLDER)
        top_row.addWidget(self.search, 1)
        self.job_check: QCheckBox | None = None
        if job_filter is not None:
            self.job_check = QCheckBox(_JOB_FILTER_TEXT)
            self.job_check.setChecked(True)
            top_row.addWidget(self.job_check)
        layout.addLayout(top_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(2)
        layout.addWidget(self.tree, 1)

        bottom_row = QHBoxLayout()
        self._count_label = QLabel()
        bottom_row.addWidget(self._count_label)
        bottom_row.addStretch(1)
        clear_btn = QPushButton(_CLEAR_TEXT)
        close_btn = QPushButton(_CLOSE_TEXT)
        bottom_row.addWidget(clear_btn)
        bottom_row.addWidget(close_btn)
        layout.addLayout(bottom_row)

        self.search.textChanged.connect(self._rebuild)
        if self.job_check is not None:
            self.job_check.toggled.connect(self._on_job_toggled)
        self.tree.itemActivated.connect(self._accept_item)
        clear_btn.clicked.connect(self._on_clear)
        close_btn.clicked.connect(self.reject)

        self._rebuild()

    def _on_job_toggled(self, checked: bool) -> None:
        job_id, recompute = self._job_filter
        self._all_rows = recompute(job_id if checked else None)
        self._rebuild()

    def _rebuild(self) -> None:
        query = self.search.text().strip()
        rows = self._all_rows if not query else [r for r in self._all_rows if query in r.name]
        self.tree.clear()
        for row in rows:
            item = QTreeWidgetItem([row.name, row.rate_text])
            item.setData(0, Qt.ItemDataRole.UserRole, row.key)
            item.setToolTip(0, row.tooltip_html)
            self.tree.addTopLevelItem(item)
        self._count_label.setText(_COUNT_FORMAT.format(len(rows)))

    def _accept_item(self, item: QTreeWidgetItem, _column: int) -> None:
        self.result = item.data(0, Qt.ItemDataRole.UserRole)
        self.accept()

    def _on_clear(self) -> None:
        self.result = CLEAR
        self.accept()

    @staticmethod
    def equipment_rows(session, slot_key: str, job_id: int | None) -> list[PickRow]:
        entries = session.catalog.equipment_for_slot(slot_key, job_id=job_id)
        return [PickRow(e.item_id, e.display_name, "", description_to_html(e.description)) for e in entries]

    @staticmethod
    def card_rows(session, slot_key: str) -> list[PickRow]:
        entries = session.catalog.cards_for_slot(slot_key)
        return [PickRow(e.item_id, e.display_name, "", description_to_html(e.description)) for e in entries]

    @staticmethod
    def stone_rows(session, slot_key: str) -> list[PickRow]:
        entries = session.catalog.stones_for_slot(slot_key)
        return [PickRow(e.item_id, e.display_name, "", description_to_html(e.description)) for e in entries]

    @staticmethod
    def enchant_rows(session, pool) -> list[PickRow]:
        return [
            PickRow(o.option_internal_name, o.display_name, f"{float(o.probability) * 100:.2f}%",
                     description_to_html(o.description))
            for o in pool.options
        ]

    @staticmethod
    def pick_equipment(parent, session, slot_key: str, job_id: int | None):
        rows = PickerDialog.equipment_rows(session, slot_key, job_id)
        job_filter = None
        if job_id is not None:
            job_filter = (job_id, lambda jid: PickerDialog.equipment_rows(session, slot_key, jid))
        title = _TITLE_EQUIPMENT_FORMAT.format(SLOT_LABELS[slot_key])
        dlg = PickerDialog(parent, session, title, _NOTE_TEXT, rows, job_filter=job_filter)
        dlg.exec()
        return dlg.result

    @staticmethod
    def pick_card(parent, session, slot_key: str):
        rows = PickerDialog.card_rows(session, slot_key)
        title = _TITLE_CARD_FORMAT.format(SLOT_LABELS[slot_key])
        dlg = PickerDialog(parent, session, title, _NOTE_TEXT, rows)
        dlg.exec()
        return dlg.result

    @staticmethod
    def pick_stone(parent, session, slot_key: str):
        rows = PickerDialog.stone_rows(session, slot_key)
        title = _TITLE_STONE_FORMAT.format(SLOT_LABELS[slot_key])
        dlg = PickerDialog(parent, session, title, _NOTE_TEXT, rows)
        dlg.exec()
        return dlg.result

    @staticmethod
    def pick_enchant(parent, session, item_id: int, pool):
        rows = PickerDialog.enchant_rows(session, pool)
        title = _TITLE_ENCHANT_FORMAT.format(session.item_display(item_id), pool.slot_index)
        dlg = PickerDialog(parent, session, title, _NOTE_TEXT, rows)
        dlg.exec()
        return dlg.result
