from app.core import lua_expr
from app.core.context import CalcContext


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


# ---------------------------------------------------------------------------
# Brief's core 10 skeletons
# ---------------------------------------------------------------------------


def test_eval_simple_arithmetic():
    assert lua_expr.safe_eval("3+4*2", {}, _ctx(), None) == 11


def test_lua_integer_division():
    assert lua_expr.safe_eval("7/2", {}, _ctx(), None) == 3  # IntDiv語意


def test_getrefinelevel_substitution():
    ctx = _ctx(refine_inputs={5: 11})
    assert lua_expr.safe_eval("GetRefineLevel(5)*2", {}, ctx, None) == 22


def test_condition_true_false():
    ctx = _ctx(scalars={"base_STR": 130})
    ok, missing = lua_expr.eval_condition("base_STR >= 90", {}, ctx, None)
    assert ok is True and missing == set()


def test_condition_missing_scalar_returns_none():
    ok, missing = lua_expr.eval_condition("total_STR >= 90", {}, _ctx(), None)
    assert ok is None and "total_STR" in missing


def test_condition_missing_skill_level():
    ok, missing = lua_expr.eval_condition("GetSkillLevel(5015) > 0", {}, _ctx(), None)
    assert ok is None and "skill:5015" in missing


def test_lua_operators_translated():
    ok, _ = lua_expr.eval_condition("1 ~= 2 && true", {}, _ctx(), None)
    assert ok is True


def test_getpurejob_membership():
    ctx = _ctx(pure_jobs=[4055])
    ok, _ = lua_expr.eval_condition("GetPureJob() == 4055", {}, ctx, None)
    assert ok is True


def test_disallowed_chars_rejected():
    assert lua_expr.safe_eval("__import__('os')", {}, _ctx(), None) is None


def test_split_lua_args_nested():
    assert lua_expr.split_lua_args('1, GetRefineLevel(5), "a,b"') == ['1', 'GetRefineLevel(5)', '"a,b"']


# ---------------------------------------------------------------------------
# Extra coverage (>= 4 required): current_slot location variants, weapon/armor
# maps, long-name-first variable substitution, paren padding tolerance.
# ---------------------------------------------------------------------------


def test_refine_location_with_current_slot():
    ctx = _ctx(refine_inputs={3: 7})
    assert lua_expr.safe_eval("GetRefineLevel(GetLocation())", {}, ctx, 3) == 7


def test_refine_location_without_current_slot_defaults_zero():
    ctx = _ctx(refine_inputs={3: 7})
    assert lua_expr.safe_eval("GetRefineLevel(GetLocation())", {}, ctx, None) == 0


def test_weapon_and_armor_level_map_substitution():
    ctx = _ctx(weapon_level_map={2: 4}, armor_level_map={6: 9})
    assert lua_expr.safe_eval("GetEquipWeaponLv(2) + GetEquipArmorLv(6)", {}, ctx, None) == 13


def test_weapon_and_armor_level_map_location_variant():
    ctx = _ctx(weapon_level_map={1: 4}, armor_level_map={1: 9})
    assert lua_expr.safe_eval(
        "GetEquipWeaponLv(GetLocation()) + GetEquipArmorLv(GetLocation())", {}, ctx, 1
    ) == 13


def test_variables_substitution_long_name_priority():
    variables = {"temp": 2, "temp1": 100}
    assert lua_expr.safe_eval("temp + temp1", variables, _ctx(), None) == 102


def test_paren_padding_tolerance():
    # 原始行為: Lua來源少寫右括號時自動補齊, 容忍解析
    assert lua_expr.safe_eval("(1+2", {}, _ctx(), None) == 3


# ---------------------------------------------------------------------------
# Remaining substitution rules from normalize_lua_expr (637-676)
# ---------------------------------------------------------------------------


def test_get_value_substitution():
    ctx = _ctx(get_values={7: 42})
    assert lua_expr.safe_eval("get(7)", {}, ctx, None) == 42


def test_get_value_missing_tracks_and_returns_none():
    # Deliberate change (7): a missing get(N) no longer defaults to 0 — it
    # records "get:{N}" and safe_eval refuses to guess (returns None).
    ctx = _ctx(get_values={})
    assert lua_expr.safe_eval("get(7)", {}, ctx, None) is None
    assert "get:7" in ctx.missing_keys


def test_grade_level_explicit_slot():
    ctx = _ctx(grade={5: 3})
    assert lua_expr.safe_eval("GetEquipGradeLevel(5)", {}, ctx, None) == 3


