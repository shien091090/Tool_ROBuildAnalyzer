import os

import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication  # noqa: E402

from tests.fixtures_session import make_session  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def session(tmp_path):
    s = make_session(tmp_path)
    yield s
    s.close()


def test_main_window_builds_with_two_panels_of_20_slots(qapp, session):
    from app.gui.main_window import MainWindow
    from app.gui.slot_widget import SLOT_LABELS
    win = MainWindow(session)
    assert len(SLOT_LABELS) == 20
    assert len(win.panel_a.slot_widgets) == 20 and len(win.panel_b.slot_widgets) == 20
    assert win.character_combo.count() == 1
    assert "2026-09-04" in win.data_label.text()


def test_panel_set_build_renders_names(qapp, session):
    from app.gui.build_panel import BuildPanel
    panel = BuildPanel("A", session)
    path = session.builds_dir / "a.json"
    panel.set_build(session.load_build(path), path)
    w = panel.slot_widgets["armor"]
    assert w.name_label.text() == "測試鎧甲[1]"   # 一般格裝備名帶洞數後綴
    assert "鎧甲" in w.name_label.toolTip()        # 懸停裝備名顯示敘述tooltip(同選擇清單)
    assert "+7" in w.refine_label.text()
    assert panel.slot_widgets["weapon"].name_label.toolTip() == ""   # 未裝備無tooltip
    chip_texts = [c.text() for c in w.chip_buttons()]
    assert "測試卡片" in chip_texts and "詞條A" in chip_texts
    assert "+ 附魔" in chip_texts        # 表有2槽, 只填1個
    assert "+ 卡片" not in chip_texts    # 1洞已插滿
    assert "未裝備" in panel.slot_widgets["weapon"].name_label.text()


def test_recompute_timer_interval_survives_character_combo_change(qapp, session):
    from app.gui.main_window import MainWindow
    win = MainWindow(session)
    # 直接emit currentIndexChanged(int)模擬使用者切換角色檔選單 — 曾經這個int
    # 會被誤傳進QTimer.start(int msec), 把250ms間隔悄悄改成傳入的index值。
    win.character_combo.currentIndexChanged.emit(2)
    win.panel_a.changed.emit()
    assert win._timer.interval() == 250
    assert win._timer.isActive()


def test_slot_widget_dim_property_updates_on_unequip(qapp, session):
    from app.gui.build_panel import BuildPanel
    from app.gui.slot_widget import _UNEQUIPPED_TEXT
    panel = BuildPanel("A", session)
    path = session.builds_dir / "a.json"
    panel.set_build(session.load_build(path), path)
    w = panel.slot_widgets["armor"]
    assert w.name_label.property("dim") is False
    w.set_config(None, session)
    assert w.name_label.property("dim") is True
    assert w.name_label.text() == _UNEQUIPPED_TEXT


def test_picker_rows_and_search(qapp, session):
    from app.gui.picker_dialog import PickerDialog
    rows = PickerDialog.equipment_rows(session, "weapon", 4252)
    assert [r.name for r in rows] == ["測試武器[2]"]   # 一般格清單名帶洞數後綴
    assert PickerDialog.equipment_rows(session, "weapon", 4255) == []
    pool = session.enchant_pools(2001)[0]
    erows = PickerDialog.enchant_rows(session, pool)
    assert erows[0].name == "詞條A" and erows[0].rate_text == "75.00%"
    dlg = PickerDialog(None, session, "t", "n", rows)
    assert dlg.tree.topLevelItemCount() == 1
    # 名稱欄要吃滿剩餘寬度、機率欄依內容縮放, 對話框要有可讀的初始尺寸(避免名稱被截成「RO十週…」)
    from PySide6.QtWidgets import QHeaderView
    header = dlg.tree.header()
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Stretch
    assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.ResizeToContents
    assert dlg.width() >= 480 and dlg.height() >= 560
    dlg.search.setText("不存在")
    assert dlg.tree.topLevelItemCount() == 0


