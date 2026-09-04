import json
import sqlite3
from fractions import Fraction

import pytest

from app.core.build import Build, CostTargets, SlotConfig, load_build
from app.core.cost.enchant import solve_enchant
from app.core.cost.report import BuildCostReport, evaluate_build_cost, evaluate_item_cost
from app.core.cost.rules import CostRules, GradeStep, RefineStep, load_rules
from app.core.db_reader import DbReader
from importer import db

REAL_RULES_PATH = "userdata/refine_rules.json"

# 基準凍結價格, 勿隨prices.json更新(controller amendment 4) — 基準Zeny測試鎖定
# 使用者定案的錨點總計(651530187/106289325/350978060), 用當時的prices.json
# 逐字複製進來; 之後使用者手動調整userdata/prices.json不該讓這三個回歸測試變動。
FROZEN_PRICES = {
    "鐵匠的祝福": 725000,
    "鋁": 0,
    "神之金屬": 0,
    "濃縮鋁": 150000,
    "濃縮神之金屬": 137500,
    "高濃縮鋁": 172500,
    "高濃縮神之金屬": 172500,
    "鈣礦石": 0,
    "鈰鐳礦石": 0,
    "高密度鈣礦石": 172500,
    "高密度鈰鐳礦石": 172500,
    "特殊祝福的防具礦石": 6000000,
    "特殊祝福的武器礦石": 6000000,
    "天藍寶石": 4560,
    "黃寶石": 4560,
    "紫寶石": 4560,
    "琥珀": 3420,
    "乙太星塵": 0,
    "乙太魔石": 100000,
}


def _empty_manual():
    return {"reset_rules": {}, "manual_tables": [], "targeted": [], "upgrade_chains": []}


def _item_row(item_id, internal_name, display_name=None):
    return {
        "item_id": item_id, "internal_name": internal_name, "display_name": display_name,
        "description": "", "slot_count": None, "class_num": None, "equip_type": None,
        "stat_vector": None, "onstart_equip_src": None, "combi_ids": None,
    }


def _enchant_row(table_index, target, slot_index, require_cost, option, weight, success_rate=100000):
    return {
        "table_index": table_index, "target_internal_names": target, "slot_index": slot_index,
        "require_cost": require_cost, "success_rate": success_rate,
        "option_internal_name": option, "option_weight": weight,
    }


def _make_db(tmp_path, name, items=None, enchant_rows=None):
    db_path = str(tmp_path / name)
    conn = sqlite3.connect(db_path)
    db.create(conn)
    if items:
        db.insert_items(conn, items)
    if enchant_rows:
        db.insert_enchants(conn, enchant_rows)
    conn.commit()
    conn.close()
    return db_path


# 3槽附魔表(3,2,1)沿用test_cost_enchant.py的手算基準, 供derivation測項用。
_MULTI_SLOT_ROWS = [
    _enchant_row(10, ["EnchantArmor"], 3, '1000, {"Mat_A", 2}', "OptA", 30),
    _enchant_row(10, ["EnchantArmor"], 3, '1000, {"Mat_A", 2}', "OptB", 70),
    _enchant_row(10, ["EnchantArmor"], 2, '2000, {"Mat_B", 1}', "OptC", 40),
    _enchant_row(10, ["EnchantArmor"], 2, '2000, {"Mat_B", 1}', "OptD", 60),
    _enchant_row(10, ["EnchantArmor"], 1, '500, {"Mat_C", 3}', "OptE", 30),
    _enchant_row(10, ["EnchantArmor"], 1, '500, {"Mat_C", 3}', "OptF", 90),
]


# ---------------------------------------------------------------------------
# CostTargets(build.py) json round-trip
# ---------------------------------------------------------------------------


