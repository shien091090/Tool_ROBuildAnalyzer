"""EffectsTab — 效果結算頁(T7): 四分類對齊表 + 優勢高亮 + 未計入條件效果 +
其他效果(收合) + warnings, 整頁包在QScrollArea裡(spec §9.1版面對策)。

資料只透過session.describe_missing()做缺項可讀化, 其餘全部吃AnalyzerSession.
evaluate()/compare()回傳的dataclass(BuildEffects/CompareRow) — 不重新解析
key字串或重跑分類邏輯(分類已由parser.py算好放在categories/CompareRow.category)。

四分類表格版面: 3欄(效果/配裝A名/配裝B名), 每個分類先插一列dim小字標題並
setSpan橫跨3欄, 再逐列印該分類的CompareRow; 數值欄等寬字體右對齊, 優勢方
cell字色good且粗體, None cell顯示"—"(dim色), tie不著色。
"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.entries import CAT_ABILITY, CAT_DAMAGE, CAT_OTHER, CAT_RESIST, CAT_SECONDARY, KIND_UNRECOGNIZED
from app.gui.slot_widget import SLOT_LABELS
from app.gui.theme import DIM, GOOD, WARN

GLOBAL_NOTE = "機率觸發類效果與部分敘述有寫但client腳本未編碼的效果不在數值加總內, 請以道具敘述為準"

CATEGORY_LABEL = {
    CAT_DAMAGE: "傷害",
    CAT_RESIST: "抗性",
    CAT_ABILITY: "能力",
    CAT_SECONDARY: "次要能力",
    CAT_OTHER: "其他",
}
CATEGORY_ORDER = [CAT_DAMAGE, CAT_RESIST, CAT_ABILITY, CAT_SECONDARY, CAT_OTHER]

_DASH_TEXT = "—"
_MISSING_PREFIX = "缺: "
_MISSING_SEP = "、"
_UNCOMPUTABLE_TEXT = "表達式無法計算"
_UNCOUNTED_TITLE_FORMAT = "⚠ 未計入的條件效果 ({})"
_OTHERS_TITLE_FORMAT = "其他效果(不計入加總) ({})"
_COL_HEADERS = ["效果", "配裝A", "配裝B"]

_TABLE_FONT_FAMILY = "Consolas"


def fmt_value(value: float | None, unit: str) -> str:
    if value is None:
        return _DASH_TEXT
    if value == 0:
        value = 0.0  # 正規化負零(-0.0): 避免":g"把它印成"-0"導致"+-0%"
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:g}{unit}"


def _clear_layout(layout) -> None:
    """清空一個QVBoxLayout裡所有子widget — _fill_uncounted/_fill_others/
    show_error共用, 避免各自複製同一段takeAt/deleteLater迴圈。"""
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()


class EffectsTab(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        content = QWidget()
        scroll.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet(f"color: {WARN}; font-weight: bold;")
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        self.note_label = QLabel(GLOBAL_NOTE)
        self.note_label.setStyleSheet(f"color: {WARN};")
        self.note_label.setWordWrap(True)
        layout.addWidget(self.note_label)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(_COL_HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        layout.addWidget(self.table)

        self.uncounted_box = QGroupBox()
        self.uncounted_box.setObjectName("uncounted_box")
        self.uncounted_box.setStyleSheet(f"QGroupBox#uncounted_box::title {{ color: {WARN}; }}")
        self._uncounted_layout = QVBoxLayout(self.uncounted_box)
        layout.addWidget(self.uncounted_box)

        self.others_box = QGroupBox()
        self.others_box.setCheckable(False)
        self._others_toggle = QToolButton()
        self._others_toggle.setCheckable(True)
        self._others_toggle.setChecked(False)
        self._others_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._others_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._others_toggle.toggled.connect(self._on_others_toggled)
        others_outer = QVBoxLayout(self.others_box)
        others_outer.setContentsMargins(0, 0, 0, 0)
        header_row = QHBoxLayout()
        header_row.addWidget(self._others_toggle)
        header_row.addStretch(1)
        others_outer.addLayout(header_row)
        self._others_body = QWidget()
        self._others_layout = QVBoxLayout(self._others_body)
        self._others_body.setVisible(False)
        others_outer.addWidget(self._others_body)
        layout.addWidget(self.others_box)

        self.warnings_label = QLabel("")
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setVisible(False)
        layout.addWidget(self.warnings_label)

        layout.addStretch(1)

    def _on_others_toggled(self, checked: bool) -> None:
        self._others_toggle.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        self._others_body.setVisible(checked)

    def show_error(self, text: str) -> None:
        """顯示錯誤前先清掉舊的成功結果 — 否則錯誤banner之下還留著上一次
        recompute的table/未計入/其他/warnings, 使用者可能誤把舊數字當成
        目前結果讀。"""
        self.table.clearContents()
        self.table.setRowCount(0)

        _clear_layout(self._uncounted_layout)
        self.uncounted_box.setTitle(_UNCOUNTED_TITLE_FORMAT.format(0))

        _clear_layout(self._others_layout)
        self._others_toggle.setText(_OTHERS_TITLE_FORMAT.format(0))

        self.warnings_label.setText("")
        self.warnings_label.setVisible(False)

        self.error_label.setText(text)
        self.error_label.setVisible(True)

    def set_results(self, session, name_a: str, eff_a, name_b: str, eff_b, rows: list) -> None:
        self.error_label.setVisible(False)
        self.error_label.setText("")

        self.table.setHorizontalHeaderLabels(["效果", name_a, name_b])
        self._fill_table(rows)
        self._fill_uncounted(session, eff_a, eff_b)
        self._fill_others(name_a, eff_a, name_b, eff_b)
        self._fill_warnings(name_a, eff_a, name_b, eff_b)

    def _fill_table(self, rows: list) -> None:
        self.table.clearContents()
        self.table.setRowCount(0)

        by_cat: dict[str, list] = {c: [] for c in CATEGORY_ORDER}
        for row in rows:
            by_cat.setdefault(row.category, []).append(row)

        mono_font = QFont(_TABLE_FONT_FAMILY)

        r = 0
        for cat in CATEGORY_ORDER:
            cat_rows = by_cat.get(cat, [])
            if not cat_rows:
                continue
            self.table.insertRow(r)
            header_item = QTableWidgetItem(CATEGORY_LABEL[cat])
            header_item.setForeground(QColor(DIM))
            self.table.setItem(r, 0, header_item)
            self.table.setSpan(r, 0, 1, 3)
            r += 1

            for row in cat_rows:
                self.table.insertRow(r)
                key_item = QTableWidgetItem(row.key)
                self.table.setItem(r, 0, key_item)

                for col, value in ((1, row.a), (2, row.b)):
                    item = QTableWidgetItem(fmt_value(value, row.unit))
                    item.setFont(mono_font)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    if value is None:
                        item.setForeground(QColor(DIM))
                    elif row.advantage != "tie" and row.advantage == ("a" if col == 1 else "b"):
                        item.setForeground(QColor(GOOD))
                        f = QFont(mono_font)
                        f.setBold(True)
                        item.setFont(f)
                    self.table.setItem(r, col, item)
                r += 1

    def _fill_uncounted(self, session, eff_a, eff_b) -> None:
        _clear_layout(self._uncounted_layout)

        entries = [("A", se) for se in eff_a.unresolved] + [("B", se) for se in eff_b.unresolved]
        self.uncounted_box.setTitle(_UNCOUNTED_TITLE_FORMAT.format(len(entries)))

        for tag, se in entries:
            entry = se.entry
            extra = entry.extra or {}
            condition = extra.get("condition")
            missing = extra.get("missing") or []
            raw_lines = extra.get("raw_lines") or []
            slot_label = SLOT_LABELS.get(se.slot_key, se.slot_key)
            missing_text = (
                _MISSING_PREFIX + _MISSING_SEP.join(session.describe_missing(missing))
                if missing else _MISSING_PREFIX + _UNCOMPUTABLE_TEXT
            )
            label = QLabel(f"{tag}・{se.source}（{slot_label}）  <code>{condition}</code>  {missing_text}")
            label.setToolTip("\n".join(raw_lines))
            label.setTextFormat(Qt.TextFormat.RichText)
            self._uncounted_layout.addWidget(label)

    def _fill_others(self, name_a: str, eff_a, name_b: str, eff_b) -> None:
        _clear_layout(self._others_layout)

        entries = [("A", se) for se in eff_a.others] + [("B", se) for se in eff_b.others]
        self._others_toggle.setText(_OTHERS_TITLE_FORMAT.format(len(entries)))

        for tag, se in entries:
            entry = se.entry
            if entry.kind == KIND_UNRECOGNIZED:
                text = (entry.extra or {}).get("raw_line", "")
            else:
                text = entry.key
            label = QLabel(f"{tag}・{se.source}: {text}")
            self._others_layout.addWidget(label)

    def _fill_warnings(self, name_a: str, eff_a, name_b: str, eff_b) -> None:
        lines = []
        for name, eff in ((name_a, eff_a), (name_b, eff_b)):
            for w in eff.warnings:
                lines.append(f"{name}: {w}")
        if lines:
            self.warnings_label.setText("\n".join(lines))
            self.warnings_label.setVisible(True)
        else:
            self.warnings_label.setText("")
            self.warnings_label.setVisible(False)
