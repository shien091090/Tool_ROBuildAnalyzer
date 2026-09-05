from app.core import entries, parser
from app.core.context import CalcContext
from app.core.maps import EffectMaps


def _ctx(**kw):
    defaults = dict(
        scalars={}, refine_inputs={}, grade=0, get_values={}, enabled_skill_levels={},
        pure_jobs=[], slot_item_id_map={}, weapon_level_map={}, armor_level_map={},
        weapon_type_map={}, armor_weapon_map={}, weapon_atk_map={}, weapon_matk_map={},
        used_skill_levels={},
    )
    defaults.update(kw)
    return CalcContext(**defaults)


def _maps():
    return EffectMaps(skill_map={})


def _kinds(result):
    return [e.kind for e in result.entries]


def test_skill_level_variable_consumer_becomes_unresolved():
    block = "temp1 = GetSkillLevel(5015)\nAddExtParam(0, 41, temp1 * 2)"
    r = parser.parse_effect_block(block, _ctx(), 2, _maps())
    assert _kinds(r) == [entries.KIND_UNRESOLVED]
    e = r.entries[0]
    assert e.extra["missing"] == ["skill:5015"]
    assert e.extra["raw_lines"] == ["AddExtParam(0, 41, temp1 * 2)"]
    assert "temp1 = GetSkillLevel(5015)" in e.extra["condition"]


def test_skill_level_variable_resolves_when_character_provides_skill():
    block = "temp1 = GetSkillLevel(5015)\nAddExtParam(0, 41, temp1 * 2)"
    r = parser.parse_effect_block(block, _ctx(enabled_skill_levels={5015: 3}), 2, _maps())
    assert _kinds(r) == [entries.KIND_NUMERIC]
    assert r.entries[0].key == "ATK" and r.entries[0].value == 6


def test_get_variable_missing_routes_to_unresolved():
    block = "temp1 = get(255)\nAddExtParam(0, 41, math.floor(temp1 / 15) * 5)"
    r = parser.parse_effect_block(block, _ctx(), 2, _maps())
    assert _kinds(r) == [entries.KIND_UNRESOLVED]
    assert r.entries[0].extra["missing"] == ["get:255"]


def test_chained_variable_propagates_missing():
    block = "a = GetSkillLevel(1)\nb = a * 2\nAddExtParam(0, 41, b)"
    r = parser.parse_effect_block(block, _ctx(), 2, _maps())
    assert _kinds(r) == [entries.KIND_UNRESOLVED]
    assert r.entries[0].extra["missing"] == ["skill:1"]


def test_math_floor_assignment_missing_routes_to_unresolved():
    block = "a = math.floor(GetSkillLevel(9) / 2)\nAddExtParam(0, 41, a)"
    r = parser.parse_effect_block(block, _ctx(), 2, _maps())
    assert _kinds(r) == [entries.KIND_UNRESOLVED]
    assert r.entries[0].extra["missing"] == ["skill:9"]


def test_direct_skill_level_in_handler_arg_unresolved():
    r = parser.parse_effect_block("AddExtParam(0, 41, GetSkillLevel(7) * 3)", _ctx(), 2, _maps())
    assert _kinds(r) == [entries.KIND_UNRESOLVED]
    assert r.entries[0].extra["missing"] == ["skill:7"]


def test_reassignment_clears_unresolved_variable():
    block = "a = GetSkillLevel(1)\na = 5\nAddExtParam(0, 41, a)"
    r = parser.parse_effect_block(block, _ctx(), 2, _maps())
    assert _kinds(r) == [entries.KIND_NUMERIC]
    assert r.entries[0].value == 5


def test_truly_unknown_function_stays_unrecognized():
    r = parser.parse_effect_block("SomeTotallyUnknownFunction(1,2)", _ctx(), None, _maps())
    assert _kinds(r) == [entries.KIND_UNRECOGNIZED]


def test_unknown_function_using_unresolved_variable_becomes_unresolved():
    block = "a = GetSkillLevel(1)\nSomeTotallyUnknownFunction(a)"
    r = parser.parse_effect_block(block, _ctx(), None, _maps())
    assert _kinds(r) == [entries.KIND_UNRESOLVED]
    assert r.entries[0].extra["missing"] == ["skill:1"]
