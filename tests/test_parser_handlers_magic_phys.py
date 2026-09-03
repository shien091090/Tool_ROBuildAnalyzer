"""Tests for handler batch 2 (魔法段+物理段, inventory #14-44,
ro_core.py:1418-1857).

Assertions are always against structured EffectEntry fields (key/value/unit/
kind/extra), never display strings — per task-7/task-8 brief 移植轉換規則.
"""

from app.core import entries, parser
from app.core.context import CalcContext
from app.core.maps import EffectMaps


def _ctx(**kw):
    """Build a minimal CalcContext with empty/zero defaults, overridable via kwargs."""
    defaults = dict(
        scalars={},
        refine_inputs={},
        grade=0,
        get_values={},
        enabled_skill_levels={},
        pure_jobs=[],
        slot_item_id_map={},
        weapon_level_map={},
        armor_level_map={},
        weapon_type_map={},
        armor_weapon_map={},
        weapon_atk_map={},
        weapon_matk_map={},
        used_skill_levels={},
    )
    defaults.update(kw)
    return CalcContext(**defaults)


def _maps(skill_map=None):
    return EffectMaps(skill_map=skill_map or {})


# ---------------------------------------------------------------------------
# #14 AddSkillMDamage / SubSkillMDamage
# ---------------------------------------------------------------------------


def test_skill_mdamage_add_and_sub():
    ctx = _ctx()
    r_add = parser.parse_effect_block("AddSkillMDamage(3,20)", ctx, None, _maps())
    e = r_add.entries[0]
    assert e.key == "火屬性 的魔法傷害"
    assert e.value == 20.0
    assert e.unit == "%"
    assert e.kind == entries.KIND_NUMERIC
    assert e.category == entries.CAT_MAGICAL
    assert e.extra == {"target_kind": "element", "target_id": 3}

    r_sub = parser.parse_effect_block("SubSkillMDamage(3,20)", _ctx(), None, _maps())
    assert r_sub.entries[0].value == -20.0


def test_skill_mdamage_unresolvable_becomes_unrecognized():
    ctx = _ctx()
    r = parser.parse_effect_block("AddSkillMDamage(3,total_STR)", ctx, None, _maps())
    assert len(r.entries) == 1
    e = r.entries[0]
    assert e.kind == entries.KIND_UNRECOGNIZED
    assert e.extra["raw_line"] == "AddSkillMDamage(3,total_STR)"


# ---------------------------------------------------------------------------
# #15 AddMDamage_Size / SubMDamage_Size (size_map miss fallback "尺寸{id}")
# ---------------------------------------------------------------------------


def test_mdamage_size():
    ctx = _ctx()
    r = parser.parse_effect_block("AddMDamage_Size(1,1,15)", ctx, None, _maps())
    e = r.entries[0]
    assert e.key == "對 中型 敵人的魔法傷害"
    assert e.value == 15.0
    assert e.extra == {"target_kind": "size", "target_id": 1}


def test_mdamage_size_map_miss_fallback():
    ctx = _ctx()
    r = parser.parse_effect_block("AddMDamage_Size(1,99,15)", ctx, None, _maps())
    assert r.entries[0].key == "對 尺寸99 敵人的魔法傷害"


# ---------------------------------------------------------------------------
# #16 AddMdamage_Race / SubMdamage_Race — full-string check #1 (race_map)
# ---------------------------------------------------------------------------


def test_mdamage_race_full_string():
    ctx = _ctx()
    r = parser.parse_effect_block("AddMdamage_Race(1,10)", ctx, None, _maps())
    e = r.entries[0]
    assert e.key == "對 不死 型怪的魔法傷害"
    assert e.value == 10.0
    assert e.unit == "%"
    assert e.extra == {"target_kind": "race", "target_id": 1}


# ---------------------------------------------------------------------------
# #17 AddMDamage_Property / SubMDamage_Property
# ---------------------------------------------------------------------------


def test_mdamage_property():
    ctx = _ctx()
    r = parser.parse_effect_block("SubMDamage_Property(1,6,12)", ctx, None, _maps())
    e = r.entries[0]
    assert e.key == "對 聖屬性 對象的魔法傷害"
    assert e.value == -12.0
    assert e.extra == {"target_kind": "element", "target_id": 6}


# ---------------------------------------------------------------------------
# #18 AddMdamage_Class / SubMdamage_Class
# ---------------------------------------------------------------------------


def test_mdamage_class():
    ctx = _ctx()
    r = parser.parse_effect_block("AddMdamage_Class(1,8)", ctx, None, _maps())
    e = r.entries[0]
    assert e.key == "對 首領 階級的魔法傷害"
    assert e.value == 8.0
    assert e.extra == {"target_kind": "class", "target_id": 1}


