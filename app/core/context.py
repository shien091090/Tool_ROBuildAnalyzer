from dataclasses import dataclass, field

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
