from app.core import entries

def test_effect_entry_fields():
    e = entries.EffectEntry(key="爆擊傷害", value=7.0, unit="%",
                            kind=entries.KIND_NUMERIC, category=entries.CAT_PHYSICAL)
    assert e.extra is None

def test_classify_physical():
    assert entries.classify_category("近距離物理傷害") == entries.CAT_PHYSICAL

def test_classify_magical():
    assert entries.classify_category("變動詠唱時間") == entries.CAT_MAGICAL

def test_classify_magical_keyword_matk():
    # "MATK" should be classified as CAT_MAGICAL (not CAT_PHYSICAL from "ATK" substring)
    assert entries.classify_category("MATK") == entries.CAT_MAGICAL

def test_classify_magical_keyword_s_matk():
    # "S.MATK" should be classified as CAT_MAGICAL (not CAT_PHYSICAL from "ATK" substring)
    assert entries.classify_category("S.MATK") == entries.CAT_MAGICAL

def test_classify_physical_keyword_p_atk():
    # "P.ATK" should be classified as CAT_PHYSICAL (contains physical keyword)
    assert entries.classify_category("P.ATK") == entries.CAT_PHYSICAL

def test_classify_physical_keyword_c_rate():
    # "C.RATE" should be classified as CAT_PHYSICAL (contains physical keyword)
    assert entries.classify_category("C.RATE") == entries.CAT_PHYSICAL

def test_classify_physical_when_no_magical():
    # When no magical keyword is present, physical keywords are checked.
    # "物理傷害" contains "物理" (physical keyword), so it returns CAT_PHYSICAL.
    assert entries.classify_category("受到 不死 型怪的物理傷害") == entries.CAT_PHYSICAL

def test_classify_other():
    assert entries.classify_category("SP消耗") == entries.CAT_OTHER
