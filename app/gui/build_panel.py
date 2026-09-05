"""BuildPanel — 單一配裝面板(A/B兩個並排): 標頭列(檔案選單/存檔按鈕) + 三段20格。

T6接線: 20格SlotWidget的每個訊號都接到這裡對應的_on_*handler(dialog-driven,
會開QInputDialog/QFileDialog/QMessageBox/PickerDialog, 屬於「呼叫端」), 各
自算完結果再轉呼叫下面成對的`apply_*`純方法(只碰Build dataclass, 不開任何
對話框, 方便測試直接呼叫驗證); apply_*結尾一律`_mark_changed()`
(dirty=True; refresh(); changed.emit())。save_to/load_from/start_new同樣是
不開對話框的純方法, 檔案combo/存檔按鈕的實際使用者互動(含存在時另存另存
新增選檔的QFileDialog/QInputDialog/dirty時的QMessageBox三選一)另外包在
_save_as/_on_new_clicked/_on_file_combo_changed這幾個thin handler裡。
"""
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.core.build import Build, CostTargets, SlotConfig, new_build
from app.gui.picker_dialog import CLEAR, PickerDialog
from app.gui.slot_widget import COSTUME_SLOTS, GENERAL_SLOTS, SLOT_SECTIONS, SlotWidget

_TAG_COLORS = {"A": "#7ec3e8", "B": "#cf9ee8"}
_UNSAVED_ENTRY = "(未儲存新配裝)"
_SAVE_TEXT = "儲存"
_SAVE_AS_TEXT = "另存"
_NEW_TEXT = "新增"

_REFINE_MAX_GENERAL = 20
_REFINE_MAX_SHADOW = 10
_REFINE_DIALOG_TITLE = "精煉"
_REFINE_DIALOG_LABEL = "精煉值"
_GRADE_DIALOG_TITLE = "階級"
_GRADE_DIALOG_LABEL = "選擇階級"
_GRADE_CHOICES = ["none", "D", "C", "B", "A"]
_NEW_DIALOG_TITLE = "新增配裝"
_NEW_DIALOG_LABEL = "配裝名稱"
_SAVE_AS_DIALOG_TITLE = "另存配裝為"
_JSON_FILTER = "JSON (*.json)"
_CONFIRM_TITLE = "尚未儲存"
_CONFIRM_TEXT = "目前配裝有未儲存的變更, 要如何處理?"
_DISCARD_TEXT = "放棄"
_CANCEL_TEXT = "取消"


