from dataclasses import dataclass, field

# GET_FIELD_NAMES: get(N) 角色數值UI欄位對照 — 逐字移植自ItemSearchApp.py:2048
# stat_fields(唯一權威來源)。涵蓋原碼定義的全部N, 供未來UI顯示「未計入」訊息時
# 把 "get:200" 這類機器可讀key轉成人類可讀欄位名(如"MHP")用。
#
# 注意: 這是「client介面定義了哪些N」的完整對照, 不代表角色檔JSON都能提供對應
# 值 — aggregate.GET_VALUE_FIELDS 才是「角色檔實際能填的子集」, 兩者刻意分開
# (200/202/263/264 在這裡有名字, 但角色檔沒有這些欄位, get_value()仍會回報缺席)。
GET_FIELD_NAMES: dict[int, str] = {
    11: "BaseLv", 12: "JobLv", 19: "JOB", 200: "MHP", 202: "MSP",
    32: "STR", 33: "AGI", 34: "VIT", 35: "INT", 36: "DEX", 37: "LUK",
    255: "POW", 256: "STA", 257: "WIS", 258: "SPL", 259: "CON", 260: "CRT",
    263: "石碑開啟格數", 264: "石碑精煉",
}

# Build SCALAR_KEYS from loose keys and stat expansion
_LOOSE_KEYS = {"target_element", "skill_focus_AGI", "skill_focus_DEX", "total_AGI", "total_DEX"}
_STAT_NAMES = ("STR", "AGI", "VIT", "INT", "DEX", "LUK", "POW", "STA", "WIS", "SPL", "CON", "CRT")
_PREFIXES = ("base_", "job_", "equip_", "base_equip_", "total_")
_EXPANDED_KEYS = {f"{prefix}{stat}" for prefix in _PREFIXES for stat in _STAT_NAMES}

# Union of loose keys and expanded keys (loose keys include total_AGI and total_DEX which overlap with expansion)
SCALAR_KEYS = frozenset(_LOOSE_KEYS | _EXPANDED_KEYS)


@dataclass
class CalcContext:
    scalars: dict[str, int]                 # 角色檔能提供的子集(如base_*), 缺=miss
    refine_inputs: dict[int, int]
    grade: int | dict[int, int]
    get_values: dict[int, int]
    enabled_skill_levels: dict[int, int]    # 角色檔skills + EnableSkill寫入
    pure_jobs: list[int]
    slot_item_id_map: dict[int, int]
    weapon_level_map: dict[int, int]        # 讀寫
    armor_level_map: dict[int, int]
    weapon_type_map: dict[int, int]
    armor_weapon_map: dict[int, str]        # 只寫
    weapon_atk_map: dict[int, int]
    weapon_matk_map: dict[int, int]
    used_skill_levels: dict[int, bool]
    missing_keys: set[str] = field(default_factory=set)

    def scalar(self, key: str) -> int | None:
        """Get scalar value by key. Returns None if key is in SCALAR_KEYS but not in scalars,
        and records the missing key."""
        if key in SCALAR_KEYS and key not in self.scalars:
            self.missing_keys.add(key)
            return None
        return self.scalars.get(key)

    def get_value(self, n: int) -> int | None:
        """Get a get(N) character-stat UI field value. Returns None if N is
        not in get_values (either the field has no character-file source at
        all — see aggregate.GET_VALUE_FIELDS, e.g. N=200/MHP — or the
        character file simply didn't provide that particular stat), and
        records the missing key as f"get:{n}". Mirrors skill_level()'s shape:
        no static "known keys" gate, any absent N is a miss."""
        if n not in self.get_values:
            self.missing_keys.add(f"get:{n}")
            return None
        return self.get_values[n]

    def skill_level(self, skill_id: int) -> int | None:
        """Get skill level by ID. Returns None if skill is in SCALAR_KEYS but not in enabled_skill_levels,
        and records the missing key."""
        if skill_id not in self.enabled_skill_levels:
            self.missing_keys.add(f"skill:{skill_id}")
            return None
        return self.enabled_skill_levels[skill_id]

    def grade_value(self, slot: int | None) -> int:
        """Get grade value for a specific slot. Supports both int grade and per-slot dict grade."""
        if isinstance(self.grade, dict):
            try:
                return self.grade.get(int(slot), 0) if slot is not None else 0
            except Exception:
                return 0
        try:
            return int(self.grade or 0)
        except Exception:
            return 0
