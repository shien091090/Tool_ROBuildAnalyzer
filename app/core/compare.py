"""Two-build effect comparison — align totals and derive advantage.

compare_builds() takes two BuildEffects and produces a list of CompareRow,
one per (key, unit) from the union of both builds' totals.

Advantage determination:
- Both values present, both negative → advantage goes to the MORE negative
  value (spec §9.1: 皆負代表消耗/詠唱時間等「越負越好」的削減類效果, 例如
  兩邊都是"SP消耗"減免, -7%比-3%更省, 應判-7%那方勝)
- Both values present, not both negative → advantage goes to the larger value
- Values equal → "tie"
- One value None → advantage goes to the build with a value
- Both None → "" (reserved for incomparable case; unreachable from union)

CAVEAT/已知限制: 這條「皆負時更負者勝」規則假設同一個key兩邊都是負值時,
負值一律代表削減類效果的加強(對玩家有利)。若某個key的負值其實是劣勢(例如
兩邊都是"ATK"的負向減益, 更負代表更差), 此規則會判反。目前資料中這種情況
罕見(負值key幾乎都是消耗/詠唱/延遲類削減), 故接受此限制。
"""

from dataclasses import dataclass

from app.core.aggregate import BuildEffects
from app.core.entries import CAT_ABILITY, CAT_DAMAGE, CAT_OTHER, CAT_RESIST, CAT_SECONDARY


@dataclass(frozen=True)
class CompareRow:
    key: str
    unit: str
    category: str
    a: float | None  # None = this build lacks this effect
    b: float | None  # None = this build lacks this effect
    advantage: str  # "a"|"b"|"tie"|"" (不可比 reserved but unreachable)


def compare_builds(a: BuildEffects, b: BuildEffects) -> list[CompareRow]:
    """Align totals from two BuildEffects and derive advantage for each row.

    Args:
        a: BuildEffects
        b: BuildEffects

    Returns:
        list[CompareRow] sorted by category (傷害→抗性→能力→次要能力→其他) then by key.
    """
    # Union of all (key, unit) pairs from both builds
    all_keys = set(a.totals.keys()) | set(b.totals.keys())

    rows = []
    for key, unit in all_keys:
        val_a = a.totals.get((key, unit))
        val_b = b.totals.get((key, unit))
        # category不重新解析: 讀BuildEffects.categories(parser.py算好的結構化
        # 欄位一路帶到這裡), a缺就退回b(缺一側totals的key,categories也只在
        # 有值的那一側)——不得對key字串再跑分類邏輯(spec §5).
        category = a.categories.get((key, unit)) or b.categories.get((key, unit))

        # Determine advantage
        if val_a is not None and val_b is not None:
            if val_a == val_b:
                advantage = "tie"
            elif val_a < 0 and val_b < 0:
                # spec §9.1: 皆負(減傷/詠唱/消耗類)更負者勝
                advantage = "a" if val_a < val_b else "b"
            else:
                advantage = "a" if val_a > val_b else "b"
        elif val_a is not None:
            advantage = "a"
        elif val_b is not None:
            advantage = "b"
        else:
            # Both None — unreachable from union, but reserve "" for clarity
            advantage = ""

        rows.append(
            CompareRow(
                key=key,
                unit=unit,
                category=category,
                a=val_a,
                b=val_b,
                advantage=advantage,
            )
        )

    # Sort: by category (傷害→抗性→能力→次要能力→其他), then by key
    category_order = {CAT_DAMAGE: 0, CAT_RESIST: 1, CAT_ABILITY: 2, CAT_SECONDARY: 3, CAT_OTHER: 4}
    rows.sort(key=lambda r: (category_order[r.category], r.key))

    return rows
