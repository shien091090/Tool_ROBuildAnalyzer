import os
import sqlite3
from fractions import Fraction

import pytest

from app.core.cost.enchant import EnchantCostResult, parse_require_cost, solve_enchant
from app.core.db_reader import DbReader
from importer import db

REAL_DB_PATH = "data/ro_items.db"


def _row(table_index, target, slot_index, require_cost, option, weight, success_rate=100000):
    return {
        "table_index": table_index,
        "target_internal_names": target,
        "slot_index": slot_index,
        "require_cost": require_cost,
        "success_rate": success_rate,
        "option_internal_name": option,
        "option_weight": weight,
    }


def _make_db(tmp_path, rows):
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    db.create(conn)
    db.insert_enchants(conn, rows)
    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# parse_require_cost()
# ---------------------------------------------------------------------------


def test_parse_require_cost_single_material():
    assert parse_require_cost('100000, {"Ep18_Amethyst_Fragment", 15}') == (
        100000,
        [("Ep18_Amethyst_Fragment", 15)],
    )


def test_parse_require_cost_multi_material():
    assert parse_require_cost(
        '100000, {"Ep18_Amethyst_Fragment", 15}, {"Force_of_Fullmoon", 1}'
    ) == (100000, [("Ep18_Amethyst_Fragment", 15), ("Force_of_Fullmoon", 1)])


def test_parse_require_cost_zeny_only():
    assert parse_require_cost("150000") == (150000, [])


def test_parse_require_cost_zero_zeny_with_materials():
    assert parse_require_cost('0, {"Silvervine", 1}, {"MD_Geffen_Coin", 30}') == (
        0,
        [("Silvervine", 1), ("MD_Geffen_Coin", 30)],
    )


def test_parse_require_cost_none_and_empty_are_free():
    assert parse_require_cost(None) == (0, [])
    assert parse_require_cost("") == (0, [])
    assert parse_require_cost("   ") == (0, [])


def test_parse_require_cost_malformed_raises():
    with pytest.raises(ValueError):
        parse_require_cost("not_a_number")
    with pytest.raises(ValueError):
        parse_require_cost('100000, {"Missing_Qty"}')
    with pytest.raises(ValueError):
        parse_require_cost('100000, {"Trailing_Junk", 1} garbage')


# ---------------------------------------------------------------------------
# solve_enchant() — 分母資料驅動 + 兩策略前置差異(共用同一個3槽fixture)
# ---------------------------------------------------------------------------

_MULTI_SLOT_TABLE = 1
_MULTI_SLOT_ROWS = [
    _row(_MULTI_SLOT_TABLE, ["Test_Robe"], 3, '1000, {"Mat_A", 2}', "Slot3_OptA", 30),
    _row(_MULTI_SLOT_TABLE, ["Test_Robe"], 3, '1000, {"Mat_A", 2}', "Slot3_OptB", 70),
    _row(_MULTI_SLOT_TABLE, ["Test_Robe"], 2, '2000, {"Mat_B", 1}', "OptC", 40),
    _row(_MULTI_SLOT_TABLE, ["Test_Robe"], 2, '2000, {"Mat_B", 1}', "OptD", 60),
    _row(_MULTI_SLOT_TABLE, ["Test_Robe"], 1, '500, {"Mat_C", 3}', "OptE", 30),
    _row(_MULTI_SLOT_TABLE, ["Test_Robe"], 1, '500, {"Mat_C", 3}', "OptF", 90),
]


def _empty_manual():
    return {"reset_rules": {}, "manual_tables": [], "targeted": [], "upgrade_chains": []}


def test_denominator_uses_actual_weight_sum_not_500000(tmp_path):
    # slot1總權重=30+90=120(不是實測常見的500000), goal(OptE)權重=30
    # → p=30/120=1/4, N=4 — 驗證分母是「查到的實際總和」, 不是寫死的常數。
    db_path = _make_db(tmp_path, _MULTI_SLOT_ROWS)
    reader = DbReader(db_path)

    result = solve_enchant(
        reader, _empty_manual(), "Test_Robe", 1, "OptE", "last_slot_only"
    )

    assert result.expected_rounds == Fraction(4)
    reader.close()


