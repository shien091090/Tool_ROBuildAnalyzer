import math
from fractions import Fraction

import pytest

from app.core.cost.refine import (
    RefineExpectation,
    RefineExpectation2,
    solve_grade_path,
    solve_refine,
)
from app.core.cost.rules import RefineStep, load_rules

REAL_RULES_PATH = "userdata/refine_rules.json"


def _step(from_lv, to_lv, material, qty, rate, fail, blessing=0, fee=0):
    return RefineStep(
        from_lv=from_lv,
        to_lv=to_lv,
        material=material,
        qty=qty,
        rate=Fraction(rate),
        fail=fail,
        blessing=blessing,
        fee=fee,
    )


# ---------------------------------------------------------------------------
# 單元級: 手算小例自洽
# ---------------------------------------------------------------------------


def test_pure_safe_chain():
    steps = [
        _step(0, 1, "X", 1, "1", "safe"),
        _step(1, 2, "X", 1, "1", "safe"),
        _step(2, 3, "X", 1, "1", "safe"),
    ]
    result = solve_refine(steps, target=3, blessing_item="祝福")
    assert result.materials["X"] == Fraction(3)
    assert result.body_count == Fraction(1)
    assert result.zeny_fee == Fraction(0)


def test_single_stay_with_blessing_and_fee():
    steps = [_step(0, 1, "Y", 2, "1/4", "stay", blessing=1, fee=100)]
    result = solve_refine(steps, target=1, blessing_item="祝福水")
    assert result.materials["Y"] == Fraction(8)  # qty2 / p(1/4) = 8
    assert result.materials["祝福水"] == Fraction(4)  # blessing1 / p(1/4) = 4
    assert result.zeny_fee == Fraction(400)  # fee100 / p(1/4) = 400
    assert result.body_count == Fraction(1)


def test_single_break_self_consistency():
    # E0 = 1 + p*0 + (1-p)*(body+E0); p=1/2 → 材料/本體皆為幾何期望1/p=2
    steps = [_step(0, 1, "Z", 1, "1/2", "break")]
    result = solve_refine(steps, target=1, blessing_item="祝福")
    assert result.materials["Z"] == Fraction(2)
    assert result.body_count == Fraction(2)
    assert result.zeny_fee == Fraction(0)


def test_minus1_coupling_three_level_hand_example():
    # 手算: E2=1; E1=1+p*E2+(1-p)*E0(p=1/2)=1.5+0.5*E0; E0=1+E1
    # 解得 E0=5, E1=4, E2=1
    steps = [
        _step(0, 1, "M", 1, "1", "safe"),
        _step(1, 2, "M", 1, "1/2", "minus1"),
        _step(2, 3, "M", 1, "1", "safe"),
    ]
    result = solve_refine(steps, target=3, blessing_item="祝福")
    assert result.materials["M"] == Fraction(5)
    assert result.body_count == Fraction(1)
    assert result.zeny_fee == Fraction(0)


def test_start_parameter_uses_e_start_not_e0():
    steps = [
        _step(0, 1, "M", 1, "1", "safe"),
        _step(1, 2, "M", 1, "1/2", "minus1"),
        _step(2, 3, "M", 1, "1", "safe"),
    ]
    result_from_1 = solve_refine(steps, target=3, blessing_item="祝福", start=1)
    assert result_from_1.materials["M"] == Fraction(4)  # E1手算=4


def test_invalid_target_zero_raises():
    with pytest.raises(ValueError):
        solve_refine([], target=0, blessing_item="祝福")


def test_missing_step_in_chain_raises():
    steps = [_step(0, 1, "X", 1, "1", "safe")]
    with pytest.raises(ValueError, match="缺少"):
        solve_refine(steps, target=3, blessing_item="祝福")


# ---------------------------------------------------------------------------
# 基準1: armor_lv1 0→18 (使用者定案錨點, 逐字Fraction斷言)
# ---------------------------------------------------------------------------


def test_baseline1_armor_lv1_zero_to_18():
    rules = load_rules(REAL_RULES_PATH)
    result = solve_refine(rules.refine_tables["armor_lv1"], target=18, blessing_item=rules.blessing_item)

    assert result.body_count == Fraction(1000, 441)
    assert result.materials["鋁"] == Fraction(4000, 441)
    assert result.materials["濃縮鋁"] == Fraction(6940, 441)
    assert result.materials["鈣礦石"] == Fraction(50)
    assert result.materials["特殊祝福的防具礦石"] == Fraction(400, 7)
    assert result.materials["鐵匠的祝福"] == Fraction(845, 2)
    assert result.zeny_fee == Fraction(0)


