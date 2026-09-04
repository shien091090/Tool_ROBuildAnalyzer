import math
from fractions import Fraction

import pytest

from app.core.cost.refine import (
    RefineExpectation,
    RefineExpectation2,
    solve_grade_path,
    solve_refine,
)
from app.core.cost.rules import CostRules, GradeStep, RefineStep, load_rules

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


def test_minus1_at_from_zero_raises_in_solver_directly():
    # rules.py的load_rules本身會擋(from=0時fail不得為minus1), 但這裡刻意
    # 直接建構RefineStep物件呼叫solve_refine, 繞過load_rules的驗證, 驗證
    # 求解器本身也要有防護 —不能只依賴上游rules.py把關, 否則k==0時
    # matrix[k][k-1]會用Python負索引悄悄wrap到最後一欄, 算出錯誤答案卻
    # 完全不拋例外(review findings第1項)。
    steps = [_step(0, 1, "X", 1, "1/2", "minus1")]
    with pytest.raises(ValueError, match="minus1"):
        solve_refine(steps, target=1, blessing_item="祝福")


def test_invalid_start_equal_target_raises():
    steps = [_step(0, 1, "X", 1, "1", "safe")]
    with pytest.raises(ValueError):
        solve_refine(steps, target=1, blessing_item="祝福", start=1)


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


# ---------------------------------------------------------------------------
# solve_grade_path升階鏈損毀模型(review findings第2項): 最終精煉段含break階時,
# 每次爆件要重跑整條升階鏈G, 不是只補一個素體
# ---------------------------------------------------------------------------


def _synthetic_break_final_leg_rules() -> CostRules:
    # 精煉表T: 0→1 safe(材料m1), 1→2 break rate1/2(材料m2)
    refine_table = [
        _step(0, 1, "m1", 1, "1", "safe"),
        _step(1, 2, "m2", 1, "1/2", "break"),
    ]
    # 升階none→D: refine_req=1(即0→1這段, 恰好是safe, 不會爆件),
    # rate1/2, 升階寶石g×1, 手續費100
    grade_step = GradeStep(
        from_grade="none",
        to_grade="D",
        refine_req=1,
        rate=Fraction(1, 2),
        materials=(("g", 1),),
        fee=100,
    )
    return CostRules(
        refine_tables={"T": refine_table},
        table_displays={"T": "T"},
        blessing_item="祝福",
        grade_steps=[grade_step],
        exchange_recipes={},
    )


def test_solve_grade_path_break_in_final_leg_replicates_whole_chain():
    # 手算(見task-4-report.md「fix 2」段落完整推導):
    # G(升階鏈, 0→refine_req=1的m1材料 + 升階寶石g/手續費fee, 皆按1/p放大):
    #   G_materials = {'m1': 1}(0→1 safe, 恰1次)
    #   G_zeny_fee = 0
    #   G_grade_materials = {'g': 1/(1/2) = 2}
    #   G_grade_fee = 100/(1/2) = 200
    # final_exp = solve_refine(T, target=2, ...): 手算聯立方程式(見報告)
    #   解得 E0(m1)=2, E0(m2)=2, E0(body)=1 → body_count=2 → R=1
    # scale = 1+R = 2
    # materials_total = scale*G_materials + final_exp.materials
    #   m1: 2*1 + 2 = 4;  m2: 0 + 2 = 2
    # zeny_fee_total = scale*0 + 0 = 0
    # grade_materials_total = scale*{'g':2} = {'g':4}
    # grade_fee_total = scale*200 = 400
    # body_count = scale = 2
    rules = _synthetic_break_final_leg_rules()
    result = solve_grade_path(rules, "T", "none", "D", final_refine=2)

    assert result.materials["m1"] == Fraction(4)
    assert result.materials["m2"] == Fraction(2)
    assert result.zeny_fee == Fraction(0)
    assert result.grade_materials["g"] == Fraction(4)
    assert result.grade_fee == Fraction(400)
    assert result.body_count == Fraction(2)


def test_solve_grade_path_break_in_grade_leg_raises():
    # 升階段落自己的0→refine_req精煉如果含break, 這個線性放大簡化模型
    # 不成立(素體重來的成本會疊代性地卷進更早的升階段落), 必須直接拋
    # ValueError, 不能算出一個看似合理但實際上錯誤的數字。
    refine_table = [_step(0, 1, "m", 1, "1/2", "break")]
    grade_step = GradeStep(
        from_grade="none",
        to_grade="D",
        refine_req=1,
        rate=Fraction(1, 2),
        materials=(("g", 1),),
        fee=0,
    )
    rules = CostRules(
        refine_tables={"T2": refine_table},
        table_displays={"T2": "T2"},
        blessing_item="祝福",
        grade_steps=[grade_step],
        exchange_recipes={},
    )
    with pytest.raises(ValueError, match="爆件"):
        solve_grade_path(rules, "T2", "none", "D", final_refine=1)