def test_stop_when_hit_pre_slots_excludes_slots_after_goal(tmp_path):
    # goal=slot2(OptC), stop_when_hit的前置只該包含slot3(比goal大的槽),
    # 絕不能碰slot1(比goal小, 附中goal就停手, 根本不會附到它)。
    db_path = _make_db(tmp_path, _MULTI_SLOT_ROWS)
    reader = DbReader(db_path)

    result = solve_enchant(
        reader, _empty_manual(), "Test_Robe", 2, "OptC", "stop_when_hit"
    )

    # 無重置規則時reset成本記為0, 所以total_zeny恰等於N×(單輪費用),
    # 藉此反推單輪費用只包含slot3(1000), 不含slot1(500)。
    assert "無重置規則, 以免費重置計" in result.warnings
    # 單輪費用 = 前置(slot3=1000) + goal slot自己(slot2=2000) = 3000。
    round_zeny = result.zeny / result.expected_rounds
    assert round_zeny == Fraction(3000)
    round_mat_a = result.materials["Mat_A"] / result.expected_rounds
    assert round_mat_a == Fraction(2)  # 來自slot3(前置)
    round_mat_b = result.materials["Mat_B"] / result.expected_rounds
    assert round_mat_b == Fraction(1)  # 來自slot2(goal自己)
    assert "Mat_C" not in result.materials  # slot1(Mat_C)不該被stop_when_hit碰到
    reader.close()


def test_last_slot_only_pre_slots_includes_all_other_slots(tmp_path):
    # goal=slot1(OptE, 全表最小槽), last_slot_only的前置要包含slot3+slot2
    # 全部, 跟stop_when_hit在goal=2時只算slot3明顯不同 — 這就是brief要的
    # 「兩策略的前置費用差異」。
    db_path = _make_db(tmp_path, _MULTI_SLOT_ROWS)
    reader = DbReader(db_path)

    result = solve_enchant(
        reader, _empty_manual(), "Test_Robe", 1, "OptE", "last_slot_only"
    )

    round_zeny = result.zeny / result.expected_rounds
    assert round_zeny == Fraction(1000 + 2000 + 500)
    for name, qty, expected_per_round in [
        ("Mat_A", None, 2),
        ("Mat_B", None, 1),
        ("Mat_C", None, 3),
    ]:
        assert result.materials[name] / result.expected_rounds == Fraction(expected_per_round)
    reader.close()


def test_last_slot_only_goal_not_last_slot_raises(tmp_path):
    db_path = _make_db(tmp_path, _MULTI_SLOT_ROWS)
    reader = DbReader(db_path)

    with pytest.raises(ValueError):
        solve_enchant(reader, _empty_manual(), "Test_Robe", 2, "OptC", "last_slot_only")

    reader.close()


def test_goal_slot_index_absent_from_table_raises(tmp_path):
    # 該表實際slot只有{3,2,1}, goal_slot_index=99完全不存在 — 兩種strategy
    # 都該在同一道防呆(「目標slot不存在於此附魔表」)被擋下, 不該算出任何
    # 看似合理的數字。用stop_when_hit驗證(last_slot_only的goal-not-last
    # 防呆是另一條獨立路徑, 已在上面的測項覆蓋)。
    db_path = _make_db(tmp_path, _MULTI_SLOT_ROWS)
    reader = DbReader(db_path)

    with pytest.raises(ValueError, match="目標slot 99不存在於此附魔表"):
        solve_enchant(reader, _empty_manual(), "Test_Robe", 99, "OptE", "stop_when_hit")

    reader.close()


def test_unknown_strategy_raises(tmp_path):
    db_path = _make_db(tmp_path, _MULTI_SLOT_ROWS)
    reader = DbReader(db_path)

    with pytest.raises(ValueError):
        solve_enchant(reader, _empty_manual(), "Test_Robe", 1, "OptE", "bogus_strategy")

    reader.close()


# ---------------------------------------------------------------------------
# 重置期望(rate 0.8 → ×1.25) 與 (N-1)乘法
# ---------------------------------------------------------------------------


