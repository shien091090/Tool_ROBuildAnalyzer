"""Lua expression normalization and restricted evaluation.

Ported from ROItemSearchApp's ro_core.py (parse_lua_effects_with_variables,
lines ~588-809). ``normalize_lua_expr`` and ``_eval_python_expr`` are ported
logic-for-logic (regex substitution rules, IntDivTransformer for Lua-style
integer division, the allowed-character whitelist and the
``{"__builtins__": None}`` sandbox). ``split_lua_args`` / ``get_lua_call_args``
are ported verbatim.

Deliberate behavioral changes from the original (binding, see M2 plan Task 5):

1. ``GetSkillLevel(id)`` is resolved via ``ctx.skill_level(id)`` instead of a
   raw dict ``.get(id, 0)``. A miss does NOT substitute 0 — it records
   ``"skill:{id}"`` in the missing-keys set and leaves the call untouched.
2. After variable substitution, any residual identifier that is a member of
   ``context.SCALAR_KEYS`` is resolved via ``ctx.scalar(name)``. A miss
   records the bare key name in the missing-keys set instead of substituting.
3. ``safe_eval`` returns ``None`` when the missing-keys set is non-empty, or
   when evaluation raises for any other reason. The original padded every
   missing value with 0 and always produced a number; this port refuses to
   guess so callers can distinguish "computed" from "cannot be resolved yet"
   (feeds the UNRECOGNIZED / unresolved-condition reporting added in this
   port, see app/core/entries.py KIND_UNRESOLVED).
4. ``eval_condition`` mirrors that: returns ``(True/False, set())`` when
   computable, ``(None, missing_keys)`` when not (missing keys, or eval
   failure with an empty missing set).
5. ``normalize`` returns ``(normalized_expr_string, missing_keys_set)``
   instead of just a string.
6. ``GetPetRelationship()`` is ported as-is: it substitutes the *grade*
   value (same source as ``GetEquipGradeLevel(GetLocation())``). This is a
   quirk inherited from the original tool, not a bug introduced here.
7. ``get(N)`` (character-stat UI field read, N->field per
   ItemSearchApp.py:2048 stat_fields, see app/core/context.py
   GET_FIELD_NAMES / app/core/aggregate.py GET_VALUE_FIELDS) is resolved via
   ``ctx.get_value(N)`` instead of a raw dict ``.get(N, 0)``. A miss does NOT
   substitute 0 — it records ``"get:{N}"`` in the missing-keys set and leaves
   the call untouched, same shape as change (1)'s GetSkillLevel handling.
"""

from __future__ import annotations

import ast
import math
import re

from app.core.context import CalcContext, SCALAR_KEYS

# =========================================================
# Regex cache (ported from ro_core.py:588-622) as module-level constants.
# =========================================================

_RE_GET = re.compile(r"get\((\d+)\)")
_RE_REFINE_LOCATION = re.compile(r"GetRefineLevel\s*\(\s*GetLocation\s*\(\s*\)\s*\)")
_RE_REFINE = re.compile(r"GetRefineLevel\((\d+)\)")
_RE_GRADE_LOCATION = re.compile(r"GetEquipGradeLevel\s*\(\s*GetLocation\s*\(\s*\)\s*\)")
_RE_GRADE = re.compile(r"GetEquipGradeLevel\((\d+)\)")
_RE_ARMOR_LOCATION = re.compile(r"GetEquipArmorLv\s*\(\s*GetLocation\s*\(\s*\)\s*\)")
_RE_ARMOR = re.compile(r"GetEquipArmorLv\((\d+)\)")
_RE_WEAPON_LV_LOCATION = re.compile(r"GetEquipWeaponLv\s*\(\s*GetLocation\s*\(\s*\)\s*\)")
_RE_WEAPON_LV = re.compile(r"GetEquipWeaponLv\((\d+)\)")
_RE_WEAPON_CLASS_LOCATION = re.compile(r"GetWeaponClass\s*\(\s*GetLocation\s*\(\s*\)\s*\)")
_RE_ITEM_ID_LOCATION = re.compile(r"GetItemIDLocation\((\d+)\)")
_RE_SKILL_LEVEL = re.compile(r"GetSkillLevel\((\d+)\)")
_RE_PET_RELATIONSHIP = re.compile(r"GetPetRelationship\s*\(\s*\)")
_RE_ALLOWED_EVAL = re.compile(r"^[0-9A-Za-z_+\-*/%().<>=!&|,\[\]\s]+$")

# Sorted longest-first once; SCALAR_KEYS is a frozenset built at import time.
_SCALAR_KEYS_BY_LENGTH = sorted(SCALAR_KEYS, key=lambda x: -len(x))


