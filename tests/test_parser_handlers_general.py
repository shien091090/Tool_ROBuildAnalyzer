"""Tests for handler batch 1 (通用段, inventory #1-13, ro_core.py:1144-1410).

Assertions are always against structured EffectEntry fields (key/value/unit/
kind/extra), never display strings — per task-7 brief.
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
# #1 EnableSkill
# ---------------------------------------------------------------------------


def test_enable_skill_descriptive_entry_and_writes_ctx():
    ctx = _ctx()
    r = parser.parse_effect_block("EnableSkill(63,5)", ctx, None, _maps({63: "波動拳"}))
    assert len(r.entries) == 1
    e = r.entries[0]
    assert e.key == "可使用【波動拳】Lv.5"
    assert e.value is None
    assert e.kind == entries.KIND_DESCRIPTIVE
    # category-taxonomy: handler #1 EnableSkill -> CAT_SECONDARY (binding
    # handler-level mapping; not derived from the skill-name key string).
    assert e.category == entries.CAT_SECONDARY
    assert e.extra == {"target_kind": "skill", "target_id": 63, "level": 5}
    assert ctx.enabled_skill_levels[63] == 5


def test_enable_skill_feeds_later_getskilllevel_condition():
    # EnableSkill writes ctx.enabled_skill_levels; a later if-block's
    # GetSkillLevel(63) condition should then be determinable (not
    # unresolved) within the SAME block.
    ctx = _ctx()
    block = "EnableSkill(63,5)\nif GetSkillLevel(63) >= 5 then\nAddExtParam(1,52,3)\nend"
    r = parser.parse_effect_block(block, ctx, None, _maps({63: "波動拳"}))
    assert not any(e.kind == entries.KIND_UNRESOLVED for e in r.entries)
    numeric = [e for e in r.entries if e.key == "CRI"]
    assert len(numeric) == 1
    assert numeric[0].value == 0.0  # 3 // 10 == 0


def test_enable_skill_skill_map_miss_fallback():
    ctx = _ctx()
    r = parser.parse_effect_block("EnableSkill(9999,1)", ctx, None, _maps())
    assert r.entries[0].key == "可使用【技能ID 9999】Lv.1"


# ---------------------------------------------------------------------------
# #2 UseSkill
# ---------------------------------------------------------------------------


def test_use_skill_descriptive_entry_and_writes_ctx():
    ctx = _ctx()
    r = parser.parse_effect_block("UseSkill(63)", ctx, None, _maps({63: "波動拳"}))
    assert len(r.entries) == 1
    e = r.entries[0]
    assert e.key == "使用【波動拳】"
    assert e.value is None
    assert e.kind == entries.KIND_DESCRIPTIVE
    # category-taxonomy: handler #2 UseSkill -> CAT_SECONDARY (same as #1);
    # extra has no "level" key (UseSkill takes no skill-level argument).
    assert e.category == entries.CAT_SECONDARY
    assert e.extra == {"target_kind": "skill", "target_id": 63}
    assert ctx.used_skill_levels[63] is True


# ---------------------------------------------------------------------------
# #3a-c AddExtParam / SubExtParam
# ---------------------------------------------------------------------------


def test_ext_param_cri_divided_by_10():
    ctx = _ctx()
    r = parser.parse_effect_block("AddExtParam(1,52,37)", ctx, None, _maps())
    e = r.entries[0]
    assert e.key == "CRI"
    assert e.value == 3.0  # 37 // 10
    assert e.unit == ""
    assert e.kind == entries.KIND_NUMERIC


def test_ext_param_perfect_dodge_sub_divided_by_10():
    ctx = _ctx()
    r = parser.parse_effect_block("SubExtParam(1,51,25)", ctx, None, _maps())
    e = r.entries[0]
    assert e.key == "完全迴避"
    assert e.value == -2.0  # -(25 // 10)


def test_ext_param_after_delay_sign_inverted():
    ctx = _ctx()
    # effect_map[167] == "攻擊後延遲"; Add normally means "+" but this key
    # inverts to "-".
    r_add = parser.parse_effect_block("AddExtParam(1,167,10)", ctx, None, _maps())
    e_add = r_add.entries[0]
    assert e_add.key == "攻擊後延遲"
    assert e_add.value == -10.0
    assert e_add.unit == "%"

    r_sub = parser.parse_effect_block("SubExtParam(1,167,10)", _ctx(), None, _maps())
    e_sub = r_sub.entries[0]
    assert e_sub.value == 10.0
    assert e_sub.unit == "%"


def test_ext_param_general_name_with_percent_suffix():
    ctx = _ctx()
    # effect_map[207] == "ATK%" -> name itself ends with %, so unit becomes "%"
    r = parser.parse_effect_block("AddExtParam(1,207,15)", ctx, None, _maps())
    e = r.entries[0]
    assert e.key == "ATK%"
    assert e.value == 15.0
    assert e.unit == "%"


def test_ext_param_general_name_without_percent_suffix():
    ctx = _ctx()
    # effect_map[41] == "ATK" -> no % suffix
    r = parser.parse_effect_block("SubExtParam(1,41,8)", ctx, None, _maps())
    e = r.entries[0]
    assert e.key == "ATK"
    assert e.value == -8.0
    assert e.unit == ""


def test_ext_param_effect_map_miss_fallback():
    ctx = _ctx()
    r = parser.parse_effect_block("AddExtParam(1,9999,5)", ctx, None, _maps())
    e = r.entries[0]
    assert e.key == "參數9999"
    assert e.value == 5.0


def test_ext_param_category_routing_via_extparam_category_dict():
    # category-taxonomy: AddExtParam/SubExtParam category is looked up by
    # effect_map id via parser.EXTPARAM_CATEGORY, not by effect_str keyword
    # matching. id 41 (ATK) -> damage, id 47 (MDEF) -> ability,
    # id 113 (HP自然恢復%) -> secondary, unknown id -> other (fallback path).
    r_41 = parser.parse_effect_block("AddExtParam(1,41,8)", _ctx(), None, _maps())
    assert r_41.entries[0].category == entries.CAT_DAMAGE

    r_47 = parser.parse_effect_block("AddExtParam(1,47,8)", _ctx(), None, _maps())
    assert r_47.entries[0].category == entries.CAT_ABILITY

    r_113 = parser.parse_effect_block("AddExtParam(1,113,8)", _ctx(), None, _maps())
    assert r_113.entries[0].category == entries.CAT_SECONDARY

    r_unknown = parser.parse_effect_block("AddExtParam(1,9999,5)", _ctx(), None, _maps())
    assert r_unknown.entries[0].key == "參數9999"
    assert r_unknown.entries[0].category == entries.CAT_OTHER


def test_ext_param_unresolvable_value_becomes_unrecognized():
    ctx = _ctx()  # no scalars -> total_STR unresolvable
    r = parser.parse_effect_block("AddExtParam(1,41,total_STR)", ctx, None, _maps())
    assert len(r.entries) == 1
    e = r.entries[0]
    assert e.kind == entries.KIND_UNRECOGNIZED
    assert e.key == "無法辨識"
    assert e.extra["raw_line"] == "AddExtParam(1,41,total_STR)"


# ---------------------------------------------------------------------------
# #4 AddSpellDelay / SubSpellDelay
# ---------------------------------------------------------------------------


def test_spell_delay_add_and_sub():
    r_add = parser.parse_effect_block("AddSpellDelay(10)", _ctx(), None, _maps())
    e_add = r_add.entries[0]
    assert e_add.key == "技能後延遲"
    assert e_add.value == 10.0
    assert e_add.unit == "%"
    assert e_add.kind == entries.KIND_NUMERIC

    r_sub = parser.parse_effect_block("SubSpellDelay(10)", _ctx(), None, _maps())
    assert r_sub.entries[0].value == -10.0


# ---------------------------------------------------------------------------
# #5 AddSpellCastTime / SubSpellCastTime
# ---------------------------------------------------------------------------


def test_spell_cast_time_add_and_sub():
    r_add = parser.parse_effect_block("AddSpellCastTime(20)", _ctx(), None, _maps())
    e_add = r_add.entries[0]
    assert e_add.key == "變動詠唱時間"
    assert e_add.value == 20.0
    assert e_add.unit == "%"

    r_sub = parser.parse_effect_block("SubSpellCastTime(20)", _ctx(), None, _maps())
    assert r_sub.entries[0].value == -20.0


def test_spell_cast_time_unresolvable_becomes_unrecognized():
    ctx = _ctx()  # no scalars -> total_STR unresolvable
    r = parser.parse_effect_block("AddSpellCastTime(total_STR)", ctx, None, _maps())
    assert len(r.entries) == 1
    e = r.entries[0]
    assert e.kind == entries.KIND_UNRECOGNIZED
    assert e.key == "無法辨識"
    assert e.extra["raw_line"] == "AddSpellCastTime(total_STR)"


# ---------------------------------------------------------------------------
# #6/#7 SFCT (sfct_handled once-lock, ASYMMETRIC per original ro_core.py:
# only #6 AddSFCTEquipAmount/SubSFCTEquipAmount ever sets the lock
# (ro_core.py:1276); #7 AddSFCTEquipPermill/SubSFCTEquipPermill checks it
# but never sets it (ro_core.py:1283-1297). So: #7-then-#6 → both emit;
# #6-then-#7 → only #6 emits; #6-then-#6 → only first #6 emits.)
# ---------------------------------------------------------------------------


def test_sfct_equip_amount_ms_to_seconds():
    ctx = _ctx()
    r = parser.parse_effect_block("AddSFCTEquipAmount(1000,500,0)", ctx, None, _maps())
    numeric = [e for e in r.entries if e.key == "固定詠唱時間"]
    assert len(numeric) == 1
    assert numeric[0].value == 0.5  # 500ms / 1000
    assert numeric[0].unit == "秒"


def test_sfct_equip_permill_to_percent():
    ctx = _ctx()
    r = parser.parse_effect_block("SubSFCTEquipPermill(1000,150,0)", ctx, None, _maps())
    numeric = [e for e in r.entries if e.key == "固定詠唱時間"]
    assert len(numeric) == 1
    assert numeric[0].value == -15.0  # -(150 // 10)
    assert numeric[0].unit == "%"


def test_sfct_amount_then_permill_only_amount_emits():
    # #6 (Amount) locks the chain; #7 (Permill) checks the lock and is
    # blocked. Only #6's entry emits.
    ctx = _ctx()
    block = "AddSFCTEquipAmount(1000,500,0)\nAddSFCTEquipPermill(1000,150,0)\n"
    r = parser.parse_effect_block(block, ctx, None, _maps())
    numeric = [e for e in r.entries if e.key == "固定詠唱時間"]
    assert len(numeric) == 1
    assert numeric[0].value == 0.5
    assert numeric[0].unit == "秒"


def test_sfct_permill_then_amount_both_emit():
    # #7 (Permill) never sets the lock, so a subsequent #6 (Amount) line is
    # NOT blocked — both emit. This is the original's genuine asymmetry,
    # not a bug in this port.
    ctx = _ctx()
    block = "AddSFCTEquipPermill(1000,150,0)\nAddSFCTEquipAmount(1000,500,0)\n"
    r = parser.parse_effect_block(block, ctx, None, _maps())
    numeric = [e for e in r.entries if e.key == "固定詠唱時間"]
    assert len(numeric) == 2
    percent_entry = next(e for e in numeric if e.unit == "%")
    seconds_entry = next(e for e in numeric if e.unit == "秒")
    assert percent_entry.value == 15.0  # 150 // 10
    assert seconds_entry.value == 0.5  # 500 / 1000


def test_sfct_once_lock_two_amount_lines_only_first_emits():
    ctx = _ctx()
    block = "AddSFCTEquipAmount(1000,500,0)\nSubSFCTEquipAmount(1000,300,0)\n"
    r = parser.parse_effect_block(block, ctx, None, _maps())
    numeric = [e for e in r.entries if e.key == "固定詠唱時間"]
    assert len(numeric) == 1
    assert numeric[0].value == 0.5


# ---------------------------------------------------------------------------
# #8/#9 Damage_SKID / Damage_passive_SKID
# ---------------------------------------------------------------------------


def test_damage_skid_equip_segment():
    ctx = _ctx()
    r = parser.parse_effect_block("AddDamage_SKID(1,63,20)", ctx, None, _maps({63: "波動拳"}))
    e = r.entries[0]
    assert e.key == "技能【波動拳】傷害(裝備段)"
    assert e.value == 20.0
    assert e.unit == "%"
    assert e.extra == {"target_kind": "skill", "target_id": 63}


def test_damage_passive_skid_skill_segment():
    ctx = _ctx()
    r = parser.parse_effect_block("SubDamage_passive_SKID(1,63,15)", ctx, None, _maps({63: "波動拳"}))
    e = r.entries[0]
    assert e.key == "技能【波動拳】傷害(技能段)"
    assert e.value == -15.0
    assert e.extra == {"target_kind": "skill", "target_id": 63}


# ---------------------------------------------------------------------------
# #10 AddSkillDelay / SubSkillDelay (delayed flush)
# ---------------------------------------------------------------------------


def test_skill_delay_no_immediate_entry():
    ctx = _ctx()
    r = parser.parse_effect_block("AddSkillDelay(63,500)", ctx, None, _maps({63: "波動拳"}))
    # Not flushed until block end, but since this IS the whole block, the
    # flush at the end of parse_effect_block should have produced exactly
    # one merged entry (no separate per-line entry).
    assert len(r.entries) == 1
    e = r.entries[0]
    assert e.key == "技能【波動拳】冷卻時間"
    assert e.value == 0.5
    assert e.unit == "秒"
    assert e.kind == entries.KIND_NUMERIC


def test_skill_delay_two_lines_merge_positive_and_negative():
    ctx = _ctx()
    block = "AddSkillDelay(63,500)\nSubSkillDelay(63,200)\n"
    r = parser.parse_effect_block(block, ctx, None, _maps({63: "波動拳"}))
    delay_entries = [e for e in r.entries if e.key == "技能【波動拳】冷卻時間"]
    assert len(delay_entries) == 1
    assert delay_entries[0].value == 0.3  # (500-200)/1000
    assert delay_entries[0].unit == "秒"


def test_skill_delay_unresolvable_becomes_unrecognized():
    ctx = _ctx()
    r = parser.parse_effect_block("AddSkillDelay(63,total_STR)", ctx, None, _maps({63: "波動拳"}))
    assert len(r.entries) == 1
    assert r.entries[0].kind == entries.KIND_UNRECOGNIZED


# ---------------------------------------------------------------------------
# #11 AddSpecificSpellCastTime / SubSpecificSpellCastTime
# ---------------------------------------------------------------------------


def test_specific_spell_cast_time():
    ctx = _ctx()
    r = parser.parse_effect_block("AddSpecificSpellCastTime(63,25)", ctx, None, _maps({63: "波動拳"}))
    e = r.entries[0]
    assert e.key == "技能【波動拳】變動詠唱時間"
    assert e.value == 25.0
    assert e.unit == "%"
    assert e.extra == {"target_kind": "skill", "target_id": 63}


# ---------------------------------------------------------------------------
# #12 AddEXPPercent_KillRace / SubEXPPercent_KillRace
# ---------------------------------------------------------------------------


def test_exp_percent_kill_race():
    ctx = _ctx()
    r = parser.parse_effect_block("AddEXPPercent_KillRace(1,10)", ctx, None, _maps())
    e = r.entries[0]
    assert e.key == "從 不死 型怪的經驗值"
    assert e.value == 10.0
    assert e.unit == "%"
    assert e.extra == {"target_kind": "race", "target_id": 1}


def test_exp_percent_kill_race_unresolvable_becomes_unrecognized():
    ctx = _ctx()
    r = parser.parse_effect_block("SubEXPPercent_KillRace(1,total_STR)", ctx, None, _maps())
    assert len(r.entries) == 1
    assert r.entries[0].kind == entries.KIND_UNRECOGNIZED


# ---------------------------------------------------------------------------
# #13 AddReceiveItem_Equip / SubReceiveItem_Equip
# ---------------------------------------------------------------------------


def test_receive_item_equip_drop_rate_numeric():
    ctx = _ctx()
    r = parser.parse_effect_block("AddReceiveItem_Equip(5)", ctx, None, _maps())
    e = r.entries[0]
    assert e.key == "掉寶率"
    assert e.value == 5.0
    assert e.unit == "%"
    assert e.kind == entries.KIND_NUMERIC
    assert e.category == entries.CAT_SECONDARY


def test_receive_item_equip_sub():
    ctx = _ctx()
    r = parser.parse_effect_block("SubReceiveItem_Equip(5)", ctx, None, _maps())
    assert r.entries[0].value == -5.0


def test_receive_item_equip_unresolvable_becomes_unrecognized():
    ctx = _ctx()  # no scalars -> total_STR unresolvable
    r = parser.parse_effect_block("AddReceiveItem_Equip(total_STR)", ctx, None, _maps())
    assert len(r.entries) == 1
    e = r.entries[0]
    assert e.kind == entries.KIND_UNRECOGNIZED
    assert e.key == "無法辨識"
    assert e.extra["raw_line"] == "AddReceiveItem_Equip(total_STR)"