def test_panel_edit_flow_marks_dirty_and_saves(qapp, session):
    from app.core.build import CostTargets
    from app.gui.build_panel import BuildPanel
    panel = BuildPanel("A", session)
    path = session.builds_dir / "a.json"
    panel.set_build(session.load_build(path), path)
    fired = []
    panel.changed.connect(lambda: fired.append(1))
    panel.apply_item("weapon", 1001)
    panel.apply_refine("weapon", 12)
    panel.apply_enchant("armor", 1, "Opt_B")
    panel.apply_item("costume_top", 29001)
    assert panel.dirty and len(fired) >= 3
    assert panel.build.slots["weapon"].item_id == 1001 and panel.build.slots["weapon"].refine == 12
    assert panel.build.slots["armor"].enchants == ["Opt_A", "Opt_B"]
    panel.save_to(path)
    assert not panel.dirty
    assert session.load_build(path).slots["weapon"].refine == 12

    # I4回歸: 換裝(apply_item)前先掛好cost_targets, 換裝後該欄位必須被清成
    # None — 舊cost_targets(refine_table/enchant_goal)是描述"舊道具"的養成
    # 路徑, 對新道具完全對不上(spec §6)。
    panel.apply_cost_targets("armor", CostTargets(refine_from=0, grade_from="none"))
    assert panel.build.slots["armor"].cost_targets is not None
    panel.apply_item("armor", 2001)
    assert panel.build.slots["armor"].cost_targets is None

    panel.apply_item("weapon", None)
    assert "weapon" not in panel.build.slots


def test_save_as_reload_combo_does_not_swap_visible_build(qapp, session):
    """fix round1 Critical1回歸: _reload_file_combo()以前沒擋訊號, clear()+第
    一個addItem()各自觸發currentIndexChanged(0), 會被_on_file_combo_changed
    誤當成「使用者選了字母序第一個檔案」載入, 蓋掉剛存好的build(dirty已被
    save_to清掉, guard擋不住)。"""
    from app.gui.build_panel import BuildPanel
    panel = BuildPanel("A", session)
    path = session.builds_dir / "a.json"
    panel.set_build(session.load_build(path), path)
    panel.apply_item("weapon", 1001)
    new_path = session.builds_dir / "z_new.json"
    panel.save_to(new_path)
    panel._reload_file_combo()
    panel._sync_file_combo_selection()
    assert panel.path.name == "z_new.json"
    assert "weapon" in panel.build.slots
    assert panel.file_combo.currentText() == "z_new.json"


def test_confirm_discard_or_save_aborts_when_save_as_cancelled(qapp, session, monkeypatch):
    """fix round1 Critical2回歸: 選「儲存」但path未定, 另存的QFileDialog又被
    使用者取消時, _save_current()/_save_as()必須回傳False, _confirm_discard_
    or_save()才能正確中止切換而不是誤放行去load_from覆蓋掉未存的build。"""
    from app.gui.build_panel import BuildPanel
    panel = BuildPanel("A", session)
    panel.start_new("我的新配裝")
    panel.apply_item("armor", 2001)
    monkeypatch.setattr(panel, "_ask_save_path", lambda: None)
    monkeypatch.setattr(panel, "_ask_discard_or_save", lambda: "save")
    assert panel._confirm_discard_or_save() is False
    assert panel.dirty
    assert panel.build.name == "我的新配裝"


def test_refine_label_always_shown_when_equipped_except_costume(qapp, session):
    """fix round1 Important3回歸(裁決覆蓋brief規則2"refine>0才顯示"): 已裝備的
    GENERAL/SHADOW格恆顯示精煉值(含+0), 服飾格依然永不顯示。"""
    from app.core.build import SlotConfig
    from app.gui.build_panel import BuildPanel
    panel = BuildPanel("A", session)
    panel.apply_item("weapon", 1001)
    w = panel.slot_widgets["weapon"]
    assert w.refine_label.isVisibleTo(w) is True
    assert w.refine_label.text() == "+0"

    costume_widget = panel.slot_widgets["costume_top"]
    costume_widget.set_config(SlotConfig(item_id=2001), session)
    assert costume_widget.refine_label.isVisibleTo(costume_widget) is False


def test_costume_slot_holds_stone_directly(qapp, session, monkeypatch):
    """服飾本體無任何效果不顯示: 服飾格item_id直接存強化石(同CLI配裝檔),
    格內顯示石頭名、沒有任何chip, 點格子開的是強化石清單不是服飾清單。"""
    from app.gui import picker_dialog
    from app.gui.build_panel import BuildPanel
    panel = BuildPanel("A", session)
    panel.apply_item("costume_top", 29001)
    w = panel.slot_widgets["costume_top"]
    assert w.name_label.text() == "測試石(頭上)"   # 服飾格不帶洞數後綴
    assert w.chip_buttons() == []
    assert panel.build.slots["costume_top"].cards == []

    calls = []
    monkeypatch.setattr(picker_dialog.PickerDialog, "pick_stone", staticmethod(lambda *a: calls.append(("stone", a[2])) or 29001))
    monkeypatch.setattr(picker_dialog.PickerDialog, "pick_equipment", staticmethod(lambda *a: calls.append(("equip", a[2])) or None))
    panel._on_item_clicked("costume_garment")
    panel._on_item_clicked("head_top")
    assert calls == [("stone", "costume_garment"), ("equip", "head_top")]
    assert panel.build.slots["costume_garment"].item_id == 29001


