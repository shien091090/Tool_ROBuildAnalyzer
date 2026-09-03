"""CLI entrypoint — spec §13 手動驗證面, task-13 brief 輸出格式.

Usage:
    python -m app.cli effects <build.json> <character.json>
    python -m app.cli compare <a.json> <b.json> <character.json>

輸出格式 (brief 逐字): totals 依 category 分組印 ``{key} {+/-}{value}{unit}``,
之後印「未計入的條件效果」區塊(condition/missing/raw_lines), 之後印 warnings。
純 print, 不做花式排版。``effects`` 額外印一個「其他效果」區塊
(DESCRIPTIVE/PROC/UNRECOGNIZED — 敘述性技能解鎖、狀態觸發、無法辨識的行), 因為
BuildEffects.others 若完全不印, 這些資訊就從CLI輸出中消失了; brief 沒有禁止,
只是沒把它列進三段式輸出格式裡, 故排在 totals 之後、未計入區塊之前。
``compare`` 只印對齊表(brief 原話「印對齊表」), 額外在表格後方各自印兩個build的
warnings(如果非空) — 同樣是「不隱藏錯誤」的最小擴充, 不影響對齊表本身格式。
"""

from __future__ import annotations

import argparse
import sys

from app.core.aggregate import BuildEffects, evaluate_build
from app.core.build import load_build, load_character
from app.core.compare import CompareRow, compare_builds
from app.core.db_reader import DbReader
from app.core.entries import CAT_MAGICAL, CAT_OTHER, CAT_PHYSICAL
from app.core.maps import make_maps
from importer.config import ConfigInvalidError, ConfigNotFoundError
from importer.config import load as load_config

_CATEGORY_ORDER = [CAT_PHYSICAL, CAT_MAGICAL, CAT_OTHER]
_CATEGORY_LABEL = {CAT_PHYSICAL: "physical", CAT_MAGICAL: "magical", CAT_OTHER: "other"}


def resolve_db_path(config_path: str = "config.json") -> str:
    """config.json 的 db_path 欄位(不存在/不合法時退回預設 data/ro_items.db)."""
    try:
        return load_config(config_path).db_path
    except (ConfigNotFoundError, ConfigInvalidError):
        return "data/ro_items.db"


def _signed(value: float, unit: str) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}{abs(value)}{unit}"


def _print_totals(effects: BuildEffects) -> None:
    print("[分類效果加總]")
    by_cat: dict[str, list[tuple[str, str, float]]] = {c: [] for c in _CATEGORY_ORDER}
    for (key, unit), value in effects.totals.items():
        # category不重新解析key字串, 讀BuildEffects.categories(parser.py算好
        # 一路帶下來的結構化欄位, spec §5).
        by_cat[effects.categories[(key, unit)]].append((key, unit, value))
    any_row = False
    for cat in _CATEGORY_ORDER:
        rows = sorted(by_cat[cat])
        if not rows:
            continue
        any_row = True
        print(f"-- {_CATEGORY_LABEL[cat]} --")
        for key, unit, value in rows:
            print(f"{key} {_signed(value, unit)}")
    if not any_row:
        print("(無)")


def _print_others(effects: BuildEffects) -> None:
    print()
    print("[其他效果(不計入加總): 敘述性/技能觸發/無法辨識]")
    if not effects.others:
        print("(無)")
        return
    for se in effects.others:
        entry = se.entry
        extra = f" extra={entry.extra}" if entry.extra else ""
        print(f"- {se.source}（部位:{se.slot_key}）: {entry.key}{extra}")


def _print_unresolved(effects: BuildEffects) -> None:
    print()
    print("[未計入的條件效果]")
    if not effects.unresolved:
        print("(無)")
        return
    for se in effects.unresolved:
        extra = se.entry.extra or {}
        print(f"- {se.source}（部位:{se.slot_key}）")
        print(f"  condition: {extra.get('condition')}")
        print(f"  missing: {extra.get('missing')}")
        print(f"  raw_lines: {extra.get('raw_lines')}")


def _print_warnings(warnings: list[str]) -> None:
    print()
    print("[warnings]")
    if not warnings:
        print("(無)")
        return
    for w in warnings:
        print(w)


def cmd_effects(build_path: str, character_path: str) -> None:
    db_path = resolve_db_path()
    build = load_build(build_path)
    character = load_character(character_path)
    maps = make_maps(db_path)
    with DbReader(db_path) as reader:
        effects = evaluate_build(build, character, reader, maps)

    print(f"=== {build.name} 效果結算 ===")
    _print_totals(effects)
    _print_others(effects)
    _print_unresolved(effects)
    _print_warnings(effects.warnings)


def _print_compare_row(row: CompareRow) -> None:
    a_str = _signed(row.a, row.unit) if row.a is not None else "(無)"
    b_str = _signed(row.b, row.unit) if row.b is not None else "(無)"
    print(f"{row.key}: A={a_str} B={b_str} advantage={row.advantage}")


def cmd_compare(a_path: str, b_path: str, character_path: str) -> None:
    db_path = resolve_db_path()
    build_a = load_build(a_path)
    build_b = load_build(b_path)
    character = load_character(character_path)
    maps = make_maps(db_path)
    with DbReader(db_path) as reader:
        effects_a = evaluate_build(build_a, character, reader, maps)
        effects_b = evaluate_build(build_b, character, reader, maps)

    rows = compare_builds(effects_a, effects_b)
    print(f"=== {build_a.name} vs {build_b.name} 比較 ===")
    if not rows:
        print("(無)")
    current_cat = None
    for row in rows:
        if row.category != current_cat:
            current_cat = row.category
            print(f"-- {_CATEGORY_LABEL.get(current_cat, current_cat)} --")
        _print_compare_row(row)

    for label, effects in ((build_a.name, effects_a), (build_b.name, effects_b)):
        if effects.warnings:
            print()
            print(f"[warnings: {label}]")
            for w in effects.warnings:
                print(w)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    p_effects = sub.add_parser("effects", help="印單一配裝的分類效果清單+unresolved+warnings")
    p_effects.add_argument("build", help="build.json 路徑")
    p_effects.add_argument("character", help="character.json 路徑")

    p_compare = sub.add_parser("compare", help="印兩個配裝的對齊比較表")
    p_compare.add_argument("a", help="build a.json 路徑")
    p_compare.add_argument("b", help="build b.json 路徑")
    p_compare.add_argument("character", help="character.json 路徑")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.command == "effects":
        cmd_effects(args.build, args.character)
    elif args.command == "compare":
        cmd_compare(args.a, args.b, args.character)
    return 0


if __name__ == "__main__":
    sys.exit(main())
