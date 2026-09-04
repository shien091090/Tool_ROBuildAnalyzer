"""材料兌換鏈遞迴展開與計價 — spec M3 §7.3.

expand() 把一組(合成品或基礎材料混合的)期望數量, 沿 exchange_recipes 遞迴展開
到全部是「無配方」的基礎材料為止 — 每往下一層, 該層的期望數量乘上配方的
單位用量往下傳(quantities 允許是 Fraction, 因為輸入常常是機率倒數算出來的
期望值, 不是整數)。展開過程中每個「中間合成品」名稱與其被需要的總量都記進
intermediates, 供 UI 顯示完整鏈路用(不是只回傳最終基礎材料); 每一層配方的
手續費(fee)乘上該層次的期望數量後累加進 exchange_fee。

recipes 的形狀沿用 rules.CostRules.exchange_recipes:
    dict[str, tuple[list[tuple[str, int]], int]]  # name -> (inputs, fee)

循環偵測: 用「目前展開路徑上的祖先集合」判斷, 不是「全域已訪問集合」——
同一個基礎/中間材料被兩條不同的分支各自需要(鑽石形依賴)是正常情況, 不算
循環; 只有某名稱出現在自己的展開路徑(祖先鏈)上才是真的循環配方。祖先鏈
同時用 frozenset(O(1)成員檢查)跟 tuple(保留走訪順序)各存一份 —
循環訊息必須照實際走訪順序組字串, 用 set 迭代順序不保證, 3個節點以上的
循環會拼出錯亂的鏈路。
"""

from dataclasses import dataclass, field
from fractions import Fraction

Recipes = dict[str, tuple[list[tuple[str, int]], int]]


@dataclass
class MaterialBreakdown:
    base: dict[str, Fraction] = field(default_factory=dict)  # 基礎材料名→期望數量
    intermediates: dict[str, Fraction] = field(default_factory=dict)  # 中間合成品名→期望數量
    exchange_fee: Fraction = Fraction(0)  # 兌換手續費合計


def expand(quantities: dict[str, Fraction], recipes: Recipes) -> MaterialBreakdown:
    """把 quantities(合成品/基礎材料混合需求)遞迴展開成 MaterialBreakdown。"""
    base: dict[str, Fraction] = {}
    intermediates: dict[str, Fraction] = {}
    exchange_fee = Fraction(0)

    def _expand(name: str, qty: Fraction, path_set: frozenset[str], path_order: tuple[str, ...]) -> None:
        nonlocal exchange_fee
        if name not in recipes:
            base[name] = base.get(name, Fraction(0)) + qty
            return

        if name in path_set:
            # path_order 是走訪順序(祖先鏈), path_set 只拿來做O(1)成員檢查
            # — 訊息必須照 path_order 組, 不能對 set 迭代(順序不保證, 3+節點
            # 的循環會被拼成錯的鏈路, 誤導使用者去查錯的配方)。
            chain = " → ".join((*path_order, name))
            raise ValueError(f"材料兌換配方偵測到循環: {chain}")

        intermediates[name] = intermediates.get(name, Fraction(0)) + qty
        inputs, fee = recipes[name]
        exchange_fee += Fraction(fee) * qty

        next_path_set = path_set | {name}
        next_path_order = (*path_order, name)
        for input_name, input_qty in inputs:
            _expand(input_name, qty * Fraction(input_qty), next_path_set, next_path_order)

    for name, qty in quantities.items():
        _expand(name, Fraction(qty), frozenset(), ())

    return MaterialBreakdown(base=base, intermediates=intermediates, exchange_fee=exchange_fee)


def price_total(
    breakdown: MaterialBreakdown,
    prices: dict[str, int],
    extra_fees: Fraction = Fraction(0),
) -> tuple[Fraction, list[str]]:
    """回傳(Zeny總計 = Σ base×單價 + exchange_fee + extra_fees, warnings)。

    材料不在 prices 裡才算「無價格」並記警告; 價格恰好是 0(如已知不用花錢
    買的材料)是合法值, 不算缺價, 不生成警告 — 兩者用 `not in` 明確區分,
    不能用 `prices.get(name, 0)` 之類會把兩種情況混在一起的寫法。
    """
    warnings: list[str] = []
    total = Fraction(0)
    for name, qty in breakdown.base.items():
        if name not in prices:
            warnings.append(f"材料{name}無價格, 以0計")
            price = 0
        else:
            price = prices[name]
        total += qty * Fraction(price)

    total += breakdown.exchange_fee + extra_fees
    return total, warnings