def test_grade_level_location_variant():
    ctx = _ctx(grade={2: 8})
    assert lua_expr.safe_eval("GetEquipGradeLevel(GetLocation())", {}, ctx, 2) == 8


def test_getpetrelationship_quirk_shares_grade_value():
    # Ported quirk: GetPetRelationship() substitutes the same grade value source
    # as GetEquipGradeLevel(GetLocation()), per ro_core.py:653.
    ctx = _ctx(grade={4: 6})
    assert lua_expr.safe_eval("GetPetRelationship()", {}, ctx, 4) == 6


def test_getweaponclass_location():
    ctx = _ctx(weapon_type_map={1: 2})
    assert lua_expr.safe_eval("GetWeaponClass(GetLocation())", {}, ctx, 1) == 2


def test_getitemidlocation():
    ctx = _ctx(slot_item_id_map={4: 1101})
    assert lua_expr.safe_eval("GetItemIDLocation(4)", {}, ctx, None) == 1101


def test_getskilllevel_substitution_success():
    ctx = _ctx(enabled_skill_levels={5015: 10})
    assert lua_expr.safe_eval("GetSkillLevel(5015)", {}, ctx, None) == 10


def test_getpurejob_not_equal():
    ctx = _ctx(pure_jobs=[4055])
    ok, missing = lua_expr.eval_condition("GetPureJob() ~= 4054", {}, ctx, None)
    assert ok is True and missing == set()


def test_nil_replaced_with_zero():
    assert lua_expr.safe_eval("nil + 5", {}, _ctx(), None) == 5


def test_true_false_case_insensitive():
    ok, _ = lua_expr.eval_condition("TRUE && not FALSE", {}, _ctx(), None)
    assert ok is True


# ---------------------------------------------------------------------------
# Missing-key propagation (deliberate behavioral change)
# ---------------------------------------------------------------------------


def test_normalize_reports_missing_scalar_and_skill_together():
    normalized, missing = lua_expr.normalize(
        "total_STR + GetSkillLevel(5015)", {}, _ctx(), None
    )
    assert missing == {"total_STR", "skill:5015"}


def test_safe_eval_none_when_missing_even_if_evaluable_without_it():
    # Deliberate change: original padded missing values with 0 and evaluated
    # anyway; this port refuses to guess and returns None instead.
    ok = lua_expr.safe_eval("total_STR * 0", {}, _ctx(), None)
    assert ok is None


def test_eval_condition_none_missing_set_not_empty_blocks_short_circuit():
    ok, missing = lua_expr.eval_condition("false && total_STR >= 90", {}, _ctx(), None)
    assert ok is None and "total_STR" in missing


def test_get_value_34_substitutes_with_character_value():
    # get(34) = VIT UI field (ItemSearchApp.py:2048 stat_fields), populated
    # from the character file by aggregate.make_context.
    ctx = _ctx(get_values={34: 100})
    assert lua_expr.safe_eval("get(34)", {}, ctx, None) == 100


def test_get_value_200_missing_none_and_recorded():
    # get(200) = MHP; the character file has no such field (aggregate.
    # GET_VALUE_FIELDS deliberately excludes it) so it always misses.
    ctx = _ctx(get_values={})
    assert lua_expr.safe_eval("get(200)", {}, ctx, None) is None
    assert "get:200" in ctx.missing_keys


def test_get_value_condition_missing_returns_none_and_missing_set():
    ok, missing = lua_expr.eval_condition("get(200) > 0", {}, _ctx(get_values={}), None)
    assert ok is None and missing == {"get:200"}


# ---------------------------------------------------------------------------
# split_lua_args / get_lua_call_args / eval_lua_arg
# ---------------------------------------------------------------------------


def test_split_lua_args_empty():
    assert lua_expr.split_lua_args("") == []


def test_split_lua_args_single():
    assert lua_expr.split_lua_args("42") == ["42"]


def test_get_lua_call_args_matches():
    assert lua_expr.get_lua_call_args("EnableSkill", "EnableSkill(5015, 3)") == ["5015", "3"]


def test_get_lua_call_args_no_match_returns_none():
    assert lua_expr.get_lua_call_args("EnableSkill", "NotTheRightCall(1)") is None


def test_eval_lua_arg_uses_default_when_missing_index():
    assert lua_expr.eval_lua_arg([], 0, "fallback", {}, _ctx(), None) == "fallback"


def test_eval_lua_arg_evaluates_present_index():
    assert lua_expr.eval_lua_arg(["3+4"], 0, None, {}, _ctx(), None) == 7
