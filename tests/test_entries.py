from app.core import entries

def test_effect_entry_fields():
    e = entries.EffectEntry(key="爆擊傷害", value=7.0, unit="%",
                            kind=entries.KIND_NUMERIC, category=entries.CAT_PHYSICAL)
    assert e.extra is None

def test_classify_physical():
    assert entries.classify_category("近距離物理傷害") == entries.CAT_PHYSICAL

def test_classify_magical():
    assert entries.classify_category("變動詠唱時間") == entries.CAT_MAGICAL

def test_classify_physical_wins_over_magical():
    # 原版先檢查physical: "物理魔法混合鍵"歸physical
    assert entries.classify_category("受到 不死 型怪的物理傷害") == entries.CAT_PHYSICAL

def test_classify_other():
    assert entries.classify_category("SP消耗") == entries.CAT_OTHER
