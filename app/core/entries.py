from dataclasses import dataclass

# Constants for effect kind
KIND_NUMERIC = "numeric"
KIND_DESCRIPTIVE = "descriptive"
KIND_PROC = "proc"
KIND_UNRESOLVED = "unresolved_condition"
KIND_UNRECOGNIZED = "unrecognized"

# Constants for effect category (user-approved 4-group taxonomy, assigned
# explicitly at handler level in parser.py — NOT derived from key keywords).
CAT_DAMAGE = "damage"        # 傷害
CAT_RESIST = "resist"        # 抗性
CAT_ABILITY = "ability"      # 能力
CAT_SECONDARY = "secondary"  # 次要能力
CAT_OTHER = "other"          # 其他(非效果條目)


@dataclass(frozen=True)
class EffectEntry:
    key: str
    value: float | None
    unit: str            # "" | "%" | "秒"
    kind: str
    category: str
    extra: dict | None = None