def test_cost_targets_roundtrip_with_all_new_fields(tmp_path):
    data = {
        "name": "測試配裝",
        "slots": {
            "armor": {
                "item_id": 1,
                "refine": 13, "grade": "A",
                "cost_targets": {
                    "refine_from": 0, "grade_from": "none",
                    "refine_table": "armor_lv1",
                    "enchant_strategy": "stop_when_hit",
                    "enchant_goal": [1, "Star_Cluster_Of_Pow3"],
                },
            }
        },
    }
    path = tmp_path / "build.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    build = load_build(path)

    ct = build.slots["armor"].cost_targets
    assert ct == CostTargets(
        refine_from=0, grade_from="none", refine_table="armor_lv1",
        enchant_strategy="stop_when_hit", enchant_goal=(1, "Star_Cluster_Of_Pow3"),
    )


def test_cost_targets_roundtrip_without_new_fields_applies_defaults(tmp_path):
    data = {
        "name": "測試配裝",
        "slots": {"armor": {"item_id": 1, "cost_targets": {}}},
    }
    path = tmp_path / "build.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    build = load_build(path)

    ct = build.slots["armor"].cost_targets
    assert ct == CostTargets(
        refine_from=0, grade_from="none", refine_table=None,
        enchant_strategy="last_slot_only", enchant_goal=None,
    )


def test_cost_targets_absent_key_is_none(tmp_path):
    data = {"name": "測試配裝", "slots": {"armor": {"item_id": 1}}}
    path = tmp_path / "build.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    build = load_build(path)

    assert build.slots["armor"].cost_targets is None


def test_cost_targets_bad_grade_from_raises_at_load_time(tmp_path):
    data = {
        "name": "壞配裝",
        "slots": {"armor": {"item_id": 1, "cost_targets": {"grade_from": "S"}}},
    }
    path = tmp_path / "build.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="grade_from"):
        load_build(path)


def test_cost_targets_bad_enchant_goal_shape_raises_at_load_time(tmp_path):
    data = {
        "name": "壞配裝",
        "slots": {"armor": {"item_id": 1, "cost_targets": {"enchant_goal": [1]}}},
    }
    path = tmp_path / "build.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="enchant_goal"):
        load_build(path)


def test_invalid_refine_table_name_raises_at_eval_time(tmp_path):
    # build.py無從得知表名是否合法(它不持有CostRules) — 驗證留給report層
    # 在真的要用到規則表時做, 這裡確認load_build本身「不」在載入時擋這個。
    data = {
        "name": "壞表名配裝",
        "slots": {"armor": {"item_id": 1, "refine": 5, "cost_targets": {"refine_table": "no_such_table"}}},
    }
    path = tmp_path / "build.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    build = load_build(path)  # 不拋

    rules = load_rules(REAL_RULES_PATH)
    reader = DbReader(_make_db(tmp_path, "db.sqlite", items=[_item_row(1, "TestArmor", "測試防具")]))

    with pytest.raises(ValueError, match="不存在"):
        evaluate_build_cost(build, rules, FROZEN_PRICES, reader, _empty_manual())
    reader.close()


# ---------------------------------------------------------------------------
# enchant_goal預設推導(controller amendment 2)
# ---------------------------------------------------------------------------


def test_enchant_goal_derivation_last_non_null_middle_position(tmp_path):
    # brief指定例: table slots(3,2,1), enchants=[null,"OptC",null] → 最末非null
    # 在position1, 對位到table_slots[1]=2 → goal=(2,"OptC")。goal非末slot,
    # 必須用stop_when_hit(last_slot_only會因goal非末slot報錯)。
    db_path = _make_db(
        tmp_path, "db.sqlite",
        items=[_item_row(2, "EnchantArmor", "附魔防具")],
        enchant_rows=_MULTI_SLOT_ROWS,
    )
    reader = DbReader(db_path)
    manual = _empty_manual()
    slot = SlotConfig(
        item_id=2, enchants=[None, "OptC", None],
        cost_targets=CostTargets(enchant_strategy="stop_when_hit"),
    )

    report = evaluate_item_cost("armor", slot, load_rules(REAL_RULES_PATH), {}, reader, manual)

    expected = solve_enchant(reader, manual, "EnchantArmor", 2, "OptC", "stop_when_hit", {})
    assert report.enchant_zeny == expected.zeny
    for name, qty in expected.materials.items():
        assert report.direct[name] == qty
    reader.close()


