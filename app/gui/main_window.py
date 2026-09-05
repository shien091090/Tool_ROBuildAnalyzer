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
from app.gui.cost_tab import CostTab
from app.gui.effects_tab import EffectsTab

_NO_CHARACTER_TEXT = "(無角色檔, 請在userdata/characters建立)"
_WINDOW_TITLE = "RO Build Analyzer"
_CHARACTER_LABEL_TEXT = "角色檔"
_DATA_LABEL_FORMAT = "資料: {} 匯入 ・ 目錄未分類 {} 件"
_UNKNOWN_IMPORT_DATE = "未知"
_TAB_EFFECTS_TEXT = "效果結算"
_TAB_COST_TEXT = "成本估算"
_NO_CHARACTER_ERROR_TEXT = "請先在userdata/characters建立角色檔"
_LOAD_ERROR_TITLE = "載入配裝失敗"
_LOAD_ERROR_FORMAT = "無法載入配裝檔 {path}: {error}"


class MainWindow(QMainWindow):
    def __init__(self, session):
        super().__init__()
        self._session = session
        self.setWindowTitle(_WINDOW_TITLE)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        top_row = QHBoxLayout()
        title_label = QLabel(_WINDOW_TITLE)
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        top_row.addWidget(title_label)
        top_row.addStretch(1)

        top_row.addWidget(QLabel(_CHARACTER_LABEL_TEXT))
        self.character_combo = QComboBox()
        self._fill_character_combo()
        top_row.addWidget(self.character_combo)

        top_row.addStretch(1)
        import_date = session.import_date()
        self.data_label = QLabel(
            _DATA_LABEL_FORMAT.format(import_date or _UNKNOWN_IMPORT_DATE, session.unclassified_count())
        )
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
        self.effects_tab = EffectsTab()
        self.tabs.addTab(self.effects_tab, _TAB_EFFECTS_TEXT)
        self.cost_tab = CostTab()
        self.tabs.addTab(self.cost_tab, _TAB_COST_TEXT)
        center_row.addWidget(self.tabs, 53)

        root.addLayout(center_row, 1)

        had_load_error = self._load_initial_builds()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self.recompute)
        self.panel_a.changed.connect(self._schedule_recompute)
        self.panel_b.changed.connect(self._schedule_recompute)
        self.character_combo.currentIndexChanged.connect(self._schedule_recompute)

        # I2修復: 啟動時不重算的話, 兩頁都是空白、panel.job_id也還是None(職業
        # 過濾checkbox要等第一次編輯後debounce計時器觸發recompute才會建出來)
        # — 一開始就跑一次同步recompute, 讓畫面在使用者做任何操作前就有內容。
        # 例外: 若初始載入某面板失敗(_load_initial_builds已把錯誤訊息顯示在
        # 效果頁), 這裡就不再自動recompute蓋掉那則訊息 — 讓使用者先看到是哪個
        # 檔案壞了, 之後任何編輯動作(_schedule_recompute)一樣會正常觸發重算。
        if not had_load_error:
            self.recompute()

    def _schedule_recompute(self, *_args) -> None:
        """重啟debounce計時器 — 獨立無參數slot, 避免currentIndexChanged的int
        參數被誤傳進QTimer.start(int msec)覆寫掉250ms間隔(曾經真的發生過:
        選到index 2, timer.interval()就被悄悄改成2)。panel.changed亦統一走
        這裡(即使它本身無參數), 保持兩種來源對稱、都不直接連QTimer.start。
        """
        self._timer.start()

    def _fill_character_combo(self) -> None:
        paths = self._session.list_characters()
        if not paths:
            self.character_combo.addItem(_NO_CHARACTER_TEXT)
            self.character_combo.setEnabled(False)
            return
        for p in paths:
            self.character_combo.addItem(p.name)

    def _load_initial_builds(self) -> bool:
        """回傳是否有任一面板初始載入失敗(呼叫端據此決定要不要接著自動
        recompute — 見__init__的說明)。"""
        had_error = False
        paths = self._session.list_builds()
        for i, panel in enumerate((self.panel_a, self.panel_b)):
            if i < len(paths):
                path = paths[i]
                try:
                    panel.set_build(self._session.load_build(path), path)
                except (ValueError, OSError) as e:
                    # I3修復: 壞配裝json(缺欄位/格式錯誤)不該讓整個app.gui進程
                    # 直接崩潰 — 該面板退回一個空白新配裝, 並把錯誤顯示在效果頁,
                    # 讓使用者知道哪個檔案有問題、但仍能繼續操作其他面板。
                    panel.set_build(new_build("未命名"), None)
                    self.effects_tab.show_error(
                        _LOAD_ERROR_FORMAT.format(path=path.name, error=f"{type(e).__name__}: {e}")
                    )
                    had_error = True
            else:
                panel.set_build(new_build("未命名"), None)
        return had_error

    def current_character(self) -> Character | None:
        if self.character_combo.count() == 0 or not self.character_combo.isEnabled():
            return None
        paths = self._session.list_characters()
        index = self.character_combo.currentIndex()
        if index < 0 or index >= len(paths):
            return None
        return self._session.load_character(paths[index])

    def recompute(self) -> None:
        character = self.current_character()
        for p in (self.panel_a, self.panel_b):
            p.job_id = character.job if character else None

        # 成本估算不需要角色檔(cost_targets/裝備本體資訊全在build本身), 不論
        # 上面character是否選到都要跑; 兩側各自獨立try/except(不吞: 讓
        # refine_table查無等ValueError顯示在該側卡片, 不擋另一側或效果頁)。
        results = []
        for panel in (self.panel_a, self.panel_b):
            try:
                results.append((self._session.cost(panel.build), None))
            except Exception as e:
                results.append((None, f"{type(e).__name__}: {e}"))
        self.cost_tab.set_results(
            self._session, self.panel_a.build.name, self.panel_a.build, *results[0],
            self.panel_b.build.name, self.panel_b.build, *results[1],
        )

        if character is None:
            self.effects_tab.show_error(_NO_CHARACTER_ERROR_TEXT)
            return
        try:
            eff_a = self._session.evaluate(self.panel_a.build, character)
            eff_b = self._session.evaluate(self.panel_b.build, character)
            rows = self._session.compare(eff_a, eff_b)
            self.effects_tab.set_results(
                self._session, self.panel_a.build.name, eff_a, self.panel_b.build.name, eff_b, rows
            )
        except Exception as e:  # 不吞: 顯示在頁面
            self.effects_tab.show_error(f"{type(e).__name__}: {e}")