class BuildPanel(QFrame):
    changed = Signal()

    def __init__(self, tag: str, session):
        super().__init__()
        self.setObjectName("BuildPanel")
        self._tag = tag
        self._session = session
        self.job_id: int | None = None
        self._build: Build = new_build("未命名")
        self._path: Path | None = None
        self._dirty = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        header = QHBoxLayout()
        self._tag_label = QLabel(tag)
        self._tag_label.setStyleSheet(f"color: {_TAG_COLORS.get(tag, '#e2e6ef')}; font-weight: bold;")
        header.addWidget(self._tag_label)

        self.file_combo = QComboBox()
        self._reload_file_combo()
        header.addWidget(self.file_combo, 1)

        self.save_btn = QPushButton(_SAVE_TEXT)
        self.save_as_btn = QPushButton(_SAVE_AS_TEXT)
        self.new_btn = QPushButton(_NEW_TEXT)
        header.addWidget(self.save_btn)
        header.addWidget(self.save_as_btn)
        header.addWidget(self.new_btn)
        outer.addLayout(header)

        self.file_combo.currentIndexChanged.connect(self._on_file_combo_changed)
        self.save_btn.clicked.connect(self._on_save_clicked)
        self.save_as_btn.clicked.connect(self._on_save_as_clicked)
        self.new_btn.clicked.connect(self._on_new_clicked)

        self.slot_widgets: dict[str, SlotWidget] = {}
        for section_title, slot_keys in SLOT_SECTIONS:
            section_label = QLabel(section_title)
            section_label.setProperty("dim", True)
            section_label.setFixedHeight(18)
            outer.addWidget(section_label)

            section_body = QVBoxLayout()
            section_body.setSpacing(0)
            for slot_key in slot_keys:
                widget = SlotWidget(slot_key)
                self.slot_widgets[slot_key] = widget
                self._wire_slot(slot_key, widget)
                section_body.addWidget(widget)
            outer.addLayout(section_body)

        outer.addStretch(0)

    def _wire_slot(self, slot_key: str, widget: SlotWidget) -> None:
        widget.item_clicked.connect(lambda sk=slot_key: self._on_item_clicked(sk))
        widget.refine_clicked.connect(lambda sk=slot_key: self._on_refine_clicked(sk))
        widget.grade_clicked.connect(lambda sk=slot_key: self._on_grade_clicked(sk))
        widget.card_clicked.connect(lambda i, sk=slot_key: self._on_card_clicked(sk, i))
        widget.enchant_clicked.connect(lambda i, sk=slot_key: self._on_enchant_clicked(sk, i))
        widget.stone_clicked.connect(lambda sk=slot_key: self._on_stone_clicked(sk))
        widget.add_card_clicked.connect(lambda sk=slot_key: self._on_add_card_clicked(sk))
        widget.add_enchant_clicked.connect(lambda sk=slot_key: self._on_add_enchant_clicked(sk))
        widget.add_stone_clicked.connect(lambda sk=slot_key: self._on_stone_clicked(sk))
        widget.clear_requested.connect(lambda sk=slot_key: self.apply_item(sk, None))
        widget.cost_targets_requested.connect(lambda sk=slot_key: self._on_cost_targets_requested(sk))
        widget.hovered.connect(lambda on, sk=slot_key: self._on_slot_hovered(sk, on))

    def _reload_file_combo(self) -> None:
        """fix round1第1點: clear()/第一個addItem()各自會發出
        currentIndexChanged(0), 若不擋訊號, 掛著的_on_file_combo_changed會把它
        當成「使用者選了字母序第一個檔案」去load_from — 而此時往往剛save_to()
        完把dirty清乾淨, guard擋不住, 於是剛存好的build被悄悄換成別的檔案。
        呼叫端(目前是_save_as)重建完combo後務必接著呼叫
        _sync_file_combo_selection()把選取項對回真正目前load的檔案。
        """
        self.file_combo.blockSignals(True)
        self.file_combo.clear()
        for p in self._session.list_builds():
            self.file_combo.addItem(p.name)
        self.file_combo.addItem(_UNSAVED_ENTRY)
        self.file_combo.blockSignals(False)

    @property
    def build(self) -> Build:
        return self._build

    @property
    def path(self) -> Path | None:
        return self._path

    @property
    def dirty(self) -> bool:
        return self._dirty

    def set_build(self, build: Build, path: Path | None) -> None:
        self._build = build
        self._path = path
        self._dirty = False
        self.refresh()
        self._sync_file_combo_selection()

    def refresh(self) -> None:
        for slot_key, widget in self.slot_widgets.items():
            widget.set_config(self._build.slots.get(slot_key), self._session)
        suffix = "*" if self._dirty else ""
        self._tag_label.setText(f"{self._tag}{suffix}")

    def _sync_file_combo_selection(self) -> None:
        """程式化載入/存檔後把combo選取項對回目前實際的build path — 用
        blockSignals包起來, 避免觸發_on_file_combo_changed造成重複load_from
        (那個handler是給「使用者手動切換combo」用的, 不是給我們自己同步用的)。
        """
        target = self._path.name if self._path is not None else _UNSAVED_ENTRY
        idx = self.file_combo.findText(target)
        if idx < 0:
            idx = self.file_combo.count() - 1
        self.file_combo.blockSignals(True)
        self.file_combo.setCurrentIndex(idx)
        self.file_combo.blockSignals(False)

    def _mark_changed(self) -> None:
        self._dirty = True
        self.refresh()
        self.changed.emit()

    # -- apply_* (純方法, 不開任何對話框, 供handler與測試共用) --------------

    def apply_item(self, slot_key: str, item_id: int | None) -> None:
        if item_id is None:
            self._build.slots.pop(slot_key, None)
        else:
            old = self._build.slots.get(slot_key)
            self._build.slots[slot_key] = SlotConfig(
                item_id=item_id,
                refine=old.refine if old is not None else 0,
                grade=old.grade if old is not None else "none",
                cards=[],
                enchants=[],
                cost_targets=old.cost_targets if old is not None else None,
            )
        self._mark_changed()

    def apply_refine(self, slot_key: str, refine: int) -> None:
        cfg = self._build.slots.get(slot_key)
        if cfg is None:
            return
        cfg.refine = refine
        self._mark_changed()

    def apply_grade(self, slot_key: str, grade: str) -> None:
        cfg = self._build.slots.get(slot_key)
        if cfg is None:
            return
        cfg.grade = grade
        self._mark_changed()

    def apply_card(self, slot_key: str, index: int | None, card_id: int | None) -> None:
        cfg = self._build.slots.get(slot_key)
        if cfg is None:
            return
        if index is None:
            if card_id is not None:
                cfg.cards.append(card_id)
        elif 0 <= index < len(cfg.cards):
            if card_id is None:
                del cfg.cards[index]
            else:
                cfg.cards[index] = card_id
        self._mark_changed()

    def apply_enchant(self, slot_key: str, index: int, option: str | None) -> None:
        cfg = self._build.slots.get(slot_key)
        if cfg is None:
            return
        pools = self._session.enchant_pools(cfg.item_id)
        while len(cfg.enchants) < len(pools):
            cfg.enchants.append(None)
        if 0 <= index < len(cfg.enchants):
            cfg.enchants[index] = option
        self._mark_changed()

    def apply_stone(self, slot_key: str, stone_id: int | None) -> None:
        cfg = self._build.slots.get(slot_key)
        if cfg is None:
            return
        cfg.cards = [] if stone_id is None else [stone_id]
        self._mark_changed()

    def apply_cost_targets(self, slot_key: str, ct: CostTargets | None) -> None:
        cfg = self._build.slots.get(slot_key)
        if cfg is None:
            return
        cfg.cost_targets = ct
        self._mark_changed()

    # -- 檔案操作(純方法, 不開對話框) -----------------------------------

    def save_to(self, path) -> None:
        self._session.save_build(self._build, path)
        self._path = Path(path)
        self._dirty = False
        self.refresh()

    def load_from(self, path) -> None:
        self.set_build(self._session.load_build(path), Path(path))
        self.changed.emit()

    def start_new(self, name: str) -> None:
        self.set_build(new_build(name), None)
        self.changed.emit()

    # -- dialog-driven handler(thin, 呼叫端): 開對話框→轉呼叫上面的純方法 --

    def _on_item_clicked(self, slot_key: str) -> None:
        result = PickerDialog.pick_equipment(self, self._session, slot_key, self.job_id)
        if result is CLEAR:
            self.apply_item(slot_key, None)
        elif result is not None:
            self.apply_item(slot_key, result)

    def _on_refine_clicked(self, slot_key: str) -> None:
        if slot_key in COSTUME_SLOTS:
            return
        cfg = self._build.slots.get(slot_key)
        if cfg is None:
            return
        upper = _REFINE_MAX_GENERAL if slot_key in GENERAL_SLOTS else _REFINE_MAX_SHADOW
        value, ok = QInputDialog.getInt(self, _REFINE_DIALOG_TITLE, _REFINE_DIALOG_LABEL, cfg.refine, 0, upper)
        if ok:
            self.apply_refine(slot_key, value)

    def _on_grade_clicked(self, slot_key: str) -> None:
        if slot_key not in GENERAL_SLOTS:
            return
        cfg = self._build.slots.get(slot_key)
        if cfg is None:
            return
        current_index = _GRADE_CHOICES.index(cfg.grade) if cfg.grade in _GRADE_CHOICES else 0
        choice, ok = QInputDialog.getItem(
            self, _GRADE_DIALOG_TITLE, _GRADE_DIALOG_LABEL, _GRADE_CHOICES, current_index, False
        )
        if ok:
            self.apply_grade(slot_key, choice)

    def _on_card_clicked(self, slot_key: str, index: int) -> None:
        result = PickerDialog.pick_card(self, self._session, slot_key)
        if result is CLEAR:
            self.apply_card(slot_key, index, None)
        elif result is not None:
            self.apply_card(slot_key, index, result)

    def _on_add_card_clicked(self, slot_key: str) -> None:
        result = PickerDialog.pick_card(self, self._session, slot_key)
        if result is not None and result is not CLEAR:
            self.apply_card(slot_key, None, result)

    def _on_enchant_clicked(self, slot_key: str, index: int) -> None:
        cfg = self._build.slots.get(slot_key)
        if cfg is None:
            return
        pools = self._session.enchant_pools(cfg.item_id)
        if index >= len(pools):
            return
        result = PickerDialog.pick_enchant(self, self._session, cfg.item_id, pools[index])
        if result is CLEAR:
            self.apply_enchant(slot_key, index, None)
        elif result is not None:
            self.apply_enchant(slot_key, index, result)

    def _on_add_enchant_clicked(self, slot_key: str) -> None:
        cfg = self._build.slots.get(slot_key)
        if cfg is None:
            return
        pools = self._session.enchant_pools(cfg.item_id)
        padded = list(cfg.enchants) + [None] * max(0, len(pools) - len(cfg.enchants))
        if None not in padded:
            return
        index = padded.index(None)
        result = PickerDialog.pick_enchant(self, self._session, cfg.item_id, pools[index])
        if result is not None and result is not CLEAR:
            self.apply_enchant(slot_key, index, result)

    def _on_stone_clicked(self, slot_key: str) -> None:
        result = PickerDialog.pick_stone(self, self._session, slot_key)
        if result is CLEAR:
            self.apply_stone(slot_key, None)
        elif result is not None:
            self.apply_stone(slot_key, result)

    def _on_cost_targets_requested(self, slot_key: str) -> None:
        pass  # T8接成本設定對話框; 右鍵選單項目T6先disabled, 此訊號目前不會被觸發

    def _on_slot_hovered(self, slot_key: str, on: bool) -> None:
        if not on:
            for widget in self.slot_widgets.values():
                widget.set_highlight(False)
            return
        cfg = self._build.slots.get(slot_key)
        if cfg is None:
            return
        members: set[int] = set()
        for item_id in [cfg.item_id, *cfg.cards]:
            members |= self._session.active_combo_members(self._build, item_id)
        for other_key, widget in self.slot_widgets.items():
            other_cfg = self._build.slots.get(other_key)
            highlight = other_cfg is not None and (
                other_cfg.item_id in members or any(c in members for c in other_cfg.cards)
            )
            widget.set_highlight(highlight)

    def _on_save_clicked(self) -> None:
        self._save_current()

    def _on_save_as_clicked(self) -> None:
        self._save_as()

    def _on_new_clicked(self) -> None:
        name, ok = QInputDialog.getText(self, _NEW_DIALOG_TITLE, _NEW_DIALOG_LABEL)
        if ok and name:
            self.start_new(name)

    def _on_file_combo_changed(self, index: int) -> None:
        if index < 0:
            return
        text = self.file_combo.itemText(index)
        if text == _UNSAVED_ENTRY:
            return
        target = self._session.builds_dir / text
        if self._path == target:
            return
        if self._dirty and not self._confirm_discard_or_save():
            self._sync_file_combo_selection()  # 使用者取消 → combo復原成目前實際載入的檔案
            return
        self.load_from(target)

    def _confirm_discard_or_save(self) -> bool:
        """dirty時切換檔案前的三選一: 儲存/放棄/取消。回傳True代表可以繼續切換
        (已存檔或使用者選擇放棄變更), False代表要中止切換(使用者選取消, 或
        選了儲存但path未定、又在另存的QFileDialog中取消——fix round1第2點:
        這種情況下save根本沒發生, dirty依然是True, 絕不能讓呼叫端誤以為
        「儲存」選項已經處理完畢就放行去load_from覆蓋掉未存的build)。
        """
        choice = self._ask_discard_or_save()
        if choice == "cancel":
            return False
        if choice == "save":
            return self._save_current()
        return True  # discard: 不存檔但允許繼續切換

    def _ask_discard_or_save(self) -> str:
        """回傳"save"/"discard"/"cancel" — 拆成單獨方法方便測試monkeypatch掉
        QMessageBox, 不必真的彈出視窗就能驗證_confirm_discard_or_save的邏輯。
        """
        box = QMessageBox(self)
        box.setWindowTitle(_CONFIRM_TITLE)
        box.setText(_CONFIRM_TEXT)
        save_btn = box.addButton(_SAVE_TEXT, QMessageBox.ButtonRole.AcceptRole)
        discard_btn = box.addButton(_DISCARD_TEXT, QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = box.addButton(_CANCEL_TEXT, QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save_btn:
            return "save"
        if clicked is discard_btn:
            return "discard"
        return "cancel"

    def _save_current(self) -> bool:
        """回傳True代表真的存到檔了(path已存在直接存, 或另存成功); False代表
        沒有path且另存被使用者取消 — 呼叫端(_confirm_discard_or_save)靠這個
        回傳值判斷能不能繼續切換檔案。
        """
        if self._path is not None:
            self.save_to(self._path)
            return True
        return self._save_as()

    def _ask_save_path(self) -> Path | None:
        """拆成單獨方法方便測試monkeypatch掉QFileDialog(回傳None模擬使用者
        取消), 不必真的彈出檔案選取視窗。
        """
        path_str, _filter = QFileDialog.getSaveFileName(
            self, _SAVE_AS_DIALOG_TITLE, str(self._session.builds_dir), _JSON_FILTER
        )
        return Path(path_str) if path_str else None

    def _save_as(self) -> bool:
        path = self._ask_save_path()
        if path is None:
            return False
        self.save_to(path)
        self._reload_file_combo()
        self._sync_file_combo_selection()
        return True
