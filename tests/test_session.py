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
    assert session.option_display("Opt_B") == "詞條B"
    assert session.option_display("Nope") == "Nope"
    assert session.describe_missing(["skill:5015"]) == ["技能「測試技能」等級"]
    assert ("armor_lv1", "一級防具") in session.refine_table_choices()


def test_cost_runs_on_build_without_targets(session):
    report = session.cost(session.load_build(session.builds_dir / "a.json"))
    assert report.items == []
