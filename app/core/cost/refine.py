"""精煉/升階期望值求解器 — spec M3 §7.1/§7.2 材料/成本引擎核心。

求解方式: 把「從等級k精煉到target」的期望消耗 E[k] (k=0..target-1, E[target]=0
是邊界條件)當成線性方程組的未知數, 每一階(RefineStep)依失敗型態(fail)貢獻
係數矩陣A的一列與各材料/祝福/手續費/本體(body)各自獨立RHS向量裡的一格,
再用Fraction全程精確(無浮點)的高斯-喬丹消去一次解出所有RHS欄位。四型態
的方程式來源(spec §7.1, 已由控制者定案並經練習腳本驗證):

    safe:   E[k] = C_k + E[k+1]                       (保證成功, 不看rate)
    minus1: E[k] = C_k + p*E[k+1] + (1-p)*E[k-1]       (失敗退一級, 材料/手續費
                                                          每次嘗試恰消耗一次,
                                                          不必除以p —
                                                          多次嘗試已經隱含在
                                                          E[k-1]的遞迴裡)
    stay:   E[k] = C_k/p + E[k+1]                      (失敗留原地重試, 材料/
                                                          祝福/手續費按1/p的
                                                          幾何期望次數放大)
    break:  E[k] = C_k + p*E[k+1] + (1-p)*(body+E[0])  (失敗爆件, 從E[0]重來,
                                                          並在body欄位記一次
                                                          期望額外本體)

body_count語意(依使用者定案錨點, ledger Ruling 2): 求解出的E[start].body分量
是「因爆件而額外需要的本體件數期望值」, 不含本來就要用的那一件, 所以
body_count = E[start].body + 1 才是「含初始1件」的總本體件數期望值 —
不可對這個+1再加一次(基準1的1000/441本身已經是「含初始件」的總數)。

祝福(blessing)比照材料的「每次嘗試消耗次數」邏輯: safe/minus1/break每次
出現只算一次, stay則跟material qty一樣除以p — 因為它是「每次嘗試都要
再喝一瓶祝福藥水」, 跟材料本身沒有時間點上的差異, 只是消耗的道具名稱換成
blessing_item而已(兩者若同名會自然疊加, 用同一個RHS欄位存)。

手續費(zeny_fee, RefineStep.fee)比照材料同一時間點邏輯(控制者task-4修正案
amendment 1): safe/minus1/break每次嘗試各算一次(內含在C_k類比裡, 不除p),
stay除以p。這是精煉「每次嘗試」的NPC手續費, 跟升階(grade)的手續費是
不同東西(升階手續費在solve_grade_path裡走grade_fee, 保持分開)。

solve_grade_path的升階組合模型(spec §7.2規則5/6, 升階失敗保留+11可重試—
spec §12假設2, 所以升階失敗不必重新精煉, 只有升階寶石/手續費按1/p的幾何
期望次數放大; 精煉到refine_req只需要算一次): 對grade_from(不含)到grade_to
(含)鏈上每一階, 疊加(精煉0→refine_req的solve_refine結果) + (該階升階材料
qty/p, 手續費fee/p); 最後鏈路走完後, 再疊加一次精煉0→final_refine
(因爲升階成功後拿到的是全新的、尚未精煉的下一階裝備)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

from app.core.cost.rules import CostRules, RefineStep

GRADE_ORDER = ["none", "D", "C", "B", "A"]


@dataclass
class RefineExpectation:
    materials: dict[str, Fraction]  # 精煉直接消耗(含祝福), 未展開兌換
    body_count: Fraction  # 期望本體件數(含初始1件)
    zeny_fee: Fraction = Fraction(0)  # 精煉每次嘗試NPC手續費期望總計


@dataclass
class RefineExpectation2(RefineExpectation):
    grade_materials: dict[str, Fraction] = field(default_factory=dict)  # 升階寶石(未展開)
    grade_fee: Fraction = Fraction(0)  # 升階手續費期望(與精煉zeny_fee分開計)


def _solve_linear_system(
    matrix: list[list[Fraction]], rhs_columns: list[list[Fraction]]
) -> list[list[Fraction]]:
    """高斯-喬丹消去(全程Fraction, partial pivot=往下找第一個非零列), 一次解出
    matrix @ X = rhs_columns(逐欄)的所有欄位, 回傳與rhs_columns同形狀的解欄位
    list。用增廣矩陣一次處理全部RHS欄位, 避免對同一個係數矩陣重複消去。
    """
    n = len(matrix)
    m = len(rhs_columns)
    aug = [matrix[i][:] + [rhs_columns[j][i] for j in range(m)] for i in range(n)]

    for col in range(n):
        pivot_row = next((r for r in range(col, n) if aug[r][col] != 0), None)
        if pivot_row is None:
            raise ValueError(f"線性系統在第{col}行找不到非零主元, 無法求解(係數矩陣異常)")
        if pivot_row != col:
            aug[col], aug[pivot_row] = aug[pivot_row], aug[col]
        pivot_val = aug[col][col]
        if pivot_val != 1:
            aug[col] = [v / pivot_val for v in aug[col]]
        for r in range(n):
            if r != col and aug[r][col] != 0:
                factor = aug[r][col]
                aug[r] = [mv - factor * cv for mv, cv in zip(aug[r], aug[col])]

    return [[aug[i][n + j] for i in range(n)] for j in range(m)]


def solve_refine(
    steps: list[RefineStep], target: int, blessing_item: str, start: int = 0
) -> RefineExpectation:
    """解「從等級start精煉到等級target」的期望消耗。

    steps 只需要涵蓋 from_lv 0..target-1 這段(允許傳整張表, 多餘的高階step會被
    忽略); 缺任何一階(斷鏈)一律拋ValueError, 不默默用0頂替。
    """
    if target <= 0:
        raise ValueError(f"target必須為正整數, 得到{target}")
    if not (0 <= start < target):
        raise ValueError(f"start必須介於[0,{target})之間, 得到{start}")

    step_by_lv = {s.from_lv: s for s in steps if s.from_lv < target}
    for k in range(target):
        if k not in step_by_lv:
            raise ValueError(f"精煉表缺少從{k}到{k + 1}的階段, 無法求解到target={target}")

    n = target
    matrix = [[Fraction(0)] * n for _ in range(n)]

    material_names: list[str] = []
    seen: set[str] = set()

    def _track(name: str) -> None:
        if name not in seen:
            seen.add(name)
            material_names.append(name)

    for k in range(n):
        s = step_by_lv[k]
        _track(s.material)
        if s.blessing:
            _track(blessing_item)

    material_index = {name: idx for idx, name in enumerate(material_names)}
    body_col = len(material_names)
    fee_col = body_col + 1
    rhs_columns = [[Fraction(0)] * n for _ in range(len(material_names) + 2)]

    for k in range(n):
        s = step_by_lv[k]
        p = s.rate
        matrix[k][k] += Fraction(1)

        if s.fail == "safe":
            if k + 1 < n:
                matrix[k][k + 1] -= Fraction(1)
            multiplier = Fraction(1)
        elif s.fail == "minus1":
            if k + 1 < n:
                matrix[k][k + 1] -= p
            matrix[k][k - 1] -= Fraction(1) - p
            multiplier = Fraction(1)
        elif s.fail == "stay":
            if k + 1 < n:
                matrix[k][k + 1] -= Fraction(1)
            multiplier = Fraction(1) / p
        elif s.fail == "break":
            if k + 1 < n:
                matrix[k][k + 1] -= p
            matrix[k][0] -= Fraction(1) - p
            multiplier = Fraction(1)
            rhs_columns[body_col][k] += Fraction(1) - p
        else:
            raise ValueError(f"未知fail類型: {s.fail}")

        mat_col = material_index[s.material]
        rhs_columns[mat_col][k] += Fraction(s.qty) * multiplier
        if s.blessing:
            bless_col = material_index[blessing_item]
            rhs_columns[bless_col][k] += Fraction(s.blessing) * multiplier
        rhs_columns[fee_col][k] += Fraction(s.fee) * multiplier

    solutions = _solve_linear_system(matrix, rhs_columns)

    materials_result = {name: solutions[material_index[name]][start] for name in material_names}
    body_count = solutions[body_col][start] + 1
    zeny_fee = solutions[fee_col][start]

    return RefineExpectation(materials=materials_result, body_count=body_count, zeny_fee=zeny_fee)


def _merge_into(target: dict[str, Fraction], source: dict[str, Fraction]) -> None:
    for name, qty in source.items():
        target[name] = target.get(name, Fraction(0)) + qty


def solve_grade_path(
    rules: CostRules,
    table_key: str,
    grade_from: str,
    grade_to: str,
    final_refine: int,
) -> RefineExpectation2:
    """解「grade_from(不含)升階到grade_to(含), 再精煉到final_refine」的期望消耗。

    grade_from=="none"且grade_to=="none"這種純精煉情境不歸這個函式管(呼叫端
    應直接用solve_refine) — 這裡grade_to必須在GRADE_ORDER鏈上嚴格排在
    grade_from之後, 否則(含兩者相同的情況)一律拋ValueError。
    """
    if grade_from not in GRADE_ORDER:
        raise ValueError(f"未知的起始階級: {grade_from}")
    if grade_to not in GRADE_ORDER:
        raise ValueError(f"未知的目標階級: {grade_to}")
    if GRADE_ORDER.index(grade_to) <= GRADE_ORDER.index(grade_from):
        raise ValueError(f"grade_to({grade_to})必須在鏈路上排在grade_from({grade_from})之後")
    if table_key not in rules.refine_tables:
        raise ValueError(f"精煉表「{table_key}」不存在")

    chain = []
    cursor = grade_from
    for gs in rules.grade_steps:
        if gs.from_grade == cursor:
            chain.append(gs)
            cursor = gs.to_grade
            if cursor == grade_to:
                break
    if cursor != grade_to:
        raise ValueError(f"升階表中找不到從{grade_from}到{grade_to}的連續鏈路")

    refine_table = rules.refine_tables[table_key]

    materials_total: dict[str, Fraction] = {}
    zeny_fee_total = Fraction(0)
    body_extra_total = Fraction(0)
    grade_materials_total: dict[str, Fraction] = {}
    grade_fee_total = Fraction(0)

    for gs in chain:
        refine_exp = solve_refine(refine_table, gs.refine_req, rules.blessing_item)
        _merge_into(materials_total, refine_exp.materials)
        zeny_fee_total += refine_exp.zeny_fee
        body_extra_total += refine_exp.body_count - 1

        inv_p = Fraction(1) / gs.rate
        for name, qty in gs.materials:
            grade_materials_total[name] = grade_materials_total.get(name, Fraction(0)) + Fraction(qty) * inv_p
        grade_fee_total += Fraction(gs.fee) * inv_p

    final_exp = solve_refine(refine_table, final_refine, rules.blessing_item)
    _merge_into(materials_total, final_exp.materials)
    zeny_fee_total += final_exp.zeny_fee
    body_extra_total += final_exp.body_count - 1

    return RefineExpectation2(
        materials=materials_total,
        body_count=body_extra_total + 1,
        zeny_fee=zeny_fee_total,
        grade_materials=grade_materials_total,
        grade_fee=grade_fee_total,
    )
