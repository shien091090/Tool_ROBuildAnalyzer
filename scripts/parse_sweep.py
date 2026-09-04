"""全量解析健康掃描腳本(M2 final review建議4, task-7 hygiene batch)。

對 data/ro_items.db 裡每一筆 items.onstart_equip_src 與 combos.onstart_src,
用一組固定context(無角色檔)跑 parse_effect_block, 統計:
  - 總block數(有onstart原始碼的列數)
  - 例外數(parse_effect_block本身不該丟例外 — 必須是0, 非0時腳本以exit
    code 1結束, 供CI/人工快速判斷解析器有沒有回歸)
  - 各EffectEntry.kind的條目計數(numeric/descriptive/proc/unresolved_condition/
    unrecognized合計)
  - UNRECOGNIZED raw_line 正規化後(數字統一替換成N, 供分組)最常見的前20種樣式

固定context(brief裁決, 不讀真實角色檔):
  - refine 13、grade {slot_id: 4}(對應4級, 見app.core.build.GRADE_LEVELS)
  - slot_id 依 items.equip_type 粗分: armor -> 2; Mweapon/Rweapon -> 4;
    其餘(ammo/Cannonball/None等) -> 2
  - combos沒有equip_type欄位, 固定用slot_id=2(視同防具槽, 與armor同組)
  - 角色相關欄位一律空: scalars={}, enabled_skill_levels={}, get_values={}

用法:
    PYTHONIOENCODING=utf-8 py -3.12-64 scripts/parse_sweep.py [--db PATH] [--top N]
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

from app.core.context import CalcContext
from app.core.entries import (
    KIND_DESCRIPTIVE,
    KIND_NUMERIC,
    KIND_PROC,
    KIND_UNRECOGNIZED,
    KIND_UNRESOLVED,
)
from app.core.maps import make_maps
from app.core.parser import parse_effect_block

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB = _REPO_ROOT / "data" / "ro_items.db"

_ALL_KINDS = (KIND_NUMERIC, KIND_DESCRIPTIVE, KIND_PROC, KIND_UNRESOLVED, KIND_UNRECOGNIZED)

_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _slot_id_for_equip_type(equip_type: str | None) -> int:
    """armor -> 2; Mweapon/Rweapon -> 4; 其餘(含None) -> 2(brief裁決的粗分規則)。"""
    if equip_type in ("Mweapon", "Rweapon"):
        return 4
    return 2


def _empty_ctx(slot_id: int) -> CalcContext:
    return CalcContext(
        scalars={},
        refine_inputs={slot_id: 13},
        grade={slot_id: 4},
        get_values={},
        enabled_skill_levels={},
        pure_jobs=[],
        slot_item_id_map={},
        weapon_level_map={},
        armor_level_map={},
        weapon_type_map={},
        armor_weapon_map={},
        weapon_atk_map={},
        weapon_matk_map={},
        used_skill_levels={},
    )


def _normalize_raw_line(line: str) -> str:
    """把raw_line裡的數字統一換成N, 讓同函式不同參數的行能分到同一組
    (如 AddExtParam(0, 45, 3) / AddExtParam(0, 45, 5) -> AddExtParam(N, N, N))。
    """
    return _NUM_RE.sub("N", line)


class _SweepResult:
    def __init__(self, label: str):
        self.label = label
        self.total_rows = 0       # 有onstart原始碼的列數
        self.total_blocks = 0     # 實際跑完parse_effect_block(未丟例外)的block數
        self.exceptions: list[tuple[int, str]] = []  # (id, error message)
        self.kind_counts: Counter = Counter()
        self.unrecognized_patterns: Counter = Counter()

    @property
    def exception_count(self) -> int:
        return len(self.exceptions)

    def record(self, row_id: int, src: str, slot_id: int, maps) -> None:
        self.total_rows += 1
        ctx = _empty_ctx(slot_id)
        try:
            result = parse_effect_block(src, ctx, slot_id, maps)
        except Exception as exc:  # noqa: BLE001 - 掃描腳本要抓住一切例外並列出
            self.exceptions.append((row_id, f"{type(exc).__name__}: {exc}"))
            return

        self.total_blocks += 1
        for entry in result.entries:
            self.kind_counts[entry.kind] += 1
            if entry.kind == KIND_UNRECOGNIZED:
                raw_line = entry.extra.get("raw_line", "") if entry.extra else ""
                self.unrecognized_patterns[_normalize_raw_line(raw_line)] += 1

    def print_report(self, top_n: int) -> None:
        print(f"=== {self.label} ===")
        print(f"總列數(有onstart原始碼): {self.total_rows}")
        print(f"成功解析block數: {self.total_blocks}")
        print(f"例外數: {self.exception_count}")
        if self.exceptions:
            print("例外明細(前20筆):")
            for row_id, msg in self.exceptions[:20]:
                print(f"  id={row_id}: {msg}")

        print("各kind條目計數:")
        for kind in _ALL_KINDS:
            print(f"  {kind}: {self.kind_counts.get(kind, 0)}")

        print(f"UNRECOGNIZED raw_line 樣式頻率排行(前{top_n}):")
        for pattern, count in self.unrecognized_patterns.most_common(top_n):
            print(f"  {count:6d}  {pattern}")
        print()


def sweep_items(conn: sqlite3.Connection, maps) -> _SweepResult:
    result = _SweepResult("items.onstart_equip_src")
    cursor = conn.execute(
        "SELECT item_id, equip_type, onstart_equip_src FROM items"
        " WHERE onstart_equip_src IS NOT NULL AND onstart_equip_src != ''"
    )
    for item_id, equip_type, src in cursor.fetchall():
        slot_id = _slot_id_for_equip_type(equip_type)
        result.record(item_id, src, slot_id, maps)
    return result


def sweep_combos(conn: sqlite3.Connection, maps) -> _SweepResult:
    result = _SweepResult("combos.onstart_src")
    cursor = conn.execute(
        "SELECT combo_id, onstart_src FROM combos"
        " WHERE onstart_src IS NOT NULL AND onstart_src != ''"
    )
    for combo_id, src in cursor.fetchall():
        result.record(combo_id, src, 2, maps)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(_DEFAULT_DB), help="ro_items.db路徑(預設 data/ro_items.db)")
    parser.add_argument("--top", type=int, default=20, help="UNRECOGNIZED樣式排行顯示筆數(預設20)")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"找不到資料庫: {db_path}（需先執行 importer.cli 產生 data/ro_items.db）")
        return 1

    maps = make_maps(str(db_path))
    conn = sqlite3.connect(str(db_path))
    try:
        items_result = sweep_items(conn, maps)
        combos_result = sweep_combos(conn, maps)
    finally:
        conn.close()

    items_result.print_report(args.top)
    combos_result.print_report(args.top)

    total_exceptions = items_result.exception_count + combos_result.exception_count
    print(f"=== 總結 ===")
    print(f"總例外數(items+combos): {total_exceptions}")
    if total_exceptions:
        print("有例外, 解析器出現回歸 — 需修復。")
        return 1

    print("零例外, 解析器健康。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
