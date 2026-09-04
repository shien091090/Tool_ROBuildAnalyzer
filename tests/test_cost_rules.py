import json
from fractions import Fraction

import pytest

from app.core.cost.rules import CostRules, GradeStep, RefineStep, load_prices, load_rules

REAL_RULES_PATH = "userdata/refine_rules.json"
REAL_PRICES_PATH = "userdata/prices.json"


# ---------------------------------------------------------------------------
# 真實 userdata 抽樣斷言
# ---------------------------------------------------------------------------


def test_load_rules_armor_lv1_step_7_to_8():
    rules = load_rules(REAL_RULES_PATH)
    step = next(s for s in rules.refine_tables["armor_lv1"] if s.from_lv == 7 and s.to_lv == 8)
    assert step.rate == Fraction(2, 5)
    assert step.blessing == 1
    assert step.fail == "stay"
    assert step.fee == 0


def test_load_rules_shadow_armor_step_7_to_8_fee():
    rules = load_rules(REAL_RULES_PATH)
    step = next(s for s in rules.refine_tables["shadow_armor"] if s.from_lv == 7 and s.to_lv == 8)
    assert step.fee == 500000


def test_load_rules_ether_weapon5_step_14_to_15_fail_break():
    rules = load_rules(REAL_RULES_PATH)
    step = next(s for s in rules.refine_tables["ether_weapon5"] if s.from_lv == 14 and s.to_lv == 15)
    assert step.fail == "break"


def test_load_rules_grade_step_b_to_a():
    rules = load_rules(REAL_RULES_PATH)
    step = next(g for g in rules.grade_steps if g.from_grade == "B" and g.to_grade == "A")
    assert step.rate == Fraction(2, 5)
    assert step.materials == (("乙太琥珀", 10),)
    assert step.fee == 2500000


def test_load_rules_exchange_recipe_乙太魔石():
    rules = load_rules(REAL_RULES_PATH)
    inputs, fee = rules.exchange_recipes["乙太魔石"]
    assert inputs == [("乙太星塵", 5)]
    assert fee == 100000


def test_load_rules_exchange_recipe_高密度乙太礦石改名層():
    # I1(M3 final review交辦): excel原始「乙太鈣礦石」/「乙太鈰鐳礦石」兩列的
    # product名與礦石input名都缺"高密度"前綴, 對照ether_armor2表15級以後
    # 真正消耗的材料名"高密度乙太鈣礦石"/"高密度乙太鈰鐳礦石"(由prices.json
    # 已登記172,500的"高密度鈣礦石"/"高密度鈰鐳礦石"兌換而成, 不是單價0的
    # "鈣礦石"/"鈰鐳礦石") — scripts/convert_refine_rules.py的_ETHER_ORE_RENAME
    # 改名層修正這個落差, 這裡驗證改名後的json確實接上正確的input。
    rules = load_rules(REAL_RULES_PATH)

    ca_inputs, ca_fee = rules.exchange_recipes["高密度乙太鈣礦石"]
    assert ca_inputs == [("乙太星塵", 3), ("高密度鈣礦石", 1)]
    assert ca_fee == 50000

    la_inputs, la_fee = rules.exchange_recipes["高密度乙太鈰鐳礦石"]
    assert la_inputs == [("乙太星塵", 3), ("高密度鈰鐳礦石", 1)]
    assert la_fee == 50000

    # 舊的(未改名)product名不該再存在, 避免改名沒生效卻誤判成功。
    assert "乙太鈣礦石" not in rules.exchange_recipes
    assert "乙太鈰鐳礦石" not in rules.exchange_recipes


def test_load_rules_table_displays():
    rules = load_rules(REAL_RULES_PATH)
    assert rules.table_displays["armor_lv1"] == "一級防具"
    assert rules.table_displays["shadow_armor"] == "影子防具"


def test_load_rules_blessing_item():
    rules = load_rules(REAL_RULES_PATH)
    assert rules.blessing_item == "鐵匠的祝福"


def test_load_rules_steps_sorted_by_from_lv():
    rules = load_rules(REAL_RULES_PATH)
    for steps in rules.refine_tables.values():
        levels = [s.from_lv for s in steps]
        assert levels == sorted(levels)


