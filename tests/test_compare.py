import pytest

from app.core.aggregate import BuildEffects, SourcedEffect
from app.core.compare import CompareRow, compare_builds
from app.core.entries import (
    CAT_MAGICAL,
    CAT_OTHER,
    CAT_PHYSICAL,
    KIND_NUMERIC,
    EffectEntry,
)


def _make_build_effects(totals_dict: dict[tuple[str, str], float]) -> BuildEffects:
    """Helper to create a BuildEffects with only totals populated."""
    return BuildEffects(
        sourced=[],
        totals=totals_dict,
        unresolved=[],
        others=[],
        warnings=[],
    )


def test_compare_builds_both_present_a_wins():
    """Both builds have the same key; a's value is larger."""
    a = _make_build_effects({("ATK", ""): 100.0})
    b = _make_build_effects({("ATK", ""): 80.0})
    rows = compare_builds(a, b)

    assert len(rows) == 1
    assert rows[0].key == "ATK"
    assert rows[0].unit == ""
    assert rows[0].a == 100.0
    assert rows[0].b == 80.0
    assert rows[0].advantage == "a"
    assert rows[0].category == CAT_PHYSICAL


def test_compare_builds_both_present_b_wins():
    """Both builds have the same key; b's value is larger."""
    a = _make_build_effects({("MATK", ""): 50.0})
    b = _make_build_effects({("MATK", ""): 150.0})
    rows = compare_builds(a, b)

    assert len(rows) == 1
    assert rows[0].key == "MATK"
    assert rows[0].a == 50.0
    assert rows[0].b == 150.0
    assert rows[0].advantage == "b"
    assert rows[0].category == CAT_MAGICAL


def test_compare_builds_tie():
    """Both builds have the same key with equal values."""
    a = _make_build_effects({("HP", ""): 500.0})
    b = _make_build_effects({("HP", ""): 500.0})
    rows = compare_builds(a, b)

    assert len(rows) == 1
    assert rows[0].key == "HP"
    assert rows[0].a == 500.0
    assert rows[0].b == 500.0
    assert rows[0].advantage == "tie"


def test_compare_builds_single_none_a_only():
    """Only a has this key; b is None."""
    a = _make_build_effects({("DEF", ""): 100.0})
    b = _make_build_effects({})
    rows = compare_builds(a, b)

    assert len(rows) == 1
    assert rows[0].key == "DEF"
    assert rows[0].a == 100.0
    assert rows[0].b is None
    assert rows[0].advantage == "a"


def test_compare_builds_single_none_b_only():
    """Only b has this key; a is None."""
    a = _make_build_effects({})
    b = _make_build_effects({("變動詠唱", "秒"): 2.5})
    rows = compare_builds(a, b)

    assert len(rows) == 1
    assert rows[0].key == "變動詠唱"
    assert rows[0].unit == "秒"
    assert rows[0].a is None
    assert rows[0].b == 2.5
    assert rows[0].advantage == "b"
    assert rows[0].category == CAT_MAGICAL


def test_compare_builds_union_multiple_keys():
    """Keys from a and b are unioned correctly."""
    a = _make_build_effects({("ATK", ""): 100.0, ("HP", ""): 500.0})
    b = _make_build_effects({("MATK", ""): 150.0, ("DEF", ""): 50.0})
    rows = compare_builds(a, b)

    assert len(rows) == 4
    keys = {row.key for row in rows}
    assert keys == {"ATK", "HP", "MATK", "DEF"}


def test_compare_builds_sort_by_category():
    """Rows are sorted by category: physical → magical → other."""
    a = _make_build_effects({})
    b = _make_build_effects({
        ("MATK", ""): 100.0,  # magical
        ("SP消耗", ""): 10.0,  # other
        ("ATK", ""): 200.0,  # physical
    })
    rows = compare_builds(a, b)

    # Expected order: physical (ATK), magical (MATK), other (SP消耗)
    assert rows[0].key == "ATK"
    assert rows[0].category == CAT_PHYSICAL
    assert rows[1].key == "MATK"
    assert rows[1].category == CAT_MAGICAL
    assert rows[2].key == "SP消耗"
    assert rows[2].category == CAT_OTHER


