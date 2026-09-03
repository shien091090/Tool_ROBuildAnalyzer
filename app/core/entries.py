from dataclasses import dataclass

# Constants for effect kind
KIND_NUMERIC = "numeric"
KIND_DESCRIPTIVE = "descriptive"
KIND_PROC = "proc"
KIND_UNRESOLVED = "unresolved_condition"
KIND_UNRECOGNIZED = "unrecognized"

# Constants for effect category
CAT_PHYSICAL = "physical"
CAT_MAGICAL = "magical"
CAT_OTHER = "other"


@dataclass(frozen=True)
class EffectEntry:
    key: str
    value: float | None
    unit: str            # "" | "%" | "秒"
    kind: str
    category: str
    extra: dict | None = None


def classify_category(key: str) -> str:
    """Classify effect category based on key keywords.

    Physical keywords take priority, then magical, then other.
    """
    physical_keywords = ("物理", "ATK", "P.ATK", "CRI", "C.RATE", "HIT", "近距離", "遠距離", "爆擊", "暴擊", "武器", "誘導攻擊")
    magical_keywords = ("魔法", "MATK", "S.MATK", "MDEF", "MRES", "變動詠唱", "固定詠唱", "詠唱")

    # Check physical keywords first (physical takes priority)
    for keyword in physical_keywords:
        if keyword in key:
            return CAT_PHYSICAL

    # Then check magical keywords
    for keyword in magical_keywords:
        if keyword in key:
            return CAT_MAGICAL

    # Default to other
    return CAT_OTHER