def test_load_prices_real_spot_values():
    prices = load_prices(REAL_PRICES_PATH)
    assert prices["鐵匠的祝福"] == 725000
    assert prices["乙太魔石"] == 100000
    assert prices["鋁"] == 0


# ---------------------------------------------------------------------------
# 驗證: 壞 json
# ---------------------------------------------------------------------------


def _minimal_rules_dict() -> dict:
    return {
        "refine_tables": {
            "t1": {
                "display": "測試表",
                "steps": [
                    {
                        "from": 0,
                        "to": 1,
                        "material": "鋁",
                        "qty": 1,
                        "rate": "1",
                        "fail": "safe",
                        "blessing": 0,
                        "fee": 0,
                    },
                    {
                        "from": 1,
                        "to": 2,
                        "material": "鋁",
                        "qty": 1,
                        "rate": "0.5",
                        "fail": "stay",
                        "blessing": 0,
                        "fee": 0,
                    },
                ],
            }
        },
        "blessing_item": "祝福道具",
        "grade_steps": [
            {
                "from": "none",
                "to": "D",
                "refine_req": 11,
                "rate": "0.7",
                "materials": [{"name": "寶石", "qty": 5}],
                "fee": 500000,
            }
        ],
        "exchange_recipes": {
            "兌換品": {"inputs": [{"name": "星塵", "qty": 5}], "fee": 100000},
        },
    }


def _write_rules(tmp_path, data: dict) -> str:
    path = tmp_path / "bad_rules.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return str(path)


def test_invalid_rate_out_of_range_raises(tmp_path):
    data = _minimal_rules_dict()
    data["refine_tables"]["t1"]["steps"][1]["rate"] = "1.5"
    path = _write_rules(tmp_path, data)
    with pytest.raises(ValueError):
        load_rules(path)


def test_invalid_rate_zero_raises(tmp_path):
    data = _minimal_rules_dict()
    data["refine_tables"]["t1"]["steps"][1]["rate"] = "0"
    path = _write_rules(tmp_path, data)
    with pytest.raises(ValueError):
        load_rules(path)


def test_invalid_fail_value_raises(tmp_path):
    data = _minimal_rules_dict()
    data["refine_tables"]["t1"]["steps"][1]["fail"] = "explode"
    path = _write_rules(tmp_path, data)
    with pytest.raises(ValueError):
        load_rules(path)


def test_invalid_step_skips_level_raises(tmp_path):
    data = _minimal_rules_dict()
    data["refine_tables"]["t1"]["steps"][1]["to"] = 3  # from 1 to 3, 跳級
    path = _write_rules(tmp_path, data)
    with pytest.raises(ValueError):
        load_rules(path)


def test_invalid_step_noncontiguous_raises(tmp_path):
    data = _minimal_rules_dict()
    data["refine_tables"]["t1"]["steps"][1]["from"] = 2
    data["refine_tables"]["t1"]["steps"][1]["to"] = 3
    path = _write_rules(tmp_path, data)
    with pytest.raises(ValueError):
        load_rules(path)


def test_invalid_minus1_at_from_zero_raises(tmp_path):
    data = _minimal_rules_dict()
    data["refine_tables"]["t1"]["steps"][0]["fail"] = "minus1"
    path = _write_rules(tmp_path, data)
    with pytest.raises(ValueError):
        load_rules(path)


def test_invalid_negative_fee_raises(tmp_path):
    data = _minimal_rules_dict()
    data["refine_tables"]["t1"]["steps"][0]["fee"] = -1
    path = _write_rules(tmp_path, data)
    with pytest.raises(ValueError):
        load_rules(path)


def test_invalid_grade_step_negative_fee_raises(tmp_path):
    data = _minimal_rules_dict()
    data["grade_steps"][0]["fee"] = -100
    path = _write_rules(tmp_path, data)
    with pytest.raises(ValueError):
        load_rules(path)


