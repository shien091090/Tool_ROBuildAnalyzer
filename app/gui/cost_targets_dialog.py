"""CostTargetsDialog — 右鍵部位「成本設定…」開的每格成本目標對話框(T8)。

只碰CostTargets/SlotConfig dataclass與session的唯讀查詢方法(refine_table_
choices/enchant_pools/option_display), 不呼叫任何cost引擎求解函式 — 這裡
只負責蒐集使用者輸入、組出CostTargets(或None代表不計此格成本), 真正的
apply_cost_targets(純方法)/成本重算(MainWindow.recompute)都在別處。

grade_from只有GENERAL_SLOTS(一般裝備)可選 — 服飾/影子裝備沒有升階概念
(spec §6), 該combo固定"none"且disabled。「計算此格養成成本」checkbox未勾
時, edit()回傳的CostTargets為None, 等同呼叫apply_cost_targets(slot_key,
None)清掉此格的cost_targets(不計成本, 跟從未設定過毫無區別)。

enchant_goal的選項清單依controller amendment 2的降冪對位規則, 只列出
cfg.enchants裡目前已選(非None)的槽位 — 跟session.enchant_pools(cfg.item_id)
依索引一一對應(cfg.enchants[i] <-> pools[i].slot_index), 與cost引擎
report._derive_enchant_goal同一套對位邏輯, 不重新推導。
"""
from PySide6.QtWidgets import QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QSpinBox

from app.core.build import CostTargets, GRADE_LEVELS, SlotConfig
from app.gui.slot_widget import GENERAL_SLOTS

GRADE_LABEL = {"none": "無階", "D": "D階", "C": "C階", "B": "B階", "A": "A階"}
STRATEGY_LABEL = {"last_slot_only": "只看最後格", "stop_when_hit": "中途附到即停"}

_TITLE = "成本設定"
_ENABLE_TEXT = "計算此格養成成本"
_REFINE_FROM_LABEL = "起始精煉"
_GRADE_FROM_LABEL = "起始階級"
_REFINE_TABLE_LABEL = "精煉表"
_ENCHANT_STRATEGY_LABEL = "附魔策略"
_ENCHANT_GOAL_LABEL = "附魔目標"
_REFINE_TABLE_UNSET_TEXT = "(未指定)"
_ENCHANT_GOAL_AUTO_TEXT = "自動(取最末詞條)"
_ENCHANT_GOAL_ENTRY_FMT = "slot{}: {}"


class CostTargetsDialog(QDialog):
    def __init__(self, parent, session, slot_key: str, cfg: SlotConfig):
        super().__init__(parent)
        self.setWindowTitle(_TITLE)
        ct = cfg.cost_targets

        form = QFormLayout(self)

        self.enable_check = QCheckBox(_ENABLE_TEXT)
        self.enable_check.setChecked(ct is not None)
        form.addRow(self.enable_check)

        self.refine_from = QSpinBox()
        self.refine_from.setRange(0, cfg.refine)
        self.refine_from.setValue(ct.refine_from if ct is not None else 0)
        form.addRow(_REFINE_FROM_LABEL, self.refine_from)

        self.grade_from = QComboBox()
        if slot_key in GENERAL_SLOTS:
            for grade in GRADE_LEVELS:
                self.grade_from.addItem(GRADE_LABEL[grade], grade)
            initial = ct.grade_from if ct is not None else "none"
            idx = self.grade_from.findData(initial)
            if idx >= 0:
                self.grade_from.setCurrentIndex(idx)
        else:
            self.grade_from.addItem(GRADE_LABEL["none"], "none")
            self.grade_from.setEnabled(False)
        form.addRow(_GRADE_FROM_LABEL, self.grade_from)

        self.refine_table = QComboBox()
        self.refine_table.addItem(_REFINE_TABLE_UNSET_TEXT, None)
        for key, display in session.refine_table_choices():
            self.refine_table.addItem(display, key)
        if ct is not None and ct.refine_table is not None:
            idx = self.refine_table.findData(ct.refine_table)
            if idx >= 0:
                self.refine_table.setCurrentIndex(idx)
        form.addRow(_REFINE_TABLE_LABEL, self.refine_table)

        self.enchant_strategy = QComboBox()
        for key, label in STRATEGY_LABEL.items():
            self.enchant_strategy.addItem(label, key)
        initial_strategy = ct.enchant_strategy if ct is not None else "last_slot_only"
        idx = self.enchant_strategy.findData(initial_strategy)
        if idx >= 0:
            self.enchant_strategy.setCurrentIndex(idx)
        form.addRow(_ENCHANT_STRATEGY_LABEL, self.enchant_strategy)

        self.enchant_goal = QComboBox()
        self.enchant_goal.addItem(_ENCHANT_GOAL_AUTO_TEXT, None)
        pools = session.enchant_pools(cfg.item_id)
        for i, option in enumerate(cfg.enchants):
            if option is None or i >= len(pools):
                continue
            slot_index = pools[i].slot_index
            text = _ENCHANT_GOAL_ENTRY_FMT.format(slot_index, session.option_display(option))
            self.enchant_goal.addItem(text, (slot_index, option))
        if ct is not None and ct.enchant_goal is not None:
            idx = self.enchant_goal.findData(ct.enchant_goal)
            if idx >= 0:
                self.enchant_goal.setCurrentIndex(idx)
        form.addRow(_ENCHANT_GOAL_LABEL, self.enchant_goal)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def result_cost_targets(self) -> CostTargets | None:
        if not self.enable_check.isChecked():
            return None
        return CostTargets(
            refine_from=self.refine_from.value(),
            grade_from=self.grade_from.currentData(),
            refine_table=self.refine_table.currentData(),
            enchant_strategy=self.enchant_strategy.currentData(),
            enchant_goal=self.enchant_goal.currentData(),
        )

    @staticmethod
    def edit(parent, session, slot_key: str, cfg: SlotConfig) -> tuple[bool, CostTargets | None]:
        dlg = CostTargetsDialog(parent, session, slot_key, cfg)
        accepted = dlg.exec() == QDialog.DialogCode.Accepted
        return accepted, (dlg.result_cost_targets() if accepted else None)
