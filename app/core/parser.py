"""Effect-block line-scanning state machine.

Ported from ROItemSearchApp's ro_core.py (parse_lua_effects_with_variables).
See docs/superpowers/notes/2026-09-03-effect-parser-inventory.md for the full
section-by-section line-number map this port is based on, and
.superpowers/sdd/2026-09-03-m2-effects/task-6-brief.md for the binding
interfaces and rulings this module implements.

This module started as the M2 "skeleton" (Task 6): line preprocessing, the
P.S/Type+Stat/Stat non-gated lines, the if/elseif/else/end state machine
(extended with the new unresolved-condition mechanism), the V1-V8
variable-assignment handlers, the handler hook, and the fallback.
``_match_effect_handlers`` now implements the 通用段 handlers #1-13
(EnableSkill..ReceiveItem_Equip, Task 7), the 魔法段/物理段 handlers #14-44
(AddSkillMDamage..SetInvestigate, Task 8), and the 補完解析段 handlers #45-68
(AddHealValue..Condition, Task 9) — the full handler chain from
ro_core.py:1144-2350.

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
    CAT_ABILITY,
    CAT_DAMAGE,
    CAT_OTHER,
    CAT_RESIST,
    CAT_SECONDARY,
    EffectEntry,
    KIND_DESCRIPTIVE,
    KIND_NUMERIC,
    KIND_PROC,
    KIND_UNRECOGNIZED,
    KIND_UNRESOLVED,
)
from app.core.maps import EffectMaps

IGNORE_PREFIXES = ("local ", "Stat ", "{Type ", "}", "function")

# AddExtParam/SubExtParam (handler #3) sub-mapping by static_maps.EFFECT_MAP
# id — source: user's 效果分類.xlsx (category-taxonomy branch ruling). Every
# id currently in EFFECT_MAP is covered here; an id NOT in EFFECT_MAP falls
# back to the f"參數{param_id}" display string (handler #3's own fallback)
# and is categorized CAT_OTHER via this dict's own .get() fallback.
EXTPARAM_CATEGORY: dict[int, str] = {
    # CAT_DAMAGE: ATK / ATK% / MATK / MATK%
    41: CAT_DAMAGE, 207: CAT_DAMAGE, 200: CAT_DAMAGE, 140: CAT_DAMAGE,
    # CAT_ABILITY: DEF/MDEF/HIT/FLEE/完全迴避/CRI/ASPD, 六圍, MHP/MSP(%),
    # 攻擊後延遲, POW/STA/WIS/SPL/CON/CRT, P.ATK/S.MATK/RES/MRES, C.RATE/H.PLUS,
    # (2轉以下)攻擊後延遲/(2轉以下)ASPD
    45: CAT_ABILITY, 47: CAT_ABILITY, 49: CAT_ABILITY, 50: CAT_ABILITY,
    51: CAT_ABILITY, 52: CAT_ABILITY, 54: CAT_ABILITY,
    103: CAT_ABILITY, 104: CAT_ABILITY, 105: CAT_ABILITY, 106: CAT_ABILITY,
    107: CAT_ABILITY, 108: CAT_ABILITY,
    109: CAT_ABILITY, 110: CAT_ABILITY, 111: CAT_ABILITY, 112: CAT_ABILITY,
    167: CAT_ABILITY,
    234: CAT_ABILITY, 235: CAT_ABILITY, 236: CAT_ABILITY, 237: CAT_ABILITY,
    238: CAT_ABILITY, 239: CAT_ABILITY,
    242: CAT_ABILITY, 243: CAT_ABILITY, 244: CAT_ABILITY, 245: CAT_ABILITY,
    253: CAT_ABILITY, 254: CAT_ABILITY,
    301: CAT_ABILITY, 302: CAT_ABILITY,
    # CAT_SECONDARY: HP/SP自然恢復%
    113: CAT_SECONDARY, 114: CAT_SECONDARY,
}


def _stat_category(stat_name: str) -> str:
    """Category for Stat={...}/Type+Stat entries — stat-name based (not
    keyword-based matching). 武器/箭矢/砲彈的ATK系欄位算傷害;
    未知{idx} fallback(超出stat_names_list長度, 含STAT_NAME_SETS本身既有的
    「未知7」「未知8」佔位欄位)算other; 其餘(DEF/MDEF/六圍/特性/屬性等)算能力。
    """
    if stat_name in ("武器ATK", "武器MATK", "箭矢/彈藥ATK", "砲彈ATK"):
        return CAT_DAMAGE
    if stat_name.startswith("未知"):
        return CAT_OTHER
    return CAT_ABILITY


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
            EffectEntry(key=name, value=float(val), unit="", kind=KIND_NUMERIC, category=_stat_category(name))
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
                key=stat_name, value=float(val), unit="", kind=KIND_NUMERIC, category=_stat_category(stat_name)
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
# Handler hook (Task 7: 通用段 #1-13. Task 8-9 append more branches to this
# same first-match-wins chain, in ro_core.py:1144-2350 order.)
# =========================================================


def _unrecognized(line: str) -> EffectEntry:
    """Shared UNRECOGNIZED entry for a parameter eval that returned None.

    Binding rule (task-7 brief, 移植轉換規則): whenever a handler's value
    expression can't be resolved (missing context / parse failure), the line
    becomes this structured entry instead of the original's ad-hoc
    "（無法解析）" string suffix — never an exception.
    """
    return EffectEntry(
        key="無法辨識", value=None, unit="", kind=KIND_UNRECOGNIZED, category=CAT_OTHER,
        extra={"raw_line": line},
    )


def _skill_name(maps: EffectMaps, skill_id: int) -> str:
    return maps.skill_map.get(skill_id, f"技能ID {skill_id}")


def _signed(val: float, op: str) -> float:
    return val if op == "Add" else -val


def _map_int_arg_with_id(
    args: list[str] | None,
    index: int,
    mapping: dict,
    fallback_prefix: str,
    variables: dict,
    ctx: CalcContext,
    slot_id: int | None,
) -> tuple[int | None, str]:
    """Map args[index] (evaluated to int) through mapping, with text fallbacks
    (ported from ro_core.py's map_int_arg, ro_core.py:799-809), but also
    returns the resolved int id alongside the mapped name — the #45-68
    batch's (c)-type handlers need both: the name for the key string, the id
    for extra={"target_id": ...} metadata (task-7 移植轉換規則). This is the
    single implementation (no separate lua_expr.map_int_arg — that name-only
    variant was deleted as dead code once every call site here switched to
    this one, which is a strict superset).

    NOTE: the returned id can be None when the id argument itself is
    unresolvable (out of range, or fails both the safe_eval and raw-int
    fallback paths) — every caller passes this straight into
    extra={"target_id": id}, so downstream consumers of EffectEntry.extra
    must tolerate target_id being None, not just the mapped name falling
    back to a fallback_prefix+text string.
    """
    if args is None or index >= len(args):
        return None, f"{fallback_prefix}?"
    try:
        key = int(lua_expr.safe_eval(args[index], variables, ctx, slot_id))
    except Exception:
        try:
            key = int(args[index])
        except Exception:
            return None, f"{fallback_prefix}{args[index]}"
    return key, mapping.get(key, f"{fallback_prefix}{key}")


def _match_effect_handlers(
    line: str,
    variables: dict,
    ctx: CalcContext,
    slot_id: int | None,
    maps: EffectMaps,
    entries_out: list[EffectEntry],
    skill_delay_accum: dict[str, int],
    sfct_state: dict[str, bool],
) -> bool:
    """通用段/魔法段/物理段/補完解析段 handlers #1-68 (ro_core.py:1144-2350).

    Ported top-to-bottom, first-match-wins (mirrors the original's
    `if ... and condition_met: ...; continue` chain — this hook is only
    invoked while the current block is active, so the `condition_met` check
    from the original is already covered by the caller). Every
    `dependencies.register_function(...)` call in the source range is dead
    code (function_defs is never read) and is not ported.

    ``skill_delay_accum`` and ``sfct_state`` are mutable channels owned by
    ``parse_effect_block`` (created once per whole block_text, matching the
    original's function-scope `sfct_handled = False` / `skill_delay_accum =
    {}` at ro_core.py:572-573 — NOT reset per if/elseif branch).

    #14-44 (魔法段/物理段, ro_core.py:1427-1836), every branch that calls
    `lua_expr.safe_eval(...)` on an expression argument (i.e. all of them
    EXCEPT #36/#37/#42/#43/#44, which are either DESCRIPTIVE with no value,
    constants, or take a literal digits-only regex capture with no eval step): the
    original's `safe_eval_expr` always pads a missing value with 0 and
    returns a number, so none of these branches have an `isinstance`/None
    check of their own. This port's `lua_expr.safe_eval` CAN return None —
    per the task-7 binding rule ("None → UNRECOGNIZED, no exceptions",
    reaffirmed for this batch by the task-8 brief), every such handler gets a
    `val is None` guard added even though the original has none. Not called
    out per-handler below beyond this note, to avoid repeating the same
    justification ~25 times.

    #45-68 (補完解析段, ro_core.py:1884-2350, Task 9): same "None →
    UNRECOGNIZED" rule applies throughout. This section additionally ports
    ro_core.py's own `split_lua_args`/`eval_lua_arg`/`map_int_arg` helpers
    (`split_lua_args`/`eval_lua_arg` on `lua_expr`; `map_int_arg` as this
    module's `_map_int_arg_with_id`, which also surfaces the resolved id for
    extra={"target_id": ...} — the only implementation, see its own
    docstring) for the handlers whose original regex captured the whole raw
    args_text into one group
    instead of one group per argument — ported in that shape for 逐字移植
    fidelity rather than restructured into #1-44's per-argument-group style.
    See the section banner comment below for the one sign-inversion quirk
    (#57 AddRaceTolerace/SubRaceTolerace) and other batch-specific notes.
    """
    # 1. EnableSkill(skill_id, level)
    m = re.match(r"EnableSkill\((\d+),\s*(\d+)\)", line)
    if m:
        skill_id, level = int(m.group(1)), int(m.group(2))
        skill_name = _skill_name(maps, skill_id)
        key = f"可使用【{skill_name}】Lv.{level}"
        entries_out.append(
            EffectEntry(key=key, value=None, unit="", kind=KIND_DESCRIPTIVE, category=CAT_SECONDARY,
                        extra={"target_kind": "skill", "target_id": skill_id, "level": level})
        )
        ctx.enabled_skill_levels[skill_id] = level
        return True

    # 2. UseSkill(skill_id)
    m = re.match(r"UseSkill\(\s*(\d+)\s*\)", line)
    if m:
        skill_id = int(m.group(1))
        skill_name = _skill_name(maps, skill_id)
        key = f"使用【{skill_name}】"
        entries_out.append(
            EffectEntry(key=key, value=None, unit="", kind=KIND_DESCRIPTIVE, category=CAT_SECONDARY,
                        extra={"target_kind": "skill", "target_id": skill_id})
        )
        ctx.used_skill_levels[skill_id] = True
        return True

    # 3a-c. AddExtParam / SubExtParam(unit, param_id, value_expr)
    m = re.match(r"(Add|Sub)ExtParam\((\d+),\s*(\d+),\s*(.+)\)", line)
    if m:
        op, _unit, param_id, val_expr = m.groups()
        val = lua_expr.safe_eval(val_expr, variables, ctx, slot_id)
        param_id_int = int(param_id)
        effect_str = static_maps.EFFECT_MAP.get(param_id_int, f"參數{param_id}")
        # Category is looked up by effect_map id (EXTPARAM_CATEGORY), NOT by
        # effect_str keyword matching — an id missing from EFFECT_MAP (the
        # f"參數{param_id}" fallback above) also misses EXTPARAM_CATEGORY and
        # falls back to CAT_OTHER here.
        category = EXTPARAM_CATEGORY.get(param_id_int, CAT_OTHER)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True

        # 3a: CRI / 完全迴避 — value is per-10 (原碼 val // 10)
        if effect_str in ("CRI", "完全迴避"):
            v = float(int(val) // 10)
            entries_out.append(
                EffectEntry(key=effect_str, value=_signed(v, op), unit="", kind=KIND_NUMERIC,
                            category=category)
            )
            return True

        # 3b: 攻擊後延遲類 — sign INVERTED (Add=減少/-、Sub=增加/+), always %
        if effect_str in ("攻擊後延遲", "(2轉以下)攻擊後延遲"):
            signed = -val if op == "Add" else val
            entries_out.append(
                EffectEntry(key=effect_str, value=signed, unit="%", kind=KIND_NUMERIC,
                            category=category)
            )
            return True

        # 3c: 一般情況 — % 只在 effect_map 名稱本身以 % 結尾時附加
        percent_suffix = "%" if str(effect_str).endswith("%") else ""
        entries_out.append(
            EffectEntry(key=effect_str, value=_signed(val, op), unit=percent_suffix, kind=KIND_NUMERIC,
                        category=category)
        )
        return True

    # 4. AddSpellDelay / SubSpellDelay(value_expr) — 技能後延遲 %
    m = re.match(r"(Add|Sub)SpellDelay\(\s*(.+)\s*\)\s*$", line)
    if m:
        op, expr = m.groups()
        val = lua_expr.safe_eval(expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "技能後延遲"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_ABILITY)
        )
        return True

    # 5. AddSpellCastTime / SubSpellCastTime(value_expr) — 變動詠唱時間 %
    m = re.match(r"(Add|Sub)SpellCastTime\(\s*(.+)\s*\)", line)
    if m:
        op, value_expr = m.groups()
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "變動詠唱時間"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_ABILITY)
        )
        return True

    # 6. AddSFCTEquipAmount / SubSFCTEquipAmount(item_id?, ms_expr, dummy) —
    # 固定詠唱時間 秒 (ms/1000). sfct_handled once-lock: ASYMMETRIC in the
    # original, ported as-is (ruling: restore original behavior, not the
    # symmetric lock this port previously had). ro_core.py:1264 (#6) checks
    # `not sfct_handled` AND ro_core.py:1276 sets `sfct_handled = True` after
    # emitting — #6 is the only branch that ever sets the lock.
    m = re.match(r"(Add|Sub)SFCTEquipAmount\(\s*(?:(\d+)\s*,\s*)?(.+?)\s*,\s*(\d+)\s*\)\s*$", line)
    if m and not sfct_state["handled"]:
        op, _item_id, expr, _dummy = m.groups()
        val_ms = lua_expr.safe_eval(expr, variables, ctx, slot_id)
        sfct_state["handled"] = True
        if val_ms is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "固定詠唱時間"
        entries_out.append(
            EffectEntry(key=key, value=round(_signed(val_ms, op) / 1000, 2), unit="秒", kind=KIND_NUMERIC,
                        category=CAT_ABILITY)
        )
        return True

    # 7. AddSFCTEquipPermill / SubSFCTEquipPermill(item_id?, permill_expr, dummy) —
    # 固定詠唱時間 % (permill/10). ro_core.py:1283 checks `not sfct_handled`
    # (so a prior #6 match blocks this) but ro_core.py:1283-1297's own body
    # NEVER sets `sfct_handled = True` — this branch alone can never trip the
    # lock. Consequence (verified against the source, not a guess): a #7
    # line followed by a #6 line both emit (the #7 line never locked
    # anything); a #6 line followed by a #7 line — only #6 emits (the #6
    # line already tripped the lock). Deliberately asymmetric; do not
    # "fix" by adding `sfct_state["handled"] = True` here.
    m = re.match(r"(Add|Sub)SFCTEquipPermill\(\s*(?:(\d+)\s*,\s*)?(.+?)\s*,\s*(\d+)\s*\)\s*$", line)
    if m and not sfct_state["handled"]:
        op, _item_id, expr, _dummy = m.groups()
        val = lua_expr.safe_eval(expr, variables, ctx, slot_id)
        if val is None:
            # Deliberate fix vs literal transliteration: the original does
            # `val = val // 10` BEFORE checking whether `val` parsed, which
            # would raise TypeError on a None safe_eval_expr result. The
            # binding "no exceptions" rule takes priority here.
            entries_out.append(_unrecognized(line))
            return True
        v = int(val) // 10
        key = "固定詠唱時間"
        entries_out.append(
            EffectEntry(key=key, value=float(_signed(v, op)), unit="%", kind=KIND_NUMERIC,
                        category=CAT_ABILITY)
        )
        return True

    # 8. AddDamage_SKID / SubDamage_SKID(1, skill_id, value_expr) — 技能傷害(裝備段) %
    m = re.match(r"(Add|Sub)Damage_SKID\(\s*1\s*,\s*(\d+)\s*,\s*(.+)\s*\)\s*$", line)
    if m:
        op, skill_id, value_expr = m.groups()
        skill_id = int(skill_id)
        skill_name = _skill_name(maps, skill_id)
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"技能【{skill_name}】傷害(裝備段)"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_DAMAGE, extra={"target_kind": "skill", "target_id": skill_id})
        )
        return True

    # 9. AddDamage_passive_SKID / SubDamage_passive_SKID(1, skill_id, value_expr) —
    # 技能傷害(技能段) %
    m = re.match(r"(Add|Sub)Damage_passive_SKID\(\s*1\s*,\s*(\d+)\s*,\s*(.+)\s*\)\s*$", line)
    if m:
        op, skill_id, value_expr = m.groups()
        skill_id = int(skill_id)
        skill_name = _skill_name(maps, skill_id)
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"技能【{skill_name}】傷害(技能段)"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_DAMAGE, extra={"target_kind": "skill", "target_id": skill_id})
        )
        return True

    # 10. AddSkillDelay / SubSkillDelay(skill_id, ms_expr) — 累加, 無即時條目;
    # flush 由 parse_effect_block 結尾統一輸出(技能【X】冷卻時間, 秒).
    m = re.match(r"(Add|Sub)SkillDelay\(\s*(\d+)\s*,\s*(.+)\s*\)", line)
    if m:
        op, skill_id, delay_expr = m.groups()
        skill_id = int(skill_id)
        skill_name = _skill_name(maps, skill_id)
        val_ms = lua_expr.safe_eval(delay_expr, variables, ctx, slot_id)
        if val_ms is None:
            entries_out.append(_unrecognized(line))
            return True
        delta = val_ms if op == "Add" else -val_ms
        skill_delay_accum[skill_name] = skill_delay_accum.get(skill_name, 0) + delta
        return True

    # 11. AddSpecificSpellCastTime / SubSpecificSpellCastTime(skill_id, value_expr) —
    # 技能【X】變動詠唱時間 %
    m = re.match(r"(Add|Sub)SpecificSpellCastTime\(\s*(\d+)\s*,\s*(.+)\s*\)", line)
    if m:
        op, skill_id, value_expr = m.groups()
        skill_id = int(skill_id)
        skill_name = _skill_name(maps, skill_id)
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"技能【{skill_name}】變動詠唱時間"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_ABILITY, extra={"target_kind": "skill", "target_id": skill_id})
        )
        return True

    # 12. AddEXPPercent_KillRace / SubEXPPercent_KillRace(race_id, value_expr) —
    # 從{race}型怪的經驗值 %
    m = re.match(r"(Add|Sub)EXPPercent_KillRace\(\s*(\d+)\s*,\s*(.+)\s*\)", line)
    if m:
        op, race_id, value_expr = m.groups()
        race_id = int(race_id)
        race_name = static_maps.RACE_MAP.get(race_id, f"種族{race_id}")
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            # Deliberate fix vs literal transliteration: the original never
            # checked isinstance(val, int) here and would emit a "None%"
            # string on parse failure. Binding "no exceptions / None→
            # UNRECOGNIZED" rule takes priority.
            entries_out.append(_unrecognized(line))
            return True
        key = f"從 {race_name} 型怪的經驗值"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_SECONDARY, extra={"target_kind": "race", "target_id": race_id})
        )
        return True

    # 13. AddReceiveItem_Equip / SubReceiveItem_Equip(value_expr) — 掉寶率 %
    m = re.match(r"(Add|Sub)ReceiveItem_Equip\(\s*(.+?)\s*\)", line)
    if m:
        op, value_expr = m.groups()
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "掉寶率"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC, category=CAT_SECONDARY)
        )
        return True

    # =====================================================
    # 魔法段 (ro_core.py:1418-1580)
    # =====================================================

    # 14. AddSkillMDamage / SubSkillMDamage(elem_id, value_expr) — {屬性}的魔法傷害 %
    m = re.match(r"(Add|Sub)SkillMDamage\(\s*(\d+)\s*,\s*(.+)\s*\)", line)
    if m:
        op, elem_id, value_expr = m.groups()
        elem_id = int(elem_id)
        element = static_maps.ELEMENT_MAP.get(elem_id, f"屬性{elem_id}")
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"{element} 的魔法傷害"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_DAMAGE, extra={"target_kind": "element", "target_id": elem_id})
        )
        return True

    # 15. AddMDamage_Size / SubMDamage_Size(1, size_id, value_expr) —
    # 對{體型}敵人的魔法傷害 %。size_map miss fallback f"尺寸{size_id}" (ro_core.py:1451).
    m = re.match(r"(Add|Sub)MDamage_Size\(\s*1\s*,\s*(\d+)\s*,\s*(.+)\s*\)", line)
    if m:
        op, size_id, value_expr = m.groups()
        size_id = int(size_id)
        size_name = static_maps.SIZE_MAP.get(size_id, f"尺寸{size_id}")
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"對 {size_name} 敵人的魔法傷害"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_DAMAGE, extra={"target_kind": "size", "target_id": size_id})
        )
        return True

    # 16. AddMdamage_Race / SubMdamage_Race(race_id, value_expr) — 對{種族}型怪的魔法傷害 %
    m = re.match(r"(Add|Sub)Mdamage_Race\(\s*(\d+)\s*,\s*(.+)\s*\)", line)
    if m:
        op, race_id, value_expr = m.groups()
        race_id = int(race_id)
        race_name = static_maps.RACE_MAP.get(race_id, f"種族{race_id}")
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"對 {race_name} 型怪的魔法傷害"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_DAMAGE, extra={"target_kind": "race", "target_id": race_id})
        )
        return True

    # 17. AddMDamage_Property / SubMDamage_Property(1, elem_id, value_expr) —
    # 對{屬性}對象的魔法傷害 %
    m = re.match(r"(Add|Sub)MDamage_Property\(\s*1\s*,\s*(\d+)\s*,\s*(.+)\s*\)", line)
    if m:
        op, elem_id, value_expr = m.groups()
        elem_id = int(elem_id)
        elem_name = static_maps.ELEMENT_MAP.get(elem_id, f"屬性{elem_id}")
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"對 {elem_name} 對象的魔法傷害"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_DAMAGE, extra={"target_kind": "element", "target_id": elem_id})
        )
        return True

    # 18. AddMdamage_Class / SubMdamage_Class(class_id, value_expr) — 對{階級}階級的魔法傷害 %
    m = re.match(r"(Add|Sub)Mdamage_Class\(\s*(\d+)\s*,\s*(.+?)\s*\)", line)
    if m:
        op, class_id, value_expr = m.groups()
        class_id = int(class_id)
        class_name = static_maps.CLASS_MAP.get(class_id, f"階級{class_id}")
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"對 {class_name} 階級的魔法傷害"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_DAMAGE, extra={"target_kind": "class", "target_id": class_id})
        )
        return True

    # 19. SetIgnoreMdefClass(class_id, value_expr) — 無視{階級}階級的魔法防禦 %
    # (no Add/Sub prefix, no sign in the original — value used as-is)
    m = re.match(r"SetIgnoreMdefClass\((\d+),\s*(.+?)\)", line)
    if m:
        class_id, value_expr = m.groups()
        class_id = int(class_id)
        class_name = static_maps.CLASS_MAP.get(class_id, f"階級{class_id}")
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"無視 {class_name} 階級的魔法防禦"
        entries_out.append(
            EffectEntry(key=key, value=val, unit="%", kind=KIND_NUMERIC,
                        category=CAT_DAMAGE, extra={"target_kind": "class", "target_id": class_id})
        )
        return True

    # 20. SetIgnoreMdefRace(race_id, value_expr) — 無視{種族}型怪的魔法防禦 %
    m = re.match(r"SetIgnoreMdefRace\((\d+),\s*(.+?)\)", line)
    if m:
        race_id, value_expr = m.groups()
        race_id = int(race_id)
        race_name = static_maps.RACE_MAP.get(race_id, f"種族{race_id}")
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"無視 {race_name} 型怪的魔法防禦"
        entries_out.append(
            EffectEntry(key=key, value=val, unit="%", kind=KIND_NUMERIC,
                        category=CAT_DAMAGE, extra={"target_kind": "race", "target_id": race_id})
        )
        return True

    # 21. AddIgnore_MRES_RacePercent / SubIgnore_MRES_RacePercent(race_id, value_expr) —
    # 無視{種族}型怪的魔法抗性 ±%
    m = re.match(r"(Add|Sub)Ignore_MRES_RacePercent\((\d+),\s*(.+?)\)", line)
    if m:
        op, race_id, value_expr = m.groups()
        race_id = int(race_id)
        race_name = static_maps.RACE_MAP.get(race_id, f"種族{race_id}")
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"無視 {race_name} 型怪的魔法抗性"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_DAMAGE, extra={"target_kind": "race", "target_id": race_id})
        )
        return True

    # 22. MonsterMAtkPercent(value_expr) — 特定魔物魔法增傷 +N% (always positive;
    # anchored re.match means this never catches a "SubMonsterMAtkPercent(...)"
    # line, so handler #23 below does not need to run first).
    m = re.match(r"MonsterMAtkPercent\(\s*(.+)\s*\)", line)
    if m:
        val = lua_expr.safe_eval(m.group(1), variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "特定魔物魔法增傷"
        entries_out.append(
            EffectEntry(key=key, value=val, unit="%", kind=KIND_NUMERIC, category=CAT_DAMAGE)
        )
        return True

    # 23. SubMonsterMAtkPercent(value_expr) — 特定魔物魔法增傷 -N%
    m = re.match(r"SubMonsterMAtkPercent\(\s*(.+)\s*\)", line)
    if m:
        val = lua_expr.safe_eval(m.group(1), variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "特定魔物魔法增傷"
        entries_out.append(
            EffectEntry(key=key, value=-val, unit="%", kind=KIND_NUMERIC, category=CAT_DAMAGE)
        )
        return True

    # =====================================================
    # 物理段 (ro_core.py:1584-1857)
    # =====================================================

    # 24. WeaponMasteryATK(value_expr) — 修煉ATK +N (no % unit, always positive)
    m = re.match(r"WeaponMasteryATK\(\s*(.+?)\s*\)", line)
    if m:
        val = lua_expr.safe_eval(m.group(1), variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "修煉ATK"
        entries_out.append(
            EffectEntry(key=key, value=val, unit="", kind=KIND_NUMERIC, category=CAT_DAMAGE)
        )
        return True

    # 25. Kamui_SpecialATK(value_expr) — 神威ATK +N (no % unit, always positive)
    m = re.match(r"Kamui_SpecialATK\(\s*(.+?)\s*\)", line)
    if m:
        val = lua_expr.safe_eval(m.group(1), variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "神威ATK"
        entries_out.append(
            EffectEntry(key=key, value=val, unit="", kind=KIND_NUMERIC, category=CAT_DAMAGE)
        )
        return True

    # 26. AddGuideAttack(value_expr) — 誘導攻擊機率 +N% (always positive)
    m = re.match(r"AddGuideAttack\(\s*(.+?)\s*\)", line)
    if m:
        val = lua_expr.safe_eval(m.group(1), variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "誘導攻擊機率"
        entries_out.append(
            EffectEntry(key=key, value=val, unit="%", kind=KIND_NUMERIC, category=CAT_DAMAGE)
        )
        return True

    # 27. AddDamage_HIT / SubDamage_HIT(1, value_expr) — 物理命中傷害 ±N%
    m = re.match(r"(Add|Sub)Damage_HIT\(\s*1\s*,\s*(.+)\)", line)
    if m:
        op, value_expr = m.groups()
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "物理命中傷害"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC, category=CAT_DAMAGE)
        )
        return True

    # 28. AddMeleeAttackDamage / SubMeleeAttackDamage(1, value_expr) — 近距離物理傷害 ±N%
    m = re.match(r"(Add|Sub)MeleeAttackDamage\(\s*1\s*,\s*(.+)\)", line)
    if m:
        op, value_expr = m.groups()
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "近距離物理傷害"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC, category=CAT_DAMAGE)
        )
        return True

    # 29. AddRangeAttackDamage / SubRangeAttackDamage(1, value_expr) — 遠距離物理傷害 ±N%
    m = re.match(r"(Add|Sub)RangeAttackDamage\(\s*1\s*,\s*(.+)\)", line)
    if m:
        op, value_expr = m.groups()
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "遠距離物理傷害"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC, category=CAT_DAMAGE)
        )
        return True

    # 30. AddBowAttackDamage(1, value_expr) — 弓攻擊力 +N% (always positive; no
    # Sub variant in the original — the commented-out SubBowAttackDamage at
    # ro_core.py:2288-2296 is dead code, not ported per inventory doc §死碼).
    m = re.match(r"AddBowAttackDamage\(\s*1\s*,\s*(.+)\)", line)
    if m:
        val = lua_expr.safe_eval(m.group(1), variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "弓攻擊力"
        entries_out.append(
            EffectEntry(key=key, value=val, unit="%", kind=KIND_NUMERIC, category=CAT_DAMAGE)
        )
        return True

    # 31. AddDamage_CRI / SubDamage_CRI(1, value_expr) — 爆擊傷害 ±N%
    m = re.match(r"(Add|Sub)Damage_CRI\(\s*1\s*,\s*(.+)\)", line)
    if m:
        op, value_expr = m.groups()
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "爆擊傷害"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC, category=CAT_DAMAGE)
        )
        return True

    # 32. AddDamage_Size / SubDamage_Size(1, size_id, value_expr) — 對{體型}敵人的物理傷害 ±N%.
    # size_map miss fallback f"體型{size_id}" (ro_core.py:1706) — deliberately
    # DIFFERENT from #15's f"尺寸{size_id}" fallback; the original itself is
    # inconsistent here, ported verbatim per-handler.
    m = re.match(r"(Add|Sub)Damage_Size\(\s*1\s*,\s*(\d+)\s*,\s*(.+)\s*\)", line)
    if m:
        op, size_id, value_expr = m.groups()
        size_id = int(size_id)
        size_name = static_maps.SIZE_MAP.get(size_id, f"體型{size_id}")
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"對 {size_name} 敵人的物理傷害"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_DAMAGE, extra={"target_kind": "size", "target_id": size_id})
        )
        return True

    # 33. RaceAddDamage / RaceSubDamage(race_id, value_expr) — 對{種族}型怪的物理傷害 ±N%
    m = re.match(r"Race(Add|Sub)Damage\(\s*(\d+)\s*,\s*(.+)\s*\)\s*$", line)
    if m:
        op, race_id, value_expr = m.groups()
        race_id = int(race_id)
        race_name = static_maps.RACE_MAP.get(race_id, f"種族{race_id}")
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"對 {race_name} 型怪的物理傷害"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_DAMAGE, extra={"target_kind": "race", "target_id": race_id})
        )
        return True

    # 34. AddDamage_Property / SubDamage_Property(1, elem_id, value_expr) —
    # 對{屬性}對象的物理傷害 ±N%
    m = re.match(r"(Add|Sub)Damage_Property\(\s*1\s*,\s*(\d+)\s*,\s*(.+)\s*\)", line)
    if m:
        op, elem_id, value_expr = m.groups()
        elem_id = int(elem_id)
        elem_name = static_maps.ELEMENT_MAP.get(elem_id, f"屬性{elem_id}")
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"對 {elem_name} 對象的物理傷害"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_DAMAGE, extra={"target_kind": "element", "target_id": elem_id})
        )
        return True

    # 35. ClassAddDamage / ClassSubDamage(class_id, 1, value_expr) — 對{階級}階級的物理傷害 ±N%
    m = re.match(r"Class(Add|Sub)Damage\(\s*(\d+)\s*,\s*1\s*,\s*(.+?)\s*\)", line)
    if m:
        op, class_id, value_expr = m.groups()
        class_id = int(class_id)
        class_name = static_maps.CLASS_MAP.get(class_id, f"階級{class_id}")
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"對 {class_name} 階級的物理傷害"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_DAMAGE, extra={"target_kind": "class", "target_id": class_id})
        )
        return True

    # 36. SetIgnoreDEFClass(class_id) — 無視{階級}階級的物理防禦 (DESCRIPTIVE, no value —
    # the original emits no percentage at all here, unlike #37/#42).
    m = re.match(r"SetIgnoreDEFClass\((\d+)\)", line)
    if m:
        class_id = int(m.group(1))
        class_name = static_maps.CLASS_MAP.get(class_id, f"階級{class_id}")
        key = f"無視 {class_name} 階級的物理防禦"
        entries_out.append(
            EffectEntry(key=key, value=None, unit="", kind=KIND_DESCRIPTIVE,
                        category=CAT_DAMAGE, extra={"target_kind": "class", "target_id": class_id})
        )
        return True

    # 37. SetIgnoreDefClass_Percent(class_id, value) — 無視{階級}階級的物理防禦 N%.
    # `value` is captured directly as \d+ by the regex (the original doesn't
    # run this one through safe_eval_expr either) — always resolves, no
    # None-safety needed. No sign (value used as-is, always non-negative).
    m = re.match(r"SetIgnoreDefClass_Percent\((\d+),\s*(\d+)\)", line)
    if m:
        class_id, value = m.groups()
        class_id = int(class_id)
        class_name = static_maps.CLASS_MAP.get(class_id, f"階級{class_id}")
        key = f"無視 {class_name} 階級的物理防禦"
        entries_out.append(
            EffectEntry(key=key, value=float(value), unit="%", kind=KIND_NUMERIC,
                        category=CAT_DAMAGE, extra={"target_kind": "class", "target_id": class_id})
        )
        return True

    # 38. SetIgnoreDefRace_Percent(race_id, value_expr) — 無視{種族}型怪的物理防禦 N%
    # (no Add/Sub prefix, no sign — value used as-is, same shape as #19/#20)
    m = re.match(r"SetIgnoreDefRace_Percent\((\d+),\s*(.+?)\)", line)
    if m:
        race_id, value_expr = m.groups()
        race_id = int(race_id)
        race_name = static_maps.RACE_MAP.get(race_id, f"種族{race_id}")
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"無視 {race_name} 型怪的物理防禦"
        entries_out.append(
            EffectEntry(key=key, value=val, unit="%", kind=KIND_NUMERIC,
                        category=CAT_DAMAGE, extra={"target_kind": "race", "target_id": race_id})
        )
        return True

    # 39. AddIgnore_RES_RacePercent / SubIgnore_RES_RacePercent(race_id, value_expr) —
    # 無視{種族}型怪的物理抗性 ±N%
    m = re.match(r"(Add|Sub)Ignore_RES_RacePercent\((\d+),\s*(.+?)\)", line)
    if m:
        op, race_id, value_expr = m.groups()
        race_id = int(race_id)
        race_name = static_maps.RACE_MAP.get(race_id, f"種族{race_id}")
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"無視 {race_name} 型怪的物理抗性"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_DAMAGE, extra={"target_kind": "race", "target_id": race_id})
        )
        return True

    # 40. MonsterAtkPercent(value_expr) — 特定魔物物理增傷 +N% (always positive;
    # anchored re.match means this never catches a "SubMonsterAtkPercent(...)"
    # line, so handler #41 below does not need to run first).
    m = re.match(r"MonsterAtkPercent\(\s*(.+)\s*\)", line)
    if m:
        val = lua_expr.safe_eval(m.group(1), variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "特定魔物物理增傷"
        entries_out.append(
            EffectEntry(key=key, value=val, unit="%", kind=KIND_NUMERIC, category=CAT_DAMAGE)
        )
        return True

    # 41. SubMonsterAtkPercent(value_expr) — 特定魔物物理增傷 -N%
    m = re.match(r"SubMonsterAtkPercent\(\s*(.+)\s*\)", line)
    if m:
        val = lua_expr.safe_eval(m.group(1), variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "特定魔物物理增傷"
        entries_out.append(
            EffectEntry(key=key, value=-val, unit="%", kind=KIND_NUMERIC, category=CAT_DAMAGE)
        )
        return True

    # 42. SetIgnoreDEFRace(race_id) — 無視{種族}型怪的物理防禦 +100% (constant, NUMERIC).
    m = re.match(r"SetIgnoreDEFRace\((\d+)\)", line)
    if m:
        race_id = int(m.group(1))
        race_name = static_maps.RACE_MAP.get(race_id, f"種族{race_id}")
        key = f"無視 {race_name} 型怪的物理防禦"
        entries_out.append(
            EffectEntry(key=key, value=100.0, unit="%", kind=KIND_NUMERIC,
                        category=CAT_DAMAGE, extra={"target_kind": "race", "target_id": race_id})
        )
        return True

    # 43. PerfectDamage(1) — 武器體型修正 100% (DESCRIPTIVE constant; original
    # literal string ro_core.py:1849 is "武器體型修正 100%" with a space before
    # the number — the inventory doc's own summary line drops that space,
    # ported the literal source string instead).
    m = re.match(r"PerfectDamage\(1\)\s*$", line)
    if m:
        key = "武器體型修正 100%"
        entries_out.append(
            EffectEntry(key=key, value=None, unit="", kind=KIND_DESCRIPTIVE, category=CAT_DAMAGE)
        )
        return True

    # 44. SetInvestigate() — 浸透勁 (DESCRIPTIVE) + 全種族無視物防+100% (NUMERIC, like #42).
    # Deliberate regex fix vs ro_core.py:1852: the original's
    # `re.match(r"SetInvestigate()", line)` has an EMPTY capture group —
    # `()` in regex is a zero-width empty group, not a literal `()` — so the
    # pattern is equivalent to a bare `SetInvestigate` prefix match (it would
    # also match e.g. "SetInvestigateXYZ" as a prefix). Fixed here to require
    # an actual empty-argument call. The commented-out
    # `context.used_skill_levels[266] = True` (ro_core.py:1856) is dead code
    # moved to the calculation layer by the original author — NOT ported
    # (inventory doc 狀態副作用#7).
    m = re.match(r"SetInvestigate\s*\(\s*\)", line)
    if m:
        entries_out.append(
            EffectEntry(key="武器浸透勁效果", value=None, unit="", kind=KIND_DESCRIPTIVE,
                        category=CAT_DAMAGE)
        )
        key2 = "無視 全種族 型怪的物理防禦"
        entries_out.append(
            EffectEntry(key=key2, value=100.0, unit="%", kind=KIND_NUMERIC, category=CAT_DAMAGE)
        )
        return True

    # =====================================================
    # 補完解析段 (ro_core.py:1884-2350, Task 9). Unlike #1-44 (which capture
    # each argument via its own regex group and call lua_expr.safe_eval
    # directly on it), most of this batch mirrors the ORIGINAL's own code
    # shape: a single regex group captures the whole raw args_text, which is
    # then split via lua_expr.split_lua_args and picked apart with
    # lua_expr.eval_lua_arg (ro_core.py's own eval_lua_arg, ported to
    # app/core/lua_expr.py ahead of this task specifically for this section)
    # and this module's own _map_int_arg_with_id (ro_core.py's map_int_arg —
    # kept here rather than on lua_expr since every call site needs the
    # resolved id too, not just the mapped name; see its docstring) — ported
    # this way deliberately for 逐字移植 fidelity, not simplified into the
    # #1-44 shape, since the original itself chose this shape for these
    # handlers. A handful (#51/52/55/56/58/59/60/66) still used direct
    # per-argument regex groups in the original and are ported in the #1-44
    # shape accordingly.
    #
    # eval_lua_arg(args, index, default, ...) returns `default` only when
    # `index` is out of range (argument not supplied) — it returns None when
    # the argument IS present but lua_expr.safe_eval couldn't resolve it. Both
    # cases funnel through this same call, so a `val is None` check after
    # calling it with a non-None default (0) is still exactly the task-7
    # binding "None → UNRECOGNIZED" guard; it is only skipped for id/name
    # lookups (_map_int_arg_with_id), which — like the original's map_int_arg
    # — never fail: they degrade to a fallback_prefix+text/id string instead,
    # matching ro_core.py:799-809.
    # =====================================================

    # 45. AddHealValue / SubHealValue(value) — 治癒量 ±N%
    m = re.match(r"(Add|Sub)HealValue\s*\((.*)\)\s*$", line)
    if m:
        op, args_text = m.groups()
        args = lua_expr.split_lua_args(args_text)
        val = lua_expr.eval_lua_arg(args, 0, 0, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "治癒量"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC, category=CAT_SECONDARY)
        )
        return True

    # 46. AddHealModifyPercent / SubHealModifyPercent(value) — 被治癒量 ±N%
    m = re.match(r"(Add|Sub)HealModifyPercent\s*\((.*)\)\s*$", line)
    if m:
        op, args_text = m.groups()
        args = lua_expr.split_lua_args(args_text)
        val = lua_expr.eval_lua_arg(args, 0, 0, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "被治癒量"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC, category=CAT_SECONDARY)
        )
        return True

    # 47a/b. (Add|Sub)(HP|SP)drain(rate[, amount]) — single-arg: {pool}吸收
    # ±N% (one entry); two-arg: {pool}吸收機率 ±N% + {pool}吸收量 ±N% (TWO
    # entries). Branch on len(args) rather than "amount is None". In the
    # ORIGINAL, eval_lua_arg's None only ever meant "no 2nd arg" — a
    # present-but-unresolvable arg came back as an error-suffixed STRING, not
    # None, so `amount is None` was unambiguous there. The ambiguity is a
    # side effect of THIS port's Task-5 deliberate change (lua_expr.safe_eval
    # returns None on any resolution failure, not just "missing"), which
    # makes eval_lua_arg's out-of-range `default=None` collide with a
    # present-but-failed 2nd arg. len(args) sidesteps that collision so a
    # present-but-unresolvable amount correctly becomes its own UNRECOGNIZED
    # entry instead of silently degrading to single-arg mode.
    m = re.match(r"(Add|Sub)(HP|SP)drain\s*\((.*)\)\s*$", line)
    if m:
        op, pool, args_text = m.groups()
        args = lua_expr.split_lua_args(args_text)
        rate = lua_expr.eval_lua_arg(args, 0, 0, variables, ctx, slot_id)
        if rate is None:
            entries_out.append(_unrecognized(line))
            return True
        if len(args) < 2:
            key = f"{pool}吸收"
            entries_out.append(
                EffectEntry(key=key, value=_signed(rate, op), unit="%", kind=KIND_NUMERIC,
                            category=CAT_SECONDARY)
            )
            return True
        amount = lua_expr.eval_lua_arg(args, 1, None, variables, ctx, slot_id)
        if amount is None:
            entries_out.append(_unrecognized(line))
            return True
        key_rate = f"{pool}吸收機率"
        key_amount = f"{pool}吸收量"
        entries_out.append(
            EffectEntry(key=key_rate, value=_signed(rate, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_SECONDARY)
        )
        entries_out.append(
            EffectEntry(key=key_amount, value=_signed(amount, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_SECONDARY)
        )
        return True

    # 48. AddSPconsumption / SubSPconsumption(value) — SP消耗 ±N%
    m = re.match(r"(Add|Sub)SPconsumption\s*\((.*)\)\s*$", line)
    if m:
        op, args_text = m.groups()
        args = lua_expr.split_lua_args(args_text)
        val = lua_expr.eval_lua_arg(args, 0, 0, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "SP消耗"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC, category=CAT_SECONDARY)
        )
        return True

    # 49. add/subspconsumption(value, skill_id) — LOWERCASE function name in
    # the original (ro_core.py:1938, deliberately distinct from #48's
    # Add/SubSPconsumption); re.match is case-sensitive so the two never
    # collide regardless of dispatch order. 技能【X】SP消耗 ±N%
    m = re.match(r"(add|sub)spconsumption\s*\((.*)\)\s*$", line)
    if m:
        op, args_text = m.groups()
        args = lua_expr.split_lua_args(args_text)
        val = lua_expr.eval_lua_arg(args, 0, 0, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        try:
            skill_id = int(lua_expr.eval_lua_arg(args, 1, 0, variables, ctx, slot_id))
        except Exception:
            skill_id = 0
        skill_name = _skill_name(maps, skill_id)
        key = f"技能【{skill_name}】SP消耗"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op.capitalize()), unit="%", kind=KIND_NUMERIC,
                        category=CAT_SECONDARY, extra={"target_kind": "skill", "target_id": skill_id})
        )
        return True

    # 50. AddSkillSP / SubSkillSP(skill_id, value) — 技能【X】SP消耗 ±N (NO %
    # unit — ro_core.py:1966's f-string has no trailing % unlike #49's).
    m = re.match(r"(Add|Sub)SkillSP\s*\((.*)\)\s*$", line)
    if m:
        op, args_text = m.groups()
        args = lua_expr.split_lua_args(args_text)
        try:
            skill_id = int(lua_expr.eval_lua_arg(args, 0, 0, variables, ctx, slot_id))
        except Exception:
            skill_id = 0
        skill_name = _skill_name(maps, skill_id)
        val = lua_expr.eval_lua_arg(args, 1, 0, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"技能【{skill_name}】SP消耗"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="", kind=KIND_NUMERIC,
                        category=CAT_SECONDARY, extra={"target_kind": "skill", "target_id": skill_id})
        )
        return True

    # 51. AddMeleeAttackDamage / SubMeleeAttackDamage(0, value_expr) — 受到近距離物理傷害 ±N%
    m = re.match(r"(Add|Sub)MeleeAttackDamage\(\s*0\s*,\s*(.+)\)", line)
    if m:
        op, value_expr = m.groups()
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "受到近距離物理傷害"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC, category=CAT_RESIST)
        )
        return True

    # 52. AddRangeAttackDamage / SubRangeAttackDamage(0, value_expr) — 受到遠距離物理傷害 ±N%
    m = re.match(r"(Add|Sub)RangeAttackDamage\(\s*0\s*,\s*(.+)\)", line)
    if m:
        op, value_expr = m.groups()
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "受到遠距離物理傷害"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC, category=CAT_RESIST)
        )
        return True

    # 53. AddAttrTolerace / SubAttrTolerace(element, value) — 對{屬性}攻擊抗性 ±N%
    m = re.match(r"(Add|Sub)AttrTolerace\s*\((.*)\)\s*$", line)
    if m:
        op, args_text = m.groups()
        args = lua_expr.split_lua_args(args_text)
        elem_id, elem_name = _map_int_arg_with_id(args, 0, static_maps.ELEMENT_MAP, "屬性", variables, ctx, slot_id)
        val = lua_expr.eval_lua_arg(args, 1, 0, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"對 {elem_name} 攻擊抗性"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_RESIST, extra={"target_kind": "element", "target_id": elem_id})
        )
        return True

    # 54. add/subattrtolerace(element, value) — LOWERCASE synonym of #53
    # (ro_core.py:2020); case-sensitive match, never collides with #53.
    m = re.match(r"(add|sub)attrtolerace\s*\((.*)\)\s*$", line)
    if m:
        op, args_text = m.groups()
        args = lua_expr.split_lua_args(args_text)
        elem_id, elem_name = _map_int_arg_with_id(args, 0, static_maps.ELEMENT_MAP, "屬性", variables, ctx, slot_id)
        val = lua_expr.eval_lua_arg(args, 1, 0, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"對 {elem_name} 攻擊抗性"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op.capitalize()), unit="%", kind=KIND_NUMERIC,
                        category=CAT_RESIST, extra={"target_kind": "element", "target_id": elem_id})
        )
        return True

    # 55. AddDamage_Size / SubDamage_Size(0, size_id, value_expr) — 受到{體型}敵人的物理傷害 ±N%.
    # size_map miss fallback f"體型{size_id}" (ro_core.py:2034 — same fallback text as #32).
    m = re.match(r"(Add|Sub)Damage_Size\(\s*0\s*,\s*(\d+)\s*,\s*(.+)\s*\)", line)
    if m:
        op, size_id, value_expr = m.groups()
        size_id = int(size_id)
        size_name = static_maps.SIZE_MAP.get(size_id, f"體型{size_id}")
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"受到 {size_name} 敵人的物理傷害"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_RESIST, extra={"target_kind": "size", "target_id": size_id})
        )
        return True

    # 56. AddMDamage_Size / SubMDamage_Size(0, size_id, value_expr) — 受到{體型}敵人的魔法傷害 ±N%.
    # size_map miss fallback f"尺寸{size_id}" (ro_core.py:2044 — same fallback text as #15,
    # DIFFERENT from #55's "體型" — the original itself is inconsistent, ported verbatim).
    m = re.match(r"(Add|Sub)MDamage_Size\(\s*0\s*,\s*(\d+)\s*,\s*(.+)\s*\)", line)
    if m:
        op, size_id, value_expr = m.groups()
        size_id = int(size_id)
        size_name = static_maps.SIZE_MAP.get(size_id, f"尺寸{size_id}")
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"受到 {size_name} 敵人的魔法傷害"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_RESIST, extra={"target_kind": "size", "target_id": size_id})
        )
        return True

    # 57. AddRaceTolerace / SubRaceTolerace(race, value) — 受到{種族}型怪的傷害 ±N%.
    # SIGN-INVERSION QUIRK (ro_core.py:2059-2060): Tolerace is a *resistance* —
    # Add(增加耐性) means damage TAKEN goes DOWN ("-"), Sub(減少耐性) means
    # damage taken goes UP ("+"). This is the OPPOSITE of every Add=+/Sub=-
    # handler elsewhere in this file (do not reuse `_signed` here). Reproduced
    # exactly per the original's own comment; not a bug fix candidate.
    m = re.match(r"(Add|Sub)RaceTolerace\s*\((.*)\)\s*$", line)
    if m:
        op, args_text = m.groups()
        args = lua_expr.split_lua_args(args_text)
        race_id, race_name = _map_int_arg_with_id(args, 0, static_maps.RACE_MAP, "種族", variables, ctx, slot_id)
        val = lua_expr.eval_lua_arg(args, 1, 0, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        signed_val = -val if op == "Add" else val
        key = f"受到 {race_name} 型怪的傷害"
        entries_out.append(
            EffectEntry(key=key, value=signed_val, unit="%", kind=KIND_NUMERIC,
                        category=CAT_RESIST, extra={"target_kind": "race", "target_id": race_id})
        )
        return True

    # 58. AddDamage_Property / SubDamage_Property(0, elem_id, value_expr) — 受到{屬性}對象的物理傷害 ±N%
    m = re.match(r"(Add|Sub)Damage_Property\(\s*0\s*,\s*(\d+)\s*,\s*(.+)\s*\)", line)
    if m:
        op, elem_id, value_expr = m.groups()
        elem_id = int(elem_id)
        elem_name = static_maps.ELEMENT_MAP.get(elem_id, f"屬性{elem_id}")
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"受到 {elem_name} 對象的物理傷害"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_RESIST, extra={"target_kind": "element", "target_id": elem_id})
        )
        return True

    # 59. AddMDamage_Property / SubMDamage_Property(0, elem_id, value_expr) — 受到{屬性}對象的魔法傷害 ±N%
    m = re.match(r"(Add|Sub)MDamage_Property\(\s*0\s*,\s*(\d+)\s*,\s*(.+)\s*\)", line)
    if m:
        op, elem_id, value_expr = m.groups()
        elem_id = int(elem_id)
        elem_name = static_maps.ELEMENT_MAP.get(elem_id, f"屬性{elem_id}")
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"受到 {elem_name} 對象的魔法傷害"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_RESIST, extra={"target_kind": "element", "target_id": elem_id})
        )
        return True

    # 60. ClassAddDamage / ClassSubDamage(class_id, 0, value_expr) — 受到{階級}階級的物理傷害 ±N%
    m = re.match(r"Class(Add|Sub)Damage\(\s*(\d+)\s*,\s*0\s*,\s*(.+?)\s*\)", line)
    if m:
        op, class_id, value_expr = m.groups()
        class_id = int(class_id)
        class_name = static_maps.CLASS_MAP.get(class_id, f"階級{class_id}")
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"受到 {class_name} 階級的物理傷害"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_RESIST, extra={"target_kind": "class", "target_id": class_id})
        )
        return True

    # 61. RaceSubDamageSelf / RaceAddDamageSelf(race, value) — 受到{種族}型怪的傷害 ±N%.
    # Regex alternation order (Sub|Add) matches ro_core.py:2119 verbatim per
    # task-9 brief instruction — alternation order doesn't change which
    # literal matches, only documented here for byte-fidelity with the source.
    m = re.match(r"Race(Sub|Add)DamageSelf\s*\((.*)\)\s*$", line)
    if m:
        op, args_text = m.groups()
        args = lua_expr.split_lua_args(args_text)
        race_id, race_name = _map_int_arg_with_id(args, 0, static_maps.RACE_MAP, "種族", variables, ctx, slot_id)
        val = lua_expr.eval_lua_arg(args, 1, 0, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        signed_val = -val if op == "Sub" else val
        key = f"受到 {race_name} 型怪的傷害"
        entries_out.append(
            EffectEntry(key=key, value=signed_val, unit="%", kind=KIND_NUMERIC,
                        category=CAT_RESIST, extra={"target_kind": "race", "target_id": race_id})
        )
        return True

    # 62. AddCRIPercent_Race / SubCRIPercent_Race(race, value) — 對{種族}型怪的CRI ±N%
    m = re.match(r"(Add|Sub)CRIPercent_Race\s*\((.*)\)\s*$", line)
    if m:
        op, args_text = m.groups()
        args = lua_expr.split_lua_args(args_text)
        race_id, race_name = _map_int_arg_with_id(args, 0, static_maps.RACE_MAP, "種族", variables, ctx, slot_id)
        val = lua_expr.eval_lua_arg(args, 1, 0, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"對 {race_name} 型怪的CRI"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_DAMAGE, extra={"target_kind": "race", "target_id": race_id})
        )
        return True

    # 63. AddMeleeAttackReflect / SubMeleeAttackReflect(value) — 近距離物理反射 ±N%
    m = re.match(r"(Add|Sub)MeleeAttackReflect\s*\((.*)\)\s*$", line)
    if m:
        op, args_text = m.groups()
        args = lua_expr.split_lua_args(args_text)
        val = lua_expr.eval_lua_arg(args, 0, 0, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "近距離物理反射"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC, category=CAT_RESIST)
        )
        return True

    # 64. AddReflectMagic / SubReflectMagic(value) — 魔法反射 ±N%
    m = re.match(r"(Add|Sub)ReflectMagic\s*\((.*)\)\s*$", line)
    if m:
        op, args_text = m.groups()
        args = lua_expr.split_lua_args(args_text)
        val = lua_expr.eval_lua_arg(args, 0, 0, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "魔法反射"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC, category=CAT_RESIST)
        )
        return True

    # 65. AddReflectTolerace / SubReflectTolerace(value) — 反射傷害耐性 ±N%
    m = re.match(r"(Add|Sub)ReflectTolerace\s*\((.*)\)\s*$", line)
    if m:
        op, args_text = m.groups()
        args = lua_expr.split_lua_args(args_text)
        val = lua_expr.eval_lua_arg(args, 0, 0, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = "反射傷害耐性"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC, category=CAT_RESIST)
        )
        return True

    # 66. AddDamage_SKID / SubDamage_SKID(0, skill_id, value_expr) — 受到技能【X】傷害 ±N%.
    # Distinct from #8's AddDamage_SKID(1, ...) (裝備段) — both anchor on the
    # literal first argument (0 here, 1 for #8), so dispatch order between #8
    # and #66 doesn't matter (a line can only ever satisfy one of them).
    m = re.match(r"(Add|Sub)Damage_SKID\(\s*0\s*,\s*(\d+)\s*,\s*(.+)\s*\)\s*$", line)
    if m:
        op, skill_id, value_expr = m.groups()
        skill_id = int(skill_id)
        skill_name = _skill_name(maps, skill_id)
        val = lua_expr.safe_eval(value_expr, variables, ctx, slot_id)
        if val is None:
            entries_out.append(_unrecognized(line))
            return True
        key = f"受到技能【{skill_name}】傷害"
        entries_out.append(
            EffectEntry(key=key, value=_signed(val, op), unit="%", kind=KIND_NUMERIC,
                        category=CAT_RESIST, extra={"target_kind": "skill", "target_id": skill_id})
        )
        return True

    # 67. plain_effect_map — 8 個無參數旗標，DESCRIPTIVE，key 為
    # maps.PLAIN_EFFECT_MAP 對應的固定敘述句(不是函式名本身)。原碼
    # (ro_core.py:2317) 的正則同時容忍可有可無的空括號呼叫
    # (?:\((.*)\))? — 括號內容從未被使用，照樣不使用。
    m = re.match(
        r"(NoDispell|Magicimmune|NoJamstone|NoMadogearfuel|AddNeverknockback|Clairvoyance|Reincarnation|SplashAttack)"
        r"\s*(?:\((.*)\))?\s*$",
        line,
    )
    if m:
        func_name = m.group(1)
        key = static_maps.PLAIN_EFFECT_MAP.get(func_name, func_name)
        entries_out.append(
            EffectEntry(key=key, value=None, unit="", kind=KIND_DESCRIPTIVE, category=CAT_SECONDARY)
        )
        return True

    # 68. Condition(status_id, duration, chance) — 賦予狀態：{status}，kind=PROC.
    # status_map 只認 5 種 ID(13/14/15/21/26)；miss fallback f"狀態ID {id}"
    # (ro_core.py:2341)。status_id 求值失敗時比照原碼 try/except 退回 0 —
    # 這是原碼對這個欄位自己內建的防呆(ro_core.py:2337-2340)，不屬於本port一般
    # 「None→UNRECOGNIZED」規則管轄範圍；退回的 0 一樣正常落 miss fallback
    # "狀態ID 0"，不算UNRECOGNIZED。duration/chance 求值不到時維持 None(原碼
    # eval_lua_arg對「缺該參數」與「該參數求值失敗」本就不區分，兩者皆落None，
    # 照搬)。`if args:`（非`is not None`）比照原碼 ro_core.py:2329 的truthy檢查
    # ——「Condition()」零參數會是空list、真值False，不會走這條分支。
    args = lua_expr.get_lua_call_args("Condition", line)
    if args:
        try:
            status_id = int(lua_expr.eval_lua_arg(args, 0, 0, variables, ctx, slot_id))
        except Exception:
            status_id = 0
        status_name = static_maps.STATUS_MAP.get(status_id, f"狀態ID {status_id}")
        duration = lua_expr.eval_lua_arg(args, 1, None, variables, ctx, slot_id)
        chance = lua_expr.eval_lua_arg(args, 2, None, variables, ctx, slot_id)
        key = f"賦予狀態：{status_name}"
        entries_out.append(
            EffectEntry(key=key, value=None, unit="", kind=KIND_PROC, category=CAT_SECONDARY,
                        extra={"status": status_name, "duration": duration, "chance": chance})
        )
        return True

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
    sfct_state: dict[str, bool] = {"handled": False}

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
            if _match_effect_handlers(
                line, variables, ctx, slot_id, maps, entries_out, skill_delay_accum, sfct_state
            ):
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

    # ---- EOF unresolved-block flush. If block_text ends without enough
    # `end` lines to close every open if/elseif/else (malformed/truncated
    # source), any block still left on block_stack whose condition was never
    # resolved would otherwise be silently dropped (no _handle_end ever runs
    # for it). Emit its KIND_UNRESOLVED entry here instead, same shape as
    # _handle_end's own flush. Blocks that ARE resolved (active True/False,
    # not unresolved) still get no entry here — only unresolved ones did in
    # the closed-block path either. ----
    for block in block_stack:
        if block["unresolved"]:
            entries_out.append(_unresolved_entry(block))

    # ---- skill_delay_accum flush (ro_core.py:2370-2375). Fed by handler #10
    # (AddSkillDelay/SubSkillDelay, Task 7) — accumulates per skill_name
    # across every matching line in this whole block_text (function-scope,
    # not per if/elseif branch), then emits one merged 秒 entry per skill
    # here at the end. ----
    for skill_name, total_ms in skill_delay_accum.items():
        value = round(total_ms / 1000, 2)
        key = f"技能【{skill_name}】冷卻時間"
        entries_out.append(
            EffectEntry(key=key, value=value, unit="秒", kind=KIND_NUMERIC, category=CAT_ABILITY)
        )

    return ParseResult(entries=entries_out, trace=trace)