def test_enchant_goal_derivation_last_position_all_filled(tmp_path):
    # enchants全部非null → 依「最末非null項」規則仍取最後一個(position2→slot1,
    # 全表最小槽), 剛好滿足last_slot_only的前提(goal必須是末slot)。
    db_path = _make_db(
        tmp_path, "db.sqlite",
        items=[_item_row(2, "EnchantArmor", "附魔防具")],
        enchant_rows=_MULTI_SLOT_ROWS,
    )
    reader = DbReader(db_path)
    manual = _empty_manual()
    slot = SlotConfig(item_id=2, enchants=["OptA", "OptC", "OptE"], cost_targets=CostTargets())

    report = evaluate_item_cost("armor", slot, load_rules(REAL_RULES_PATH), {}, reader, manual)

    expected = solve_enchant(reader, manual, "EnchantArmor", 1, "OptE", "last_slot_only", {})
    assert report.enchant_zeny == expected.zeny
    for name, qty in expected.materials.items():
        assert report.direct[name] == qty
    reader.close()


def test_enchant_goal_explicit_overrides_derivation(tmp_path):
    db_path = _make_db(
        tmp_path, "db.sqlite",
        items=[_item_row(2, "EnchantArmor", "附魔防具")],
        enchant_rows=_MULTI_SLOT_ROWS,
    )
    reader = DbReader(db_path)
    manual = _empty_manual()
    # enchants清單刻意跟explicit goal矛盾, 驗證有enchant_goal時完全不看它。
    slot = SlotConfig(
        item_id=2, enchants=["irrelevant", "values", "here"],
        cost_targets=CostTargets(enchant_strategy="stop_when_hit", enchant_goal=(2, "OptC")),
    )

    report = evaluate_item_cost("armor", slot, load_rules(REAL_RULES_PATH), {}, reader, manual)

    expected = solve_enchant(reader, manual, "EnchantArmor", 2, "OptC", "stop_when_hit", {})
    assert report.enchant_zeny == expected.zeny
    reader.close()


def test_enchant_goal_derivation_list_longer_than_table_raises(tmp_path):
    db_path = _make_db(
        tmp_path, "db.sqlite",
        items=[_item_row(2, "EnchantArmor", "附魔防具")],
        enchant_rows=_MULTI_SLOT_ROWS,
    )
    reader = DbReader(db_path)
    manual = _empty_manual()
    # table只有3槽, enchants卻有4個位置(最末非null在position3, 超出table_slots長度)。
    slot = SlotConfig(item_id=2, enchants=[None, None, None, "Overflow"], cost_targets=CostTargets())

    with pytest.raises(ValueError, match="超過"):
        evaluate_item_cost("armor", slot, load_rules(REAL_RULES_PATH), {}, reader, manual)
    reader.close()


def test_enchant_no_targets_configured_skips_silently(tmp_path):
    db_path = _make_db(
        tmp_path, "db.sqlite",
        items=[_item_row(2, "EnchantArmor", "附魔防具")],
        enchant_rows=_MULTI_SLOT_ROWS,
    )
    reader = DbReader(db_path)
    manual = _empty_manual()
    # enchants全null(沒有要附魔的目標) — 即使item有附魔表, 也不該去查表、
    # 不該產生任何警告(跟頂層cost_targets缺漏同一種opt-in哲學)。
    slot = SlotConfig(item_id=2, enchants=[None, None, None], cost_targets=CostTargets())

    report = evaluate_item_cost("armor", slot, load_rules(REAL_RULES_PATH), {}, reader, manual)

    assert report.enchant_zeny == Fraction(0)
    assert report.warnings == []
    reader.close()


def test_unavailable_enchant_item_warns_and_skips_cost(tmp_path):
    # LegacyArmor完全沒有附魔表資料(自動+手動皆查無), 但enchants清單有非null
    # 項 → 應該產生「舊式附魔未建檔」警告並略過enchant成本(controller amendment2)。
    db_path = _make_db(tmp_path, "db.sqlite", items=[_item_row(3, "LegacyArmor", "舊式防具")])
    reader = DbReader(db_path)
    manual = _empty_manual()
    slot = SlotConfig(item_id=3, enchants=["SomeGoal"], cost_targets=CostTargets())

    report = evaluate_item_cost("armor", slot, load_rules(REAL_RULES_PATH), {}, reader, manual)

    assert report.enchant_zeny == Fraction(0)
    assert report.direct == {}
    assert "舊式附魔未建檔, 不計入" in report.warnings
    reader.close()


