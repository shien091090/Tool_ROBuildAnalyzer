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
    assert "測試鎧甲" in w.name_label.text()
    assert "+7" in w.refine_label.text()
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
    assert [r.name for r in rows] == ["測試武器"]
    assert PickerDialog.equipment_rows(session, "weapon", 4255) == []
    pool = session.enchant_pools(2001)[0]
    erows = PickerDialog.enchant_rows(session, pool)
    assert erows[0].name == "詞條A" and erows[0].rate_text == "75.00%"
    dlg = PickerDialog(None, session, "t", "n", rows)
    assert dlg.tree.topLevelItemCount() == 1
    dlg.search.setText("不存在")
    assert dlg.tree.topLevelItemCount() == 0


def test_panel_edit_flow_marks_dirty_and_saves(qapp, session):
    from app.gui.build_panel import BuildPanel
    panel = BuildPanel("A", session)
    path = session.builds_dir / "a.json"
    panel.set_build(session.load_build(path), path)
    fired = []
    panel.changed.connect(lambda: fired.append(1))
    panel.apply_item("weapon", 1001)
    panel.apply_refine("weapon", 12)
    panel.apply_enchant("armor", 1, "Opt_B")
    panel.apply_stone("costume_top", 8) if session.catalog.get(8) else None
    assert panel.dirty and len(fired) >= 3
    assert panel.build.slots["weapon"].item_id == 1001 and panel.build.slots["weapon"].refine == 12
    assert panel.build.slots["armor"].enchants == ["Opt_A", "Opt_B"]
    panel.save_to(path)
    assert not panel.dirty
    assert session.load_build(path).slots["weapon"].refine == 12
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
