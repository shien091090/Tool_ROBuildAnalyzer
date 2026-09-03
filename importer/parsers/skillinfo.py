import re

from importer.lua_scan import find_matching_brace

_PAIR_RE = re.compile(r"(\w+)\s*=\s*(-?\d+)")


def parse_skillid(text: str) -> dict[str, int]:
    """Parse SkillInfoZ/skillid.lub's `SKID = {NAME = id, ...}` table."""
    return {name: int(value) for name, value in _PAIR_RE.findall(text)}


_ENTRY_START_RE = re.compile(r"\[SKID\.(\w+)\]\s*=\s*\{")
_SKILL_NAME_RE = re.compile(r'SkillName\s*=\s*"([^"]*)"')
_MAX_LV_RE = re.compile(r"MaxLv\s*=\s*(\d+)")
_TYPE_RE = re.compile(r'Type\s*=\s*"(\w+)"')
_IS_LEVEL_SELECT_RE = re.compile(r"bSeperateLv\s*=\s*(true|false)")
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _extract_number_array(block: str, field_name: str) -> list | None:
    m = re.search(rf"\b{field_name}\s*=\s*\{{", block)
    if not m:
        return None
    brace_start = m.end() - 1
    brace_end = find_matching_brace(block, brace_start)
    return [int(n) for n in _NUMBER_RE.findall(block[brace_start + 1:brace_end])]


_SCALE_ENTRY_RE = re.compile(r"\[(\d+)\]\s*=\s*\{x\s*=\s*(-?\d+),\s*y\s*=\s*(-?\d+)\}")


def _extract_skill_scale(block: str) -> list | None:
    m = re.search(r"\bSkillScale\s*=\s*\{", block)
    if not m:
        return None
    brace_start = m.end() - 1
    brace_end = find_matching_brace(block, brace_start)
    inner = block[brace_start + 1:brace_end]
    entries = sorted(
        ((int(idx), int(x), int(y)) for idx, x, y in _SCALE_ENTRY_RE.findall(inner)),
        key=lambda e: e[0],
    )
    return [{"x": x, "y": y} for _, x, y in entries]


_PREREQ_PAIR_RE = re.compile(r"\{SKID\.(\w+),\s*(\d+)\}")


def _extract_base_prerequisites(block: str) -> list | None:
    # `_NeedSkillList` (leading underscore) is the skill's own unconditional
    # prerequisite list -- distinct from the job-specific `NeedSkillList`
    # (see _extract_job_prerequisites). Confirmed 2026-08-27 via item
    # AL_CURE, which carries BOTH at once with different content.
    m = re.search(r"\b_NeedSkillList\s*=\s*\{", block)
    if not m:
        return None
    brace_start = m.end() - 1
    brace_end = find_matching_brace(block, brace_start)
    inner = block[brace_start + 1:brace_end]
    return [
        {"skill": name, "level": int(level)}
        for name, level in _PREREQ_PAIR_RE.findall(inner)
    ]


_JOB_GROUP_START_RE = re.compile(r"\[JOBID\.(\w+)\]\s*=\s*\{")


def _extract_job_prerequisites(block: str) -> dict | None:
    # `NeedSkillList` (no underscore) is grouped by JOBID -- different job
    # trees converging on the same skill (e.g. Bard vs Dancer lineage) can
    # need different extra prerequisites. Distinct from `_NeedSkillList`
    # (see _extract_base_prerequisites); item AL_CURE carries both.
    m = re.search(r"(?<!_)\bNeedSkillList\s*=\s*\{", block)
    if not m:
        return None
    outer_brace_start = m.end() - 1
    outer_brace_end = find_matching_brace(block, outer_brace_start)
    outer_inner = block[outer_brace_start + 1:outer_brace_end]

    result = {}
    for job_m in _JOB_GROUP_START_RE.finditer(outer_inner):
        job_id = job_m.group(1)
        group_brace_start = job_m.end() - 1
        group_brace_end = find_matching_brace(outer_inner, group_brace_start)
        group_inner = outer_inner[group_brace_start + 1:group_brace_end]
        result[job_id] = [
            {"skill": name, "level": int(level)}
            for name, level in _PREREQ_PAIR_RE.findall(group_inner)
        ]
    return result


# A skill_name containing this is a tell-tale sign the decompiled string
# literal never closed where it should have and swallowed the next entry's
# opening syntax instead (real example, 2026-08-28: DA_TIMEOUT's SkillName
# absorbed all of ALL_TIMEIN's definition up to ALL_TIMEIN's own first
# quote). Neither skill's fields can be safely recovered from this --
# skip rather than record contaminated/misattributed data.
_CORRUPTION_MARKER_RE = re.compile(r"\[SKID\.")


