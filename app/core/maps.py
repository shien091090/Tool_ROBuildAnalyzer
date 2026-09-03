import sqlite3
from dataclasses import dataclass

# Static tables copied from ItemSearchApp.py (lines 2100-2249)
EFFECT_MAP = {
    41: "ATK", 45: "DEF", 47: "MDEF", 49: "HIT", 50: "FLEE", 51: "完全迴避", 52: "CRI", 54: "ASPD",
    103: "STR", 104: "AGI", 105: "VIT", 106: "INT", 107: "DEX", 108: "LUK",
    109: "MHP", 110: "MSP", 111: "MHP%", 112: "MSP%", 113: "HP自然恢復%", 114: "SP自然恢復%",
    140: "MATK%", 167: "攻擊後延遲", 200: "MATK", 207: "ATK%",
    234: "POW", 235: "STA", 236: "WIS", 237: "SPL", 238: "CON", 239: "CRT",
    242: "P.ATK", 243: "S.MATK", 244: "RES", 245: "MRES",
    253: "C.RATE", 254: "H.PLUS",
    #非官方編碼 用於二轉以下的技能跟集中覺醒波色克藥水
    301: "(2轉以下)攻擊後延遲",302: "(2轉以下)ASPD"
}

ELEMENT_MAP = {
    0: "無屬性",
    1: "水屬性",
    2: "地屬性",
    3: "火屬性",
    4: "風屬性",
    5: "毒屬性",
    6: "聖屬性",
    7: "暗屬性",
    8: "念屬性",
    9: "不死屬性",
    10: "全屬性",
    999: "（不使用）"
}

SIZE_MAP = {
    0: "小型",
    1: "中型",
    2: "大型"
}

RACE_MAP = {
    0: "無形",
    1: "不死",
    2: "動物",
    3: "植物",
    4: "昆蟲",
    5: "魚貝",
    6: "惡魔",
    7: "人形",
    8: "天使",
    9: "龍族",
    10: "玩家（人類）",
    11: "玩家（貓族）",
    9999: "全種族"
}

UNIT_MAP = {
    0: "玩家",
    1: "魔物"
}

CLASS_MAP = {
    0: "一般",
    1: "首領",
    2: "監護人"
}

STAT_NAME_SETS = {  # 裝備基礎編碼
    "armor": [
        "DEF", "STR", "INT", "VIT", "DEX", "AGI", "LUK", "未知7", "未知8",
        "MDEF", "防具等級", "POW", "SPL", "STA", "WIS", "CON", "CRT"
    ],
    "Mweapon": [
        "武器屬性", "武器類型", "武器ATK", "武器MATK", "STR", "INT", "VIT", "DEX", "AGI",
        "LUK", "武器等級", "POW", "SPL", "STA", "WIS", "CON", "CRT"
    ],
    "Rweapon": [
        "武器類型", "武器ATK", "STR", "INT", "VIT", "DEX", "AGI", "LUK", "武器等級",
         "POW", "SPL", "STA", "WIS", "CON", "CRT"
    ],
    "ammo": [
        "屬性", "箭矢/彈藥ATK"
    ],
    "Cannonball": [
        "屬性", "砲彈ATK"
    ]
}

WEAPON_TYPE_MAP = {  # WPon()
    0: "空手", 1: "短劍", 2: "單手劍", 3: "雙手劍", 4: "單手矛", 5: "雙手矛",
    6: "單手斧", 7: "雙手斧", 8: "鈍器", 10: "單手仗", 12: "拳套",
    13: "樂器", 14: "鞭子", 15: "書", 16: "拳刃", 23: "雙手仗",
    11: "弓", 17: "左輪手槍", 18: "來福槍", 19: "格林機關槍",
    20: "霰彈槍", 21: "榴彈槍", 22: "風魔飛鏢"
}

EXCLUDED_STAT_NAMES = {  # 過濾不顯示到效果
    "防具等級", "武器等級", "武器類型"
}

# Plain effect map from ro_core.py (lines 2307-2320)
PLAIN_EFFECT_MAP = {
    "NoDispell": "詠唱不中斷",
    "Magicimmune": "不受魔法效果影響",
    "NoJamstone": "使用技能不消耗魔力礦石",
    "NoMadogearfuel": "不消耗魔導機甲燃料",
    "AddNeverknockback": "不會被擊退",
    "Clairvoyance": "可看見隱匿目標",
    "Reincarnation": "復活時恢復 HP/SP 100%",
    "SplashAttack": "普攻範圍增加",
}

# Status map from ro_core.py (lines 2330-2336)
STATUS_MAP = {
    13: "霸體",
    14: "移動速度增加",
    15: "攻擊速度增加",
    21: "集中",
    26: "看見隱匿目標",
}


@dataclass
class EffectMaps:
    skill_map: dict[int, str]  # skill_id→中文名(來自DB)


def load_skill_map(db_path: str) -> dict[int, str]:
    """Load skill map from database (skill_id -> skill_name).

    Raises sqlite3.OperationalError if the skills table does not exist or other DB errors occur.
    Uses context manager to ensure connection always closes.
    """
    skill_map = {}
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT skill_id, skill_name FROM skills")
            for skill_id, skill_name in cursor.fetchall():
                skill_map[skill_id] = skill_name
        finally:
            cursor.close()
    return skill_map


def make_maps(db_path: str) -> EffectMaps:
    """Create EffectMaps instance with skill map loaded from database."""
    return EffectMaps(skill_map=load_skill_map(db_path))
