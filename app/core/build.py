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
class CostTargets:
    """描述某格「從什麼狀態養到目前狀態」— spec §6, M3成本引擎的計算輸入。

    只有掛了cost_targets的格才計成本(見report.evaluate_build_cost) — 沒掛=
    使用者不關心該格成本, 不是「查無資料」, 不產生警告。
    """
    refine_from: int = 0
    grade_from: str = "none"
    refine_table: str | None = None  # 精煉表名(對照CostRules.refine_tables的key);
    # 必填才算精煉/升階成本 — 缺漏不在這裡(load_build)報錯, 因為build.py不持有
    # CostRules, 無從判斷表名是否存在; 留到report.evaluate_build_cost在eval-time
    # 對照真正的規則表驗證(不存在的表名一律ValueError, 沿用rules.py「不默默」
    # 的一貫作法), 目標為0(沒有實際養成動作)時則連warning都不產生。
    enchant_strategy: str = "last_slot_only"
    enchant_goal: tuple[int, str] | None = None  # (slot_index, option內部名);
    # 缺→report層取slot.enchants最末非null者, 依附魔表實際slot_index降冪對位


@dataclass
class SlotConfig:
    item_id: int
    refine: int = 0
    grade: str = "none"
    cards: list[int] = field(default_factory=list)
    enchants: list[str | None] = field(default_factory=list)  # internal_name
    cost_targets: CostTargets | None = None


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


_ENCHANT_STRATEGIES = frozenset({"stop_when_hit", "last_slot_only"})


def _load_cost_targets(slot_key: str, raw: dict | None) -> CostTargets | None:
    """解析單一格的cost_targets(spec §6) — 缺該鍵回傳None(該格不計成本)。

    M2/M5收尾補齊(M3 final review交辦): refine_from/enchant_strategy/
    enchant_goal三個欄位原本沒有在load時驗證(refine_from負數、
    enchant_strategy打錯字、enchant_goal塞一個剛好2字元的字串——len("ab")==2
    會被舊版len()==2判斷誤當成合法的[slot_index,option]兩元素陣列——都會
    一路帶著壞值往下游算, 直到report.py才用不明不白的方式失敗甚至算出
    看似合理但錯誤的數字), 這裡比照grade_from的一貫作法, 在load時就地擋下。
    """
    if raw is None:
        return None

    grade_from = raw.get("grade_from", "none")
    if grade_from not in GRADE_LEVELS:
        raise ValueError(
            f"配裝檔部位 '{slot_key}' 的cost_targets.grade_from '{grade_from}' 不合法,"
            f" 合法值: none/D/C/B/A"
        )

    refine_from = raw.get("refine_from", 0)
    # bool是int的子類別(isinstance(True, int)為True) — 明確排除, 否則JSON裡
    # 手滑寫成true/false的refine_from會被靜靜地當成1/0接受。
    if isinstance(refine_from, bool) or not isinstance(refine_from, int) or refine_from < 0:
        raise ValueError(
            f"配裝檔部位 '{slot_key}' 的cost_targets.refine_from '{refine_from}' 不合法,"
            f" 須為>=0的整數"
        )

    enchant_strategy = raw.get("enchant_strategy", "last_slot_only")
    if enchant_strategy not in _ENCHANT_STRATEGIES:
        raise ValueError(
            f"配裝檔部位 '{slot_key}' 的cost_targets.enchant_strategy "
            f"'{enchant_strategy}' 不合法, 合法值: {sorted(_ENCHANT_STRATEGIES)}"
        )

    enchant_goal_raw = raw.get("enchant_goal")
    if enchant_goal_raw is None:
        enchant_goal = None
    elif isinstance(enchant_goal_raw, (list, tuple)) and len(enchant_goal_raw) == 2:
        enchant_goal = (int(enchant_goal_raw[0]), str(enchant_goal_raw[1]))
    else:
        # 型別必須是list/tuple(不能是字串) — 一個剛好2字元的字串(如"ab")在
        # 純len()==2判斷下會被誤當成合法的兩元素陣列, 必須先擋型別再看長度。
        raise ValueError(
            f"配裝檔部位 '{slot_key}' 的cost_targets.enchant_goal必須是"
            f"[slot_index, option內部名]兩元素陣列, 得到{enchant_goal_raw!r}"
        )

    return CostTargets(
        refine_from=refine_from,
        grade_from=grade_from,
        refine_table=raw.get("refine_table"),
        enchant_strategy=enchant_strategy,
        enchant_goal=enchant_goal,
    )


def load_build(path) -> Build:
    """Load a Build from userdata/builds/*.json (spec §6).

    Each slot's ``cost_targets`` (M3 cost-engine input describing what state
    the item was grown FROM) is parsed into a CostTargets dataclass when
    present; absent entirely means the user opted out of costing that slot
    (see app.core.cost.report.evaluate_build_cost) — it is NOT ignored/dropped
    silently, unlike the M2-era behaviour this docstring used to describe.
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
            cost_targets=_load_cost_targets(slot_key, slot_data.get("cost_targets")),
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
