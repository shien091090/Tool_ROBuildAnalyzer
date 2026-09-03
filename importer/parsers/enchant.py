import re

_TABLE_CREATE_RE = re.compile(r"Table\[(\d+)\]\s*=\s*CreateEnchantInfo\(\)")
_ADD_TARGET_RE = re.compile(r'Table\[(\d+)\]:AddTargetItem\("([^"]+)"\)')
_SLOT_REQUIRE_RE = re.compile(r"Table\[(\d+)\]\.Slot\[(\d+)\]:SetRequire\(([^)]*)\)")
_SLOT_SUCCESS_RE = re.compile(r"Table\[(\d+)\]\.Slot\[(\d+)\]:SetSuccessRate\((\d+)\)")
_SLOT_ENCHANT_RE = re.compile(
    r'Table\[(\d+)\]\.Slot\[(\d+)\]:SetEnchant\(\d+,\s*"([^"]+)",\s*(\d+)\)'
)


def parse(text: str) -> list[dict]:
    targets_by_table: dict[int, list[str]] = {}
    require_by_slot: dict[tuple[int, int], str] = {}
    success_by_slot: dict[tuple[int, int], int] = {}
    rows = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        m = _ADD_TARGET_RE.match(line)
        if m:
            table_index = int(m.group(1))
            targets_by_table.setdefault(table_index, []).append(m.group(2))
            continue

        m = _SLOT_REQUIRE_RE.match(line)
        if m:
            key = (int(m.group(1)), int(m.group(2)))
            require_by_slot[key] = m.group(3).strip()
            continue

        m = _SLOT_SUCCESS_RE.match(line)
        if m:
            key = (int(m.group(1)), int(m.group(2)))
            success_by_slot[key] = int(m.group(3))
            continue

        m = _SLOT_ENCHANT_RE.match(line)
        if m:
            table_index = int(m.group(1))
            slot_index = int(m.group(2))
            key = (table_index, slot_index)
            rows.append({
                "table_index": table_index,
                "target_internal_names": list(targets_by_table.get(table_index, [])),
                "slot_index": slot_index,
                "require_cost": require_by_slot.get(key),
                "success_rate": success_by_slot.get(key),
                "option_internal_name": m.group(3),
                "option_weight": int(m.group(4)),
            })
            continue

    return rows
