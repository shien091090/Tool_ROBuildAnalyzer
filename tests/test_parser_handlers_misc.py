"""Tests for handler batch 3 (補完解析段, inventory #45-68,
ro_core.py:1884-2350).

Assertions are always against structured EffectEntry fields (key/value/unit/
kind/extra), never display strings — per task-7/task-8/task-9 brief
移植轉換規則.
"""

from app.core import entries, parser
from app.core.context import CalcContext
from app.core.maps import EffectMaps, PLAIN_EFFECT_MAP


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
# #45 AddHealValue / SubHealValue
# ---------------------------------------------------------------------------


def test_heal_value_add_and_sub():
    r_add = parser.parse_effect_block("AddHealValue(20)", _ctx(), None, _maps())
    e_add = r_add.entries[0]
    assert e_add.key == "治癒量"
    assert e_add.value == 20.0
    assert e_add.unit == "%"
    assert e_add.kind == entries.KIND_NUMERIC

    r_sub = parser.parse_effect_block("SubHealValue(20)", _ctx(), None, _maps())
    assert r_sub.entries[0].value == -20.0


def test_heal_value_unresolvable_becomes_unrecognized():
    r = parser.parse_effect_block("AddHealValue(total_STR)", _ctx(), None, _maps())
    assert len(r.entries) == 1
    e = r.entries[0]
    assert e.kind == entries.KIND_UNRECOGNIZED
    assert e.extra["raw_line"] == "AddHealValue(total_STR)"


# ---------------------------------------------------------------------------
# #46 AddHealModifyPercent / SubHealModifyPercent
# ---------------------------------------------------------------------------