def test_effects_tab_renders_rows_and_uncounted(qapp, session):
    from app.gui.effects_tab import fmt_value
    from app.gui.main_window import MainWindow
    assert fmt_value(12.0, "%") == "+12%" and fmt_value(-0.5, "秒") == "-0.5秒" and fmt_value(None, "") == "—"
    win = MainWindow(session)
    win.recompute()
    tab = win.effects_tab
    texts = [tab.table.item(r, 0).text() for r in range(tab.table.rowCount()) if tab.table.item(r, 0)]
    assert "ATK" in texts and "傷害" in texts
    assert "請以道具敘述為準" in tab.note_label.text()
    assert win.panel_a.job_id == 4252


def test_fmt_value_normalizes_negative_zero():
    """fix round1 Important1回歸: parser.py會產生負值運算, -0.0若不正規化,
    ":g"格式化會印成"-0", 疊上恆顯示的"+"號變成錯誤的"+-0%"。"""
    from app.gui.effects_tab import fmt_value
    assert fmt_value(-0.0, "%") == "+0%"
    assert fmt_value(0.0, "") == "+0"
    assert fmt_value(0.5, "秒") == "+0.5秒"


def test_effects_tab_show_error_clears_prior_results(qapp, session):
    """fix round1 Important2回歸: show_error()以前只顯示error_label, 沒清掉
    上一次recompute留下的table/未計入/其他/warnings — 使用者可能把錯誤banner
    下面的舊數字誤讀成目前結果。"""
    from app.gui.main_window import MainWindow
    win = MainWindow(session)
    win.recompute()
    tab = win.effects_tab
    assert tab.table.rowCount() > 0
    assert tab.error_label.isVisibleTo(tab) is False

    tab.show_error("boom")
    assert tab.table.rowCount() == 0
    assert tab.error_label.isVisibleTo(tab) is True
    assert "boom" in tab.error_label.text()
    assert tab._uncounted_layout.count() == 0
    assert tab._others_layout.count() == 0
    assert tab.warnings_label.isVisibleTo(tab) is False

    win.recompute()
    assert tab.table.rowCount() > 0
    assert tab.error_label.isVisibleTo(tab) is False


def test_cost_tab_renders_report(qapp, session):
    from fractions import Fraction
    from app.core.build import CostTargets, SlotConfig
    from app.core.cost.report import BuildCostReport, ItemCostReport
    from app.gui.cost_tab import CostTab, fmt_zeny, path_text
    assert fmt_zeny(Fraction(1234567)) == "1,234,567"
    cfg = SlotConfig(item_id=2001, refine=13, grade="A",
                     cost_targets=CostTargets(refine_from=0, grade_from="none", refine_table="ether_armor2"))
    assert path_text(cfg) == "無階+0 → A階+13"
    item = ItemCostReport(slot_key="armor", item_name="測試鎧甲", direct={"乙太鋁": Fraction(3)}, grade_fee=Fraction(0),
                          enchant_zeny=Fraction(0), refine_fee=Fraction(100), intermediates={}, base={"乙太星塵": Fraction(9)},
                          exchange_fee=Fraction(0), body_count=Fraction(1), zeny_total=Fraction(100),
                          warnings=["附魔查無附魔表, 附魔成本略過"])
    report = BuildCostReport(items=[item], zeny_total=Fraction(100), warnings=[])
    b = session.load_build(session.builds_dir / "a.json")
    b.slots["armor"] = cfg
    tab = CostTab()
    tab.set_results(session, "A", b, report, None, "B", b, None, "ValueError: 壞表名")
    assert "100" in tab.total_a.text() and "壞表名" in tab.total_b.text()
    assert tab.tree.topLevelItemCount() == 2


def test_main_window_recomputes_on_startup(qapp, session):
    """I2回歸: 建構MainWindow後(不手動呼叫recompute), 效果頁應該已經有內容,
    panel.job_id也已經被填上(否則PickerDialog的職業過濾checkbox建不出來)。"""
    from app.gui.main_window import MainWindow
    win = MainWindow(session)
    assert win.effects_tab.table.rowCount() > 0
    assert win.panel_a.job_id == 4252


