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