# ---------------------------------------------------------------------------
# #19 SetIgnoreMdefClass (no sign, no Add/Sub prefix)
# ---------------------------------------------------------------------------


def test_ignore_mdef_class_no_sign():
    ctx = _ctx()
    r = parser.parse_effect_block("SetIgnoreMdefClass(1,50)", ctx, None, _maps())
    e = r.entries[0]
    assert e.key == "無視 首領 階級的魔法防禦"
    assert e.value == 50.0
    assert e.unit == "%"
    assert e.kind == entries.KIND_NUMERIC
    assert e.extra == {"target_kind": "class", "target_id": 1}


# ---------------------------------------------------------------------------
# #20 SetIgnoreMdefRace (no sign)
# ---------------------------------------------------------------------------


def test_ignore_mdef_race_no_sign():
    ctx = _ctx()
    r = parser.parse_effect_block("SetIgnoreMdefRace(1,30)", ctx, None, _maps())
    e = r.entries[0]
    assert e.key == "無視 不死 型怪的魔法防禦"
    assert e.value == 30.0
    assert e.extra == {"target_kind": "race", "target_id": 1}


# ---------------------------------------------------------------------------
# #21 AddIgnore_MRES_RacePercent / SubIgnore_MRES_RacePercent
# ---------------------------------------------------------------------------


def test_ignore_mres_race_percent_add_and_sub():
    r_add = parser.parse_effect_block("AddIgnore_MRES_RacePercent(1,5)", _ctx(), None, _maps())
    e_add = r_add.entries[0]
    assert e_add.key == "無視 不死 型怪的魔法抗性"
    assert e_add.value == 5.0

    r_sub = parser.parse_effect_block("SubIgnore_MRES_RacePercent(1,5)", _ctx(), None, _maps())
    assert r_sub.entries[0].value == -5.0


# ---------------------------------------------------------------------------
# #22/#23 MonsterMAtkPercent / SubMonsterMAtkPercent
# ---------------------------------------------------------------------------


def test_monster_matk_percent_add_and_sub():
    r_add = parser.parse_effect_block("MonsterMAtkPercent(7)", _ctx(), None, _maps())
    e_add = r_add.entries[0]
    assert e_add.key == "特定魔物魔法增傷"
    assert e_add.value == 7.0
    assert e_add.category == entries.CAT_MAGICAL

    r_sub = parser.parse_effect_block("SubMonsterMAtkPercent(7)", _ctx(), None, _maps())
    e_sub = r_sub.entries[0]
    assert e_sub.key == "特定魔物魔法增傷"
    assert e_sub.value == -7.0


# ---------------------------------------------------------------------------
# #24 WeaponMasteryATK (no % unit)
# ---------------------------------------------------------------------------


