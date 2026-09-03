import re

from importer.lua_scan import find_matching_brace, find_matching_end

_TOP_LEVEL_HEADER_RE = re.compile(r"(\w+)\s*=\s*\{")
_ENTRY_START_RE = re.compile(r"\[(\d+)\]\s*=\s*\{")
_TYPE_RE = re.compile(r'Type\s*=\s*"(\w+)"')
_STAT_START_RE = re.compile(r"Stat\s*=\s*\{")
_COMBI_START_RE = re.compile(r"Combiitem\s*=\s*\{")
_ITEM_ARRAY_START_RE = re.compile(r"\bItem\s*=\s*\{")
_ONSTART_RE = re.compile(r"OnStartEquip\s*=\s*(function\s*\(\s*\))")
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _find_top_level_table(text: str, name: str) -> tuple[int, int] | None:
    """Locate a TOP-LEVEL `name = { ... }` table and return (open_idx, close_idx).

    EquipmentProperties.lua is NOT a single table: it declares five sibling
    top-level tables (Item, Combiitem, SkillGroup, RefiningBonus, GradeBonus).
    A naive `re.search(name + r"\\s*=\\s*\\{")` is wrong for two reasons:

    1. For `Combiitem` it would match the *nested* `Combiitem = {...}` field
       inside the very first Item entry that has one, not the top-level table.
    2. Scanning entries without a bound leaks sibling tables' `[N] = {...}`
       entries into the Item results (SkillGroup keys collide with real item
       ids, silently overwriting real equipment data).

    So walk the top level explicitly: match a header, jump over its whole
    matched brace range, and repeat. Only headers reached this way are
    top-level, and nested content is never even looked at.
    """
    pos = 0
    n = len(text)
    while pos < n:
        m = _TOP_LEVEL_HEADER_RE.search(text, pos)
        if not m:
            return None
        brace_start = m.end() - 1
        brace_end = find_matching_brace(text, brace_start)
        if m.group(1) == name:
            return brace_start, brace_end
        pos = brace_end + 1
    return None


def _extract_onstart_src(block: str) -> str | None:
    onstart_m = _ONSTART_RE.search(block)
    if not onstart_m:
        return None
    func_start = onstart_m.start(1)
    # find_matching_end requires search_from to point AT the opening
    # keyword itself ("f" in "function"), not past it. Passing a
    # position after "function()" would make the scanner's
    # first-keyword-skip logic treat the first NESTED keyword inside
    # the body (e.g. a nested "if") as the already-open block,
    # silently truncating the extracted source at the nested block's
    # "end" instead of the function's own "end".
    end_idx = find_matching_end(block, func_start)
    return block[func_start:end_idx + 3]


def _extract_number_array(block: str, start_re: re.Pattern) -> list | None:
    m = start_re.search(block)
    if not m:
        return None
    brace_start = m.end() - 1
    brace_end = find_matching_brace(block, brace_start)
    return _NUMBER_RE.findall(block[brace_start + 1:brace_end])


def parse(text: str) -> list[dict]:
    """Parse the top-level `Item` table only (see _find_top_level_table)."""
    span = _find_top_level_table(text, "Item")
    if span is None:
        return []
    brace_start, brace_end = span
    body = text[brace_start:brace_end + 1]

    rows = []
    pos = 0
    while True:
        m = _ENTRY_START_RE.search(body, pos)
        if not m:
            break
        item_id = int(m.group(1))
        entry_brace_start = m.end() - 1
        entry_brace_end = find_matching_brace(body, entry_brace_start)
        block = body[entry_brace_start:entry_brace_end + 1]
        pos = entry_brace_end + 1

        type_m = _TYPE_RE.search(block)

        stat_numbers = _extract_number_array(block, _STAT_START_RE)
        stat_vector = [_to_number(n) for n in stat_numbers] if stat_numbers is not None else None

        combi_numbers = _extract_number_array(block, _COMBI_START_RE)
        combi_ids = [int(n) for n in combi_numbers] if combi_numbers is not None else None

        rows.append({
            "item_id": item_id,
            "equip_type": type_m.group(1) if type_m else None,
            "stat_vector": stat_vector,
            "onstart_equip_src": _extract_onstart_src(block),
            "combi_item_ids": combi_ids,
        })
    return rows


def parse_combiitem(text: str) -> dict[int, dict]:
    """Parse the top-level `Combiitem` table into {combo_id: {...}}.

    `Item[id].Combiitem` holds KEYS into this separate table -- not item ids.
    Each combo entry looks like:

        [2000000007] = {
          Item = {4244, 4299, 4229, 4313},
          OnStartEquip = function() ... end
        }

    so the real set-member item ids and the raw set-bonus Lua source live
    here, and nowhere else.
    """
    span = _find_top_level_table(text, "Combiitem")
    if span is None:
        return {}
    brace_start, brace_end = span
    body = text[brace_start:brace_end + 1]

    combos: dict[int, dict] = {}
    pos = 0
    while True:
        m = _ENTRY_START_RE.search(body, pos)
        if not m:
            break
        combo_id = int(m.group(1))
        entry_brace_start = m.end() - 1
        entry_brace_end = find_matching_brace(body, entry_brace_start)
        block = body[entry_brace_start:entry_brace_end + 1]
        pos = entry_brace_end + 1

        member_numbers = _extract_number_array(block, _ITEM_ARRAY_START_RE)
        combos[combo_id] = {
            "member_item_ids": [int(n) for n in member_numbers] if member_numbers is not None else [],
            "onstart_src": _extract_onstart_src(block),
        }
    return combos


def _to_number(text: str):
    return float(text) if "." in text else int(text)