def test_reset_expectation_rate_and_n_minus_1_multiplication(tmp_path):
    rows = [
        _row(3, ["Reset_Item"], 5, "100", "GoalOpt", 1),
        _row(3, ["Reset_Item"], 5, "100", "OtherOpt", 3),
    ]
    db_path = _make_db(tmp_path, rows)
    reader = DbReader(db_path)
    manual = _empty_manual()
    manual["reset_rules"]["3"] = {"rate": "0.8", "zeny": 1000, "materials": []}

    result = solve_enchant(reader, manual, "Reset_Item", 5, "GoalOpt", "last_slot_only")

    # p=1/4 → N=4, N-1=3; reset_zeny每次=1000×(1/0.8)=1000×1.25=1250。
    assert result.expected_rounds == Fraction(4)
    expected_total = Fraction(4) * 100 + Fraction(3) * 1250
    assert result.zeny == Fraction(expected_total)
    assert "無重置規則, 以免費重置計" not in result.warnings
    reader.close()


def test_reset_rule_lookup_falls_back_to_item_internal_name(tmp_path):
    rows = [
        _row(7, ["Named_Reset_Item"], 1, "0", "GoalOpt", 1),
        _row(7, ["Named_Reset_Item"], 1, "0", "OtherOpt", 1),
    ]
    db_path = _make_db(tmp_path, rows)
    reader = DbReader(db_path)
    manual = _empty_manual()
    # 沒有table_index="7"這個key, 只用item internal_name建, 驗證fallback查詢。
    manual["reset_rules"]["Named_Reset_Item"] = {"rate": "0.5", "zeny": 10, "materials": []}

    result = solve_enchant(reader, manual, "Named_Reset_Item", 1, "GoalOpt", "last_slot_only")

    assert "無重置規則, 以免費重置計" not in result.warnings
    # N=2, N-1=1, reset_zeny=10×(1/0.5)=20
    assert result.zeny == Fraction(0) * 2 + Fraction(1) * 20
    reader.close()


# ---------------------------------------------------------------------------
# manual_tables fallback(自動表查無時查手動表)
# ---------------------------------------------------------------------------


def test_manual_tables_fallback_used_when_no_auto_table(tmp_path):
    db_path = _make_db(tmp_path, [])  # 空的enchant_tables, 完全沒有自動表
    reader = DbReader(db_path)
    manual = _empty_manual()
    manual["manual_tables"] = [
        _row(99, ["Old_NPC_Item"], 1, "300", "LegacyOpt", 1),
        _row(99, ["Old_NPC_Item"], 1, "300", "OtherOpt", 3),
    ]

    result = solve_enchant(
        reader, manual, "Old_NPC_Item", 1, "LegacyOpt", "last_slot_only"
    )

    assert result.available is True
    assert result.expected_rounds == Fraction(4)  # total=4, goal=1
    assert result.zeny == Fraction(4) * 300
    reader.close()


# ---------------------------------------------------------------------------
# 未建檔item → null result(available=False)
# ---------------------------------------------------------------------------


def test_unavailable_item_returns_null_result_with_warning(tmp_path):
    db_path = _make_db(tmp_path, [])
    reader = DbReader(db_path)

    result = solve_enchant(
        reader, _empty_manual(), "Ghost_Item", 1, "AnyOpt", "last_slot_only"
    )

    assert result == EnchantCostResult(
        expected_rounds=Fraction(0),
        zeny=Fraction(0),
        materials={},
        warnings=["舊式附魔未建檔, 不計入"],
        available=False,
    )
    reader.close()


# ---------------------------------------------------------------------------
# 指定附魔比價(targeted): 便宜採用 / 較貴不採用
# ---------------------------------------------------------------------------


def _targeted_fixture(tmp_path):
    rows = [
        _row(4, ["Targeted_Item"], 1, '0, {"Mat_X", 2}', "GoalOpt", 1),
        _row(4, ["Targeted_Item"], 1, '0, {"Mat_X", 2}', "OtherOpt", 9),
    ]
    db_path = _make_db(tmp_path, rows)
    return DbReader(db_path)


def test_targeted_adoption_when_cheaper(tmp_path):
    reader = _targeted_fixture(tmp_path)
    manual = _empty_manual()
    manual["targeted"] = [
        {"item": "Targeted_Item", "slot_index": 1, "option": "GoalOpt", "zeny": 1500, "materials": []}
    ]
    prices = {"Mat_X": 100}

    # 隨機路線: N=10, 材料Mat_X期望=10×2=20顆, 折算=20×100=2000 > 1500 → 採用指定附魔。
    result = solve_enchant(
        reader, manual, "Targeted_Item", 1, "GoalOpt", "last_slot_only", prices=prices
    )

    assert result.zeny == Fraction(1500)
    assert result.materials == {}
    assert result.expected_rounds == Fraction(1)
    assert "採指定附魔(較便宜)" in result.warnings
    reader.close()


