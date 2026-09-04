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

**升階鏈損毀模型(controller ruling, task-4修復案)**: 上面「疊加一次
0→final_refine」這句話在final_refine段落本身完全不會爆件(所有四個
user-ratified基準皆屬此類)時是對的; 但若final_refine段落含break階
(例如乙太系14級以後), 每次爆件毀掉的不是一個「素體」, 而是一個「已經
整條升階鏈跑完、精煉到refine_req、且已成功升階到grade_to」的完整裝備 —
要補回這個狀態, 得把grade_from→grade_to整條鏈(所有精煉段+所有升階寶石/
手續費)重跑一次, 不能只補一個素體材料了事(舊版實作犯的正是這個錯:
只把final_exp.body_count-1當「額外素體」加總, 完全沒有把升階鏈的成本
一起複製)。

正確模型: 令 G = 整條升階鏈(grade_from到grade_to, 不含最終精煉段)的
期望成本向量, 即所有升階段落「0→refine_req」精煉的materials/zeny_fee
加總, 加上所有段落的升階寶石(qty/p)/手續費(fee/p)加總。這裡要求每個
升階段落自己的body_count都必須恰為1(即該段refine_req以內完全沒有
break階) — 這是這個「損毀=重跑整條G」簡化模型能成立的前提, 若不成立
(某個升階段落自己也會爆件, 導致「還沒升階成功前」就要重新素體來過,
那個素體重來的成本又會疊代性地卷進更早的升階段落, 不再是簡單的線性
scale) 就直接拋ValueError, 不要算出一個看似合理但實際上錯誤的數字。

令 final_exp = solve_refine(refine_table, final_refine, ...)(最終精煉段
本身的標準單腿模型, 包含它自己內部的break重試遞迴), R = final_exp.
body_count - 1 (最終精煉段爆件導致「需要一整套全新已升階裝備」的期望
次數)。因爲每次爆件都要整條G重來, 而最初攻頂final_refine前也要先跑
一次G, 所以G的成分要乘上 (1+R) 倍; 而final_exp自己的materials/zeny_fee
不必再乘任何倍數 — 它是用標準的break遞迴模型解出來的E[0], 內部的
「失敗回到E[0]重來」遞迴本身就已經把「這一段(0→final_refine)材料被
重複消耗的次數期望值」算對了, 只是原本模型裡「回到E[0]重來」預設的
代價是「一個素體」, 現在改成「一次G」而已 — 所以只需要把body欄位的
語意換成G的整條成本, 乘上(1+R)倍, 再加上final_exp自己(0→final_refine)
的materials/zeny_fee即可, 不會出現雙重計算。

回歸檢查: 若final_refine段落完全沒有break階(四個user-ratified基準皆
如此), R恆為0, (1+R)=1, 算出來的結果跟舊版「G + final_exp」完全相同
(浮點/Fraction逐位不變) — 四個基準測試因此維持原樣不動。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

