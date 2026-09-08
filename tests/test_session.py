from fractions import Fraction

import pytest

from tests.fixtures_session import make_session


@pytest.fixture
def session(tmp_path):
    s = make_session(tmp_path)
    yield s
    s.close()


def test_lists_and_meta(session):
    assert [p.name for p in session.list_builds()] == ["a.json", "b.json"]
    assert [p.name for p in session.list_characters()] == ["rk.json"]
    assert session.import_date() == "2026-09-04"


def test_evaluate_and_compare(session):
    ch = session.load_character(session.list_characters()[0])
    a = session.evaluate(session.load_build(session.builds_dir / "a.json"), ch)
    b = session.evaluate(session.load_build(session.builds_dir / "b.json"), ch)
    assert a.totals[("ATK", "")] == 116   # 10本體+5卡+1詞條+100套裝
    rows = session.compare(a, b)
    assert rows[0].key == "ATK" and rows[0].advantage == "a"


def test_enchant_pools_probability(session):
    pools = session.enchant_pools(2001)
    assert [p.slot_index for p in pools] == [3, 2]
    assert [o.option_internal_name for o in pools[0].options] == ["Opt_A", "Opt_B"]
    assert pools[0].options[0].probability == Fraction(3, 4)
    assert pools[0].options[0].display_name == "詞條A"
    assert session.enchant_pools(1001) == []
    assert session.enchant_pools(999999) == []


def test_display_helpers(session):
    assert session.item_display(2001) == "測試鎧甲"
    assert session.item_display(42) == "item:42"
    # 可插卡裝備名尾端加[N], 無洞不加, 查無資料同item_display
    assert session.equipment_display(2001) == "測試鎧甲[1]"
    assert session.equipment_display(1001) == "測試武器[2]"
    assert session.equipment_display(29001) == "測試石(頭上)"
    assert session.equipment_display(42) == "item:42"
    assert session.option_display("Opt_B") == "詞條B"
    assert "鎧甲" in session.item_description(2001) and session.item_description(42) == ""
    assert session.option_display("Nope") == "Nope"
    assert session.describe_missing(["skill:5015"]) == ["技能「測試技能」等級"]
    assert ("armor_lv1", "一級防具") in session.refine_table_choices()


def test_cost_runs_on_build_without_targets(session):
    report = session.cost(session.load_build(session.builds_dir / "a.json"))
    assert report.items == []


def test_active_combo_members(session):
    a = session.load_build(session.builds_dir / "a.json")   # armor 2001 + card 3001 → combo 5001成立
    assert session.active_combo_members(a, 2001) == {2001, 3001}
    assert session.active_combo_members(a, 3001) == {2001, 3001}
    b = session.load_build(session.builds_dir / "b.json")
    assert session.active_combo_members(b, 1001) == set()


def test_slot_count_of(session):
    """I6: session.slot_count_of — 查無item_id時退回0, 不讓GUI直接碰
    session.catalog.get()。"""
    assert session.slot_count_of(2001) == 1
    assert session.slot_count_of(999) == 0


def test_price_of(session):
    """I6: session.price_of — 查無物價時回傳None(不是0), 讓GUI能區分「物價是
    0元」與「查無報價」兩種情況, 顯示"(無報價)"; 用真實userdata/prices.json
    驗證(fixtures_session的make_session沒有覆寫prices_path)。"""
    assert session.price_of("鐵匠的祝福") == 725000
    assert session.price_of("不存在的材料") is None


def test_equipment_for_slot(session):
    """I6: session.equipment_for_slot — 一律經session方法查目錄, 不直接碰
    session.catalog.equipment_for_slot()。"""
    rows = session.equipment_for_slot("weapon", 4252)
    assert [e.display_name for e in rows] == ["測試武器"]
    assert session.equipment_for_slot("weapon", 4255) == []


def test_unclassified_count_is_int(session):
    assert isinstance(session.unclassified_count(), int)
