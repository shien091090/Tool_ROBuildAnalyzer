"""Cost-engine rule loading & validation — spec M3 §7 材料/精煉成本引擎.

load_rules() 讀 userdata/refine_rules.json, 把每張精煉表的逐級 step 攤平成
RefineStep 列表(已依 from_lv 排序 — json 本身已是遞增順序, 這裡不重排, 只在
驗證階段確認遞增無跳級), 並把升階(grade)與乙太兌換(exchange)兩張表分別解析
成 GradeStep 列表與 exchange_recipes dict。所有機率一律用 Fraction(原始字串)
解析, 因為 json 裡的機率是十進位字串(如 "0.4"), 用字串建 Fraction 才精確,
不會像 float(0.4) 那樣帶入二進位誤差。

驗證失敗一律拋 ValueError, 訊息帶表名/階級, 方便使用者定位是哪張表哪一階
的資料錯了 — 不靜默丟棄或用預設值蓋過去(spec 對「不默默」的一貫要求)。
"""

import json
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

FAIL_VALUES = frozenset({"safe", "minus1", "stay", "break"})


@dataclass(frozen=True)
class RefineStep:
    from_lv: int
    to_lv: int
    material: str
    qty: int
    rate: Fraction
    fail: str  # "safe"|"minus1"|"stay"|"break"
    blessing: int
    fee: int  # 每次嘗試的NPC手續費(Zeny) — Task 1修正後每一階都有此欄位


@dataclass(frozen=True)
class GradeStep:
    from_grade: str
    to_grade: str
    refine_req: int
    rate: Fraction
    materials: tuple[tuple[str, int], ...]
    fee: int


@dataclass
class CostRules:
    refine_tables: dict[str, list[RefineStep]]  # 已展開成逐級step, 依from_lv排序
    table_displays: dict[str, str]
    blessing_item: str
    grade_steps: list[GradeStep]  # none→D→C→B→A順序
    exchange_recipes: dict[str, tuple[list[tuple[str, int]], int]]  # name→(inputs, fee)


def _parse_rate(raw, context: str) -> Fraction:
    try:
        rate = Fraction(str(raw))
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"{context}: rate「{raw}」格式錯誤, 須為可解析的分數/小數字串") from exc
    if not (Fraction(0) < rate <= Fraction(1)):
        raise ValueError(f"{context}: rate必須介於(0,1]之間, 得到{rate}")
    return rate


def _parse_fail(raw, context: str) -> str:
    if raw not in FAIL_VALUES:
        raise ValueError(f"{context}: fail值「{raw}」不合法, 須為{sorted(FAIL_VALUES)}其中之一")
    return raw


def _parse_fee(raw, context: str) -> int:
    fee = int(raw)
    if fee < 0:
        raise ValueError(f"{context}: fee不得為負數, 得到{fee}")
    return fee


def _parse_refine_table(table_name: str, raw_table: dict) -> list[RefineStep]:
    steps: list[RefineStep] = []
    prev_to_lv: int | None = None
    for idx, raw_step in enumerate(raw_table.get("steps", [])):
        from_lv = int(raw_step["from"])
        to_lv = int(raw_step["to"])
        context = f"精煉表「{table_name}」第{idx + 1}階({from_lv}→{to_lv})"

        if to_lv != from_lv + 1:
            raise ValueError(f"{context}: 不可跳級, to必須等於from+1")
        if prev_to_lv is not None and from_lv != prev_to_lv:
            raise ValueError(f"{context}: 階級不連續, from必須等於前一階的to({prev_to_lv})")

        rate = _parse_rate(raw_step["rate"], context)
        fail = _parse_fail(raw_step["fail"], context)
        if from_lv == 0 and fail == "minus1":
            raise ValueError(f"{context}: from=0時fail不得為minus1(沒有更低階可退)")
        fee = _parse_fee(raw_step.get("fee", 0), context)

        steps.append(
            RefineStep(
                from_lv=from_lv,
                to_lv=to_lv,
                material=raw_step["material"],
                qty=int(raw_step["qty"]),
                rate=rate,
                fail=fail,
                blessing=int(raw_step["blessing"]),
                fee=fee,
            )
        )
        prev_to_lv = to_lv
    return steps


def _parse_grade_steps(raw_steps: list) -> list[GradeStep]:
    steps: list[GradeStep] = []
    prev_to_grade: str | None = None
    for idx, raw_step in enumerate(raw_steps):
        from_grade = raw_step["from"]
        to_grade = raw_step["to"]
        context = f"升階表第{idx + 1}階({from_grade}→{to_grade})"

        if prev_to_grade is not None and from_grade != prev_to_grade:
            raise ValueError(f"{context}: 階級不連續, from必須等於前一階的to({prev_to_grade})")

        rate = _parse_rate(raw_step["rate"], context)
        fee = _parse_fee(raw_step.get("fee", 0), context)
        materials = tuple(
            (m["name"], int(m["qty"])) for m in raw_step.get("materials", [])
        )
        for name, qty in materials:
            if qty <= 0:
                raise ValueError(f"{context}: 材料「{name}」數量必須為正整數, 得到{qty}")

        steps.append(
            GradeStep(
                from_grade=from_grade,
                to_grade=to_grade,
                refine_req=int(raw_step["refine_req"]),
                rate=rate,
                materials=materials,
                fee=fee,
            )
        )
        prev_to_grade = to_grade
    return steps


def _parse_exchange_recipes(raw_recipes: dict) -> dict[str, tuple[list[tuple[str, int]], int]]:
    recipes: dict[str, tuple[list[tuple[str, int]], int]] = {}
    for name, raw_recipe in raw_recipes.items():
        context = f"兌換配方「{name}」"
        fee = _parse_fee(raw_recipe.get("fee", 0), context)
        inputs: list[tuple[str, int]] = []
        for raw_input in raw_recipe.get("inputs", []):
            qty = int(raw_input["qty"])
            if qty <= 0:
                raise ValueError(f"{context}: 材料「{raw_input['name']}」數量必須為正整數, 得到{qty}")
            inputs.append((raw_input["name"], qty))
        recipes[name] = (inputs, fee)
    return recipes


def load_rules(path: str = "userdata/refine_rules.json") -> CostRules:
    """讀取並驗證 refine_rules.json, 回傳展開後的 CostRules。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))

    refine_tables: dict[str, list[RefineStep]] = {}
    table_displays: dict[str, str] = {}
    for table_name, raw_table in data.get("refine_tables", {}).items():
        refine_tables[table_name] = _parse_refine_table(table_name, raw_table)
        table_displays[table_name] = raw_table.get("display", table_name)

    return CostRules(
        refine_tables=refine_tables,
        table_displays=table_displays,
        blessing_item=data["blessing_item"],
        grade_steps=_parse_grade_steps(data.get("grade_steps", [])),
        exchange_recipes=_parse_exchange_recipes(data.get("exchange_recipes", {})),
    )


def load_prices(path: str = "userdata/prices.json") -> dict[str, int]:
    """讀取 prices.json — 材料名→Zeny單價。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {name: int(price) for name, price in data.items()}