def test_heal_modify_percent():
    r = parser.parse_effect_block("SubHealModifyPercent(15)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "被治癒量"
    assert e.value == -15.0
    assert e.unit == "%"


# ---------------------------------------------------------------------------
# #47a/b Add/Sub(HP|SP)drain — single-arg (one entry) vs two-arg (TWO entries)
# ---------------------------------------------------------------------------


def test_drain_single_arg_form():
    r = parser.parse_effect_block("AddHPdrain(50)", _ctx(), None, _maps())
    assert len(r.entries) == 1
    e = r.entries[0]
    assert e.key == "HP吸收"
    assert e.value == 50.0
    assert e.unit == "%"
    assert e.kind == entries.KIND_NUMERIC


def test_drain_two_arg_form_produces_two_entries():
    r = parser.parse_effect_block("AddHPdrain(50,10)", _ctx(), None, _maps())
    assert len(r.entries) == 2
    e_rate, e_amount = r.entries
    assert e_rate.key == "HP吸收機率"
    assert e_rate.value == 50.0
    assert e_amount.key == "HP吸收量"
    assert e_amount.value == 10.0
    assert e_rate.unit == e_amount.unit == "%"


def test_drain_sp_pool_sub_direction():
    r = parser.parse_effect_block("SubSPdrain(50,10)", _ctx(), None, _maps())
    assert len(r.entries) == 2
    e_rate, e_amount = r.entries
    assert e_rate.key == "SP吸收機率"
    assert e_rate.value == -50.0
    assert e_amount.key == "SP吸收量"
    assert e_amount.value == -10.0


def test_drain_rate_unresolvable_becomes_unrecognized():
    r = parser.parse_effect_block("AddHPdrain(total_STR)", _ctx(), None, _maps())
    assert len(r.entries) == 1
    assert r.entries[0].kind == entries.KIND_UNRECOGNIZED


def test_drain_amount_present_but_unresolvable_becomes_unrecognized():
    # The ambiguity here is this port's own (Task-5 safe_eval-returns-None
    # change), not the original's — see the handler comment for why; this
    # port distinguishes "no 2nd arg" from "2nd arg failed to eval" via
    # len(args) instead of relying on eval_lua_arg's None default.
    r = parser.parse_effect_block("AddHPdrain(50,total_STR)", _ctx(), None, _maps())
    assert len(r.entries) == 1
    assert r.entries[0].kind == entries.KIND_UNRECOGNIZED


# ---------------------------------------------------------------------------
# #48 AddSPconsumption / SubSPconsumption
# ---------------------------------------------------------------------------


def test_sp_consumption():
    r = parser.parse_effect_block("AddSPconsumption(10)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "SP消耗"
    assert e.value == 10.0
    assert e.unit == "%"
    assert e.extra is None


# ---------------------------------------------------------------------------
# #49 add/subspconsumption(value, skill_id) — LOWERCASE function name; must
# not collide with #48's Add/SubSPconsumption (uppercase), and vice versa.
# ---------------------------------------------------------------------------


def test_skill_sp_consumption_percent_lowercase():
    r = parser.parse_effect_block("addspconsumption(10,152)", _ctx(), None, _maps({152: "後跳"}))
    e = r.entries[0]
    assert e.key == "技能【後跳】SP消耗"
    assert e.value == 10.0
    assert e.unit == "%"
    assert e.extra == {"target_kind": "skill", "target_id": 152}

    r_sub = parser.parse_effect_block("subspconsumption(10,152)", _ctx(), None, _maps({152: "後跳"}))
    assert r_sub.entries[0].value == -10.0


def test_skill_sp_consumption_lowercase_does_not_collide_with_uppercase_handler():
    # AddSPconsumption(10) (uppercase #48) must produce the generic "SP消耗"
    # key, never the skill-specific #49 key — and addspconsumption(...)
    # (lowercase #49) must never be caught by #48.
    r_upper = parser.parse_effect_block("AddSPconsumption(10)", _ctx(), None, _maps())
    assert r_upper.entries[0].key == "SP消耗"
    assert r_upper.entries[0].extra is None

    r_lower = parser.parse_effect_block("addspconsumption(10,152)", _ctx(), None, _maps({152: "後跳"}))
    assert r_lower.entries[0].key == "技能【後跳】SP消耗"


def test_skill_sp_consumption_skill_map_miss_fallback():
    r = parser.parse_effect_block("addspconsumption(10,9999)", _ctx(), None, _maps())
    assert r.entries[0].key == "技能【技能ID 9999】SP消耗"


# ---------------------------------------------------------------------------
# #50 AddSkillSP / SubSkillSP(skill_id, value) — NO % unit (unlike #49)
# ---------------------------------------------------------------------------


def test_skill_sp_no_percent_unit():
    r = parser.parse_effect_block("AddSkillSP(152,10)", _ctx(), None, _maps({152: "後跳"}))
    e = r.entries[0]
    assert e.key == "技能【後跳】SP消耗"
    assert e.value == 10.0
    assert e.unit == ""
    assert e.extra == {"target_kind": "skill", "target_id": 152}


# ---------------------------------------------------------------------------
# #51 AddMeleeAttackDamage(0,...) / #52 AddRangeAttackDamage(0,...) —
# 受到近/遠距離物理傷害 (distinct from #28/#29's ...(1,...) 裝備段 handlers)
# ---------------------------------------------------------------------------


def test_melee_attack_damage_received():
    r = parser.parse_effect_block("SubMeleeAttackDamage(0,10)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "受到近距離物理傷害"
    assert e.value == -10.0
    assert e.unit == "%"


def test_range_attack_damage_received():
    r = parser.parse_effect_block("AddRangeAttackDamage(0,10)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "受到遠距離物理傷害"
    assert e.value == 10.0


# ---------------------------------------------------------------------------
# #53 AddAttrTolerace / SubAttrTolerace(element, value)
# #54 add/subattrtolerace — LOWERCASE synonym; must not collide with #53
# ---------------------------------------------------------------------------


def test_attr_tolerace():
    r = parser.parse_effect_block("AddAttrTolerace(1,10)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "對 水屬性 攻擊抗性"
    assert e.value == 10.0
    assert e.unit == "%"
    assert e.extra == {"target_kind": "element", "target_id": 1}


def test_attr_tolerace_lowercase_synonym_matches_and_no_uppercase_collision():
    r_lower = parser.parse_effect_block("subattrtolerace(1,10)", _ctx(), None, _maps())
    e_lower = r_lower.entries[0]
    assert e_lower.key == "對 水屬性 攻擊抗性"
    assert e_lower.value == -10.0

    # The uppercase handler must still fire independently for its own casing.
    r_upper = parser.parse_effect_block("AddAttrTolerace(1,10)", _ctx(), None, _maps())
    assert r_upper.entries[0].value == 10.0


# ---------------------------------------------------------------------------
# #55 AddDamage_Size(0,...) 體型 fallback / #56 AddMDamage_Size(0,...) 尺寸 fallback
# (the original itself is inconsistent between the two fallback prefixes —
# ported verbatim, not "fixed" to be consistent).
# ---------------------------------------------------------------------------


def test_damage_size_received_physical():
    r = parser.parse_effect_block("AddDamage_Size(0,1,10)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "受到 中型 敵人的物理傷害"
    assert e.value == 10.0
    assert e.extra == {"target_kind": "size", "target_id": 1}


def test_damage_size_received_physical_map_miss_fallback():
    r = parser.parse_effect_block("AddDamage_Size(0,99,10)", _ctx(), None, _maps())
    assert r.entries[0].key == "受到 體型99 敵人的物理傷害"


def test_mdamage_size_received_magical_map_miss_fallback():
    r = parser.parse_effect_block("AddMDamage_Size(0,99,10)", _ctx(), None, _maps())
    assert r.entries[0].key == "受到 尺寸99 敵人的魔法傷害"


# ---------------------------------------------------------------------------
# #57 AddRaceTolerace / SubRaceTolerace — MANDATORY sign-inversion quirk test.
# Tolerace is a resistance: Add(增加耐性) => damage taken goes DOWN ("-");
# Sub(減少耐性) => damage taken goes UP ("+"). Opposite of every other
# Add=+/Sub=- handler in this file (ro_core.py:2059-2060).
# ---------------------------------------------------------------------------


def test_race_tolerace_add_direction_sign_is_inverted_to_negative():
    r = parser.parse_effect_block("AddRaceTolerace(1,10)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "受到 不死 型怪的傷害"
    assert e.value == -10.0  # Add => NEGATIVE, matching the original's inverted sign
    assert e.unit == "%"
    assert e.extra == {"target_kind": "race", "target_id": 1}


def test_race_tolerace_sub_direction_sign_is_positive():
    r = parser.parse_effect_block("SubRaceTolerace(1,10)", _ctx(), None, _maps())
    assert r.entries[0].value == 10.0  # Sub => POSITIVE


def test_race_tolerace_unresolvable_becomes_unrecognized():
    r = parser.parse_effect_block("AddRaceTolerace(1,total_STR)", _ctx(), None, _maps())
    assert len(r.entries) == 1
    assert r.entries[0].kind == entries.KIND_UNRECOGNIZED


# ---------------------------------------------------------------------------
# #58 AddDamage_Property(0,...) / #59 AddMDamage_Property(0,...) — 受到{屬性}對象的...傷害
# ---------------------------------------------------------------------------


def test_damage_property_received_physical():
    r = parser.parse_effect_block("AddDamage_Property(0,6,10)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "受到 聖屬性 對象的物理傷害"
    assert e.value == 10.0
    assert e.extra == {"target_kind": "element", "target_id": 6}


def test_mdamage_property_received_magical():
    r = parser.parse_effect_block("SubMDamage_Property(0,6,10)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "受到 聖屬性 對象的魔法傷害"
    assert e.value == -10.0


# ---------------------------------------------------------------------------
# #60 ClassAddDamage / ClassSubDamage(class_id, 0, value) — 受到{階級}階級的物理傷害
# ---------------------------------------------------------------------------


def test_class_damage_received():
    r = parser.parse_effect_block("ClassAddDamage(1,0,10)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "受到 首領 階級的物理傷害"
    assert e.value == 10.0
    assert e.extra == {"target_kind": "class", "target_id": 1}


# ---------------------------------------------------------------------------
# #61 RaceSubDamageSelf / RaceAddDamageSelf(race, value) — 受到{種族}型怪的傷害.
# Note the (Sub|Add) alternation order in the source regex, ported as-is.
# ---------------------------------------------------------------------------


def test_race_damage_self_sub_and_add():
    r_sub = parser.parse_effect_block("RaceSubDamageSelf(1,10)", _ctx(), None, _maps())
    e_sub = r_sub.entries[0]
    assert e_sub.key == "受到 不死 型怪的傷害"
    assert e_sub.value == -10.0
    assert e_sub.extra == {"target_kind": "race", "target_id": 1}

    r_add = parser.parse_effect_block("RaceAddDamageSelf(1,10)", _ctx(), None, _maps())
    assert r_add.entries[0].value == 10.0


# ---------------------------------------------------------------------------
# #62 AddCRIPercent_Race / SubCRIPercent_Race(race, value) — 對{種族}型怪的CRI
# ---------------------------------------------------------------------------


def test_cri_percent_race():
    r = parser.parse_effect_block("AddCRIPercent_Race(1,10)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "對 不死 型怪的CRI"
    assert e.value == 10.0
    assert e.unit == "%"
    assert e.extra == {"target_kind": "race", "target_id": 1}


# ---------------------------------------------------------------------------
# #63/#64/#65 Reflect handlers (no target metadata, always own key)
# ---------------------------------------------------------------------------


def test_melee_attack_reflect():
    r = parser.parse_effect_block("AddMeleeAttackReflect(10)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "近距離物理反射"
    assert e.value == 10.0
    assert e.unit == "%"


def test_reflect_magic():
    r = parser.parse_effect_block("SubReflectMagic(10)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "魔法反射"
    assert e.value == -10.0


def test_reflect_tolerace():
    r = parser.parse_effect_block("AddReflectTolerace(10)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "反射傷害耐性"
    assert e.value == 10.0


# ---------------------------------------------------------------------------
# #66 AddDamage_SKID(0,...) 受到技能傷害 — distinct from Task 7's #8
# AddDamage_SKID(1,...) 技能傷害(裝備段); both anchor on the literal first
# argument, so neither handler ever steals the other's line.
# ---------------------------------------------------------------------------


def test_damage_skid_received_does_not_collide_with_equip_segment_handler():
    r_received = parser.parse_effect_block("AddDamage_SKID(0,152,10)", _ctx(), None, _maps({152: "後跳"}))
    e_received = r_received.entries[0]
    assert e_received.key == "受到技能【後跳】傷害"
    assert e_received.value == 10.0
    assert e_received.extra == {"target_kind": "skill", "target_id": 152}

    r_equip = parser.parse_effect_block("AddDamage_SKID(1,152,10)", _ctx(), None, _maps({152: "後跳"}))
    e_equip = r_equip.entries[0]
    assert e_equip.key == "技能【後跳】傷害(裝備段)"
    assert e_equip.value == 10.0


# ---------------------------------------------------------------------------
# #67 plain_effect_map — MANDATORY full 8-key loop; DESCRIPTIVE, key is the
# mapped 固定敘述句, not the raw function name.
# ---------------------------------------------------------------------------


def test_plain_effect_map_all_eight_keys():
    assert len(PLAIN_EFFECT_MAP) == 8
    for func_name, expected_key in PLAIN_EFFECT_MAP.items():
        r = parser.parse_effect_block(f"{func_name}()", _ctx(), None, _maps())
        assert len(r.entries) == 1
        e = r.entries[0]
        assert e.key == expected_key
        assert e.value is None
        assert e.unit == ""
        assert e.kind == entries.KIND_DESCRIPTIVE


def test_plain_effect_map_without_parens_also_matches():
    # ro_core.py:2317's regex tolerates an optional empty/absent () call.
    r = parser.parse_effect_block("NoDispell", _ctx(), None, _maps())
    assert r.entries[0].key == "詠唱不中斷"


# ---------------------------------------------------------------------------
# #68 Condition(status_id, duration, chance) — MANDATORY PROC entry +
# status_map miss fallback.
# ---------------------------------------------------------------------------


def test_condition_proc_entry_known_status():
    r = parser.parse_effect_block("Condition(13,10,50)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "賦予狀態：霸體"
    assert e.value is None
    assert e.kind == entries.KIND_PROC
    assert e.extra == {"status": "霸體", "duration": 10.0, "chance": 50.0}


def test_condition_status_map_miss_fallback():
    r = parser.parse_effect_block("Condition(999,10,50)", _ctx(), None, _maps())
    e = r.entries[0]
    assert e.key == "賦予狀態：狀態ID 999"
    assert e.extra["status"] == "狀態ID 999"


def test_condition_zero_args_does_not_match_falls_to_unrecognized():
    # ro_core.py:2329's `if condition_effect and condition_met` is a truthy
    # check — an empty args list (Condition() with no args) is falsy, so the
    # original never treats this as a match either; ported as-is.
    r = parser.parse_effect_block("Condition()", _ctx(), None, _maps())
    assert r.entries[0].kind == entries.KIND_UNRECOGNIZED


# ---------------------------------------------------------------------------
# Dead code (inventory doc 死碼表, not ported) — MANDATORY: a one-line dead
# function call falls through every handler to the fallback UNRECOGNIZED
# entry instead of silently vanishing or raising.
# ---------------------------------------------------------------------------


def test_dead_code_function_call_becomes_unrecognized():
    r = parser.parse_effect_block("ResetIgnoreDEFClass(1)", _ctx(), None, _maps())
    assert len(r.entries) == 1
    e = r.entries[0]
    assert e.kind == entries.KIND_UNRECOGNIZED
    assert e.extra["raw_line"] == "ResetIgnoreDEFClass(1)"
