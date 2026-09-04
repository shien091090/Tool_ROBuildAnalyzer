from app.core import entries

def test_effect_entry_fields():
    e = entries.EffectEntry(key="爆擊傷害", value=7.0, unit="%",
                            kind=entries.KIND_NUMERIC, category=entries.CAT_DAMAGE)
    assert e.extra is None

def test_category_constants_are_the_four_group_taxonomy():
    # category-taxonomy: keyword-based classify_category was replaced by an
    # explicit 4-group taxonomy assigned at handler level (parser.py) —
    # this test just pins the constant values/names so a future rename is
    # caught, since nothing else asserts on the raw string values directly.
    assert entries.CAT_DAMAGE == "damage"
    assert entries.CAT_RESIST == "resist"
    assert entries.CAT_ABILITY == "ability"
    assert entries.CAT_SECONDARY == "secondary"
    assert entries.CAT_OTHER == "other"

def test_classify_category_removed():
    assert not hasattr(entries, "classify_category")
