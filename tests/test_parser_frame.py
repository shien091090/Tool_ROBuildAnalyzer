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


def _maps():
    # Ruling 3 (progress.md): tests build EffectMaps directly, no DB / make_maps.
    return EffectMaps(skill_map={})


# ---------------------------------------------------------------------------
# Brief's 11 required skeletons
# ---------------------------------------------------------------------------


def test_ps_line_descriptive_entry():
    ctx = _ctx()
    r = parser.parse_effect_block("P.S = 這是測試備註", ctx, None, _maps())
    assert len(r.entries) == 1
    e = r.entries[0]
    assert e.key == "P.S"
    assert e.value is None
    assert e.kind == entries.KIND_DESCRIPTIVE
    assert e.extra["text"] == "這是測試備註"


def test_stat_line_numeric_entries_and_ctx_maps():
    ctx = _ctx()
    # armor stat_name_sets: idx0=DEF, idx10=防具等級
    block = 'Type = "armor"\nStat = {13,0,0,0,0,0,0,0,0,0,7}\n'
    r = parser.parse_effect_block(block, ctx, 5, _maps())
    def_entries = [e for e in r.entries if e.key == "DEF"]
    assert len(def_entries) == 1
    assert def_entries[0].value == 13.0
    assert def_entries[0].kind == entries.KIND_NUMERIC
    assert ctx.armor_level_map.get(5) == 7


def test_stat_line_weapon_atk_category_damage():
    ctx = _ctx()
    # category-taxonomy: Stat-line entries are categorized by stat name, not
    # keyword matching. Mweapon stat_name_sets: idx2=武器ATK -> CAT_DAMAGE.
    block = 'Type = "Mweapon"\nStat = {0,0,120,0,0,0,0,0,0,0,0,0,0,0,0,0,0}\n'
    r = parser.parse_effect_block(block, ctx, 1, _maps())
    atk_entries = [e for e in r.entries if e.key == "武器ATK"]
    assert len(atk_entries) == 1
    assert atk_entries[0].value == 120.0
    assert atk_entries[0].category == entries.CAT_DAMAGE


def test_excluded_stat_not_emitted():
    ctx = _ctx()
    block = 'Type = "armor"\nStat = {0,0,0,0,0,0,0,0,0,0,15}\n'
    r = parser.parse_effect_block(block, ctx, 3, _maps())
    assert not any(e.key == "防具等級" for e in r.entries)
    assert ctx.armor_level_map.get(3) == 15


def test_if_true_branch_effects_parsed():
    ctx = _ctx()
    block = "if 1==1 then\nSomeUnknownCall(1)\nend"
    r = parser.parse_effect_block(block, ctx, None, _maps())
    unrecognized = [e for e in r.entries if e.kind == entries.KIND_UNRECOGNIZED]
    assert len(unrecognized) == 1
    assert unrecognized[0].extra["raw_line"] == "SomeUnknownCall(1)"


def test_if_false_branch_skipped_to_trace():
    ctx = _ctx()
    block = "if 1==2 then\nX()\nend"
    r = parser.parse_effect_block(block, ctx, None, _maps())
    assert not r.entries
    assert any("⛔" in l and "X()" in l for l in r.trace)


def test_unresolved_condition_collects_raw_lines():
    ctx = _ctx()  # 無scalars
    block = "{\nif total_STR >= 90 then\nAddDamage_CRI(1, 15)\nend\n}"
    r = parser.parse_effect_block(block, ctx, 5, _maps())
    unres = [e for e in r.entries if e.kind == entries.KIND_UNRESOLVED]
    assert len(unres) == 1
    assert "total_STR" in unres[0].extra["missing"]
    assert any("AddDamage_CRI" in l for l in unres[0].extra["raw_lines"])


def test_nested_if_inside_unresolved_swallowed():
    ctx = _ctx()
    block = "if total_STR >= 90 then\nif 1==1 then\nAddDamage_CRI(1,15)\nend\nend"
    r = parser.parse_effect_block(block, ctx, None, _maps())
    unres = [e for e in r.entries if e.kind == entries.KIND_UNRESOLVED]
    assert len(unres) == 1
    assert len(r.entries) == 1  # nested if/end fully swallowed, no other entries
    raw = unres[0].extra["raw_lines"]
    assert any("if 1==1 then" in l for l in raw)
    assert any("AddDamage_CRI" in l for l in raw)
    assert any(l == "end" for l in raw)  # the inner end is swallowed too


def test_elseif_chain_matches_original_semantics():
    ctx = _ctx()
    block = "if 1==2 then\nA()\nelseif 1==1 then\nB()\nend"
    r = parser.parse_effect_block(block, ctx, None, _maps())
    unrecognized = [e for e in r.entries if e.kind == entries.KIND_UNRECOGNIZED]
    assert len(unrecognized) == 1
    assert unrecognized[0].extra["raw_line"] == "B()"
    assert any("⛔" in l and "A()" in l for l in r.trace)


def test_variable_assignment_feeds_later_expression():
    ctx = _ctx(refine_inputs={5: 7})
    block = "temp=GetRefineLevel(5)\nresult=temp+1\n"
    r = parser.parse_effect_block(block, ctx, None, _maps())
    assert any("`temp` = 7" in l for l in r.trace)
    assert any("`result` = 8" in l for l in r.trace)


def test_unrecognized_line_becomes_entry():
    ctx = _ctx()
    r = parser.parse_effect_block("SomeTotallyUnknownFunction(1,2)", ctx, None, _maps())
    assert len(r.entries) == 1
    e = r.entries[0]
    assert e.kind == entries.KIND_UNRECOGNIZED
    assert e.key == "無法辨識"
    assert e.extra["raw_line"] == "SomeTotallyUnknownFunction(1,2)"