from app.core.cost.materials import merge_into
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
    """高斯-喬丹消去(全程Fraction, 選主元的方式是從當前行往下找首個非零列即可
    停手 — 不是classic partial pivoting那種挑「絕對值最大」的元素, 因為
    Fraction精確運算沒有浮點的數值穩定性問題, 不需要靠挑大主元來壓低誤差,
    找得到非零列就能保證消去合法), 一次解出matrix @ X = rhs_columns(逐欄)的
    所有欄位, 回傳與rhs_columns同形狀的解欄位list。用增廣矩陣一次處理全部
    RHS欄位, 避免對同一個係數矩陣重複消去。
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

    start合法範圍是[0,target), 刻意不含target本身 — target這個等級依定義
    就是E[target]=0的邊界(已經達成目標, 不必再解), 不是一個「還在半路上」
    需要求解花費的狀態; 呼叫端若真的想問「已經在target時的期望花費」,
    答案恆為0, 用不到這支函式, 所以沒有把start==target也算進合法範圍。
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
            if k == 0:
                # rules.py的_parse_refine_table已經擋掉from_lv=0時fail=minus1
                # 的情況, 但這支函式接受直接建構的RefineStep list(不見得經過
                # load_rules驗證) — 若在這裡沒有自己的防護, k==0時
                # matrix[k][k-1]會用Python負索引悄悄wrap到最後一欄
                # (matrix[0][-1]), 得到一個看似正常、實際上完全錯誤的解,
                # 且不會拋任何例外, 非常危險, 必須自己擋。
                raise ValueError(
                    f"精煉表from_lv=0的階段不可為minus1(等級0沒有更低一階可退), "
                    f"傳入的RefineStep可能繞過了rules.py的load_rules驗證"
                )
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

    final_refine允許為0(controller ruling, M3 final review交辦C1b): 代表
    「升階鏈跑完就好, 不用再往上精煉最終那件裝備」— solve_refine本身要求
    target必須為正整數(target=0是「已達成、不必求解」的邊界, 見solve_refine
    docstring), 所以這裡改成final_refine==0時直接略過「最終精煉段」這一次
    solve_refine呼叫(final_exp視為零成本、body_count=1, 即R=0、scale=1不變),
    只保留升階鏈G本身(所有段落的0→refine_req精煉+升階寶石/手續費)——不是
    連升階鏈都不算, 那樣就違背「升階路徑仍然要跑」的呼叫端語意了。
    """
    if final_refine < 0:
        raise ValueError(f"final_refine不得為負數, 得到{final_refine}")
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

    # G = 整條升階鏈(grade_from到grade_to, 不含最終精煉段)的期望成本向量。
    g_materials: dict[str, Fraction] = {}
    g_zeny_fee = Fraction(0)
    g_grade_materials: dict[str, Fraction] = {}
    g_grade_fee = Fraction(0)

    for gs in chain:
        refine_exp = solve_refine(refine_table, gs.refine_req, rules.blessing_item)
        if refine_exp.body_count != Fraction(1):
            raise ValueError(
                f"精煉表「{table_key}」在{gs.from_grade}→{gs.to_grade}階要求的"
                f"0→{gs.refine_req}精煉段內存在爆件(break)風險"
                f"(body_count={refine_exp.body_count} != 1), 升階鏈損毀模型"
                f"假設升階前的精煉段不會爆件才能用「整條鏈線性放大」簡化計算,"
                f"此表不符合這個前提, 不支援用於升階路徑計算"
            )
        merge_into(g_materials, refine_exp.materials)
        g_zeny_fee += refine_exp.zeny_fee

        inv_p = Fraction(1) / gs.rate
        for name, qty in gs.materials:
            g_grade_materials[name] = g_grade_materials.get(name, Fraction(0)) + Fraction(qty) * inv_p
        g_grade_fee += Fraction(gs.fee) * inv_p

    # 最終精煉段(升階成功後, 全新裝備從0精煉到final_refine)自己的標準單腿
    # 模型, 內含它自己的break重試遞迴。R=最終精煉段爆件導致「需要一整套
    # 全新已升階裝備(重跑整條G)」的期望次數。final_refine==0(見上方docstring
    # C1b說明)時這一段完全不存在, 視為零成本、body_count=1(R=0)。
    if final_refine == 0:
        final_exp = RefineExpectation(materials={}, body_count=Fraction(1), zeny_fee=Fraction(0))
    else:
        final_exp = solve_refine(refine_table, final_refine, rules.blessing_item)
    replacement_cycles = final_exp.body_count - 1
    scale = Fraction(1) + replacement_cycles  # 1(最初攻頂前跑一次G) + R(每次爆件補跑一次G)

    materials_total = {name: qty * scale for name, qty in g_materials.items()}
    merge_into(materials_total, final_exp.materials)
    zeny_fee_total = g_zeny_fee * scale + final_exp.zeny_fee
    grade_materials_total = {name: qty * scale for name, qty in g_grade_materials.items()}
    grade_fee_total = g_grade_fee * scale

    return RefineExpectation2(
        materials=materials_total,
        body_count=scale,
        zeny_fee=zeny_fee_total,
        grade_materials=grade_materials_total,
        grade_fee=grade_fee_total,
    )
