import pytest

from app.core.aggregate import BuildEffects, SourcedEffect
from app.core.compare import CompareRow, compare_builds
from app.core.entries import (
    CAT_ABILITY,
    CAT_DAMAGE,
    CAT_OTHER,
    CAT_RESIST,
    CAT_SECONDARY,
    KIND_NUMERIC,
    EffectEntry,
)

# Test-fixture-only lookup mirroring real parser.py handler-level category
# assignments for the specific keys these tests use (category-taxonomy: no
# classify_category exists anymore — categories are assigned explicitly at
# handler level in parser.py, so a test fixture cannot "derive" one from a
# key string either; it must pin the same value parser.py would have
# produced for that concrete key). See app/core/parser.py handler comments
# for the source-of-truth handler# -> category mapping this mirrors:
#   ATK/MATK  <- AddExtParam id 41/200 (CAT_DAMAGE)
#   DEF/HIT/CRI <- AddExtParam id 45/49/52 (CAT_ABILITY)
#   近距離物理傷害 <- handler #28 AddMeleeAttackDamage(1,...) (CAT_DAMAGE)
#   無視 不死 型怪的物理抗性 <- handler #39 AddIgnore_RES_RacePercent (CAT_RESIST)
#   SP消耗 <- handler #48 AddSPconsumption (CAT_SECONDARY)
_FIXTURE_CATEGORY_BY_KEY = {
    "ATK": CAT_DAMAGE,
    "MATK": CAT_DAMAGE,
    "近距離物理傷害": CAT_DAMAGE,
    "無視 不死 型怪的物理抗性": CAT_RESIST,
    "DEF": CAT_ABILITY,
    "HIT": CAT_ABILITY,
    "CRI": CAT_ABILITY,
    "HP": CAT_ABILITY,
    "SP消耗": CAT_SECONDARY,
}