def normalize(
    expr: str, variables: dict, ctx: CalcContext, current_slot: int | None
) -> tuple[str, set[str]]:
    """Normalize a simple Lua expression into a Python-evaluable expression.

    Returns (normalized_expr, missing_keys) where missing_keys collects every
    GetSkillLevel(id) and SCALAR_KEYS identifier this expression touched that
    could not be resolved from ``ctx``. See module docstring changes (1)/(2).
    """
    missing: set[str] = set()
    expr = str(expr).strip()

    # Deliberate change (7, see module docstring): get(N) goes through
    # ctx.get_value(), which records a miss ("get:{N}") instead of silently
    # defaulting to 0 — mirrors GetSkillLevel's _sub_skill_level below.
    def _sub_get_value(m: re.Match) -> str:
        n = int(m.group(1))
        value = ctx.get_value(n)
        if value is None:
            missing.add(f"get:{n}")
            return m.group(0)
        return str(value)

    expr = _RE_GET.sub(_sub_get_value, expr)
    expr = _RE_REFINE_LOCATION.sub(
        lambda m: str(ctx.refine_inputs.get(current_slot, 0) if current_slot is not None else 0),
        expr,
    )
    expr = _RE_REFINE.sub(lambda m: str(ctx.refine_inputs.get(int(m.group(1)), 0)), expr)
    expr = _RE_GRADE_LOCATION.sub(lambda m: str(ctx.grade_value(current_slot)), expr)
    expr = _RE_GRADE.sub(lambda m: str(ctx.grade_value(int(m.group(1)))), expr)
    expr = _RE_ARMOR_LOCATION.sub(
        lambda m: str(ctx.armor_level_map.get(current_slot, 0) if current_slot is not None else 0),
        expr,
    )
    expr = _RE_ARMOR.sub(lambda m: str(ctx.armor_level_map.get(int(m.group(1)), 0)), expr)
    expr = _RE_WEAPON_LV_LOCATION.sub(
        lambda m: str(ctx.weapon_level_map.get(current_slot, 0) if current_slot is not None else 0),
        expr,
    )
    expr = _RE_WEAPON_LV.sub(lambda m: str(ctx.weapon_level_map.get(int(m.group(1)), 0)), expr)
    expr = _RE_WEAPON_CLASS_LOCATION.sub(
        lambda m: str(ctx.weapon_type_map.get(current_slot, 0) if current_slot is not None else 0),
        expr,
    )
    expr = _RE_ITEM_ID_LOCATION.sub(lambda m: str(ctx.slot_item_id_map.get(int(m.group(1)), 0)), expr)

    # Deliberate change (1): GetSkillLevel goes through ctx.skill_level(),
    # which records a miss instead of silently defaulting to 0.
    def _sub_skill_level(m: re.Match) -> str:
        skill_id = int(m.group(1))
        level = ctx.skill_level(skill_id)
        if level is None:
            missing.add(f"skill:{skill_id}")
            return m.group(0)
        return str(level)

    expr = _RE_SKILL_LEVEL.sub(_sub_skill_level, expr)

    # Quirk ported as-is from ro_core.py:653 — GetPetRelationship() shares the
    # same value source as GetEquipGradeLevel(GetLocation()) in the original.
    expr = _RE_PET_RELATIONSHIP.sub(lambda m: str(ctx.grade_value(current_slot)), expr)

    pure_jobs = ctx.pure_jobs
    expr = re.sub(r"GetPureJob\(\)\s*==\s*(\d+)", lambda m: f"({int(m.group(1))} in {list(pure_jobs)})", expr)
    expr = re.sub(r"GetPureJob\(\)\s*~=\s*(\d+)", lambda m: f"({int(m.group(1))} not in {list(pure_jobs)})", expr)

    expr = expr.replace("~=", "!=").replace("&&", " and ").replace("||", " or ")
    expr = re.sub(r"\btrue\b", "True", expr, flags=re.IGNORECASE)
    expr = re.sub(r"\bfalse\b", "False", expr, flags=re.IGNORECASE)
    expr = re.sub(r"\bnil\b", "0", expr, flags=re.IGNORECASE)

    # 僅替換純數值變數；dict/list 等內部狀態不應塞回 eval 字串。
    for v in sorted(variables.keys(), key=lambda x: -len(x)):
        value = variables[v]
        if isinstance(value, bool):
            value = int(value)
        if isinstance(value, (int, float)):
            expr = re.sub(rf'\b{re.escape(v)}\b', str(value), expr)

    # Deliberate change (2): any SCALAR_KEYS identifier still left after the
    # variables substitution above is resolved via ctx.scalar(); a miss
    # records the key instead of the original's implicit 0-default.
    for name in _SCALAR_KEYS_BY_LENGTH:
        if re.search(rf'\b{re.escape(name)}\b', expr):
            value = ctx.scalar(name)
            if value is None:
                missing.add(name)
            else:
                expr = re.sub(rf'\b{re.escape(name)}\b', str(value), expr)

    # 補括號，容忍部分 Lua 資料少寫右括號的狀況。
    if expr.count("(") > expr.count(")"):
        expr += ")" * (expr.count("(") - expr.count(")"))

    return expr, missing