def test_weapon_mastery_atk_no_percent_unit():
    r = parser.parse_effect_block("WeaponMasteryATK(50)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "修煉ATK"
    assert e.value == 50.0
    assert e.unit == ""
    assert e.category == entries.CAT_PHYSICAL


# ---------------------------------------------------------------------------
# #25 Kamui_SpecialATK (no % unit)
# ---------------------------------------------------------------------------


def test_kamui_special_atk_no_percent_unit():
    r = parser.parse_effect_block("Kamui_SpecialATK(30)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "神威ATK"
    assert e.value == 30.0
    assert e.unit == ""


# ---------------------------------------------------------------------------
# #26 AddGuideAttack — NUMERIC, category via "誘導攻擊" physical keyword
# ---------------------------------------------------------------------------


def test_guide_attack_numeric_physical():
    r = parser.parse_effect_block("AddGuideAttack(15)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "誘導攻擊機率"
    assert e.value == 15.0
    assert e.unit == "%"
    assert e.kind == entries.KIND_NUMERIC
    assert e.category == entries.CAT_PHYSICAL


# ---------------------------------------------------------------------------
# #27 AddDamage_HIT / SubDamage_HIT
# ---------------------------------------------------------------------------


def test_damage_hit_add_and_sub():
    r_add = parser.parse_effect_block("AddDamage_HIT(1,10)", _ctx(), None, _maps())
    assert r_add.entries[0].key == "物理命中傷害"
    assert r_add.entries[0].value == 10.0

    r_sub = parser.parse_effect_block("SubDamage_HIT(1,10)", _ctx(), None, _maps())
    assert r_sub.entries[0].value == -10.0


# ---------------------------------------------------------------------------
# #28 AddMeleeAttackDamage / SubMeleeAttackDamage
# ---------------------------------------------------------------------------


def test_melee_attack_damage():
    r = parser.parse_effect_block("AddMeleeAttackDamage(1,8)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "近距離物理傷害"
    assert e.value == 8.0
    assert e.category == entries.CAT_PHYSICAL


# ---------------------------------------------------------------------------
# #29 AddRangeAttackDamage / SubRangeAttackDamage
# ---------------------------------------------------------------------------


def test_range_attack_damage():
    r = parser.parse_effect_block("SubRangeAttackDamage(1,8)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "遠距離物理傷害"
    assert e.value == -8.0


# ---------------------------------------------------------------------------
# #30 AddBowAttackDamage (always positive, no Sub variant)
# ---------------------------------------------------------------------------


def test_bow_attack_damage():
    r = parser.parse_effect_block("AddBowAttackDamage(1,12)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "弓攻擊力"
    assert e.value == 12.0
    assert e.unit == "%"


# ---------------------------------------------------------------------------
# #31 AddDamage_CRI / SubDamage_CRI
# ---------------------------------------------------------------------------


def test_damage_cri():
    r = parser.parse_effect_block("AddDamage_CRI(1,20)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "爆擊傷害"
    assert e.value == 20.0


# ---------------------------------------------------------------------------
# #32 AddDamage_Size / SubDamage_Size — size_map miss fallback "體型{id}",
# DIFFERENT from #15's "尺寸{id}" fallback (original inconsistency, preserved).
# ---------------------------------------------------------------------------


def test_damage_size_physical():
    r = parser.parse_effect_block("AddDamage_Size(1,2,25)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "對 大型 敵人的物理傷害"
    assert e.value == 25.0
    assert e.extra == {"target_kind": "size", "target_id": 2}


def test_damage_size_physical_map_miss_fallback_differs_from_mdamage_size():
    r = parser.parse_effect_block("AddDamage_Size(1,99,25)", _ctx(), None, _maps())
    assert r.entries[0].key == "對 體型99 敵人的物理傷害"


# ---------------------------------------------------------------------------
# #33 RaceAddDamage / RaceSubDamage — full-string check #2 (race_map, matches
# batch-spec example verbatim: "對 不死 型怪的物理傷害")
# ---------------------------------------------------------------------------


def test_race_damage_full_string():
    r = parser.parse_effect_block("RaceAddDamage(1,20)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "對 不死 型怪的物理傷害"
    assert e.value == 20.0
    assert e.unit == "%"
    assert e.kind == entries.KIND_NUMERIC
    assert e.category == entries.CAT_PHYSICAL
    assert e.extra == {"target_kind": "race", "target_id": 1}


def test_race_sub_damage():
    r = parser.parse_effect_block("RaceSubDamage(1,20)", _ctx(), None, _maps())
    assert r.entries[0].value == -20.0


# ---------------------------------------------------------------------------
# #34 AddDamage_Property / SubDamage_Property — full-string check #3 (element_map)
# ---------------------------------------------------------------------------


def test_damage_property_physical_full_string():
    r = parser.parse_effect_block("AddDamage_Property(1,3,15)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "對 火屬性 對象的物理傷害"
    assert e.value == 15.0
    assert e.unit == "%"
    assert e.extra == {"target_kind": "element", "target_id": 3}


# ---------------------------------------------------------------------------
# #35 ClassAddDamage / ClassSubDamage
# ---------------------------------------------------------------------------


def test_class_damage_physical():
    r = parser.parse_effect_block("ClassAddDamage(1,1,10)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "對 首領 階級的物理傷害"
    assert e.value == 10.0
    assert e.extra == {"target_kind": "class", "target_id": 1}


def test_class_sub_damage():
    r = parser.parse_effect_block("ClassSubDamage(1,1,10)", _ctx(), None, _maps())
    assert r.entries[0].value == -10.0


# ---------------------------------------------------------------------------
# #36 SetIgnoreDEFClass — DESCRIPTIVE, no % value
# ---------------------------------------------------------------------------


def test_ignore_def_class_descriptive_no_value():
    r = parser.parse_effect_block("SetIgnoreDEFClass(1)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "無視 首領 階級的物理防禦"
    assert e.value is None
    assert e.unit == ""
    assert e.kind == entries.KIND_DESCRIPTIVE
    assert e.category == entries.CAT_PHYSICAL
    assert e.extra == {"target_kind": "class", "target_id": 1}


# ---------------------------------------------------------------------------
# #37 SetIgnoreDefClass_Percent (literal digits, no safe_eval, no sign)
# ---------------------------------------------------------------------------


def test_ignore_def_class_percent():
    r = parser.parse_effect_block("SetIgnoreDefClass_Percent(1,40)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "無視 首領 階級的物理防禦"
    assert e.value == 40.0
    assert e.unit == "%"
    assert e.kind == entries.KIND_NUMERIC
    assert e.extra == {"target_kind": "class", "target_id": 1}


# ---------------------------------------------------------------------------
# #38 SetIgnoreDefRace_Percent (no sign)
# ---------------------------------------------------------------------------


def test_ignore_def_race_percent():
    r = parser.parse_effect_block("SetIgnoreDefRace_Percent(1,35)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "無視 不死 型怪的物理防禦"
    assert e.value == 35.0
    assert e.extra == {"target_kind": "race", "target_id": 1}


# ---------------------------------------------------------------------------
# #39 AddIgnore_RES_RacePercent / SubIgnore_RES_RacePercent
# ---------------------------------------------------------------------------


def test_ignore_res_race_percent_add_and_sub():
    r_add = parser.parse_effect_block("AddIgnore_RES_RacePercent(1,5)", _ctx(), None, _maps())
    assert r_add.entries[0].key == "無視 不死 型怪的物理抗性"
    assert r_add.entries[0].value == 5.0

    r_sub = parser.parse_effect_block("SubIgnore_RES_RacePercent(1,5)", _ctx(), None, _maps())
    assert r_sub.entries[0].value == -5.0


# ---------------------------------------------------------------------------
# #40/#41 MonsterAtkPercent / SubMonsterAtkPercent
# ---------------------------------------------------------------------------


def test_monster_atk_percent_add_and_sub():
    r_add = parser.parse_effect_block("MonsterAtkPercent(9)", _ctx(), None, _maps())
    e_add = r_add.entries[0]
    assert e_add.key == "特定魔物物理增傷"
    assert e_add.value == 9.0
    assert e_add.category == entries.CAT_PHYSICAL

    r_sub = parser.parse_effect_block("SubMonsterAtkPercent(9)", _ctx(), None, _maps())
    e_sub = r_sub.entries[0]
    assert e_sub.key == "特定魔物物理增傷"
    assert e_sub.value == -9.0


# ---------------------------------------------------------------------------
# #42 SetIgnoreDEFRace — constant, NUMERIC value=100 unit="%"
# ---------------------------------------------------------------------------


def test_ignore_def_race_constant_numeric_100_percent():
    r = parser.parse_effect_block("SetIgnoreDEFRace(1)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "無視 不死 型怪的物理防禦"
    assert e.value == 100.0
    assert e.unit == "%"
    assert e.kind == entries.KIND_NUMERIC
    assert e.extra == {"target_kind": "race", "target_id": 1}


# ---------------------------------------------------------------------------
# #43 PerfectDamage(1) — DESCRIPTIVE constant, exact literal source string
# ---------------------------------------------------------------------------


def test_perfect_damage_descriptive_constant():
    r = parser.parse_effect_block("PerfectDamage(1)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "武器體型修正 100%"
    assert e.value is None
    assert e.unit == ""
    assert e.kind == entries.KIND_DESCRIPTIVE
    assert e.category == entries.CAT_PHYSICAL


# ---------------------------------------------------------------------------
# #44 SetInvestigate() — corrected regex (fixes original's empty-group prefix
# match bug) + two emitted entries
# ---------------------------------------------------------------------------


def test_investigate_exact_call_emits_two_entries():
    r = parser.parse_effect_block("SetInvestigate()", _ctx(), None, _maps())
    assert len(r.entries) == 2

    e1 = r.entries[0]
    assert e1.key == "武器浸透勁效果"
    assert e1.value is None
    assert e1.kind == entries.KIND_DESCRIPTIVE
    assert e1.category == entries.CAT_PHYSICAL

    e2 = r.entries[1]
    assert e2.key == "無視 全種族 型怪的物理防禦"
    assert e2.value == 100.0
    assert e2.unit == "%"
    assert e2.kind == entries.KIND_NUMERIC
    assert e2.category == entries.CAT_PHYSICAL


def test_investigate_regex_fix_rejects_prefix_only_match():
    # ro_core.py:1852's original regex r"SetInvestigate()" has an EMPTY
    # capture group (not a literal parenthesis pair), so it degrades to a
    # bare prefix match that would incorrectly match "SetInvestigateXYZ()"
    # too. The corrected regex must NOT match this — it should fall through
    # to the generic UNRECOGNIZED fallback instead of firing handler #44.
    r = parser.parse_effect_block("SetInvestigateXYZ()", _ctx(), None, _maps())
    assert len(r.entries) == 1
    e = r.entries[0]
    assert e.kind == entries.KIND_UNRECOGNIZED
    assert e.extra["raw_line"] == "SetInvestigateXYZ()"