# ---------------------------------------------------------------------------
# 基準Zeny總計(使用者定案錨點, 凍結價格)
# ---------------------------------------------------------------------------


def test_baseline1_armor_lv1_zero_to_18_zeny_total(tmp_path):
    db_path = _make_db(tmp_path, "db.sqlite", items=[_item_row(1, "TestArmor", "測試防具")])
    reader = DbReader(db_path)
    rules = load_rules(REAL_RULES_PATH)
    slot = SlotConfig(
        item_id=1, refine=18, grade="none",
        cost_targets=CostTargets(refine_from=0, grade_from="none", refine_table="armor_lv1"),
    )

    report = evaluate_item_cost("armor", slot, rules, FROZEN_PRICES, reader, _empty_manual())

    assert report.zeny_total == Fraction(95774937500, 147)
    assert int(report.zeny_total) == 651530187
    assert report.warnings == []
    reader.close()


def test_baseline3_ether_armor2_zero_to_13_zeny_total(tmp_path):
    db_path = _make_db(tmp_path, "db.sqlite", items=[_item_row(1, "TestArmor", "測試防具")])
    reader = DbReader(db_path)
    rules = load_rules(REAL_RULES_PATH)
    slot = SlotConfig(
        item_id=1, refine=13, grade="none",
        cost_targets=CostTargets(refine_from=0, grade_from="none", refine_table="ether_armor2"),
    )

    report = evaluate_item_cost("armor", slot, rules, FROZEN_PRICES, reader, _empty_manual())

    assert report.zeny_total == Fraction(6696227500, 63)
    assert int(report.zeny_total) == 106289325
    assert report.warnings == []
    reader.close()


def test_baseline4_ether_armor2_none_to_a_final_13_zeny_total(tmp_path):
    db_path = _make_db(tmp_path, "db.sqlite", items=[_item_row(1, "TestArmor", "測試防具")])
    reader = DbReader(db_path)
    rules = load_rules(REAL_RULES_PATH)
    slot = SlotConfig(
        item_id=1, refine=13, grade="A",
        cost_targets=CostTargets(refine_from=0, grade_from="none", refine_table="ether_armor2"),
    )

    report = evaluate_item_cost("armor", slot, rules, FROZEN_PRICES, reader, _empty_manual())

    assert report.zeny_total == Fraction(22111617800, 63)
    assert int(report.zeny_total) == 350978060
    assert report.warnings == []
    # body_count不計價, 純顯示 — ether_armor2在13等以前無break階, 恆為1。
    assert report.body_count == Fraction(1)
    reader.close()


# ---------------------------------------------------------------------------
# refine_from>0部分路徑
# ---------------------------------------------------------------------------


def _partial_rules():
    steps = [
        RefineStep(from_lv=0, to_lv=1, material="pm", qty=1, rate=Fraction(1), fail="safe", blessing=0, fee=0),
        RefineStep(from_lv=1, to_lv=2, material="pm", qty=1, rate=Fraction(1), fail="safe", blessing=0, fee=0),
    ]
    return CostRules(
        refine_tables={"P": steps}, table_displays={"P": "P"}, blessing_item="祝福",
        grade_steps=[], exchange_recipes={},
    )


def test_refine_from_nonzero_partial_path(tmp_path):
    db_path = _make_db(tmp_path, "db.sqlite", items=[_item_row(1, "TestArmor", "測試防具")])
    reader = DbReader(db_path)
    slot = SlotConfig(
        item_id=1, refine=2, grade="none",
        cost_targets=CostTargets(refine_from=1, grade_from="none", refine_table="P"),
    )

    report = evaluate_item_cost("armor", slot, _partial_rules(), {"pm": 7}, reader, _empty_manual())

    # start=1: 只算第二階(1→2), 第一階(0→1)已經是「已經在的狀態」不必再算。
    assert report.direct == {"pm": Fraction(1)}
    assert report.zeny_total == Fraction(7)
    reader.close()