def test_effects_tab_uncounted_escapes_raw_lua_condition(qapp):
    """C1回歸: condition是parser保留的原始Lua if運算式, 常見`<`/`>` — 以前
    直接嵌進RichText會被Qt當成(不完整的)標籤, 截斷`<`和下一個`>`之間的內容。
    現在html.escape()後, 用QTextDocument轉回純文字仍應完整看到`<`兩側文字。
    """
    from PySide6.QtGui import QTextDocument

    from app.core.aggregate import BuildEffects, SourcedEffect
    from app.core.entries import CAT_OTHER, EffectEntry, KIND_UNRESOLVED
    from app.gui.effects_tab import EffectsTab

    entry = EffectEntry(
        key="未判定條件", value=None, unit="", kind=KIND_UNRESOLVED, category=CAT_OTHER,
        extra={
            "condition": "if 49 < temp and get(19) ~= 4054 then",
            "missing": [],
            "raw_lines": ["AddExtParam(0, 41, 5)"],
        },
    )
    se = SourcedEffect(source="X", slot_key="weapon", entry=entry)
    eff_a = BuildEffects(sourced=[se], totals={}, unresolved=[se], others=[], warnings=[],
                          missing_keys=set(), categories={})
    eff_b = BuildEffects(sourced=[], totals={}, unresolved=[], others=[], warnings=[],
                          missing_keys=set(), categories={})

    class _FakeSession:
        @staticmethod
        def describe_missing(missing):
            return []

    tab = EffectsTab()
    tab.set_results(_FakeSession(), "A", eff_a, "B", eff_b, [])

    label = tab._uncounted_layout.itemAt(0).widget()
    doc = QTextDocument()
    doc.setHtml(label.text())
    text = doc.toPlainText()
    assert "49 < temp" in text
    assert "4054" in text

    tooltip_doc = QTextDocument()
    tooltip_doc.setHtml(label.toolTip())
    assert "AddExtParam(0, 41, 5)" in tooltip_doc.toPlainText()


def test_effects_tab_unknown_category_still_rendered(qapp):
    """M9回歸: category不在CATEGORY_ORDER窮舉表裡的列以前會被by_cat.get()
    無視、整列消失 — 現在改成照樣附加在已知分類後面顯示, 標題用原始字串。"""
    from app.core.compare import CompareRow
    from app.gui.effects_tab import EffectsTab
    from tests.fixtures_session import make_session

    row = CompareRow(key="X", unit="", category="weird", a=1.0, b=None, advantage="a")
    tab = EffectsTab()
    tab._fill_table([row])
    texts = [tab.table.item(r, 0).text() for r in range(tab.table.rowCount()) if tab.table.item(r, 0)]
    assert "X" in texts
    assert "weird" in texts


def test_cost_tab_fill_card_handles_no_report_no_error(qapp, session):
    """M10回歸: report/err皆為None時_fill_card以前會直接dereference report
    炸AttributeError — 現在應該顯示空狀態而不拋例外。"""
    from app.gui.cost_tab import CostTab
    b = session.load_build(session.builds_dir / "a.json")
    tab = CostTab()
    tab.set_results(session, "A", b, None, None, "B", b, None, None)
    assert tab.total_a.text() != ""


def test_build_panel_combo_load_error_shows_message_and_keeps_build(qapp, session, monkeypatch):
    """I3回歸(a): 切檔combo選到壞json時, 不應該讓ValueError/JSONDecodeError
    直接往上炸掉整個process — 應該顯示提示、combo復原、目前build不變。"""
    from app.gui.build_panel import BuildPanel

    bad_path = session.builds_dir / "bad.json"
    bad_path.write_text('{"name": "bad", "slots": {"nope": {"item_id": 1}}}', encoding="utf-8")

    panel = BuildPanel("A", session)
    a_path = session.builds_dir / "a.json"
    panel.set_build(session.load_build(a_path), a_path)

    recorded = []
    monkeypatch.setattr(panel, "_show_load_error", lambda text: recorded.append(text))

    panel._reload_file_combo()
    panel._sync_file_combo_selection()
    idx = panel.file_combo.findText("bad.json")
    assert idx >= 0
    panel.file_combo.setCurrentIndex(idx)

    assert recorded and "bad.json" in recorded[0]
    assert panel.path.name == "a.json"
    assert "armor" in panel.build.slots


def test_main_window_bad_initial_build_falls_back_and_shows_error(qapp, session):
    """I3回歸(b): 啟動時第一個(字母序)配裝檔壞掉, MainWindow仍要能正常建構
    完成(不拋例外), 該面板退回空白新配裝, 效果頁顯示載入失敗訊息。"""
    from app.gui.main_window import MainWindow

    bad_path = session.builds_dir / "0bad.json"
    bad_path.write_text('{"name": "bad", "slots": {"nope": {"item_id": 1}}}', encoding="utf-8")

    win = MainWindow(session)
    assert win.panel_a.build.name == "未命名"
    assert "0bad.json" in win.effects_tab.error_label.text()