def test_ignore_prefixes_silent():
    ctx = _ctx()
    r = parser.parse_effect_block("local x = 1", ctx, None, _maps())
    assert not r.entries
    assert not r.trace


def test_function_wrapper_line_ignored_no_unrecognized():
    # C1: M1 stores onstart_equip_src INCLUDING the OnStartEquip = function()
    # wrapper's opening "function()" line — every real block therefore starts
    # with it. It must be silently ignored (like the trailing "end", already
    # a no-op via _handle_end on an empty block_stack), not become a bogus
    # UNRECOGNIZED "無法辨識" entry.
    ctx = _ctx()
    block = "function()\nAddDamage_CRI(1, 7)\nend"
    r = parser.parse_effect_block(block, ctx, None, _maps())
    unrecognized = [e for e in r.entries if e.kind == entries.KIND_UNRECOGNIZED]
    assert len(unrecognized) == 0
    numeric = [e for e in r.entries if e.key == "爆擊傷害"]
    assert len(numeric) == 1
    assert numeric[0].value == 7.0


# ---------------------------------------------------------------------------
# Extra coverage (>= 3 required)
# ---------------------------------------------------------------------------


def test_else_branch_normal_semantics():
    ctx = _ctx()
    block = "if 1==2 then\nA()\nelse\nB()\nend"
    r = parser.parse_effect_block(block, ctx, None, _maps())
    unrecognized = [e for e in r.entries if e.kind == entries.KIND_UNRECOGNIZED]
    assert len(unrecognized) == 1
    assert unrecognized[0].extra["raw_line"] == "B()"
    assert any("⛔" in l and "A()" in l for l in r.trace)


def test_unresolved_elseif_chain_all_subsequent_branches_unresolved():
    # Ruling: once one branch of an if-chain is unresolved, every subsequent
    # elseif/else of that chain is also unresolved — each gets its own entry
    # with its own collected raw_lines.
    ctx = _ctx()  # no scalars: both total_STR and total_AGI are unresolvable
    block = (
        "if total_STR >= 90 then\n"
        "A()\n"
        "elseif total_AGI >= 50 then\n"
        "B()\n"
        "else\n"
        "C()\n"
        "end"
    )
    r = parser.parse_effect_block(block, ctx, None, _maps())
    unres = [e for e in r.entries if e.kind == entries.KIND_UNRESOLVED]
    assert len(unres) == 3
    conditions = [e.extra["condition"] for e in unres]
    assert conditions == ["total_STR >= 90", "total_AGI >= 50", "else (前分支未判定)"]
    assert "total_STR" in unres[0].extra["missing"]
    assert unres[1].extra["missing"] == []
    assert unres[2].extra["missing"] == []
    assert any("A()" in l for l in unres[0].extra["raw_lines"])
    assert any("B()" in l for l in unres[1].extra["raw_lines"])
    assert any("C()" in l for l in unres[2].extra["raw_lines"])


def test_unparseable_condition_warns_to_trace():
    # Original ro_core.py:950 equivalent: eval_condition raising (not missing
    # keys) still produces an unresolved block + a ⚠️ trace line.
    ctx = _ctx()
    block = "if 1+2) then\nX()\nend"
    r = parser.parse_effect_block(block, ctx, None, _maps())
    unres = [e for e in r.entries if e.kind == entries.KIND_UNRESOLVED]
    assert len(unres) == 1
    assert unres[0].extra["missing"] == []
    assert any("⚠️" in l and "1+2)" in l for l in r.trace)


def test_type_stat_combined_line_preserves_quirks():
    # Quirk: Type+Stat combined line does NOT write the *stat's own value*
    # into ctx.armor_level_map (only the per-line GetLocation() side-effect
    # init writes a 0 default there, since slot_id is not None — see
    # inventory 狀態副作用#1) and does NOT filter EXCLUDED_STAT_NAMES (unlike
    # the standalone Stat handler).
    ctx = _ctx()
    block = 'Type = "armor", Stat = {0,0,0,0,0,0,0,0,0,0,9}\n'
    r = parser.parse_effect_block(block, ctx, 4, _maps())
    assert ctx.armor_level_map.get(4) == 0  # side-effect default, NOT the stat value 9
    assert any(e.key == "防具等級" and e.value == 9.0 for e in r.entries)


def test_eof_unresolved_block_flushed_when_end_missing():
    # I5: block_text ends without a matching `end` for the open if. Without
    # the post-loop flush this block would be silently dropped (no
    # _handle_end ever runs for it, since the for-loop over lines simply
    # exhausts). Must still surface exactly one KIND_UNRESOLVED entry with
    # the swallowed raw line collected.
    ctx = _ctx()  # no scalars -> total_STR unresolvable
    block = "if total_STR >= 90 then\nAddDamage_CRI(1, 5)"
    r = parser.parse_effect_block(block, ctx, None, _maps())
    unres = [e for e in r.entries if e.kind == entries.KIND_UNRESOLVED]
    assert len(unres) == 1
    assert "total_STR" in unres[0].extra["missing"]
    assert any("AddDamage_CRI" in l for l in unres[0].extra["raw_lines"])


def test_math_floor_assignment_resolves():
    # V7: math.floor(expr) via safe_eval — lua_expr's allowed-char whitelist
    # does include "." (ported from ro_core.py's own identical whitelist),
    # so this resolves normally, unlike a naive read of the character class
    # might suggest.
    ctx = _ctx()
    r = parser.parse_effect_block("temp=math.floor(3.5)\nresult=temp+1\n", ctx, None, _maps())
    assert not r.entries
    assert any("`temp` = 3" in l for l in r.trace)
    assert any("`result` = 4" in l for l in r.trace)
