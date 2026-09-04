from fractions import Fraction

import pytest

from app.core.cost.materials import MaterialBreakdown, expand, price_total
from app.core.cost.rules import load_rules

REAL_RULES_PATH = "userdata/refine_rules.json"


def _real_recipes():
    return load_rules(REAL_RULES_PATH).exchange_recipes


# ---------------------------------------------------------------------------
# expand()
# ---------------------------------------------------------------------------


def test_expand_single_level_乙太鋁():
    recipes = _real_recipes()
    result = expand({"乙太鋁": Fraction(1)}, recipes)
    assert result.base == {"乙太星塵": Fraction(1), "鋁": Fraction(1)}
    assert result.intermediates == {"乙太鋁": Fraction(1)}
    assert result.exchange_fee == Fraction(10000)


def test_expand_three_level_乙太琥珀_chain():
    recipes = _real_recipes()
    result = expand({"乙太琥珀": Fraction(1)}, recipes)
    # 乙太琥珀 -> 乙太魔石x15 + 琥珀x1(fee500000); 乙太魔石 -> 乙太星塵x5(fee100000)
    assert result.intermediates == {"乙太琥珀": Fraction(1), "乙太魔石": Fraction(15)}
    assert result.base == {"琥珀": Fraction(1), "乙太星塵": Fraction(75)}
    assert result.exchange_fee == Fraction(500000) + Fraction(100000) * 15


def test_expand_mixed_input_synthetic_and_base():
    recipes = _real_recipes()
    result = expand({"乙太鋁": Fraction(1), "鋁": Fraction(2)}, recipes)
    assert result.base == {"乙太星塵": Fraction(1), "鋁": Fraction(3)}
    assert result.intermediates == {"乙太鋁": Fraction(1)}
    assert result.exchange_fee == Fraction(10000)


def test_expand_no_recipe_passes_through_untouched():
    recipes = _real_recipes()
    result = expand({"鋁": Fraction(5)}, recipes)
    assert result.base == {"鋁": Fraction(5)}
    assert result.intermediates == {}
    assert result.exchange_fee == Fraction(0)


def test_expand_cycle_detection_raises():
    cyclic_recipes = {
        "A": ([("B", 1)], 100),
        "B": ([("A", 1)], 100),
    }
    with pytest.raises(ValueError):
        expand({"A": Fraction(1)}, cyclic_recipes)


def test_expand_self_cycle_detection_raises():
    cyclic_recipes = {
        "A": ([("A", 1)], 100),
    }
    with pytest.raises(ValueError):
        expand({"A": Fraction(1)}, cyclic_recipes)


def test_expand_diamond_shape_not_flagged_as_cycle():
    # C 被 A 跟 B 兩條路徑各自需要, 不是循環, 應正常展開並加總。
    recipes = {
        "A": ([("C", 1)], 10),
        "B": ([("C", 2)], 20),
    }
    result = expand({"A": Fraction(1), "B": Fraction(1)}, recipes)
    assert result.base == {"C": Fraction(3)}
    assert result.intermediates == {"A": Fraction(1), "B": Fraction(1)}
    assert result.exchange_fee == Fraction(30)


def test_expand_fraction_quantity_cross_check():
    # 交叉驗證算例: 546.428571...(=3826/7)個乙太魔石 -> 乙太星塵單層鏈值。
    recipes = _real_recipes()
    result = expand({"乙太魔石": Fraction(3826, 7)}, recipes)
    assert result.base["乙太星塵"] == Fraction(19130, 7)
    assert result.exchange_fee == Fraction(100000) * Fraction(3826, 7)


# ---------------------------------------------------------------------------
# price_total()
# ---------------------------------------------------------------------------


def test_price_total_basic_sum():
    breakdown = MaterialBreakdown(
        base={"鋁": Fraction(10), "乙太星塵": Fraction(5)},
        intermediates={},
        exchange_fee=Fraction(1000),
    )
    prices = {"鋁": 100, "乙太星塵": 200}
    total, warnings = price_total(breakdown, prices)
    assert total == Fraction(10 * 100 + 5 * 200 + 1000)
    assert warnings == []


def test_price_total_missing_price_warns_and_counts_zero():
    breakdown = MaterialBreakdown(
        base={"未知材料": Fraction(3)},
        intermediates={},
        exchange_fee=Fraction(0),
    )
    total, warnings = price_total(breakdown, {})
    assert total == Fraction(0)
    assert warnings == ["材料未知材料無價格, 以0計"]


def test_price_total_zero_price_generates_no_warning():
    breakdown = MaterialBreakdown(
        base={"鋁": Fraction(5)},
        intermediates={},
        exchange_fee=Fraction(0),
    )
    total, warnings = price_total(breakdown, {"鋁": 0})
    assert total == Fraction(0)
    assert warnings == []


def test_price_total_includes_extra_fees():
    breakdown = MaterialBreakdown(
        base={"鋁": Fraction(1)},
        intermediates={},
        exchange_fee=Fraction(500),
    )
    total, warnings = price_total(breakdown, {"鋁": 100}, extra_fees=Fraction(2500))
    assert total == Fraction(100 + 500 + 2500)
    assert warnings == []
