"""CostTab — 成本估算頁(T8): 兩張「期望總成本」卡 + 逐件三層明細樹。

只透過session.cost()/session.prices/session.item_display()等既有方法取數,
不重新解析/重算任何Fraction — 這裡的三個fmt_*/path_text函式是唯一把
Fraction轉成顯示字串的地方(GUI edge), 其餘全程保持Fraction原樣傳遞。

樹狀結構(4欄: 部位/養成路徑/期望Zeny/本體):
    「配裝A」/「配裝B」兩個固定頂層列(不管該側是否算成功, 恆各一個, 讓
    tree.topLevelItemCount()永遠是2) → 逐件ItemCostReport一列 → 三層子節點
    (直接消耗/中間合成品/基礎材料攤開) + 手續費節點(四筆) + item.warnings
    (逐條dim色)。report.items為空(該配裝完全沒有格掛cost_targets)時改顯示
    一列提示, 引導使用者去右鍵部位設定。
"""
from fractions import Fraction

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from app.core.build import SlotConfig
from app.core.cost.report import BuildCostReport, ItemCostReport
from app.gui.slot_widget import SLOT_LABELS
from app.gui.theme import BAD, DIM, TEXT, WARN

GRADE_LABEL = {"none": "無階", "D": "D階", "C": "C階", "B": "B階", "A": "A階"}

_CARD_TITLE_FORMAT = "配裝{} 期望總成本"
_BODY_COUNT_FORMAT = "本體消耗合計: {}件"
_ROOT_LABEL_FORMAT = "配裝{}"
_EMPTY_HINT_TEXT = "(無部位設定成本目標, 右鍵部位→成本設定…)"
_TREE_HEADERS = ["部位", "養成路徑", "期望Zeny", "本體"]
_LAYER_DIRECT_TITLE = "直接消耗(合成品層)"
_LAYER_INTERMEDIATE_TITLE = "中間合成品(供參考)"
_LAYER_BASE_TITLE = "基礎材料攤開"
_LAYER_FEES_TITLE = "手續費"
_FEE_EXCHANGE_LABEL = "兌換手續費"
_FEE_REFINE_LABEL = "精煉手續費"
_FEE_GRADE_LABEL = "升階手續費"
_FEE_ENCHANT_LABEL = "附魔費"
_NO_PRICE_SUFFIX = "(無報價)"
_MATERIAL_QTY_FORMAT = "{} x {}"
_BASE_MATERIAL_FORMAT = "{} x {} x {} = {}"


def fmt_zeny(v: Fraction) -> str:
    return f"{int(v):,}"


def fmt_qty(v: Fraction) -> str:
    return f"{float(v):.2f}"


def path_text(cfg: SlotConfig) -> str:
    ct = cfg.cost_targets
    if ct is None:
        return ""
    return f"{GRADE_LABEL[ct.grade_from]}+{ct.refine_from} → {GRADE_LABEL[cfg.grade]}+{cfg.refine}"


