"""Build (配裝) and Character (角色檔) JSON loading — spec §6 / §5.2.

``userdata/builds/*.json`` and ``userdata/characters/*.json`` are the two
user-editable save formats consumed by the app layer. This module only does
the load-time shape conversion (raw JSON dict -> dataclass); no db/context
logic lives here (see aggregate.py for that).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SlotConfig:
    item_id: int
    refine: int = 0
    grade: str = "none"
    cards: list[int] = field(default_factory=list)
    enchants: list[str | None] = field(default_factory=list)  # internal_name


@dataclass
class Build:
    name: str
    slots: dict[str, SlotConfig]  # slot鍵: 見SLOT_IDS(spec §6的20部位英文代號)


@dataclass
class Character:
    name: str
    job: int
    base_lv: int
    job_lv: int
    stats: dict[str, int]
    traits: dict[str, int]
    skills: dict[int, int]


# SLOT_IDS: 部位代號 -> 裝備介面client slot id 對照(spec §6).
#
# Insertion order here IS the evaluation order aggregate.evaluate_build()
# iterates in: armor/weapon/shield-type slots first so their Stat lines
# populate ctx.weapon_level_map/armor_level_map before OTHER items' onstart
# conditions (GetEquipWeaponLv(GetLocation())等) get parsed and read those
# maps — see aggregate.py docstring for the full rationale.
#
# 一般裝備10格 client id: 沿用ROItemSearchApp裝備介面對照(armor=2, shield=3,
# weapon=4, garment=5, shoes=6, acc_r=7, acc_l=8, head_top=10, head_mid=11,
# head_low=12).
# 影子裝備6格 client id: ItemSearchApp.py:2095-2098 equip_sitetype映射逐字採用
# (30影子鎧甲/31影子手套/32影子盾牌/33影子鞋子/34影子耳環/35影子墬子).
# 服飾4格(costume): client效果條件從未使用這些槽位id, 純屬本專案自訂編號(900起),
# 不對應任何client常數.
SLOT_IDS: dict[str, int] = {
    "armor": 2,
    "weapon": 4,
    "shield": 3,
    "garment": 5,
    "shoes": 6,
    "acc_r": 7,
    "acc_l": 8,
    "head_top": 10,
    "head_mid": 11,
    "head_low": 12,
    "shadow_armor": 30,
    "shadow_gauntlet": 31,
    "shadow_shield": 32,
    "shadow_shoes": 33,
    "shadow_earring": 34,
    "shadow_pendant": 35,
    "costume_top": 900,
    "costume_mid": 901,
    "costume_low": 902,
    "costume_garment": 903,
}

# 升階等級對照(client GetEquipGradeLevel convention): 無階=0, D=1, C=2, B=3, A=4.
GRADE_LEVELS: dict[str, int] = {"none": 0, "D": 1, "C": 2, "B": 3, "A": 4}


def load_build(path) -> Build:
    """Load a Build from userdata/builds/*.json (spec §6).

    Unknown/extra JSON keys per slot (e.g. cost_targets, which belongs to the
    M3 cost engine, not M2) are ignored rather than erroring.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    slots: dict[str, SlotConfig] = {}
    for slot_key, slot_data in data.get("slots", {}).items():
        if slot_key not in SLOT_IDS:
            raise ValueError(f"配裝檔含未知部位鍵 '{slot_key}', 合法鍵: {sorted(SLOT_IDS)}")
        grade = slot_data.get("grade", "none")
        if grade not in GRADE_LEVELS:
            raise ValueError(f"配裝檔部位 '{slot_key}' 的階級 '{grade}' 不合法, 合法值: none/D/C/B/A")
        slots[slot_key] = SlotConfig(
            item_id=slot_data["item_id"],
            refine=slot_data.get("refine", 0),
            grade=grade,
            cards=list(slot_data.get("cards", [])),
            enchants=list(slot_data.get("enchants", [])),
        )
    return Build(name=data["name"], slots=slots)


def load_character(path) -> Character:
    """Load a Character from userdata/characters/*.json (spec §5.2).

    ``skills`` keys arrive as JSON strings (JSON object keys are always
    strings) and are converted to int skill ids here.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    skills = {int(k): v for k, v in data.get("skills", {}).items()}
    return Character(
        name=data["name"],
        job=data["job"],
        base_lv=data["base_lv"],
        job_lv=data["job_lv"],
        stats=dict(data.get("stats", {})),
        traits=dict(data.get("traits", {})),
        skills=skills,
    )