def parse_skillinfolist(text: str) -> tuple[dict[str, dict], int]:
    """Parse SkillInfoZ/skillinfolist.lub's `SKILL_INFO_LIST` table.

    Keyed by internal_name (e.g. "SR_KNUCKLEARROW") rather than skill_id --
    skillinfolist.lub only ever refers to skills via `SKID.NAME`, so the
    caller must combine this with parse_skillid()'s name->id mapping.

    Returns (result, corrupted_count) -- corrupted_count surfaces how many
    entries were skipped for decompiled-string corruption (see
    _CORRUPTION_MARKER_RE) instead of that loss staying invisible.
    """
    result: dict[str, dict] = {}
    corrupted_count = 0
    for m in _ENTRY_START_RE.finditer(text):
        internal_name = m.group(1)
        brace_start = m.end() - 1
        brace_end = find_matching_brace(text, brace_start)
        block = text[brace_start:brace_end + 1]

        skill_name_m = _SKILL_NAME_RE.search(block)
        skill_name = skill_name_m.group(1) if skill_name_m else None
        if skill_name is not None and _CORRUPTION_MARKER_RE.search(skill_name):
            corrupted_count += 1
            continue

        max_lv_m = _MAX_LV_RE.search(block)
        type_m = _TYPE_RE.search(block)
        is_level_select_m = _IS_LEVEL_SELECT_RE.search(block)

        result[internal_name] = {
            "skill_name": skill_name,
            "max_level": int(max_lv_m.group(1)) if max_lv_m else None,
            "skill_type": type_m.group(1) if type_m else None,
            "is_level_select": is_level_select_m.group(1) == "true" if is_level_select_m else None,
            "sp_amount": _extract_number_array(block, "SpAmount"),
            "ap_amount": _extract_number_array(block, "ApAmount"),
            "attack_range": _extract_number_array(block, "AttackRange"),
            "skill_scale": _extract_skill_scale(block),
            "base_prerequisites": _extract_base_prerequisites(block),
            "job_prerequisites": _extract_job_prerequisites(block),
        }
    return result, corrupted_count


_QUOTED_STRING_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')


def parse_skilldescript(text: str) -> dict[str, list[str]]:
    """Parse SkillInfoZ/skilldescript.lub -- one quoted-string array per skill.

    Same raw-text-array shape as items_raw.description_lines: kept as-is
    here, no attempt to parse the "[Level N] : ..." lines yet.
    """
    result: dict[str, list[str]] = {}
    for m in _ENTRY_START_RE.finditer(text):
        internal_name = m.group(1)
        brace_start = m.end() - 1
        brace_end = find_matching_brace(text, brace_start)
        block = text[brace_start:brace_end + 1]
        result[internal_name] = _QUOTED_STRING_RE.findall(block)
    return result


def _resolve_prerequisites(prereqs: list | None, skillid_map: dict[str, int]) -> list | None:
    if prereqs is None:
        return None
    resolved = []
    for entry in prereqs:
        skill_id = skillid_map.get(entry["skill"])
        if skill_id is None:
            continue
        resolved.append({"skill_id": skill_id, "level": entry["level"]})
    return resolved


def merge_skills(
    skillid_map: dict[str, int],
    info_map: dict[str, dict],
    desc_map: dict[str, list[str]],
) -> list[dict]:
    """Combine skillid/skillinfolist/skilldescript into skills_raw rows.

    Only internal_names with a real skill_id are included -- skill_id is
    the table's primary key, so an entry skillid.lub never confirmed
    can't produce a valid row (this hasn't happened in real production
    data as of 2026-08-28, but stay defensive rather than insert a bogus
    null id).
    """
    rows = []
    for internal_name, info in info_map.items():
        skill_id = skillid_map.get(internal_name)
        if skill_id is None:
            continue

        base_prereqs = _resolve_prerequisites(info["base_prerequisites"], skillid_map)
        job_prereqs = None
        if info["job_prerequisites"] is not None:
            job_prereqs = {
                job_id: _resolve_prerequisites(entries, skillid_map)
                for job_id, entries in info["job_prerequisites"].items()
            }

        rows.append({
            "skill_id": skill_id,
            "internal_name": internal_name,
            "skill_name": info["skill_name"],
            "max_level": info["max_level"],
            "skill_type": info["skill_type"],
            "is_level_select": info["is_level_select"],
            "sp_amount": info["sp_amount"],
            "ap_amount": info["ap_amount"],
            "attack_range": info["attack_range"],
            "skill_scale": info["skill_scale"],
            "base_prerequisites": base_prereqs,
            "job_prerequisites": job_prereqs,
            "description_lines": desc_map.get(internal_name, []),
        })
    return rows
