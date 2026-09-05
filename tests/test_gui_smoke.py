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