class CostTab(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        cards_row = QHBoxLayout()
        self.total_a, self._body_a, self._title_a = self._build_card(cards_row, "A")
        self.total_b, self._body_b, self._title_b = self._build_card(cards_row, "B")
        outer.addLayout(cards_row)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(_TREE_HEADERS))
        self.tree.setHeaderLabels(_TREE_HEADERS)
        outer.addWidget(self.tree, 1)

        self.warnings_label = QLabel("")
        self.warnings_label.setWordWrap(True)
        self.warnings_label.setStyleSheet(f"color: {WARN};")
        self.warnings_label.setVisible(False)
        outer.addWidget(self.warnings_label)

    @staticmethod
    def _build_card(cards_row: QHBoxLayout, tag: str) -> tuple[QLabel, QLabel, QLabel]:
        card = QFrame()
        card.setObjectName("BuildPanel")  # 沿用既有panel色票(theme.py的QSS選擇器)
        layout = QVBoxLayout(card)
        title = QLabel(_CARD_TITLE_FORMAT.format(tag))
        title.setProperty("muted", True)
        layout.addWidget(title)
        total = QLabel("")
        total.setStyleSheet(f"color: {TEXT}; font-weight: bold; font-size: 20px; font-family: Consolas;")
        layout.addWidget(total)
        body = QLabel("")
        body.setProperty("dim", True)
        layout.addWidget(body)
        cards_row.addWidget(card, 1)
        return total, body, title

    def set_results(
        self,
        session,
        name_a,
        build_a,
        report_a: BuildCostReport | None,
        err_a: str | None,
        name_b,
        build_b,
        report_b: BuildCostReport | None,
        err_b: str | None,
    ) -> None:
        self._fill_card(self.total_a, self._body_a, report_a, err_a)
        self._fill_card(self.total_b, self._body_b, report_b, err_b)

        self.tree.clear()
        self._fill_root("A", session, build_a, report_a)
        self._fill_root("B", session, build_b, report_b)
        self.tree.expandAll()

        self._fill_warnings(name_a, report_a, name_b, report_b)

    def _fill_card(self, total_label: QLabel, body_label: QLabel, report: BuildCostReport | None,
                   err: str | None) -> None:
        if err is not None:
            total_label.setText(err)
            total_label.setStyleSheet(f"color: {BAD}; font-weight: bold; font-size: 14px;")
            body_label.setText("")
            body_label.setVisible(False)
            return
        total_label.setStyleSheet(f"color: {TEXT}; font-weight: bold; font-size: 20px; font-family: Consolas;")
        total_label.setText(fmt_zeny(report.zeny_total))
        body_sum = sum((item.body_count for item in report.items), Fraction(0))
        body_label.setText(_BODY_COUNT_FORMAT.format(fmt_qty(body_sum)))
        body_label.setVisible(True)

    def _fill_root(self, tag: str, session, build, report: BuildCostReport | None) -> None:
        root = QTreeWidgetItem([_ROOT_LABEL_FORMAT.format(tag)])
        self.tree.addTopLevelItem(root)
        if report is None:
            return
        if not report.items:
            root.addChild(QTreeWidgetItem([_EMPTY_HINT_TEXT]))
            return
        for item in report.items:
            self._fill_item(root, session, build, item)

    def _fill_item(self, root: QTreeWidgetItem, session, build, item: ItemCostReport) -> None:
        cfg = build.slots.get(item.slot_key)
        row = QTreeWidgetItem([
            f"{SLOT_LABELS.get(item.slot_key, item.slot_key)} {item.item_name}",
            path_text(cfg) if cfg is not None else "",
            fmt_zeny(item.zeny_total),
            fmt_qty(item.body_count),
        ])
        root.addChild(row)

        row.addChild(self._material_layer(_LAYER_DIRECT_TITLE, item.direct))
        row.addChild(self._material_layer(_LAYER_INTERMEDIATE_TITLE, item.intermediates))
        row.addChild(self._base_material_layer(session, item.base))
        row.addChild(self._fee_layer(item))

        for w in item.warnings:
            w_item = QTreeWidgetItem([w])
            self._dim(w_item)
            row.addChild(w_item)

    @staticmethod
    def _material_layer(title: str, materials: dict) -> QTreeWidgetItem:
        layer = QTreeWidgetItem([title])
        for name, qty in sorted(materials.items()):
            layer.addChild(QTreeWidgetItem([_MATERIAL_QTY_FORMAT.format(name, fmt_qty(qty))]))
        return layer

    @staticmethod
    def _base_material_layer(session, base: dict) -> QTreeWidgetItem:
        layer = QTreeWidgetItem([_LAYER_BASE_TITLE])
        for name, qty in sorted(base.items()):
            if name in session.prices:
                price = session.prices[name]
                price_text = f"{price:,}"
            else:
                price = 0
                price_text = f"0{_NO_PRICE_SUFFIX}"
            subtotal = qty * Fraction(price)
            layer.addChild(QTreeWidgetItem([
                _BASE_MATERIAL_FORMAT.format(name, fmt_qty(qty), price_text, fmt_zeny(subtotal))
            ]))
        return layer

    @staticmethod
    def _fee_layer(item: ItemCostReport) -> QTreeWidgetItem:
        layer = QTreeWidgetItem([_LAYER_FEES_TITLE])
        for label, value in (
            (_FEE_EXCHANGE_LABEL, item.exchange_fee),
            (_FEE_REFINE_LABEL, item.refine_fee),
            (_FEE_GRADE_LABEL, item.grade_fee),
            (_FEE_ENCHANT_LABEL, item.enchant_zeny),
        ):
            layer.addChild(QTreeWidgetItem([f"{label}: {fmt_zeny(value)}"]))
        return layer

    @staticmethod
    def _dim(tree_item: QTreeWidgetItem) -> None:
        tree_item.setForeground(0, QColor(DIM))

    def _fill_warnings(self, name_a, report_a: BuildCostReport | None, name_b, report_b: BuildCostReport | None) -> None:
        lines = []
        for name, report in ((name_a, report_a), (name_b, report_b)):
            if report is None:
                continue
            for w in report.warnings:
                lines.append(f"{name}: {w}")
        if lines:
            self.warnings_label.setText("\n".join(lines))
            self.warnings_label.setVisible(True)
        else:
            self.warnings_label.setText("")
            self.warnings_label.setVisible(False)
