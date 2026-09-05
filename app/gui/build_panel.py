"""BuildPanel — 單一配裝面板(A/B兩個並排): 標頭列(檔案選單/存檔按鈕) + 三段20格。

T5只做唯讀顯示骨架(set_build/refresh重畫20格), 檔案combo/存檔按鈕/新增按鈕
的點擊事件留給T6接線(這裡只建好widget)。`changed`訊號同樣是T6接line後才會
真的emit(例如編輯完某格觸發), T5不會emit它。
"""
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from app.core.build import Build, new_build
from app.gui.slot_widget import SLOT_SECTIONS, SlotWidget

_TAG_COLORS = {"A": "#7ec3e8", "B": "#cf9ee8"}
_UNSAVED_ENTRY = "(未儲存新配裝)"
_SAVE_TEXT = "儲存"
_SAVE_AS_TEXT = "另存"
_NEW_TEXT = "新增"


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
                section_body.addWidget(widget)
            outer.addLayout(section_body)

        outer.addStretch(0)

    def _reload_file_combo(self) -> None:
        self.file_combo.clear()
        for p in self._session.list_builds():
            self.file_combo.addItem(p.name)
        self.file_combo.addItem(_UNSAVED_ENTRY)

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

    def refresh(self) -> None:
        for slot_key, widget in self.slot_widgets.items():
            widget.set_config(self._build.slots.get(slot_key), self._session)
        suffix = "*" if self._dirty else ""
        self._tag_label.setText(f"{self._tag}{suffix}")