def test_clicking_name_or_blank_area_never_opens_refine(qapp, session):
    """2026-09-08驗收裁決: 選擇裝備清單關閉後不得連跳精煉視窗。點裝備名只發
    item_clicked且事件不穿透到SlotWidget; 點格內空白處什麼都不發, 精煉只剩
    點精煉數字或右鍵選單兩個入口。"""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    from app.core.build import SlotConfig
    from app.gui.slot_widget import SlotWidget
    w = SlotWidget("armor")
    w.set_config(SlotConfig(item_id=2001, refine=7), session)
    w.show()
    fired = []
    w.item_clicked.connect(lambda: fired.append("item"))
    w.refine_clicked.connect(lambda: fired.append("refine"))
    QTest.mouseClick(w.name_label, Qt.MouseButton.LeftButton)
    assert fired == ["item"]
    QTest.mouseClick(w, Qt.MouseButton.LeftButton, pos=QPoint(w.width() - 2, w.height() // 2))
    assert fired == ["item"]
    QTest.mouseClick(w.refine_label, Qt.MouseButton.LeftButton)
    assert fired == ["item", "refine"]


def test_chips_wrap_to_second_row_when_first_row_too_narrow(qapp, session):
    """2026-09-08驗收裁決: chips在第一列塞不下時不截字, 整組搬到第二列; 拉寬
    後塞得下就收回第一列, 格高跟著變。"""
    from app.core.build import SlotConfig
    from app.gui.slot_widget import SlotWidget, _CHIP_ROW_HEIGHT, _SLOT_HEIGHT
    w = SlotWidget("armor")
    w.show()
    w.resize(330, w.sizeHint().height())
    w.set_config(SlotConfig(item_id=2001, refine=7, cards=[3001], enchants=["Opt_A"]), session)
    qapp.processEvents()
    assert w.chips_on_second_row is True
    assert w.sizeHint().height() == _SLOT_HEIGHT + _CHIP_ROW_HEIGHT
    assert all(c.width() >= c.sizeHint().width() for c in w.chip_buttons())

    w.resize(1200, w.sizeHint().height())
    qapp.processEvents()
    assert w.chips_on_second_row is False
    assert w.sizeHint().height() == _SLOT_HEIGHT

    w.set_config(None, session)
    assert w.chips_on_second_row is False


def test_combo_hover_splits_body_and_card_and_tooltip_lists_combo(qapp, session):
    """2026-09-29驗收裁決: 懸停裝備名只亮本體的套裝、懸停卡片chip只亮那張卡
    的套裝, 格子其他地方不亮; 成立套裝列在tooltip最上方並標出夥伴所在部位。
    這裡把測試卡片插在武器(武器本體無套裝), 套裝夥伴測試鎧甲在鎧甲格。"""
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication
    from app.core.build import SlotConfig
    from app.gui.build_panel import BuildPanel
    panel = BuildPanel("A", session)
    panel.apply_item("armor", 2001)
    panel.apply_item("weapon", 1001)
    panel.build.slots["weapon"] = SlotConfig(item_id=1001, cards=[3001])
    panel.refresh()
    armor, weapon = panel.slot_widgets["armor"], panel.slot_widgets["weapon"]
    lit = lambda: {k for k, w in panel.slot_widgets.items() if w.property("highlight")}

    QApplication.sendEvent(weapon.name_label, QEvent(QEvent.Type.Enter))
    assert lit() == set()
    QApplication.sendEvent(weapon.name_label, QEvent(QEvent.Type.Leave))

    card_chip = next(c for c in weapon.chip_buttons() if c.text() == "測試卡片")
    QApplication.sendEvent(card_chip, QEvent(QEvent.Type.Enter))
    assert lit() == {"armor", "weapon"}
    QApplication.sendEvent(card_chip, QEvent(QEvent.Type.Leave))
    assert lit() == set()

    QApplication.sendEvent(armor.name_label, QEvent(QEvent.Type.Enter))
    assert lit() == {"armor", "weapon"}
    QApplication.sendEvent(armor.name_label, QEvent(QEvent.Type.Leave))

    line = "測試鎧甲(鎧甲) + 測試卡片(武器)"
    assert "成立套裝" in armor.name_label.toolTip() and line in armor.name_label.toolTip()
    assert "鎧甲" in armor.name_label.toolTip().split("<hr>")[1]   # 敘述仍在套裝段之後
    assert line in card_chip.toolTip()
    assert "成立套裝" not in weapon.name_label.toolTip()

