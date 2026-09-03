"""Two-build effect comparison — align totals and derive advantage.

compare_builds() takes two BuildEffects and produces a list of CompareRow,
one per (key, unit) from the union of both builds' totals.

Advantage determination (M2 behavior — see caveat below):
- Both values present → advantage goes to the build with larger value
- Values equal → "tie"
- One value None → advantage goes to the build with a value
- Both None → "" (reserved for incomparable case; unreachable from union)

CAVEAT: Negative effects (e.g., "SP消耗" cost reductions, healing cooldown
reductions) are NOT special-cased for direction. M2 implementation treats
"larger value = advantage" uniformly across all keys. UI phase may revisit
this logic to negate specific keys before comparison. For now, we simply
implement the contract: biggest value wins.
"""

from dataclasses import dataclass

from app.core.aggregate import BuildEffects
from app.core.entries import classify_category


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
        list[CompareRow] sorted by category (physical→magical→other) then by key.
    """
    # Union of all (key, unit) pairs from both builds
    all_keys = set(a.totals.keys()) | set(b.totals.keys())

    rows = []
    for key, unit in all_keys:
        val_a = a.totals.get((key, unit))
        val_b = b.totals.get((key, unit))
        category = classify_category(key)

        # Determine advantage
        if val_a is not None and val_b is not None:
            if val_a == val_b:
                advantage = "tie"
            elif val_a > val_b:
                advantage = "a"
            else:
                advantage = "b"
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

    # Sort: by category (physical→magical→other), then by key
    category_order = {"physical": 0, "magical": 1, "other": 2}
    rows.sort(key=lambda r: (category_order[r.category], r.key))

    return rows
