from app.core import context


def test_scalar_keys_length():
    # Note: Brief specified 65, but actual count is 63 because total_AGI and total_DEX
    # appear in both loose keys and expanded keys (total_*), so set union deduplicates them.
    # Loose keys: 5 (target_element, skill_focus_AGI, skill_focus_DEX, total_AGI, total_DEX)
    # Expanded keys: 60 (5 prefixes × 12 stats)
    # Union: 5 + 60 - 2 (overlap) = 63
    assert len(context.SCALAR_KEYS) == 63


def test_scalar_keys_contains_loose_keys():
    assert "target_element" in context.SCALAR_KEYS
    assert "skill_focus_AGI" in context.SCALAR_KEYS
    assert "skill_focus_DEX" in context.SCALAR_KEYS
    assert "total_AGI" in context.SCALAR_KEYS
    assert "total_DEX" in context.SCALAR_KEYS


def test_scalar_keys_contains_expanded_keys():
    assert "base_STR" in context.SCALAR_KEYS
    assert "total_AGI" in context.SCALAR_KEYS
    assert "job_DEX" in context.SCALAR_KEYS
    assert "equip_POW" in context.SCALAR_KEYS
    assert "base_equip_CRT" in context.SCALAR_KEYS


def test_calc_context_scalar_with_value():
    ctx = context.CalcContext(
        scalars={"base_STR": 10, "total_AGI": 15},
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
        used_skill_levels={}
    )
    assert ctx.scalar("base_STR") == 10
    assert ctx.scalar("total_AGI") == 15
    assert len(ctx.missing_keys) == 0


def test_calc_context_scalar_missing():
    ctx = context.CalcContext(
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
        used_skill_levels={}
    )
    result = ctx.scalar("base_STR")
    assert result is None
    assert "base_STR" in ctx.missing_keys


def test_calc_context_skill_level_present():
    ctx = context.CalcContext(
        scalars={},
        refine_inputs={},
        grade=0,
        get_values={},
        enabled_skill_levels={5015: 10},
        pure_jobs=[],
        slot_item_id_map={},
        weapon_level_map={},
        armor_level_map={},
        weapon_type_map={},
        armor_weapon_map={},
        weapon_atk_map={},
        weapon_matk_map={},
        used_skill_levels={}
    )
    assert ctx.skill_level(5015) == 10
    assert len(ctx.missing_keys) == 0


def test_calc_context_skill_level_missing():
    ctx = context.CalcContext(
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
        used_skill_levels={}
    )
    result = ctx.skill_level(5015)
    assert result is None
    assert "skill:5015" in ctx.missing_keys


def test_calc_context_grade_value_int():
    ctx = context.CalcContext(
        scalars={},
        refine_inputs={},
        grade=5,
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
        used_skill_levels={}
    )
    assert ctx.grade_value(None) == 5


def test_calc_context_grade_value_dict():
    ctx = context.CalcContext(
        scalars={},
        refine_inputs={},
        grade={1: 3, 2: 7},
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
        used_skill_levels={}
    )
    assert ctx.grade_value(1) == 3
    assert ctx.grade_value(2) == 7
    assert ctx.grade_value(999) == 0  # Missing slot returns 0


def test_calc_context_grade_value_dict_missing_slot():
    ctx = context.CalcContext(
        scalars={},
        refine_inputs={},
        grade={1: 3},
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
        used_skill_levels={}
    )
    assert ctx.grade_value(None) == 0


def test_calc_context_grade_value_exception():
    ctx = context.CalcContext(
        scalars={},
        refine_inputs={},
        grade="invalid",
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
        used_skill_levels={}
    )
    assert ctx.grade_value(None) == 0