# ---------------------------------------------------------------------------
# 基準3: ether_armor2 0→13
# ---------------------------------------------------------------------------


def test_baseline3_ether_armor2_zero_to_13():
    rules = load_rules(REAL_RULES_PATH)
    result = solve_refine(rules.refine_tables["ether_armor2"], target=13, blessing_item=rules.blessing_item)

    assert result.body_count == Fraction(1)
    assert math.isclose(float(result.materials["鐵匠的祝福"]), 135.83, rel_tol=1e-4)
    # Fraction自身內部一致性: 轉回float後與四捨五入到小數點後2位的練習值一致
    assert round(float(result.materials["鐵匠的祝福"]), 2) == 135.83


# ---------------------------------------------------------------------------
# 基準2: ether_weapon5 0→20
# ---------------------------------------------------------------------------


def test_baseline2_ether_weapon5_zero_to_20():
    rules = load_rules(REAL_RULES_PATH)
    result = solve_refine(rules.refine_tables["ether_weapon5"], target=20, blessing_item=rules.blessing_item)

    assert math.isclose(float(result.body_count), 2040816.33, rel_tol=1e-6)
    assert math.isclose(float(result.materials["鐵匠的祝福"]), 481292517.01, rel_tol=1e-6)


# ---------------------------------------------------------------------------
# 基準4: solve_grade_path ether_armor2 none→A, final_refine=13
# ---------------------------------------------------------------------------


def test_baseline4_grade_path_none_to_a():
    rules = load_rules(REAL_RULES_PATH)
    result = solve_grade_path(rules, "ether_armor2", "none", "A", final_refine=13)

    assert isinstance(result, RefineExpectation2)
    assert result.grade_materials["乙太天藍寶石"] == Fraction(50, 7)
    assert result.grade_materials["乙太黃寶石"] == Fraction(25, 3)
    assert result.grade_materials["乙太紫寶石"] == Fraction(10)
    assert result.grade_materials["乙太琥珀"] == Fraction(25)

    expected_grade_fee = (
        Fraction(500000 * 10, 7)
        + Fraction(625000 * 5, 3)
        + Fraction(1000000 * 2)
        + Fraction(2500000 * 5, 2)
    )
    assert result.grade_fee == expected_grade_fee
    assert math.isclose(float(expected_grade_fee), 10005952.38, rel_tol=1e-6)

    # 精煉部分: 4輪0→11 + 1輪0→13, 鐵匠的祝福總計約332.50
    assert math.isclose(float(result.materials["鐵匠的祝福"]), 332.50, rel_tol=1e-4)
    # ether_armor2在13等以前沒有break階, 4輪0→11與1輪0→13皆body_count==1,
    # 全程無爆件額外本體
    assert result.body_count == Fraction(1)


def test_solve_grade_path_invalid_order_raises():
    rules = load_rules(REAL_RULES_PATH)
    with pytest.raises(ValueError):
        solve_grade_path(rules, "ether_armor2", "A", "none", final_refine=13)


def test_solve_grade_path_same_grade_raises():
    rules = load_rules(REAL_RULES_PATH)
    with pytest.raises(ValueError):
        solve_grade_path(rules, "ether_armor2", "none", "none", final_refine=13)


def test_solve_grade_path_unknown_grade_raises():
    rules = load_rules(REAL_RULES_PATH)
    with pytest.raises(ValueError):
        solve_grade_path(rules, "ether_armor2", "none", "Z", final_refine=13)


# ---------------------------------------------------------------------------
# shadow_armor zeny_fee (0→9): 兩個500000手續費的stay階
# ---------------------------------------------------------------------------


def test_shadow_armor_zeny_fee_zero_to_9():
    # 手算: shadow_armor真實規則檔裡7→8與8→9兩階皆為stay, rate皆0.4,
    # fee皆500000 → 各fee/p=500000/0.4=1,250,000, 兩階相加=2,500,000。
    # (task brief的手算草稿誤植8→9的rate為0.2, 導致算出3,750,000;
    # 實際規則檔兩階rate皆為0.4 — 本測試依規則檔實際值與spec公式驗算,
    # 已在Task 4報告的concerns段落記錄此落差)
    rules = load_rules(REAL_RULES_PATH)
    result = solve_refine(rules.refine_tables["shadow_armor"], target=9, blessing_item=rules.blessing_item)

    assert result.zeny_fee == Fraction(2500000)
    assert isinstance(result, RefineExpectation)