# ---------------------------------------------------------------------------
# refine_table缺漏
# ---------------------------------------------------------------------------


def test_missing_refine_table_with_nonzero_target_warns_and_skips(tmp_path):
    db_path = _make_db(tmp_path, "db.sqlite", items=[_item_row(1, "TestArmor", "測試防具")])
    reader = DbReader(db_path)
    slot = SlotConfig(
        item_id=1, refine=5, grade="none",
        cost_targets=CostTargets(refine_from=0, grade_from="none", refine_table=None),
    )

    report = evaluate_item_cost("armor", slot, load_rules(REAL_RULES_PATH), {}, reader, _empty_manual())

    assert report.direct == {}
    assert report.zeny_total == Fraction(0)
    assert "部位armor未指定精煉表, 精煉成本略過" in report.warnings
    reader.close()


def test_zero_refine_target_without_table_no_warning(tmp_path):
    db_path = _make_db(tmp_path, "db.sqlite", items=[_item_row(1, "TestArmor", "測試防具")])
    reader = DbReader(db_path)
    slot = SlotConfig(
        item_id=1, refine=0, grade="none",
        cost_targets=CostTargets(refine_from=0, grade_from="none", refine_table=None),
    )

    report = evaluate_item_cost("armor", slot, load_rules(REAL_RULES_PATH), {}, reader, _empty_manual())

    assert report.warnings == []
    assert report.zeny_total == Fraction(0)
    reader.close()


# ---------------------------------------------------------------------------
# 升階+附魔組合(合成規則, 驗證三層/各費用欄位正確組裝)
# ---------------------------------------------------------------------------


def _combined_rules():
    refine_table = [
        RefineStep(from_lv=0, to_lv=1, material="m1", qty=2, rate=Fraction(1), fail="safe", blessing=0, fee=5),
    ]
    grade_step = GradeStep(
        from_grade="none", to_grade="D", refine_req=1, rate=Fraction(1, 2),
        materials=(("gem", 3),), fee=50,
    )
    return CostRules(
        refine_tables={"T": refine_table}, table_displays={"T": "T"}, blessing_item="祝福",
        grade_steps=[grade_step], exchange_recipes={"gem": ([("basegem", 2)], 10)},
    )


def test_grade_and_enchant_combined_item(tmp_path):
    # 手算(見docstring旁注): solve_grade_path(T, none->D, final_refine=1) →
    # materials={"m1":4}, zeny_fee=10, grade_materials={"gem":6}, grade_fee=100,
    # body_count=1。附魔: 單槽table(slot1), N=4(權重1/4), require_cost全為
    # '0, {"encmat", 2}' → enchant_materials={"encmat":8}, enchant_zeny=0,
    # 無重置規則故有警告。"gem"經exchange_recipes展開成basegem x2/單位+
    # 手續費10/單位。
    enchant_rows = [
        _enchant_row(20, ["CombinedItem"], 1, '0, {"encmat", 2}', "GoalEnchant", 1),
        _enchant_row(20, ["CombinedItem"], 1, '0, {"encmat", 2}', "OtherEnchant", 3),
    ]
    db_path = _make_db(
        tmp_path, "db.sqlite",
        items=[_item_row(5, "CombinedItem", "組合裝備")],
        enchant_rows=enchant_rows,
    )
    reader = DbReader(db_path)
    prices = {"m1": 100, "basegem": 50, "encmat": 10}
    slot = SlotConfig(
        item_id=5, refine=1, grade="D", enchants=["GoalEnchant"],
        cost_targets=CostTargets(refine_from=0, grade_from="none", refine_table="T"),
    )

    report = evaluate_item_cost("armor", slot, _combined_rules(), prices, reader, _empty_manual())

    assert report.direct == {"m1": Fraction(4), "gem": Fraction(6), "encmat": Fraction(8)}
    assert report.intermediates == {"gem": Fraction(6)}
    assert report.base == {"m1": Fraction(4), "basegem": Fraction(12), "encmat": Fraction(8)}
    assert report.exchange_fee == Fraction(60)
    assert report.refine_fee == Fraction(10)
    assert report.grade_fee == Fraction(100)
    assert report.enchant_zeny == Fraction(0)
    assert report.body_count == Fraction(1)
    assert "無重置規則, 以免費重置計" in report.warnings
    assert report.zeny_total == Fraction(1250)
    reader.close()