def _make_build_effects(totals_dict: dict[tuple[str, str], float]) -> BuildEffects:
    """Helper to create a BuildEffects with only totals(+matching categories)
    populated. categories is looked up here via _FIXTURE_CATEGORY_BY_KEY
    purely as test-fixture convenience (compare.py itself must NOT derive
    category from the key string — see test_e2e_effects.
    test_no_display_string_reparsing) so it mirrors what aggregate.
    evaluate_build would have recorded from each entry's own
    already-classified category.
    """
    categories = {key: _FIXTURE_CATEGORY_BY_KEY[key[0]] for key in totals_dict}
    return BuildEffects(
        sourced=[],
        totals=totals_dict,
        unresolved=[],
        others=[],
        warnings=[],
        categories=categories,
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
    assert rows[0].category == CAT_DAMAGE


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
    assert rows[0].category == CAT_DAMAGE


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
    b = _make_build_effects({("無視 不死 型怪的物理抗性", ""): 2.5})
    rows = compare_builds(a, b)

    assert len(rows) == 1
    assert rows[0].key == "無視 不死 型怪的物理抗性"
    assert rows[0].unit == ""
    assert rows[0].a is None
    assert rows[0].b == 2.5
    assert rows[0].advantage == "b"
    assert rows[0].category == CAT_RESIST


def test_compare_builds_union_multiple_keys():
    """Keys from a and b are unioned correctly."""
    a = _make_build_effects({("ATK", ""): 100.0, ("HP", ""): 500.0})
    b = _make_build_effects({("MATK", ""): 150.0, ("DEF", ""): 50.0})
    rows = compare_builds(a, b)

    assert len(rows) == 4
    keys = {row.key for row in rows}
    assert keys == {"ATK", "HP", "MATK", "DEF"}


def test_compare_builds_sort_by_category():
    """Rows are sorted by category: damage → resist → ability → secondary → other."""
    a = _make_build_effects({})
    b = BuildEffects(
        sourced=[],
        totals={("ATK", ""): 200.0, ("無視 不死 型怪的物理抗性", ""): 5.0, ("DEF", ""): 30.0, ("SP消耗", ""): 10.0},
        unresolved=[], others=[], warnings=[],
        categories={
            ("ATK", ""): CAT_DAMAGE,
            ("無視 不死 型怪的物理抗性", ""): CAT_RESIST,
            ("DEF", ""): CAT_ABILITY,
            ("SP消耗", ""): CAT_SECONDARY,
        },
    )
    rows = compare_builds(a, b)

    # Expected order: damage (ATK), resist, ability (DEF), secondary (SP消耗)
    assert rows[0].key == "ATK"
    assert rows[0].category == CAT_DAMAGE
    assert rows[1].key == "無視 不死 型怪的物理抗性"
    assert rows[1].category == CAT_RESIST
    assert rows[2].key == "DEF"
    assert rows[2].category == CAT_ABILITY
    assert rows[3].key == "SP消耗"
    assert rows[3].category == CAT_SECONDARY


def test_compare_builds_sort_by_key_within_category():
    """Within the same category, rows are sorted by key name."""
    a = _make_build_effects({})
    b = _make_build_effects({
        ("CRI", ""): 50.0,  # ability
        ("DEF", ""): 100.0,  # ability
        ("HIT", ""): 75.0,  # ability
    })
    rows = compare_builds(a, b)

    # All are ability; sorted by key: CRI, DEF, HIT (alphabetical)
    assert len(rows) == 3
    assert rows[0].key == "CRI"
    assert rows[1].key == "DEF"
    assert rows[2].key == "HIT"


def test_compare_builds_sort_mixed_categories_and_keys_five_way():
    """Sort by category first (damage->resist->ability->secondary->other), then
    by key within each category — full 5-way order (regression for the
    category-taxonomy reclassification)."""
    a = BuildEffects(sourced=[], totals={}, unresolved=[], others=[], warnings=[], categories={})
    b = BuildEffects(
        sourced=[],
        totals={
            ("SP消耗", ""): 10.0,  # secondary
            ("掉寶率", ""): 3.0,  # secondary
            ("MATK", ""): 100.0,  # damage
            ("近距離物理傷害", ""): 5.0,  # damage
            ("DEF", ""): 20.0,  # ability
            ("無視 不死 型怪的物理抗性", ""): 5.0,  # resist
            ("未判定條件", ""): 1.0,  # other (guard case — shouldn't normally exist as NUMERIC, but must still sort)
        },
        unresolved=[], others=[], warnings=[],
        categories={
            ("SP消耗", ""): CAT_SECONDARY,
            ("掉寶率", ""): CAT_SECONDARY,
            ("MATK", ""): CAT_DAMAGE,
            ("近距離物理傷害", ""): CAT_DAMAGE,
            ("DEF", ""): CAT_ABILITY,
            ("無視 不死 型怪的物理抗性", ""): CAT_RESIST,
            ("未判定條件", ""): CAT_OTHER,
        },
    )
    rows = compare_builds(a, b)

    assert len(rows) == 7
    assert [(r.key, r.category) for r in rows] == [
        ("MATK", CAT_DAMAGE),
        ("近距離物理傷害", CAT_DAMAGE),
        ("無視 不死 型怪的物理抗性", CAT_RESIST),
        ("DEF", CAT_ABILITY),
        ("SP消耗", CAT_SECONDARY),  # ASCII 'S' sorts before CJK codepoints
        ("掉寶率", CAT_SECONDARY),
        ("未判定條件", CAT_OTHER),
    ]


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


def test_compare_builds_category_read_from_categories_not_reclassified():
    """compare_builds must READ category from BuildEffects.categories, never
    recompute it from the key string. Proven by deliberately storing a
    category that would NOT be the "expected" one for this key (CAT_OTHER for
    "ATK", which would normally be CAT_DAMAGE) — if compare_builds still
    returns CAT_DAMAGE here it would mean it silently ignored our categories
    dict and reclassified the key itself, which is exactly the
    string-reparsing debt this architecture forbids.
    """
    a = BuildEffects(
        sourced=[], totals={("ATK", ""): 100.0}, unresolved=[], others=[], warnings=[],
        categories={("ATK", ""): CAT_OTHER},
    )
    b = BuildEffects(sourced=[], totals={}, unresolved=[], others=[], warnings=[], categories={})
    rows = compare_builds(a, b)

    assert len(rows) == 1
    assert rows[0].category == CAT_OTHER


def test_compare_builds_category_falls_back_to_other_side():
    """A key present only in b's totals has its category only in b.categories
    — compare_builds must fall back to b's side rather than erroring/omitting
    the category."""
    a = BuildEffects(sourced=[], totals={}, unresolved=[], others=[], warnings=[], categories={})
    b = BuildEffects(
        sourced=[], totals={("HP", ""): 500.0}, unresolved=[], others=[], warnings=[],
        categories={("HP", ""): CAT_OTHER},
    )
    rows = compare_builds(a, b)

    assert len(rows) == 1
    assert rows[0].category == CAT_OTHER


def test_compare_row_fields():
    """CompareRow dataclass has expected fields and is frozen."""
    row = CompareRow(
        key="ATK",
        unit="",
        category=CAT_DAMAGE,
        a=100.0,
        b=80.0,
        advantage="a",
    )

    assert row.key == "ATK"
    assert row.unit == ""
    assert row.category == CAT_DAMAGE
    assert row.a == 100.0
    assert row.b == 80.0
    assert row.advantage == "a"

    # Frozen means it cannot be modified
    with pytest.raises(AttributeError):
        row.a = 200.0