def test_compare_builds_sort_by_key_within_category():
    """Within the same category, rows are sorted by key name."""
    a = _make_build_effects({})
    b = _make_build_effects({
        ("CRI", ""): 50.0,  # physical
        ("ATK", ""): 100.0,  # physical
        ("HIT", ""): 75.0,  # physical
    })
    rows = compare_builds(a, b)

    # All are physical; sorted by key: ATK, CRI, HIT (alphabetical)
    assert len(rows) == 3
    assert rows[0].key == "ATK"
    assert rows[1].key == "CRI"
    assert rows[2].key == "HIT"


def test_compare_builds_sort_mixed_categories_and_keys():
    """Sort by category first, then by key within each category."""
    a = _make_build_effects({})
    b = _make_build_effects({
        ("SP消耗", ""): 10.0,  # other
        ("MATK", ""): 100.0,  # magical
        ("近距離物理傷害", ""): 5.0,  # physical
        ("HIT", ""): 75.0,  # physical
        ("變動詠唱", "秒"): 2.0,  # magical
    })
    rows = compare_builds(a, b)

    # Expected order:
    # physical: 近距離物理傷害, HIT (alphabetically)
    # magical: MATK, 變動詠唱 (alphabetically)
    # other: SP消耗
    assert len(rows) == 5
    assert rows[0].key == "HIT"
    assert rows[0].category == CAT_PHYSICAL
    assert rows[1].key == "近距離物理傷害"
    assert rows[1].category == CAT_PHYSICAL
    assert rows[2].key == "MATK"
    assert rows[2].category == CAT_MAGICAL
    assert rows[3].key == "變動詠唱"
    assert rows[3].category == CAT_MAGICAL
    assert rows[4].key == "SP消耗"
    assert rows[4].category == CAT_OTHER


def test_compare_builds_advantage_both_directions():
    """Test advantage logic with both a>b and b>a scenarios in one result."""
    a = _make_build_effects({("ATK", ""): 200.0, ("MATK", ""): 50.0})
    b = _make_build_effects({("ATK", ""): 100.0, ("MATK", ""): 150.0})
    rows = compare_builds(a, b)

    atk_row = next(r for r in rows if r.key == "ATK")
    matk_row = next(r for r in rows if r.key == "MATK")

    assert atk_row.advantage == "a"
    assert matk_row.advantage == "b"


def test_compare_builds_with_units():
    """Different units are treated as separate keys."""
    a = _make_build_effects({("ATK", ""): 100.0, ("ATK", "%"): 10.0})
    b = _make_build_effects({("ATK", ""): 80.0})
    rows = compare_builds(a, b)

    assert len(rows) == 2
    atk_empty = next(r for r in rows if r.unit == "")
    atk_percent = next(r for r in rows if r.unit == "%")

    assert atk_empty.a == 100.0
    assert atk_empty.b == 80.0
    assert atk_percent.a == 10.0
    assert atk_percent.b is None


def test_compare_builds_empty_builds():
    """Both builds have no totals."""
    a = _make_build_effects({})
    b = _make_build_effects({})
    rows = compare_builds(a, b)

    assert len(rows) == 0


def test_compare_builds_single_empty():
    """One build is empty, the other has totals."""
    a = _make_build_effects({})
    b = _make_build_effects({("HP", ""): 1000.0})
    rows = compare_builds(a, b)

    assert len(rows) == 1
    assert rows[0].a is None
    assert rows[0].b == 1000.0
    assert rows[0].advantage == "b"


def test_compare_row_fields():
    """CompareRow dataclass has expected fields and is frozen."""
    row = CompareRow(
        key="ATK",
        unit="",
        category=CAT_PHYSICAL,
        a=100.0,
        b=80.0,
        advantage="a",
    )

    assert row.key == "ATK"
    assert row.unit == ""
    assert row.category == CAT_PHYSICAL
    assert row.a == 100.0
    assert row.b == 80.0
    assert row.advantage == "a"

    # Frozen means it cannot be modified
    with pytest.raises(AttributeError):
        row.a = 200.0