def _eval_python_expr(expr: str, local_vars: dict | None = None):
    """Restricted eval of a normalized expression (ported from ro_core.py:678-724)."""
    if not _RE_ALLOWED_EVAL.fullmatch(expr):
        raise ValueError(f"含不允許字元: {expr}")

    def __idiv(a, b):
        # 除完立刻取整；正數情況等同 floor
        return int(a / b)

    class IntDivTransformer(ast.NodeTransformer):
        def visit_BinOp(self, node):
            self.generic_visit(node)

            if isinstance(node.op, ast.Div):
                return ast.copy_location(
                    ast.Call(
                        func=ast.Name(id="__idiv", ctx=ast.Load()),
                        args=[node.left, node.right],
                        keywords=[],
                    ),
                    node,
                )

            return node

    tree = ast.parse(expr, mode="eval")
    tree = IntDivTransformer().visit(tree)
    ast.fix_missing_locations(tree)

    env = {
        "math": math,
        "__idiv": __idiv,
    }

    if local_vars:
        env.update({
            k: v for k, v in local_vars.items()
            if isinstance(v, (int, float, bool))
        })

    return eval(
        compile(tree, "<expr>", "eval"),
        {"__builtins__": None},
        env,
    )


def safe_eval(expr: str, variables: dict, ctx: CalcContext, current_slot: int | None) -> float | None:
    """Evaluate expr to a number, or None if unresolvable.

    Deliberate change (3): returns None when normalize() reports missing keys,
    or when evaluation raises for any reason. The original (ro_core.py:726-734)
    padded every missing value with 0 and always returned a number; this port
    treats "cannot fully resolve" as an explicit unresolved state so callers
    can report UNRECOGNIZED / unresolved-condition instead of a wrong guess.
    """
    normalized, missing = normalize(expr, variables, ctx, current_slot)
    if missing:
        return None
    try:
        value = _eval_python_expr(normalized, variables)
        return float(int(value))
    except Exception:
        return None


def eval_condition(
    expr: str, variables: dict, ctx: CalcContext, current_slot: int | None
) -> tuple[bool | None, set[str]]:
    """Evaluate a boolean condition.

    Returns (True/False, set()) when computable, (None, missing_keys) when
    not — either because normalize() reported missing keys, or because
    evaluation raised (in which case missing_keys is the empty set).
    """
    normalized, missing = normalize(expr, variables, ctx, current_slot)
    if missing:
        return None, missing
    try:
        value = _eval_python_expr(normalized, variables)
        return bool(value), set()
    except Exception:
        return None, set()


def split_lua_args(args_text: str) -> list[str]:
    """Split simple Lua-style function arguments while preserving nested calls.

    Ported verbatim from ro_core.py:746-783.
    """
    args = []
    current = []
    depth = 0
    quote = None
    escape = False

    for ch in args_text:
        if quote:
            current.append(ch)
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            continue

        if ch in ('"', "'"):
            quote = ch
            current.append(ch)
        elif ch in "({[":
            depth += 1
            current.append(ch)
        elif ch in ")}]":
            depth = max(0, depth - 1)
            current.append(ch)
        elif ch == "," and depth == 0:
            args.append("".join(current).strip())
            current = []
        else:
            current.append(ch)

    tail = "".join(current).strip()
    if tail:
        args.append(tail)
    return args


def get_lua_call_args(func_name: str, line_text: str, flags: int = 0) -> list[str] | None:
    """Extract call arguments for func_name from a line, or None if it doesn't match.

    Ported verbatim from ro_core.py:786-790.
    """
    m = re.match(rf"{func_name}\s*\((.*)\)\s*$", line_text, flags)
    if not m:
        return None
    return split_lua_args(m.group(1))


def eval_lua_arg(args, index: int, default, variables: dict, ctx: CalcContext, current_slot: int | None):
    """Evaluate args[index] via safe_eval, or return default if out of range."""
    if args is None or index >= len(args):
        return default
    return safe_eval(args[index], variables, ctx, current_slot)