def test_invalid_exchange_recipe_negative_fee_raises(tmp_path):
    data = _minimal_rules_dict()
    data["exchange_recipes"]["兌換品"]["fee"] = -1
    path = _write_rules(tmp_path, data)
    with pytest.raises(ValueError, match="fee不得為負數"):
        load_rules(path)


def test_invalid_grade_step_negative_fee_message_fragment(tmp_path):
    data = _minimal_rules_dict()
    data["grade_steps"][0]["fee"] = -100
    path = _write_rules(tmp_path, data)
    with pytest.raises(ValueError, match="fee不得為負數"):
        load_rules(path)


def test_invalid_refine_step_zero_qty_raises(tmp_path):
    data = _minimal_rules_dict()
    data["refine_tables"]["t1"]["steps"][0]["qty"] = 0
    path = _write_rules(tmp_path, data)
    with pytest.raises(ValueError, match="數量必須為正整數"):
        load_rules(path)


def test_invalid_refine_step_negative_qty_raises(tmp_path):
    data = _minimal_rules_dict()
    data["refine_tables"]["t1"]["steps"][1]["qty"] = -3
    path = _write_rules(tmp_path, data)
    with pytest.raises(ValueError, match="數量必須為正整數"):
        load_rules(path)


def test_invalid_grade_chain_discontinuity_raises(tmp_path):
    data = _minimal_rules_dict()
    # 第一階 none→D, 接著再補一階「from=C」(應為D才連續) → 階級不連續。
    data["grade_steps"].append(
        {
            "from": "C",
            "to": "B",
            "refine_req": 11,
            "rate": "0.5",
            "materials": [{"name": "寶石2", "qty": 5}],
            "fee": 100000,
        }
    )
    path = _write_rules(tmp_path, data)
    with pytest.raises(ValueError, match="階級不連續"):
        load_rules(path)


def test_invalid_grade_step_zero_material_qty_raises(tmp_path):
    data = _minimal_rules_dict()
    data["grade_steps"][0]["materials"][0]["qty"] = 0
    path = _write_rules(tmp_path, data)
    with pytest.raises(ValueError, match="數量必須為正整數"):
        load_rules(path)


def test_invalid_grade_step_negative_material_qty_raises(tmp_path):
    data = _minimal_rules_dict()
    data["grade_steps"][0]["materials"][0]["qty"] = -5
    path = _write_rules(tmp_path, data)
    with pytest.raises(ValueError, match="數量必須為正整數"):
        load_rules(path)


def test_invalid_exchange_recipe_zero_input_qty_raises(tmp_path):
    data = _minimal_rules_dict()
    data["exchange_recipes"]["兌換品"]["inputs"][0]["qty"] = 0
    path = _write_rules(tmp_path, data)
    with pytest.raises(ValueError, match="數量必須為正整數"):
        load_rules(path)


def test_invalid_exchange_recipe_negative_input_qty_raises(tmp_path):
    data = _minimal_rules_dict()
    data["exchange_recipes"]["兌換品"]["inputs"][0]["qty"] = -2
    path = _write_rules(tmp_path, data)
    with pytest.raises(ValueError, match="數量必須為正整數"):
        load_rules(path)


def test_invalid_fee_malformed_raises(tmp_path):
    data = _minimal_rules_dict()
    data["refine_tables"]["t1"]["steps"][0]["fee"] = "not-a-number"
    path = _write_rules(tmp_path, data)
    with pytest.raises(ValueError, match="格式錯誤"):
        load_rules(path)


def test_missing_required_field_raises_valueerror_not_keyerror(tmp_path):
    data = _minimal_rules_dict()
    del data["refine_tables"]["t1"]["steps"][0]["rate"]
    path = _write_rules(tmp_path, data)
    with pytest.raises(ValueError, match="缺少必要欄位"):
        load_rules(path)


def test_valid_minimal_rules_loads_ok(tmp_path):
    data = _minimal_rules_dict()
    path = _write_rules(tmp_path, data)
    rules = load_rules(path)
    assert isinstance(rules, CostRules)
    assert rules.refine_tables["t1"][0].rate == Fraction(1)
    assert rules.refine_tables["t1"][1].rate == Fraction(1, 2)
