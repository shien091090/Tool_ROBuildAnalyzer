"""附魔期望成本 + require_cost字串解析 — spec M3 §7.5(M2 final review交辦「M3第一件事」)。

資料源分兩層: `enchant_tables`(自動匯入, 新式附魔裝備, 由DbReader查詢) +
`manual_enchants.json`(舊式NPC附魔, 同schema手動建檔, 用到哪件建哪件, 查無自動
表時fallback)。兩層都查無時視為「未建檔」的null result(available=False), 不
猜、不預設任何成本。

**機率分母資料驅動**(spec §7.5鐵律): p = 目標option在(table,goal_slot)的
權重總和 / 該(table,goal_slot)的「實際」權重總和 — 分母絕對不能寫死500000,
要用查到的原始列(含可能的重複列)直接加總; 資料髒(重複列/總和不是整數個
500000)是資料源本身的狀況, 分母資料驅動的設計就是要如實吸收, 不能在讀取層
自作主張去重或校正。

**slot順序資料驅動**: 該表實際存在的slot_index去重後由大到小排序就是附魔
順序(先附大槽), 不寫死「必為4→1」— 實測看過(1,2,3)/(2,3)/(3)/(2)/(0)
五種形態。兩條停手策略只是「前置slot集合」的算法不同, 目標slot本身的費用
永遠獨立算一次, 不會被前置或重置邏輯重複計入:

    stop_when_hit: 前置slot = 該表中slot_index大於goal_slot_index者(依降冪
                   排列, 也就是排在goal之前先附的那些槽)。goal不必是最後
                   一槽(附到目標詞條出現就停手, 後面更小的槽不會去碰)。
    last_slot_only: goal必須是全表最小的slot_index(降冪順序的最後一槽) —
                   因為這個策略要「附滿全部槽最後一槽才判定」, 若goal不是
                   最後一槽代表策略跟資料矛盾, 直接ValueError而不是默默照
                   算出一個沒意義的數字。前置 = 除goal外的全部槽。

單一round的費用 = Σ(前置slot的require_cost) + goal slot的require_cost,
每個slot的require_cost只解析一次(parse_require_cost), 不因為它同時出現在
「前置」跟「目標」等不同概念裡而被算兩次(兩者定義上互斥)。

期望總成本(spec §7.5公式) = N×(前置slot費用Σ+目標slot費用) + (N-1)×重置期望
費用, N=1/p(以Fraction精確表示, N=Fraction(該slot總權重, 目標權重總和),
不透過浮點除法算1/p再取倒數)。重置代表「附到中途沒附中, 想全部歸零重來」
這個動作本身的成本, 跑N輪隨機试附平均要重置(N-1)次(最後一輪附中就不用再
重置)。重置費用查manual["reset_rules"], key允許是table_index的字串或item
internal_name(兩種都試, table_index優先) — 查無視為「沒建檔」, 不能默默假設
免費重置或無重置費用, 必須警告「無重置規則, 以免費重置計」讓使用者知道這裡
用了一個假設值(儘管數值上就是0, 但語意上跟「查過資料庫確認免費」完全不同)。

指定附魔(manual["targeted"])比價: 若(item, goal_slot_index, goal_option)三元
比對到一筆, 算出它的固定zeny+材料成本, 跟隨機路線的期望總成本用同一組
prices字典折算成zeny做「公平比較」(材料沒有價格一律以0計, 跟price_total的
哲學一致, 並各自記警告), 嚴格更便宜(<)才採用 —
持平或更貴一律留用隨機路線結果(不確定的東西不該被「反正比較省事」的心態
覆蓋掉)。採用時的expected_rounds改記為1(指定附魔是一次到位的確定性路徑,
沒有N輪隨機重試的概念), materials/zeny直接換成指定附魔那筆的固定值(不含
隨機路線的任何殘留), warnings記「採指定附魔(較便宜)」。

升級鏈(manual["upgrade_chains"]): M3只定schema、只讀取判斷「是否跟這次查詢
的目標option有關」, 不實作多階比價演算法(YAGNI, spec §7.5允許後補) — 只要
讀到一筆chain涉及當前goal_option就記警告「升級鏈暫不比價」, 讓使用者知道
還有更便宜的路徑沒被引擎納入評估, 但不假裝算出一個數字。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from fractions import Fraction

from app.core.cost import materials
from app.core.db_reader import DbReader, EnchantRow

_REQUIRE_COST_RE = re.compile(
    r'^\s*(?P<zeny>-?\d+)\s*'
    r'(?P<materials>(?:,\s*\{\s*"[^"]+"\s*,\s*\d+\s*\})*)\s*$'
)
_MATERIAL_RE = re.compile(r'\{\s*"([^"]+)"\s*,\s*(\d+)\s*\}')

_UNAVAILABLE_WARNING = "舊式附魔未建檔, 不計入"
_NO_RESET_RULE_WARNING = "無重置規則, 以免費重置計"
_TARGETED_ADOPTED_WARNING = "採指定附魔(較便宜)"
_UPGRADE_CHAIN_WARNING = "升級鏈暫不比價"


def parse_require_cost(raw: str | None) -> tuple[int, list[tuple[str, int]]]:
    """解析require_cost字串: '100000, {"Name", 15}, {"Name2", 1}' → (100000, [(name,15),...])。

    None或空字串(去空白後為空) → (0, []): 代表這個slot沒有費用資訊, 視同免費;
    這支函式只管字串解析本身, 不對「真的沒有花費」跟「資料缺失沒填」做語意
    判斷, 那是呼叫端的責任。

    格式不符 → ValueError, 不默默回傳0或忽略解析不出來的殘餘片段 —
    require_cost壞掉多半代表匯入/手動維護資料寫錯, 提早爆炸比晚點算出一個
    看似正常但其實漏了材料的數字安全得多。用單一個fullmatch(整段字串必須
    完全符合「zeny + 0至多個{"name",qty}材料區塊」的形狀)來驗證, 不是切開
    逐段try/except, 這樣任何多餘的垃圾字元(不管出現在開頭、中間、還是結尾)
    都保證抓得到, 不會有「前面對後面錯」被默默忽略掉後半段的漏洞。
    """
    if raw is None or raw.strip() == "":
        return (0, [])

    m = _REQUIRE_COST_RE.match(raw)
    if not m:
        raise ValueError(f"require_cost格式錯誤, 無法解析: {raw!r}")

    zeny = int(m.group("zeny"))
    materials = [
        (name, int(qty)) for name, qty in _MATERIAL_RE.findall(m.group("materials"))
    ]
    return (zeny, materials)


@dataclass
class EnchantCostResult:
    expected_rounds: Fraction  # N=1/p(採用指定附魔時固定為1, 見上方模組docstring)
    zeny: Fraction  # 附魔費+重置費期望合計(材料另列, 不併入這個欄位)
    materials: dict[str, Fraction]  # 內部名→期望數量(附魔材料+重置材料合併加總)
    warnings: list[str] = field(default_factory=list)
    # 小幅介面擴充(task-5交辦): item在enchant_tables與manual_tables都查無時的
    # null result旗標, 給report層判斷要不要顯示「不計入」而不是誤把zero cost
    # 當成「真的算出來是免費」。
    available: bool = True


def _row_tuple(row: EnchantRow | dict) -> tuple[int, str | None, str, int]:
    """把EnchantRow(自動表)或dict(manual_tables手動列, schema同enchant_tables
    欄位)統一成同一形狀的tuple, 讓後續分母/費用邏輯不用區分資料來源。
    """
    if isinstance(row, EnchantRow):
        return (row.slot_index, row.require_cost, row.option_internal_name, row.option_weight)
    return (
        row["slot_index"],
        row.get("require_cost"),
        row["option_internal_name"],
        row["option_weight"],
    )


def _rows_for_item(
    reader: DbReader, manual: dict, item_internal_name: str
) -> tuple[str | int | None, list[tuple[int, str | None, str, int]]] | None:
    """找item對應的附魔列: 先查enchant_tables(自動匯入), 查無再fallback查
    manual["manual_tables"]。回傳(reset_rules查詢用的table_key, 列tuple清單),
    兩層都查無回傳None(呼叫端轉譯成available=False的null result)。
    """
    table_index = reader.enchant_table_for_item(item_internal_name)
    if table_index is not None:
        rows = reader.enchant_rows(table_index)
        return table_index, [_row_tuple(r) for r in rows]

    manual_tables = manual.get("manual_tables", [])
    matched = [
        r for r in manual_tables
        if item_internal_name in r.get("target_internal_names", [])
    ]
    if not matched:
        return None

    manual_table_index = matched[0].get("table_index")
    return manual_table_index, [_row_tuple(r) for r in matched]


def _reset_rule(manual: dict, table_index: str | int | None, item_internal_name: str) -> dict | None:
    """查重置規則: reset_rules的key允許是table_index的字串形式, 或item的
    internal_name, table_index優先(比對更精確, 同一item理論上只對到一個
    table, 但table_index是這個附魔系統真正的資料軸)。
    """
    reset_rules = manual.get("reset_rules", {})
    if table_index is not None and str(table_index) in reset_rules:
        return reset_rules[str(table_index)]
    if item_internal_name in reset_rules:
        return reset_rules[item_internal_name]
    return None


def _parse_reset_rate(reset_rule: dict, context: str) -> Fraction:
    """驗證manual_enchants.json裡reset_rules一筆的rate欄位: 比照rules.py
    「必要欄位缺漏/格式錯/範圍不合法一律ValueError, 不默默用0或100%頂替」
    的一貫作法(M2/M5收尾補齊, M3 final review交辦) — 這裡沒有直接import
    rules.py的private helper(那些函式的錯誤訊息是精煉表專用的context格式,
    硬套會誤導使用者去查錯的地方), 附魔重置規則自己獨立維護一份等價邏輯。
    """
    if "rate" not in reset_rule:
        raise ValueError(f"{context}: 缺少必要欄位「rate」")
    raw = reset_rule["rate"]
    try:
        rate = Fraction(str(raw))
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"{context}: rate「{raw}」格式錯誤, 須為可解析的分數/小數字串") from exc
    if not (Fraction(0) < rate <= Fraction(1)):
        raise ValueError(f"{context}: rate必須介於(0,1]之間, 得到{rate}")
    return rate


def _merge_add(target: dict[str, Fraction], name: str, qty: Fraction) -> None:
    # I4(M3 final review交辦): 跟materials.merge_into做的事情很像, 但簽名不
    # 相容(這裡是「單一name/qty累加進target」, materials.merge_into是「把
    # 整個source dict累加進target」) — 呼叫端這裡永遠是逐筆算出一對name/qty
    # 就要立刻併入, 沒有現成的source dict可以整包丟給merge_into, 硬改成
    # 每次都包一層{name: qty}的dict只是多一次無謂配置, 不是真的重用, 所以
    # 保留這支獨立的小輔助函式, 不跟merge_into合併。
    target[name] = target.get(name, Fraction(0)) + qty


def _slot_round_cost(
    rows: list[tuple[int, str | None, str, int]], slot_indices: set[int]
) -> tuple[Fraction, dict[str, Fraction]]:
    """把slot_indices這些槽各自的require_cost各解析一次(同槽多列共用同一個
    require_cost, 取該槽第一次出現的值即可)後加總成一輪份的(zeny, materials)。
    """
    seen_slots: set[int] = set()
    zeny = Fraction(0)
    materials: dict[str, Fraction] = {}
    for slot_index, require_cost, _option, _weight in rows:
        if slot_index not in slot_indices or slot_index in seen_slots:
            continue
        seen_slots.add(slot_index)
        slot_zeny, slot_materials = parse_require_cost(require_cost)
        zeny += Fraction(slot_zeny)
        for name, qty in slot_materials:
            _merge_add(materials, name, Fraction(qty))
    return zeny, materials


def _upgrade_chain_warning(manual: dict, goal_option: str) -> str | None:
    """upgrade_chains schema保留(M3只定schema不實作, 見模組docstring): 每筆
    預期形狀{"item":.., "slot_index":int, "options":[內部名,...]} — 只要
    goal_option出現在任一筆chain的options清單裡, 就代表這次查詢的目標跟
    一條尚未被引擎比價的升級鏈有關, 回傳警告字串; 沒有任何一筆涉及則回傳
    None(呼叫端不加這條警告)。
    """
    for chain in manual.get("upgrade_chains", []):
        if goal_option in chain.get("options", []):
            return _UPGRADE_CHAIN_WARNING
    return None


def enchant_table_slots(
    reader: DbReader, manual: dict, item_internal_name: str
) -> list[int] | None:
    """回傳item附魔表(自動優先, 查無fallback manual_tables)實際存在的slot_index
    降冪唯一清單, 供report層(task-6交辦)在cost_targets.enchant_goal缺漏時,
    依「enchants清單順序對應表slot_index降冪」推導預設目標用。兩層都查無
    (跟solve_enchant回傳available=False同一個判斷)回傳None, 呼叫端據此決定
    要不要直接沿用solve_enchant的null result(含統一警告文字), 不在這裡另外
    重複組一份訊息。
    """
    found = _rows_for_item(reader, manual, item_internal_name)
    if found is None:
        return None
    _table_index, rows = found
    return sorted({r[0] for r in rows}, reverse=True)


def solve_enchant(
    reader: DbReader,
    manual: dict,
    item_internal_name: str,
    goal_slot_index: int,
    goal_option: str,
    strategy: str,
    prices: dict[str, int] | None = None,
    exchange_recipes: materials.Recipes | None = None,
) -> EnchantCostResult:
    """解item附魔到(goal_slot_index, goal_option)的期望總成本, spec M3 §7.5。

    exchange_recipes(I4, M3 final review交辦): 指定附魔vs隨機路線的比價要在
    「同等基礎」上比才公平 — 兩邊都先過materials.expand()展開兌換鏈(乙太
    寶石之類的合成品在展開之後單價才是真正的基礎材料單價)、再用
    materials.price_total()折算, 不再各自用一支獨立的_priced_total()直接
    對「未展開的合成品名」查價(那樣如果合成品本身沒在prices.json裡登記,
    會被誤判成無價格, 即使它展開後的基礎材料其實都有登記)。缺漏(None)時
    視同空dict(不展開, 等同舊行為), 保持向下相容。
    """
    prices = prices or {}
    exchange_recipes = exchange_recipes or {}

    found = _rows_for_item(reader, manual, item_internal_name)
    if found is None:
        return EnchantCostResult(
            expected_rounds=Fraction(0),
            zeny=Fraction(0),
            materials={},
            warnings=[_UNAVAILABLE_WARNING],
            available=False,
        )
    table_index, rows = found

    slots = sorted({r[0] for r in rows}, reverse=True)
    if goal_slot_index not in slots:
        raise ValueError(
            f"目標slot {goal_slot_index}不存在於此附魔表(實際slot: {slots})"
        )

    if strategy == "stop_when_hit":
        pre_slots = {s for s in slots if s > goal_slot_index}
    elif strategy == "last_slot_only":
        if goal_slot_index != slots[-1]:
            raise ValueError(
                f"strategy=last_slot_only要求goal_slot_index為全表最小槽"
                f"({slots[-1]}), 但收到{goal_slot_index}(實際slot: {slots})"
            )
        pre_slots = {s for s in slots if s != goal_slot_index}
    else:
        raise ValueError(f"未知strategy: {strategy!r}(僅支援stop_when_hit/last_slot_only)")

    goal_weight = sum(w for s, _rc, opt, w in rows if s == goal_slot_index and opt == goal_option)
    total_weight = sum(w for s, _rc, _opt, w in rows if s == goal_slot_index)
    if total_weight == 0:
        raise ValueError(f"目標slot {goal_slot_index}查無任何權重列")
    if goal_weight == 0:
        raise ValueError(
            f"目標option「{goal_option}」在slot {goal_slot_index}查無符合權重"
            f"(可能option內部名稱打錯或此表未涵蓋)"
        )
    n = Fraction(total_weight, goal_weight)

    pre_zeny, pre_materials = _slot_round_cost(rows, pre_slots)
    goal_zeny, goal_materials = _slot_round_cost(rows, {goal_slot_index})
    round_zeny = pre_zeny + goal_zeny
    round_materials: dict[str, Fraction] = {}
    for name, qty in pre_materials.items():
        _merge_add(round_materials, name, qty)
    for name, qty in goal_materials.items():
        _merge_add(round_materials, name, qty)

    warnings: list[str] = []
    reset_rule = _reset_rule(manual, table_index, item_internal_name)
    if reset_rule is None:
        warnings.append(_NO_RESET_RULE_WARNING)
        reset_zeny = Fraction(0)
        reset_materials: dict[str, Fraction] = {}
    else:
        reset_rate = _parse_reset_rate(reset_rule, f"重置規則(table_index={table_index!r})")
        inv_reset = Fraction(1) / reset_rate
        reset_zeny = Fraction(reset_rule.get("zeny", 0)) * inv_reset
        reset_materials = {
            m["name"]: Fraction(m["qty"]) * inv_reset
            for m in reset_rule.get("materials", [])
        }

    total_zeny = n * round_zeny + (n - 1) * reset_zeny
    total_materials: dict[str, Fraction] = {}
    for name, qty in round_materials.items():
        _merge_add(total_materials, name, n * qty)
    for name, qty in reset_materials.items():
        _merge_add(total_materials, name, (n - 1) * qty)

    upgrade_warning = _upgrade_chain_warning(manual, goal_option)
    if upgrade_warning is not None:
        warnings.append(upgrade_warning)

    targeted = next(
        (
            t for t in manual.get("targeted", [])
            if t.get("item") == item_internal_name
            and t.get("slot_index") == goal_slot_index
            and t.get("option") == goal_option
        ),
        None,
    )
    if targeted is None:
        return EnchantCostResult(
            expected_rounds=n,
            zeny=total_zeny,
            materials=total_materials,
            warnings=warnings,
            available=True,
        )

    # 有指定附魔規則可比 — 用同一組prices把兩條路線都折算成單一Fraction,
    # 嚴格更便宜(<)才採用, 持平或更貴一律留用隨機路線結果(見模組docstring)。
    # I4: 兩邊都先過materials.expand()展開兌換鏈再用materials.price_total()
    # 折算, 不是直接對「未展開的合成品名」查價, 站在同一基礎上比較才公平。
    random_breakdown = materials.expand(total_materials, exchange_recipes)
    random_total, random_priced_warnings = materials.price_total(
        random_breakdown, prices, extra_fees=total_zeny
    )

    targeted_zeny = Fraction(targeted.get("zeny", 0))
    targeted_materials_list = targeted.get("materials", [])
    targeted_materials = {m["name"]: Fraction(m["qty"]) for m in targeted_materials_list}
    targeted_breakdown = materials.expand(targeted_materials, exchange_recipes)
    targeted_total, targeted_priced_warnings = materials.price_total(
        targeted_breakdown, prices, extra_fees=targeted_zeny
    )
    comparison_warnings = [*random_priced_warnings, *targeted_priced_warnings]

    if targeted_total < random_total:
        return EnchantCostResult(
            expected_rounds=Fraction(1),
            zeny=targeted_zeny,
            materials=targeted_materials,
            warnings=[*warnings, *comparison_warnings, _TARGETED_ADOPTED_WARNING],
            available=True,
        )

    return EnchantCostResult(
        expected_rounds=n,
        zeny=total_zeny,
        materials=total_materials,
        warnings=[*warnings, *comparison_warnings],
        available=True,
    )
