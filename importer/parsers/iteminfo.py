import re

from importer.lua_scan import find_matching_brace

_ENTRY_START_RE = re.compile(r"\[(\d+)\]\s*=\s*\{")
_IDENTIFIED_NAME_RE = re.compile(r'(?<!un)identifiedDisplayName\s*=\s*"((?:[^"\\]|\\.)*)"')
_DESC_START_RE = re.compile(r"(?<!un)identifiedDescriptionName\s*=\s*\{")
_QUOTED_STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
_SLOT_COUNT_RE = re.compile(r"slotCount\s*=\s*(\d+)")
_CLASS_NUM_RE = re.compile(r"ClassNum\s*=\s*(\d+)")
_EFFECT_ID_RE = re.compile(r"EffectID\s*=\s*(\d+)")


def parse(text: str) -> list[dict]:
    rows = []
    pos = 0
    while True:
        m = _ENTRY_START_RE.search(text, pos)
        if not m:
            break
        item_id = int(m.group(1))
        brace_start = m.end() - 1
        brace_end = find_matching_brace(text, brace_start)
        block = text[brace_start:brace_end + 1]
        pos = brace_end + 1

        name_m = _IDENTIFIED_NAME_RE.search(block)
        desc_m = _DESC_START_RE.search(block)
        slot_m = _SLOT_COUNT_RE.search(block)
        class_m = _CLASS_NUM_RE.search(block)
        effect_m = _EFFECT_ID_RE.search(block)

        description_lines = []
        if desc_m:
            desc_brace_start = desc_m.end() - 1
            desc_brace_end = find_matching_brace(block, desc_brace_start)
            desc_block = block[desc_brace_start:desc_brace_end + 1]
            description_lines = _QUOTED_STRING_RE.findall(desc_block)

        rows.append({
            "item_id": item_id,
            "display_name": name_m.group(1) if name_m else None,
            "description_lines": description_lines,
            "slot_count": int(slot_m.group(1)) if slot_m else None,
            "class_num": int(class_m.group(1)) if class_m else None,
            "effect_id": int(effect_m.group(1)) if effect_m else None,
        })
    return rows
