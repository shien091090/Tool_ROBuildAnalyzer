"""Effect-block line-scanning state machine.

Ported from ROItemSearchApp's ro_core.py (parse_lua_effects_with_variables).
See docs/superpowers/notes/2026-09-03-effect-parser-inventory.md for the full
section-by-section line-number map this port is based on, and
.superpowers/sdd/2026-09-03-m2-effects/task-6-brief.md for the binding
interfaces and rulings this module implements.

This module is the M2 "skeleton": line preprocessing, the P.S/Type+Stat/Stat
non-gated lines, the if/elseif/else/end state machine (extended with the new
unresolved-condition mechanism), the V1-V8 variable-assignment handlers, the
handler hook (stubbed — Task 7-9 fill it in), and the fallback. The ~90 real
effect handlers (EnableSkill, AddDamage_*, ...) are NOT part of this task;
``_match_effect_handlers`` always returns False here.

Deliberate deviations from the original (see task-6 brief for the ruling
text backing each):

1. GetSkillLevel(N) is NOT substituted at the line-preprocessing stage
   (ro_core.py:843-848 is not ported). Skill-level resolution now happens
   uniformly inside lua_expr.normalize() via ctx.skill_level(), which can
   report a miss instead of silently defaulting to 0.
2. Any if/elseif condition that can't be resolved (lua_expr.eval_condition
   returns (None, missing)) produces an "unresolved condition" block instead
   of silently defaulting to False. Its raw (unparsed) body is collected and
   surfaced as a single KIND_UNRESOLVED EffectEntry when the block closes.
3. Once any branch of an if/elseif/else chain is unresolved, every
   subsequent elseif/else of that SAME chain is also treated as unresolved
   without evaluating its own condition (controller ruling, see
   progress.md "Task 6: Ruling" and the brief) — each such branch still gets
   its own KIND_UNRESOLVED entry with its own collected raw lines.
4. The per-line "general gate" (ro_core.py:1013) is restructured so that
   lines inside an inactive (resolved-False) block still reach the fallback
   and produce a "⛔ 已跳過（條件不成立）" trace line, instead of being
   silently discarded before ever reaching the fallback's dead "not
   condition_met" branch (unreachable in the original given 1013's early
   continue). This matches the task-6 brief/tests
   (test_if_false_branch_skipped_to_trace) and is the only behavioral
   "fix" in this port; every other quirk is preserved as-is (see below).

Preserved quirks (intentionally NOT fixed, per porting policy):

- Type+Stat combined lines (ro_core.py:875-887) do not write ctx maps and do
  not filter EXCLUDED_STAT_NAMES, unlike the standalone Stat={...} handler
  (inventory doc "狀態副作用#3", "疑似原版bug照搬").
- The standalone Stat={...} handler does not `continue` after running — it
  falls through the rest of the per-line dispatch chain, relying on
  IGNORE_PREFIXES's "Stat " prefix (and, in practice, the V8 general-
  assignment skip-rule, which also matches "Stat = {...}") to keep it from
  becoming a bogus UNRECOGNIZED entry.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core import lua_expr
from app.core import maps as static_maps
from app.core.context import CalcContext
from app.core.entries import (
    CAT_OTHER,
    EffectEntry,
    KIND_DESCRIPTIVE,
    KIND_NUMERIC,
    KIND_UNRECOGNIZED,
    KIND_UNRESOLVED,
    classify_category,
)
from app.core.maps import EffectMaps

IGNORE_PREFIXES = ("local ", "Stat ", "{Type ", "}")


@dataclass
class ParseResult:
    entries: list[EffectEntry] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)   # 📌✅❌⛔⚠️類除錯行(不進entries)


# =========================================================
# block_stack helpers
# =========================================================


def _new_block(active, branch_taken, unresolved=False, condition=None, missing=None, raw_lines=None):
    return {
        "active": active,
        "branch_taken": branch_taken,
        "unresolved": unresolved,
        "condition": condition,
        "missing": missing if missing is not None else set(),
        "raw_lines": raw_lines if raw_lines is not None else [],
    }


def _all_active(block_stack: list[dict]) -> bool:
    return all(b["active"] for b in block_stack)


def _find_unresolved_ancestor(block_stack: list[dict]) -> dict | None:
    for b in reversed(block_stack):
        if b["unresolved"]:
            return b
    return None


def _unresolved_entry(block: dict) -> EffectEntry:
    return EffectEntry(
        key="未判定條件",
        value=None,
        unit="",
        kind=KIND_UNRESOLVED,
        category=CAT_OTHER,
        extra={
            "condition": block["condition"],
            "missing": sorted(block["missing"]),
            "raw_lines": list(block["raw_lines"]),
        },
    )


# =========================================================
# if/elseif/else/end state machine (ro_core.py:936-1010, ported exactly,
# extended with unresolved-condition tracking per M2 plan Task 6)
# =========================================================


def _handle_if(if_match, block_stack, entries_out, trace, variables, ctx, slot_id, original_line):
    unresolved_anc = _find_unresolved_ancestor(block_stack)
    if unresolved_anc is not None:
        # Nested inside an ancestor's unresolved zone: track depth via a
        # transparent placeholder, swallow this line's raw text into the
        # ancestor instead of evaluating anything.
        block_stack.append(_new_block(False, False))
        unresolved_anc["raw_lines"].append(original_line)
        return

    parent_active = _all_active(block_stack)
    if not parent_active:
        block_stack.append(_new_block(False, False))
        return

    expr = if_match.group(1)
    cond, missing = lua_expr.eval_condition(expr, variables, ctx, slot_id)
    if cond is None:
        trace.append(f"⚠️ 無法解析條件: {expr}")
        block_stack.append(_new_block(False, False, unresolved=True, condition=expr, missing=missing))
    else:
        trace.append(f"{'✅ if 條件成立' if cond else '❌ if 條件不成立'} : {expr}")
        block_stack.append(_new_block(cond, cond, condition=expr))


def _handle_elseif(elseif_match, block_stack, entries_out, trace, variables, ctx, slot_id, original_line):
    if not block_stack:
        raise ValueError("elseif without if")
    last = block_stack.pop()

    unresolved_anc = _find_unresolved_ancestor(block_stack)
    if unresolved_anc is not None:
        block_stack.append(_new_block(False, False))
        unresolved_anc["raw_lines"].append(original_line)
        return

    expr = elseif_match.group(1)

    if last["unresolved"]:
        # Ruling: once this chain has an unresolved branch, every subsequent
        # elseif/else of the SAME chain is also unresolved — `expr` is not
        # even evaluated. `last` closes here and gets its own entry.
        entries_out.append(_unresolved_entry(last))
        block_stack.append(_new_block(False, False, unresolved=True, condition=expr))
        return

    parent_active = _all_active(block_stack)
    if not parent_active or last["branch_taken"]:
        block_stack.append(_new_block(False, True))
        return

    cond, missing = lua_expr.eval_condition(expr, variables, ctx, slot_id)
    if cond is None:
        trace.append(f"⚠️ 無法解析條件: {expr}")
        block_stack.append(_new_block(False, False, unresolved=True, condition=expr, missing=missing))
    else:
        trace.append(f"{'✅ elseif 條件成立' if cond else '❌ elseif 條件不成立'} : {expr}")
        block_stack.append(_new_block(cond, cond, condition=expr))


def _handle_else(block_stack, entries_out, original_line):
    if not block_stack:
        raise ValueError("else without if")
    last = block_stack.pop()

    unresolved_anc = _find_unresolved_ancestor(block_stack)
    if unresolved_anc is not None:
        block_stack.append(_new_block(False, False))
        unresolved_anc["raw_lines"].append(original_line)
        return

    if last["unresolved"]:
        entries_out.append(_unresolved_entry(last))
        block_stack.append(_new_block(False, True, unresolved=True, condition="else (前分支未判定)"))
        return

    parent_active = _all_active(block_stack)
    if not parent_active or last["branch_taken"]:
        block_stack.append(_new_block(False, True))
    else:
        block_stack.append(_new_block(True, True))


def _handle_end(block_stack, entries_out, original_line):
    if not block_stack:
        return
    last = block_stack.pop()
    if last["unresolved"]:
        entries_out.append(_unresolved_entry(last))
        return
    unresolved_anc = _find_unresolved_ancestor(block_stack)
    if unresolved_anc is not None:
        unresolved_anc["raw_lines"].append(original_line)


# =========================================================
# P.S / Type+Stat / Stat (ro_core.py:863-931 — ungated by block_stack active
# state; see inventory doc "不受block_stack閘控")
# =========================================================


def _handle_type_stat(type_stat_match, entries_out) -> None:
    eq_type = type_stat_match.group(1)
    stat_str = type_stat_match.group(2)
    stat_values = [int(x.strip()) for x in stat_str.split(",")]
    stat_names_list = static_maps.STAT_NAME_SETS.get(eq_type, static_maps.STAT_NAME_SETS["armor"])

    for idx, val in enumerate(stat_values):
        if val == 0:
            continue
        name = stat_names_list[idx] if idx < len(stat_names_list) else f"未知{idx}"
        # Quirk preserved verbatim from ro_core.py:875-887: unlike the
        # standalone Stat={...} handler below, this combined Type+Stat line
        # never wrote ctx maps and never filtered EXCLUDED_STAT_NAMES in the
        # original — kept as-is (inventory 狀態副作用#3, 疑似原版bug照搬).
        entries_out.append(
            EffectEntry(key=name, value=float(val), unit="", kind=KIND_NUMERIC, category=classify_category(name))
        )


def _handle_stat(stat_match, block_text, ctx: CalcContext, slot_id, entries_out) -> None:
    stat_values = [int(x.strip()) for x in stat_match.group(1).split(",") if x.strip().isdigit()]

    type_match = re.search(r'Type\s*=\s*"(\w+)"', block_text)
    equip_type = type_match.group(1) if type_match else "armor"
    stat_names = static_maps.STAT_NAME_SETS.get(equip_type, static_maps.STAT_NAME_SETS["armor"])

    for idx, val in enumerate(stat_values):
        if val == 0:
            continue
        stat_name = stat_names[idx] if idx < len(stat_names) else f"未知{idx}"

        ctx.armor_weapon_map[slot_id] = equip_type
        if stat_name == "武器等級":
            ctx.weapon_level_map[slot_id] = val
        elif stat_name == "防具等級":
            ctx.armor_level_map[slot_id] = val
        elif stat_name == "武器ATK":
            ctx.weapon_atk_map[slot_id] = val
        elif stat_name == "武器MATK":
            ctx.weapon_matk_map[slot_id] = val

        if stat_name == "武器類型":
            ctx.weapon_type_map[slot_id] = val
            continue  # skip emitting an entry for this meta stat (ro_core.py:920-925)

        if stat_name in static_maps.EXCLUDED_STAT_NAMES:
            continue

        entries_out.append(
            EffectEntry(
                key=stat_name, value=float(val), unit="", kind=KIND_NUMERIC, category=classify_category(stat_name)
            )
        )


# =========================================================
# V1-V8 variable assignments (ro_core.py:1017-1141)
# =========================================================

_RE_MULTI_REFINE = re.compile(r"(\w+)\s*=\s*GetRefineLevel\((\d+)\)((?:\s*\+\s*GetRefineLevel\((\d+)\))+)")
_RE_REFINE_ASSIGN = re.compile(r"(\w+)\s*=\s*GetRefineLevel\((\d+)\)")
_RE_GRADE_ASSIGN = re.compile(r"(\w+)\s*=\s*GetEquipGradeLevel\((\d+)\)")
_RE_ARMOR_ASSIGN = re.compile(r"(\w+)\s*=\s*GetEquipArmorLv\((\d+)\)")
_RE_WEAPON_CLASS_ASSIGN = re.compile(r"(\w+)\s*=\s*GetWeaponClass\((\d+)\)")
_RE_WEAPON_LV_ASSIGN = re.compile(r"(\w+)\s*=\s*GetEquipWeaponLv\((\d+)\)")
_RE_MATH_FLOOR_ASSIGN = re.compile(r"(\w+)\s*=\s*math\.floor\((.+)\)")
_RE_GENERAL_ASSIGN = re.compile(r"(\w+)\s*=\s*(.+)")


def _try_variable_assignment(line: str, variables: dict, ctx: CalcContext, slot_id, trace: list[str]) -> bool:
    """V1-V8. Returns True if the line was consumed (whether or not it produced
    anything useful — matches the original's `continue`-after-match shape).

    Note: unlike condition blocks, a variable assignment that can't be
    resolved (safe_eval returns None) only produces a ⚠️ trace line — it does
    NOT create a KIND_UNRESOLVED entry. Variables aren't effects; whatever
    later line tries to *use* the missing variable/expression will surface
    its own unresolved/unrecognized signal through its own path.
    """
    # V1: multi-segment GetRefineLevel(...) + GetRefineLevel(...) + ...
    m = _RE_MULTI_REFINE.match(line)
    if m:
        var = m.group(1)
        slots = re.findall(r"GetRefineLevel\((\d+)\)", line)
        value = sum(ctx.refine_inputs.get(int(s), 0) for s in slots)
        variables[var] = value
        trace.append(f"📌 `{var}` = {value}（GetRefineLevel({'+'.join(slots)})）")
        return True

    # V2: single GetRefineLevel(slot)
    m = _RE_REFINE_ASSIGN.match(line)
    if m:
        var, slot = m.groups()
        value = ctx.refine_inputs.get(int(slot), 0)
        variables[var] = value
        trace.append(f"📌 `{var}` = {value}（GetRefineLevel({slot})）")
        return True

    # V3: GetEquipGradeLevel(slot)
    m = _RE_GRADE_ASSIGN.match(line)
    if m:
        var, slot = m.groups()
        value = ctx.grade_value(int(slot))
        variables[var] = value
        trace.append(f"📌 `{var}` = {value}（GetEquipGradeLevel({slot})）")
        return True

    # V4: GetEquipArmorLv(slot)
    m = _RE_ARMOR_ASSIGN.match(line)
    if m:
        var, slot = m.groups()
        value = ctx.armor_level_map.get(int(slot), 0)
        variables[var] = value
        trace.append(f"📌 `{var}` = {value}（GetEquipArmorLv({slot})）")
        return True

    # V5: GetWeaponClass(slot)
    m = _RE_WEAPON_CLASS_ASSIGN.match(line)
    if m:
        var, slot = m.groups()
        value = ctx.weapon_type_map.get(int(slot), 0)
        variables[var] = value
        trace.append(f"📌 `{var}` = {value}（GetWeaponClass({slot})）")
        return True

    # V6: GetEquipWeaponLv(slot)
    m = _RE_WEAPON_LV_ASSIGN.match(line)
    if m:
        var, slot = m.groups()
        value = ctx.weapon_level_map.get(int(slot), 0)
        variables[var] = value
        trace.append(f"📌 `{var}` = {value}（GetEquipWeaponLv({slot})）")
        return True

    # V7: math.floor(expr)
    m = _RE_MATH_FLOOR_ASSIGN.match(line)
    if m:
        var, inner_expr = m.groups()
        value = lua_expr.safe_eval(f"math.floor({inner_expr})", variables, ctx, slot_id)
        if value is None:
            trace.append(f"⚠️ 無法計算 `{var}` = floor({inner_expr})")
        else:
            variables[var] = value
            trace.append(f"📌 `{var}` = {value}（floor({inner_expr})）")
        return True

    # V8: general assignment. Strings/table literals/function defs are not
    # supported and are silently skipped (ro_core.py:1124-1125).
    m = _RE_GENERAL_ASSIGN.match(line)
    if m:
        var, expr = m.groups()
        if any(token in expr for token in ('"', "'", "{", "function")):
            return True
        value = lua_expr.safe_eval(expr, variables, ctx, slot_id)
        if value is None:
            trace.append(f"⚠️ 無法計算 `{var}` = {expr}")
        else:
            variables[var] = value
            trace.append(f"📌 `{var}` = {value}")
        return True

    return False


# =========================================================
# Handler hook (Task 7-9 fill this in)
# =========================================================


def _match_effect_handlers(
    line: str,
    variables: dict,
    ctx: CalcContext,
    slot_id: int | None,
    maps: EffectMaps,
    entries_out: list[EffectEntry],
) -> bool:
    """Placeholder for the ~90-entry effect handler chain (ro_core.py:1144-2350).

    Task 6 skeleton always returns False (no line matches). Tasks 7-9 fill
    this in with the real handlers. NOTE for a future task: the skill-delay
    accumulator (#10, AddSkillDelay/SubSkillDelay) needs to feed the
    ``skill_delay_accum`` dict local to ``parse_effect_block`` — this hook's
    signature will likely need to gain that parameter (or an equivalent
    mutable channel) when Task 7 lands.
    """
    return False


# =========================================================
# Main entry point
# =========================================================


def parse_effect_block(
    block_text: str, ctx: CalcContext, slot_id: int | None, maps: EffectMaps
) -> ParseResult:
    entries_out: list[EffectEntry] = []
    trace: list[str] = []
    variables: dict = {}
    block_stack: list[dict] = []
    skill_delay_accum: dict[str, int] = {}

    for raw in block_text.splitlines():
        original_line = raw.strip()
        line = original_line.split("--")[0].strip()
        # 輸入層接受 Python 習慣的 elif；解析前統一成 Lua elseif。
        line = re.sub(r"^elif\b", "elseif", line)

        if slot_id is not None:
            # GetXXX(GetLocation()) → 當前部位的字面數值代換，並隱性初始化三張
            # map 缺 key 為 0（inventory 狀態副作用#1，ro_core.py:817-858）。
            # 刻意不移植：GetSkillLevel(N) 的行級代換(ro_core.py:843-848) —
            # 技能等級解析統一走 lua_expr 的 ctx.skill_level()（見本檔案 docstring
            # 偏離事項#1）。
            refine_value = ctx.refine_inputs.get(slot_id, 0)
            line = re.sub(r"GetRefineLevel\s*\(\s*GetLocation\s*\(\s*\)\s*\)", str(refine_value), line)

            if slot_id not in ctx.weapon_level_map:
                ctx.weapon_level_map[slot_id] = 0
            line = re.sub(
                r"GetEquipWeaponLv\s*\(\s*GetLocation\s*\(\s*\)\s*\)",
                str(ctx.weapon_level_map.get(slot_id, 0)),
                line,
            )

            if slot_id not in ctx.armor_level_map:
                ctx.armor_level_map[slot_id] = 0
            line = re.sub(
                r"GetEquipArmorLv\s*\(\s*GetLocation\s*\(\s*\)\s*\)",
                str(ctx.armor_level_map.get(slot_id, 0)),
                line,
            )

            if slot_id not in ctx.weapon_type_map:
                ctx.weapon_type_map[slot_id] = 0
            line = re.sub(
                r"GetWeaponClass\s*\(\s*GetLocation\s*\(\s*\)\s*\)",
                str(ctx.weapon_type_map.get(slot_id, 0)),
                line,
            )

        if not line:
            continue

        # ---- if/elseif/else/end state machine ----
        if_match = re.match(r"if\s+(.+?)\s+then", line)
        if if_match:
            _handle_if(if_match, block_stack, entries_out, trace, variables, ctx, slot_id, original_line)
            continue

        elseif_match = re.match(r"elseif\s+(.+?)\s+then", line)
        if elseif_match:
            _handle_elseif(elseif_match, block_stack, entries_out, trace, variables, ctx, slot_id, original_line)
            continue

        else_match = re.match(r"\s*else\b", line)
        if else_match:
            _handle_else(block_stack, entries_out, original_line)
            continue

        end_match = re.match(r"\s*end\b", line)
        if end_match:
            _handle_end(block_stack, entries_out, original_line)
            continue

        # ---- unresolved swallow: any non-control-flow line nested inside an
        # unresolved block is not parsed at all; its raw text is collected on
        # the nearest unresolved ancestor instead. ----
        unresolved_anc = _find_unresolved_ancestor(block_stack)
        if unresolved_anc is not None:
            unresolved_anc["raw_lines"].append(original_line)
            continue

        # ---- P.S / Type+Stat / Stat: ungated by block_stack active state
        # (ro_core.py:863-931) ----
        if line.startswith("P.S ="):
            comment = line.split("=", 1)[1].strip()
            entries_out.append(
                EffectEntry(key="P.S", value=None, unit="", kind=KIND_DESCRIPTIVE, category=CAT_OTHER,
                            extra={"text": comment})
            )
            continue

        type_stat_match = re.match(r'Type\s*=\s*"(.*?)"\s*,\s*Stat\s*=\s*\{(.*?)\}', line)
        if type_stat_match:
            _handle_type_stat(type_stat_match, entries_out)
            continue

        stat_match = re.search(r'Stat\s*=\s*\{([^\}]+)\}', line)
        if stat_match:
            _handle_stat(stat_match, block_text, ctx, slot_id, entries_out)
            # NOTE: no `continue` here — ro_core.py:892-931 falls through to
            # the rest of the dispatch chain after handling Stat={...}; only
            # IGNORE_PREFIXES's "Stat " prefix in the fallback (and, in
            # practice, V8's own brace-skip rule) keeps this from also
            # becoming a bogus UNRECOGNIZED entry. Preserved per task-6 brief.

        # ---- general gate: V1-V8 / handler hook only run when the current
        # block is active. Unlike ro_core.py:1013 (an early silent
        # `continue` that makes the fallback's "not condition_met" branch
        # unreachable dead code), this port lets inactive lines fall through
        # to the fallback below so the ⛔ trace actually fires — required by
        # the task-6 brief/tests (test_if_false_branch_skipped_to_trace).
        # This is the one deliberate behavioral difference in this port; see
        # module docstring point 4. ----
        active = _all_active(block_stack)

        if active:
            if _try_variable_assignment(line, variables, ctx, slot_id, trace):
                continue
            if _match_effect_handlers(line, variables, ctx, slot_id, maps, entries_out):
                continue

        # ---- fallback (ro_core.py:2356-2367) ----
        if not active:
            trace.append(f"⛔ 已跳過（條件不成立）: {original_line}")
            continue

        if original_line.startswith(IGNORE_PREFIXES):
            continue

        entries_out.append(
            EffectEntry(key="無法辨識", value=None, unit="", kind=KIND_UNRECOGNIZED, category=CAT_OTHER,
                        extra={"raw_line": original_line})
        )

    # ---- skill_delay_accum flush (ro_core.py:2370-2375). The dict is always
    # empty in this task's skeleton — Task 7's #10 handler (AddSkillDelay/
    # SubSkillDelay) is what feeds it. ----
    for skill_name, total_ms in skill_delay_accum.items():
        value = round(total_ms / 1000, 2)
        key = f"技能【{skill_name}】冷卻時間"
        entries_out.append(
            EffectEntry(key=key, value=value, unit="秒", kind=KIND_NUMERIC, category=classify_category(key))
        )

    return ParseResult(entries=entries_out, trace=trace)