# ---------------------------------------------------------------------------
# 裝備本身查無(item_id在db裡查無)
# ---------------------------------------------------------------------------


def test_item_not_found_warns_and_falls_back_to_placeholder_name(tmp_path):
    db_path = _make_db(tmp_path, "db.sqlite", items=[])
    reader = DbReader(db_path)
    slot = SlotConfig(
        item_id=9999, refine=0, grade="none",
        cost_targets=CostTargets(refine_from=0, grade_from="none", refine_table=None),
    )

    report = evaluate_item_cost("armor", slot, load_rules(REAL_RULES_PATH), {}, reader, _empty_manual())

    assert report.item_name == "item:9999"
    assert "找不到裝備: item_id=9999（部位:armor）" in report.warnings
    assert report.zeny_total == Fraction(0)
    reader.close()


# ---------------------------------------------------------------------------
# 卡片: M3不計價
# ---------------------------------------------------------------------------


def test_cards_never_priced(tmp_path):
    db_path = _make_db(tmp_path, "db.sqlite", items=[_item_row(1, "TestArmor", "測試防具")])
    reader = DbReader(db_path)
    slot = SlotConfig(
        item_id=1, refine=0, grade="none", cards=[4140, 4141],
        cost_targets=CostTargets(refine_from=0, grade_from="none", refine_table=None),
    )

    report = evaluate_item_cost("armor", slot, load_rules(REAL_RULES_PATH), {}, reader, _empty_manual())

    assert report.zeny_total == Fraction(0)
    assert report.direct == {}
    assert report.base == {}
    reader.close()


# ---------------------------------------------------------------------------
# 配裝彙總 + warnings傳遞
# ---------------------------------------------------------------------------


def test_evaluate_build_cost_skips_slots_without_cost_targets(tmp_path):
    db_path = _make_db(
        tmp_path, "db.sqlite",
        items=[_item_row(1, "TestArmor", "測試防具"), _item_row(2, "TestWeapon", "測試武器")],
    )
    reader = DbReader(db_path)
    build = Build(
        name="測試配裝",
        slots={
            "armor": SlotConfig(item_id=1, cost_targets=CostTargets()),
            "weapon": SlotConfig(item_id=2, cost_targets=None),
        },
    )

    report = evaluate_build_cost(build, load_rules(REAL_RULES_PATH), {}, reader, _empty_manual())

    assert len(report.items) == 1
    assert report.items[0].slot_key == "armor"
    reader.close()


def test_evaluate_build_cost_sums_zeny_total_and_collects_warnings(tmp_path):
    db_path = _make_db(
        tmp_path, "db.sqlite",
        items=[_item_row(1, "TestArmor", "測試防具"), _item_row(2, "TestWeapon", "測試武器")],
    )
    reader = DbReader(db_path)
    build = Build(
        name="測試配裝",
        slots={
            "armor": SlotConfig(
                item_id=1, refine=2, grade="none",
                cost_targets=CostTargets(refine_from=1, grade_from="none", refine_table="P"),
            ),
            "weapon": SlotConfig(
                item_id=2, refine=5, grade="none",
                cost_targets=CostTargets(refine_from=0, grade_from="none", refine_table=None),
            ),
        },
    )

    report = evaluate_build_cost(build, _partial_rules(), {"pm": 7}, reader, _empty_manual())

    assert isinstance(report, BuildCostReport)
    assert len(report.items) == 2
    # armor: partial refine(pm=1)x7=7; weapon: 缺表警告, 成本0。
    assert report.zeny_total == Fraction(7)
    assert "部位weapon未指定精煉表, 精煉成本略過" in report.warnings
    reader.close()
