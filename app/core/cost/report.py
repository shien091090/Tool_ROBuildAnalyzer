"""三層成本報表(直接消耗/中間合成品/基礎材料)+配裝彙總 — spec M3 §7.3/§6。

evaluate_build_cost()逐格(只算有掛cost_targets的格, 見下)呼叫
refine.solve_refine/solve_grade_path、enchant.solve_enchant, 三塊直接消耗
(精煉材料含祝福+升階寶石+附魔材料)合併後走materials.expand遞迴展開兌換鏈,
再用materials.price_total折算成單一Zeny總計, 組成單格ItemCostReport; 全配裝
逐格加總成BuildCostReport。

**opt-in語意**: 只有掛了cost_targets的格才計成本, 沒掛的格直接跳過、不產生
任何警告 — 這代表使用者不關心該格養成成本(例如已經滿裝不需要再算), 跟「查無
資料」是完全不同的兩種情況, 不能混用同一種警告機制(spec §6「cost_targets
描述『從什麼狀態養到目前狀態』」本身定義上就是選填輸入)。

**卡片成本(spec M2 final review交辦)**: M3不計 — 卡片是市場直接購入的道具,
沒有像精煉/升階/附魔那樣的隨機養成期望值, 「成本」只是市價, 屬於未來
prices.json擴充(記卡片單價)的範圍, 不是這個報表引擎要解的期望值問題;
ItemCostReport.direct/base/intermediates完全不觸碰SlotConfig.cards。

**裝備本體(body_count, spec §7.2規則3)**: 不計價, 只以「期望需要幾件本體」
呈現數量, 不論refine.solve_refine/solve_grade_path解出來的body_count多大,
都絕不折算進zeny_total(材料/手續費的Fraction才會, body_count純粹是顯示用的
獨立欄位)。

**refine_table缺漏**: 該格的refine/grade目標非零(即cost_targets.refine_from
到slot.refine/slot.grade之間確實有養成動作要算)卻沒指定refine_table,
記警告「部位X未指定精煉表, 精煉成本略過」並把該格的精煉/升階成本略記為0
(不擋掉整格, 附魔仍照算) — 目標本身就是0(沒有要養成)則連警告都不產生,
因為那種情況下沒有表也無所謂, 沒有任何東西被略過。

refine_table名稱若不是CostRules.refine_tables裡的合法key: 這裡選擇eval-time
(本模組)報ValueError, 不在build.py的load_build擋 — 因為build.py不持有
CostRules, 沒有能力判斷表名合不合法, 只有在報表層真正對照到規則表時才查得出
來(跟rules.py「缺漏必要欄位一律ValueError, 不默默用0/None頂替」是同一種
「不默默」哲學, 只是把檢查點挪到唯一有能力做這個檢查的地方)。

**升階路徑優雅降級**(C1, M3 final review交辦): 不是每張精煉表都符合
refine.solve_grade_path「升階前精煉段不可爆件」的簡化模型前提(見該函式
docstring) — 表本身不支援升階路徑時solve_grade_path會拋ValueError, 這裡
用try/except接住, 記警告「部位X升階成本無法計算(原因), 已略過」並把該格的
精煉/升階成本略記為0(附魔評估不受影響, 繼續跑) — 不讓整支CLI因為某一格用
了不支援升階的表就整個traceback。refine_table不存在於規則表(表名打錯,
上面那段講的情況)仍然直接拋ValueError不降級, 兩者是不同性質的錯誤(表名
打錯是設定錯誤, 表結構不支援升階是資料本身的限制)。

grade分支若cost_targets.refine_from非0一律記警告並忽略它(I5) — 升階成功後
精煉歸0(spec §7.2規則5), solve_grade_path固定從grade_from鏈路的0開始算,
refine_from這個欄位在升階路徑裡完全用不到。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction

from app.core.build import Build, CostTargets, SlotConfig
from app.core.cost import enchant, materials
from app.core.cost.refine import solve_grade_path, solve_refine
from app.core.cost.rules import CostRules
from app.core.db_reader import DbReader

_MISSING_REFINE_TABLE_WARNING_FMT = "部位{slot_key}未指定精煉表, 精煉成本略過"


@dataclass
class ItemCostReport:
    slot_key: str
    item_name: str
    direct: dict[str, Fraction]  # 第1層: 直接消耗(精煉材料+祝福+升階寶石+附魔材料)
    grade_fee: Fraction  # 升階NPC手續費期望(不含精煉手續費, 兩者分開計)
    enchant_zeny: Fraction  # 附魔費+重置費期望合計(材料另計入direct/base)
    refine_fee: Fraction  # 精煉每次嘗試NPC手續費期望(controller amendment 1)
    intermediates: dict[str, Fraction]  # 第2層: 中間合成品(供參考, 不影響總計)
    base: dict[str, Fraction]  # 第3層: 展開到底的基礎材料
    exchange_fee: Fraction  # 材料兌換鏈手續費合計
    body_count: Fraction  # 期望本體件數(不計價, 顯示用, spec §7.2規則3)
    zeny_total: Fraction  # 該格Zeny總計 = 基礎材料單價x數量 + exchange_fee
    #                        + refine_fee + grade_fee + enchant_zeny
    warnings: list[str] = field(default_factory=list)


@dataclass
class BuildCostReport:
    items: list[ItemCostReport]
    zeny_total: Fraction
    warnings: list[str]


def _derive_enchant_goal(
    slot_key: str, enchants: list, table_slots: list[int]
) -> tuple[int, str] | None:
    """依controller amendment 2: enchants清單順序對應table_slots(已降冪排序)
    逐位對位, goal=最末一個非null項, 其slot_index取table_slots同位置的值。
    enchants全空/全null(沒有要附魔) → None(呼叫端略過, 不計enchant成本)。
    """
    goal_index = None
    for i in range(len(enchants) - 1, -1, -1):
        if enchants[i] is not None:
            goal_index = i
            break
    if goal_index is None:
        return None
    if goal_index >= len(table_slots):
        raise ValueError(
            f"部位{slot_key}的enchants清單長度({len(enchants)})超過附魔表實際"
            f"slot數({len(table_slots)}), 無法依降冪對位推導enchant_goal"
        )
    return (table_slots[goal_index], enchants[goal_index])


def _evaluate_refine_grade(
    slot_key: str,
    slot: SlotConfig,
    ct: CostTargets,
    rules: CostRules,
    warnings: list[str],
) -> tuple[dict[str, Fraction], dict[str, Fraction], Fraction, Fraction, Fraction]:
    """回傳(refine_materials, grade_materials, refine_fee, grade_fee, body_count)。

    grade_from==slot.grade(含binding情境的none==none)一律視為「這格沒有升階
    動作」, 走純solve_refine; 否則走solve_grade_path(grade_to固定取slot本身
    的grade, 見controller amendment流程說明)。
    """
    target = slot.refine

    if ct.grade_from == slot.grade:
        if target <= ct.refine_from:
            return {}, {}, Fraction(0), Fraction(0), Fraction(1)
        if ct.refine_table is None:
            warnings.append(_MISSING_REFINE_TABLE_WARNING_FMT.format(slot_key=slot_key))
            return {}, {}, Fraction(0), Fraction(0), Fraction(1)
        if ct.refine_table not in rules.refine_tables:
            raise ValueError(f"部位{slot_key}的refine_table「{ct.refine_table}」不存在於規則表")

        exp = solve_refine(
            rules.refine_tables[ct.refine_table],
            target=target,
            blessing_item=rules.blessing_item,
            start=ct.refine_from,
        )
        return dict(exp.materials), {}, exp.zeny_fee, Fraction(0), exp.body_count

    if ct.refine_from > 0:
        # I5(M3 final review交辦): 升階成功後精煉歸0(spec §7.2規則5), 所以
        # refine_from在升階路徑裡完全不會被solve_grade_path用到(它固定從
        # grade_from鏈路的0開始) — 使用者若填了非0值, 那是設定跟實際計算
        # 模型不一致, 必須警告讓使用者知道這個欄位被忽略, 不能默默照算。
        warnings.append(
            f"部位{slot_key}的refine_from={ct.refine_from}在升階路徑不適用"
            f"(升階後精煉歸0), 已忽略"
        )

    if ct.refine_table is None:
        warnings.append(_MISSING_REFINE_TABLE_WARNING_FMT.format(slot_key=slot_key))
        return {}, {}, Fraction(0), Fraction(0), Fraction(1)
    if ct.refine_table not in rules.refine_tables:
        raise ValueError(f"部位{slot_key}的refine_table「{ct.refine_table}」不存在於規則表")

    try:
        exp2 = solve_grade_path(
            rules, ct.refine_table, ct.grade_from, slot.grade, final_refine=target
        )
    except ValueError as exc:
        # C1(M3 final review交辦)優雅降級: 不是每張精煉表都符合
        # solve_grade_path「升階前精煉段不可爆件」的簡化模型前提(見refine.py
        # solve_grade_path docstring) — 這種「表本身不支援升階路徑」的情況
        # 不該讓整支CLI直接traceback, 改記警告並把這格的精煉/升階成本略記為
        # 0(附魔評估不受影響, 呼叫端仍會繼續跑), 呼應rules.py缺表同一種
        # 「不默默但也不整支炸掉」的opt-in降級哲學。
        warnings.append(f"部位{slot_key}升階成本無法計算({exc}), 已略過")
        return {}, {}, Fraction(0), Fraction(0), Fraction(1)
    return (
        dict(exp2.materials),
        dict(exp2.grade_materials),
        exp2.zeny_fee,
        exp2.grade_fee,
        exp2.body_count,
    )


def _translate_enchant_material_names(
    reader: DbReader, materials_in: dict[str, Fraction]
) -> dict[str, Fraction]:
    """I3(M3 final review交辦): 附魔材料的名稱來自require_cost字串, 存的是
    裝備item的internal_name(如MD_Geffen_Coin), 不是userdata/prices.json慣用
    的中文顯示名稱(如吉芬幣) — 兩者對不上會讓明明有登記價格的材料被誤判成
    「無價格」。在合併進direct/materials.expand之前, 逐一查
    DbReader.item_by_internal_name轉成display_name(查得到才轉, 查無則保留
    internal_name原樣, 不假裝有對應的中文名) — 轉換後是否仍然缺價格, 一律
    交給既有的materials.price_total警告機制判斷, 這裡不重複產生任何警告。
    同一個display_name理論上不該對到兩個不同internal_name, 但保險起見用
    materials.merge_into累加, 不是直接dict覆蓋。
    """
    translated: dict[str, Fraction] = {}
    for name, qty in materials_in.items():
        item = reader.item_by_internal_name(name)
        display_name = item.display_name if item is not None and item.display_name else name
        materials.merge_into(translated, {display_name: qty})
    return translated


def _evaluate_enchant(
    slot_key: str,
    slot: SlotConfig,
    ct: CostTargets,
    reader: DbReader,
    manual: dict,
    prices: dict[str, int],
    exchange_recipes: materials.Recipes,
    item_internal_name: str | None,
    warnings: list[str],
) -> tuple[dict[str, Fraction], Fraction]:
    """回傳(enchant_materials, enchant_zeny)。裝備本身查無internal_name(item
    在db裡查無, 上游已記過「找不到裝備」警告)時直接略過, 不重複警告。
    """
    if item_internal_name is None:
        return {}, Fraction(0)

    if ct.enchant_goal is not None:
        goal_slot, goal_option = ct.enchant_goal
    elif any(e is not None for e in slot.enchants):
        # enchants清單裡有非null項, 代表使用者確實想算這格的附魔成本, 才需要
        # 查表推導goal — enchants全空(沒有要附魔)則連查表都不做, 跟頂層
        # 「沒掛cost_targets的格不計成本」同一種opt-in哲學, 不對每件裝備都
        # 無條件查一次表、平白冒出「舊式附魔未建檔」警告。
        table_slots = enchant.enchant_table_slots(reader, manual, item_internal_name)
        if table_slots is None:
            # 自動表+manual_tables皆查無 — 沿用solve_enchant的available=False
            # null result取得統一警告文字, 不在這裡另外硬編一份重複訊息。
            # goal_slot_index/goal_option用不到(查表失敗發生在比對它們之前),
            # 給無意義佔位值即可。
            result = enchant.solve_enchant(
                reader, manual, item_internal_name, 0, "", ct.enchant_strategy, prices,
                exchange_recipes,
            )
            warnings.extend(result.warnings)
            return {}, Fraction(0)

        goal = _derive_enchant_goal(slot_key, slot.enchants, table_slots)
        if goal is None:
            return {}, Fraction(0)
        goal_slot, goal_option = goal
    else:
        return {}, Fraction(0)

    result = enchant.solve_enchant(
        reader, manual, item_internal_name, goal_slot, goal_option, ct.enchant_strategy, prices,
        exchange_recipes,
    )
    warnings.extend(result.warnings)
    if not result.available:
        return {}, Fraction(0)
    return _translate_enchant_material_names(reader, result.materials), result.zeny


def evaluate_item_cost(
    slot_key: str,
    slot: SlotConfig,
    rules: CostRules,
    prices: dict[str, int],
    reader: DbReader,
    manual: dict,
) -> ItemCostReport | None:
    """算單一格的三層成本報表; 該格沒掛cost_targets回傳None(呼叫端略過)。"""
    ct = slot.cost_targets
    if ct is None:
        return None

    warnings: list[str] = []
    item = reader.item(slot.item_id)
    if item is None:
        warnings.append(f"找不到裝備: item_id={slot.item_id}（部位:{slot_key}）")
        item_name = f"item:{slot.item_id}"
        internal_name = None
    else:
        item_name = item.display_name or f"item:{item.item_id}"
        internal_name = item.internal_name

    refine_mat, grade_mat, refine_fee, grade_fee, body_count = _evaluate_refine_grade(
        slot_key, slot, ct, rules, warnings
    )
    enchant_mat, enchant_zeny = _evaluate_enchant(
        slot_key, slot, ct, reader, manual, prices, rules.exchange_recipes, internal_name, warnings
    )

    direct: dict[str, Fraction] = {}
    materials.merge_into(direct, refine_mat)
    materials.merge_into(direct, grade_mat)
    materials.merge_into(direct, enchant_mat)

    breakdown = materials.expand(direct, rules.exchange_recipes)
    extra_fees = refine_fee + grade_fee + enchant_zeny
    zeny_total, price_warnings = materials.price_total(breakdown, prices, extra_fees=extra_fees)
    warnings.extend(price_warnings)

    return ItemCostReport(
        slot_key=slot_key,
        item_name=item_name,
        direct=direct,
        grade_fee=grade_fee,
        enchant_zeny=enchant_zeny,
        refine_fee=refine_fee,
        intermediates=breakdown.intermediates,
        base=breakdown.base,
        exchange_fee=breakdown.exchange_fee,
        body_count=body_count,
        zeny_total=zeny_total,
        warnings=warnings,
    )


def evaluate_build_cost(
    build: Build,
    rules: CostRules,
    prices: dict[str, int],
    reader: DbReader,
    manual: dict,
) -> BuildCostReport:
    """逐格算成本(跳過沒掛cost_targets的格)加總成整套配裝的BuildCostReport。"""
    items: list[ItemCostReport] = []
    warnings: list[str] = []
    zeny_total = Fraction(0)

    for slot_key, slot in build.slots.items():
        item_report = evaluate_item_cost(slot_key, slot, rules, prices, reader, manual)
        if item_report is None:
            continue
        items.append(item_report)
        zeny_total += item_report.zeny_total
        warnings.extend(item_report.warnings)

    return BuildCostReport(items=items, zeny_total=zeny_total, warnings=warnings)
