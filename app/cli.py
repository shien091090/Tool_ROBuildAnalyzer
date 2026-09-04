"""CLI entrypoint — spec §13 手動驗證面, task-13/task-8 brief 輸出格式.

Usage:
    python -m app.cli effects <build.json> <character.json>
    python -m app.cli compare <a.json> <b.json> <character.json>
    python -m app.cli cost <build.json>

輸出格式 (brief 逐字): totals 依 category 分組印 ``{key} {+/-}{value}{unit}``,
之後印「未計入的條件效果」區塊(condition/missing/raw_lines), 之後印 warnings。
純 print, 不做花式排版。``effects`` 額外印一個「其他效果」區塊
(DESCRIPTIVE/PROC/UNRECOGNIZED — 敘述性技能解鎖、狀態觸發、無法辨識的行), 因為
BuildEffects.others 若完全不印, 這些資訊就從CLI輸出中消失了; brief 沒有禁止,
只是沒把它列進三段式輸出格式裡, 故排在 totals 之後、未計入區塊之前。
``compare`` 只印對齊表(brief 原話「印對齊表」), 額外在表格後方各自印兩個build的
warnings(如果非空) — 同樣是「不隱藏錯誤」的最小擴充, 不影響對齊表本身格式。

``cost`` 不需要character.json(cost_targets/裝備本體資訊全在build.json本身,
養成成本不看角色屬性) — 逐格照spec §7.3三層輸出: [直接消耗(合成品層)] →
[中間合成品(供參考)] → [基礎材料攤開](name x qty x 單價 = 小計) → 兌換/精煉/
升階手續費+附魔費 → 本體(件, 純顯示不計價) → 該格Zeny小計; 逐格印完後印
配裝總Zeny + warnings。數量一律Fraction轉float取2位小數, Zeny一律
int(total)後取千分位(Fraction本身不四捨五入, 跟其餘三層數字一致用float直接
顯示, 只有錢的最終小計/總計才整數化, 呼應brief「Zeny千分位整數」的要求)。
沒有任何格掛cost_targets(evaluate_build_cost回傳items=[])時, 印一行友善訊息
而不是留空 — 使用者才知道「這不是算錯, 是這個配裝檔本來就沒設定要算成本」。
"""

from __future__ import annotations

import argparse
import json
import sys
from fractions import Fraction
from pathlib import Path

from app.core.aggregate import BuildEffects, evaluate_build
from app.core.build import load_build, load_character
from app.core.compare import CompareRow, compare_builds
from app.core.cost.report import ItemCostReport, evaluate_build_cost
from app.core.cost.rules import load_prices, load_rules
from app.core.db_reader import DbReader
from app.core.entries import CAT_ABILITY, CAT_DAMAGE, CAT_OTHER, CAT_RESIST, CAT_SECONDARY
from app.core.maps import make_maps
from importer.config import ConfigInvalidError, ConfigNotFoundError
from importer.config import load as load_config

_CATEGORY_ORDER = [CAT_DAMAGE, CAT_RESIST, CAT_ABILITY, CAT_SECONDARY, CAT_OTHER]
_CATEGORY_LABEL = {
    CAT_DAMAGE: "傷害",
    CAT_RESIST: "抗性",
    CAT_ABILITY: "能力",
    CAT_SECONDARY: "次要能力",
    CAT_OTHER: "其他",
}


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


def _load_manual_enchants(path: str = "userdata/manual_enchants.json") -> dict:
    """讀manual_enchants.json — 跟load_rules/load_prices同一種路徑慣例(相對
    repo root), enchant.py只吃dict, 這裡沒有專屬dataclass可載, 純json.loads。
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _fmt_qty(qty: Fraction) -> str:
    return f"{float(qty):.2f}"


def _fmt_zeny(value: Fraction) -> str:
    return f"{int(value):,}"


def _print_material_lines(title: str, materials: dict[str, Fraction]) -> None:
    print(title)
    if not materials:
        print("(無)")
        return
    for name, qty in sorted(materials.items()):
        print(f"{name} x {_fmt_qty(qty)}")


def _print_base_materials(base: dict[str, Fraction], prices: dict[str, int]) -> None:
    print("[基礎材料攤開]")
    if not base:
        print("(無)")
        return
    for name, qty in sorted(base.items()):
        price = prices.get(name, 0)
        subtotal = qty * Fraction(price)
        print(f"{name} x {_fmt_qty(qty)} x {price:,} = {_fmt_zeny(subtotal)}")


def _print_item_cost(item: ItemCostReport, prices: dict[str, int]) -> None:
    print()
    print(f"-- 部位:{item.slot_key}（{item.item_name}） --")
    _print_material_lines("[直接消耗(合成品層)]", item.direct)
    print()
    _print_material_lines("[中間合成品(供參考)]", item.intermediates)
    print()
    _print_base_materials(item.base, prices)
    print()
    print(f"兌換手續費: {_fmt_zeny(item.exchange_fee)} Zeny")
    print(f"精煉手續費: {_fmt_zeny(item.refine_fee)} Zeny")
    print(f"升階手續費: {_fmt_zeny(item.grade_fee)} Zeny")
    print(f"附魔費: {_fmt_zeny(item.enchant_zeny)} Zeny")
    print(f"本體(件): {_fmt_qty(item.body_count)}")
    print(f"該格Zeny小計: {_fmt_zeny(item.zeny_total)} Zeny")


def cmd_cost(build_path: str) -> None:
    db_path = resolve_db_path()
    build = load_build(build_path)
    rules = load_rules()
    prices = load_prices()
    manual = _load_manual_enchants()
    with DbReader(db_path) as reader:
        report = evaluate_build_cost(build, rules, prices, reader, manual)

    print(f"=== {build.name} 成本結算 ===")
    if not report.items:
        print("(無部位設定cost_targets, 未計算任何成本)")
        return

    for item in report.items:
        _print_item_cost(item, prices)

    print()
    print(f"配裝總Zeny: {_fmt_zeny(report.zeny_total)} Zeny")
    _print_warnings(report.warnings)


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

    p_cost = sub.add_parser("cost", help="印配裝各部位的養成成本三層報表+總計+warnings")
    p_cost.add_argument("build", help="build.json 路徑")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.command == "effects":
        cmd_effects(args.build, args.character)
    elif args.command == "compare":
        cmd_compare(args.a, args.b, args.character)
    elif args.command == "cost":
        cmd_cost(args.build)
    return 0


if __name__ == "__main__":
    sys.exit(main())
