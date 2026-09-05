"""MainWindow — GUI殼: 頂部列(標題/角色檔選單/資料日期) + 雙配裝面板 + 頁籤區。

T5只搭骨架: 雙BuildPanel唯讀顯示20格、頁籤殼(效果結算/成本估算兩個空頁,
T7/T8填內容)、250ms debounce計時器(T5的recompute是pass, T6起接編輯後
真正觸發效果/成本重算)。
"""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.build import Character, new_build
from app.gui.build_panel import BuildPanel

_NO_CHARACTER_TEXT = "(無角色檔, 請在userdata/characters建立)"


class MainWindow(QMainWindow):
    def __init__(self, session):
        super().__init__()
        self._session = session
        self.setWindowTitle("RO Build Analyzer")

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        top_row = QHBoxLayout()
        title_label = QLabel("RO Build Analyzer")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        top_row.addWidget(title_label)
        top_row.addStretch(1)

        top_row.addWidget(QLabel("角色檔"))
        self.character_combo = QComboBox()
        self._fill_character_combo()
        top_row.addWidget(self.character_combo)

        top_row.addStretch(1)
        import_date = session.import_date()
        self.data_label = QLabel(f"資料: {import_date or '未知'} 匯入")
        top_row.addWidget(self.data_label)
        root.addLayout(top_row)

        center_row = QHBoxLayout()

        panels_widget = QWidget()
        panels_layout = QHBoxLayout(panels_widget)
        panels_layout.setContentsMargins(0, 0, 0, 0)
        panels_layout.setSpacing(6)
        self.panel_a = BuildPanel("A", session)
        self.panel_b = BuildPanel("B", session)
        self.panel_a.setMinimumWidth(330)
        self.panel_b.setMinimumWidth(330)
        panels_layout.addWidget(self.panel_a)
        panels_layout.addWidget(self.panel_b)
        center_row.addWidget(panels_widget, 47)

        self.tabs = QTabWidget()
        self.tabs.addTab(QWidget(), "效果結算")
        self.tabs.addTab(QWidget(), "成本估算")
        center_row.addWidget(self.tabs, 53)

        root.addLayout(center_row, 1)

        self._load_initial_builds()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.recompute)
        self.panel_a.changed.connect(self._timer.start)
        self.panel_b.changed.connect(self._timer.start)
        self.character_combo.currentIndexChanged.connect(self._timer.start)

    def _fill_character_combo(self) -> None:
        paths = self._session.list_characters()
        if not paths:
            self.character_combo.addItem(_NO_CHARACTER_TEXT)
            self.character_combo.setEnabled(False)
            return
        for p in paths:
            self.character_combo.addItem(p.name)

    def _load_initial_builds(self) -> None:
        paths = self._session.list_builds()
        for i, panel in enumerate((self.panel_a, self.panel_b)):
            if i < len(paths):
                panel.set_build(self._session.load_build(paths[i]), paths[i])
            else:
                panel.set_build(new_build("未命名"), None)

    def current_character(self) -> Character | None:
        if self.character_combo.count() == 0 or not self.character_combo.isEnabled():
            return None
        paths = self._session.list_characters()
        index = self.character_combo.currentIndex()
        if index < 0 or index >= len(paths):
            return None
        return self._session.load_character(paths[index])

    def recompute(self) -> None:
        pass