def test_targeted_rejected_when_dearer(tmp_path):
    reader = _targeted_fixture(tmp_path)
    manual = _empty_manual()
    manual["targeted"] = [
        {"item": "Targeted_Item", "slot_index": 1, "option": "GoalOpt", "zeny": 2500, "materials": []}
    ]
    prices = {"Mat_X": 100}

    # 隨機路線折算2000 < 指定附魔2500 → 不採用, 保留隨機路線的原生單位結果。
    result = solve_enchant(
        reader, manual, "Targeted_Item", 1, "GoalOpt", "last_slot_only", prices=prices
    )

    assert result.zeny == Fraction(0)
    assert result.materials == {"Mat_X": Fraction(20)}
    assert result.expected_rounds == Fraction(10)
    assert "採指定附魔(較便宜)" not in result.warnings
    reader.close()


def test_targeted_comparison_missing_price_counts_as_zero_with_warning(tmp_path):
    reader = _targeted_fixture(tmp_path)
    manual = _empty_manual()
    manual["targeted"] = [
        {"item": "Targeted_Item", "slot_index": 1, "option": "GoalOpt", "zeny": 1, "materials": []}
    ]

    # 沒給prices(Mat_X無價格) → 隨機路線折算價=0(材料以0計), 跟指定附魔的1
    # 相比"1 < 0"不成立 → 不採用, 但要記材料無價格警告。
    result = solve_enchant(
        reader, manual, "Targeted_Item", 1, "GoalOpt", "last_slot_only"
    )

    assert "採指定附魔(較便宜)" not in result.warnings
    assert any("Mat_X無價格" in w for w in result.warnings)
    reader.close()


# ---------------------------------------------------------------------------
# 升級鏈: 只讀取+警告, 不比價
# ---------------------------------------------------------------------------


def test_upgrade_chain_touching_goal_option_emits_warning_only(tmp_path):
    reader = _targeted_fixture(tmp_path)
    manual = _empty_manual()
    manual["upgrade_chains"] = [
        {"item": "Targeted_Item", "slot_index": 1, "options": ["GoalOpt", "NextTierOpt"]}
    ]

    result = solve_enchant(
        reader, manual, "Targeted_Item", 1, "GoalOpt", "last_slot_only"
    )

    assert "升級鏈暫不比價" in result.warnings
    # 只警告, 不影響原本算出來的期望成本數字。
    assert result.expected_rounds == Fraction(10)
    reader.close()


# ---------------------------------------------------------------------------
# 真實DB案例: 月全蝕魔力外袍-LT(table 10004) slot 1 威力星團Lv3
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not os.path.exists(REAL_DB_PATH), reason="data/ro_items.db不存在")
def test_real_db_lunar_armor_star_cluster_pow3():
    reader = DbReader(REAL_DB_PATH)
    manual = _empty_manual()

    table_index = reader.enchant_table_for_item("Lunar_E_Armor_LT")
    assert table_index == 10004

    result = solve_enchant(
        reader, manual, "Lunar_E_Armor_LT", 1, "Star_Cluster_Of_Pow3", "last_slot_only"
    )

    # 實測: table 10004 slot1(威力星團Lv3="Star_Cluster_Of_Pow3")權重總和=2000,
    # 該slot實際總權重=500000 → p=2000/500000=1/250, N=250。
    assert result.expected_rounds == Fraction(500000, 2000)
    assert result.expected_rounds == Fraction(250)
    assert result.zeny == Fraction(0)  # 三個slot的require_cost開頭zeny皆為0
    # slot1(goal)材料照weight比例期望數量=N×單輪qty
    assert result.materials["Pow_Meteorite_Fragment"] == Fraction(250 * 5)
    assert result.materials["Naght_Sieger_Soul"] == Fraction(250 * 1)
    # slot3材料(Silvervine)也在last_slot_only的前置範圍內, 一併計入
    assert result.materials["Silvervine"] == Fraction(250 * 1)
    assert result.materials["MD_Geffen_Coin"] == Fraction(250 * 30)
    assert "無重置規則, 以免費重置計" in result.warnings
    reader.close()
