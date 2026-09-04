# M3 成本引擎 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 精煉/升階/附魔期望成本引擎: 強化表excel轉refine_rules.json, fractions精確期望值求解, 四個回歸基準算例全過, CLI可對配裝輸出三層成本報表。

**Architecture:** 新增`app/core/cost/`純邏輯包(rules載入/兌換鏈/精煉升階求解/附魔期望/報表組裝), 消費M2的DbReader與Build。所有機率與期望值用`fractions.Fraction`精確運算(json裡機率存十進位字串, `Fraction("0.7")`無浮點誤差), 只在最終顯示層轉float。基準算例=本session練習時與使用者逐一定案的四個數字, 是不可動的回歸錨點。

**Tech Stack:** Python 3.11+(`py -3.12-64`), pytest, fractions(標準庫)。轉換腳本用openpyxl(dev dependency)。

**Spec:** `docs/superpowers/specs/2026-09-03-robuildanalyzer-design.md` §7(成本引擎)/§6(cost_targets)
**演算法定案依據:** 使用者memory「精煉/升階成本演算法」+ spec §7.2十條裁決規則(不可自行更動)

## Global Constraints

- 測試 `py -3.12-64 -m pytest tests/ -v`, repo根目錄; 中文console前綴`PYTHONIOENCODING=utf-8`; 目前main有317測試全綠
- commit格式: `[{前綴}] [RO配裝分析工具] [{次要功能,非必要}] {內容}`一行, 多項目`1.XXXX 2.XXXX`, trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`; commit前跑完整`git status --short`
- **期望值運算全程Fraction**, 禁止中途轉float; 機率/費率從json讀入時以`Fraction(str)`解析
- **不默默丟資料**: 規則檔缺表/缺價/附魔查無, 一律進warnings或明確錯誤, 不得靜默算0
- spec §7.2的十條裁決規則逐條落實(祝福區間預設用/本體不計價列件數/升階歸0/兌換展開到底等)
- 回歸基準(§7.4)為精確值斷言: 分數比對用Fraction, Zeny總計比對到個位數

## File Structure

```
app/core/cost/
├─ __init__.py
├─ rules.py        # refine_rules.json/prices.json載入與驗證(Fraction化)
├─ materials.py    # 兌換鏈遞迴展開(合成品→基礎材料+手續費, 中間品清單)
├─ refine.py       # 精煉期望求解(線性方程組)+升階組合(歸0循環)
├─ enchant.py      # 附魔期望(隨機+重置+雙策略+指定/升級比價), require_cost解析
└─ report.py       # 三層報表組裝(直接消耗/中間合成品/基礎材料+Zeny)+配裝彙總
scripts/
├─ convert_refine_rules.py   # 一次性: RO強化表.xlsx→userdata/refine_rules.json+prices.json
└─ parse_sweep.py            # 全量效果解析健康掃描(final review建議4)
userdata/
├─ refine_rules.json         # 轉換產物, 之後以json為準(進git)
├─ prices.json               # 物價(進git, 使用者手動維護)
└─ manual_enchants.json      # 舊式附魔+重置規則+指定附魔+升級鏈(進git, 初始為含schema註解的空殼)
tests/
├─ test_cost_rules.py  test_cost_materials.py  test_cost_refine.py
├─ test_cost_enchant.py  test_cost_report.py  test_e2e_cost.py
```

---

### Task 1: refine_rules.json/prices.json schema與轉換腳本

**Files:**
- Create: `scripts/convert_refine_rules.py`, `userdata/refine_rules.json`(產物), `userdata/prices.json`(產物)
- Modify: `pyproject.toml`(dev extras加openpyxl), `README.md`(轉換腳本一行說明)
- Test: `tests/test_cost_rules.py`的schema驗證部分在Task 2

**Interfaces:**
- Produces: 兩份json(schema如下), 為後續所有task的資料基礎

refine_rules.json schema(轉換腳本輸出, 之後以json為權威):
```json
{
  "refine_tables": {
    "armor_lv1":   {"display": "一級防具",  "steps": [
      {"from": 0, "to": 1, "material": "鋁", "qty": 1, "rate": "1", "fail": "safe", "blessing": 0},
      {"from": 4, "to": 5, "material": "濃縮鋁", "qty": 1, "rate": "0.9", "fail": "break", "blessing": 0},
      {"from": 7, "to": 8, "material": "濃縮鋁", "qty": 1, "rate": "0.4", "fail": "stay", "blessing": 1},
      {"from": 14, "to": 15, "material": "特殊祝福的防具礦石", "qty": 1, "rate": "0.07", "fail": "stay", "blessing": 0}
    ]},
    "weapon_lv4": {"display": "四級武器", "steps": ["同armor_lv1結構, 材料換神之金屬系"]},
    "shadow_armor": {"display": "影子防具", "steps": ["0~10, 材料鋁系, 7~8為minus1, 8~10為stay特殊礦"]},
    "shadow_gauntlet": {"display": "影子手套", "steps": ["同shadow_armor, 材料神之金屬系"]},
    "ether_armor2": {"display": "二級防具", "steps": ["0~20乙太系, 3~7 minus1, 7~14 stay祝福, 10~15消失段照表, 14~20 break"]},
    "ether_weapon5": {"display": "五級武器", "steps": ["同ether_armor2, 材料乙太神之金屬系"]}
  },
  "blessing_item": "鐵匠的祝福",
  "grade_steps": [
    {"from": "none", "to": "D", "refine_req": 11, "rate": "0.7", "materials": [{"name": "乙太天藍寶石", "qty": 5}], "fee": 500000},
    {"from": "D", "to": "C", "refine_req": 11, "rate": "0.6", "materials": [{"name": "乙太黃寶石", "qty": 5}], "fee": 625000},
    {"from": "C", "to": "B", "refine_req": 11, "rate": "0.5", "materials": [{"name": "乙太紫寶石", "qty": 5}], "fee": 1000000},
    {"from": "B", "to": "A", "refine_req": 11, "rate": "0.4", "materials": [{"name": "乙太琥珀", "qty": 10}], "fee": 2500000}
  ],
  "exchange_recipes": {
    "乙太魔石":   {"inputs": [{"name": "乙太星塵", "qty": 5}], "fee": 100000},
    "乙太天藍寶石": {"inputs": [{"name": "乙太魔石", "qty": 3}, {"name": "天藍寶石", "qty": 1}], "fee": 100000},
    "乙太鋁":     {"inputs": [{"name": "乙太星塵", "qty": 1}, {"name": "鋁", "qty": 1}], "fee": 10000},
    "其餘照excel兌換表": "..."
  }
}
```
(steps欄內註解文字是本plan的說明, 實際json是完整step物件陣列; rate一律十進位字串; fail∈{safe,minus1,stay,break}; stay+blessing>0=祝福保護, stay+blessing=0=特殊礦原地)

prices.json schema: `{"材料名": 單價int}`, 內容=excel「各材料價值」表全數(祝福725000等, 0照填0)。

- [ ] **Step 1**: 寫`scripts/convert_refine_rules.py`: openpyxl讀`C:\Users\lithoshu\Desktop\強化表\RO強化表.xlsx`的六個sheet(精煉材料表/影子防具與手套/乙太防具與武器/升階機率表/各材料兌換/各材料價值), 依上述schema輸出兩份json到userdata/。表格解讀規則: 精煉度欄"a~b"展開成逐step(如"14~18"展開為14→15/15→16/16→17/17→18四步同參數); 機率欄"90%"→"0.9"、"0.7"(已是小數)→"0.7"; 防爆&防退欄「鐵匠的祝福xN」→stay+blessing=N、「失敗時裝備消失」→break、「-」→safe、「失敗時裝備不消失」→stay+blessing=0; 影子表失敗欄「精煉度 -1」→minus1、「裝備消失」→break、「裝備不消失」→stay; 乙太表同理; 材料正名「乙太粉塵」→「乙太星塵」(spec §7.2規則9);「鈽鐳」→「鈰鐳」(spec §12假設3)。兌換表「兌換所需材料」欄的「AxN、BxM」格式解析成inputs陣列。
- [ ] **Step 2**: 跑腳本產出兩份json, **人工抽核對照excel至少6處**(一般表7~8的祝福x1與40%; 乙太表3~4的minus1; 升階B>A的0.4/琥珀x10/250萬; 兌換乙太琥珀=魔石x15+琥珀x1+50萬; 價值表祝福725000; 特殊祝福礦6000000), 核對結果記進report。
- [ ] **Step 3**: pyproject dev extras加openpyxl; README加一行「規則來源與重轉指令」。
- [ ] **Step 4: Commit** `[feat] [RO配裝分析工具] [成本引擎] 1.新增強化表轉換腳本 2.產出精煉升階規則與物價設定檔`

---

### Task 2: rules.py(規則載入與驗證)

**Files:** Create `app/core/cost/__init__.py`, `app/core/cost/rules.py`; Test `tests/test_cost_rules.py`

**Interfaces(binding):**
```python
@dataclass(frozen=True)
class RefineStep:
    from_lv: int; to_lv: int; material: str; qty: int
    rate: Fraction; fail: str  # "safe"|"minus1"|"stay"|"break"
    blessing: int
@dataclass(frozen=True)
class GradeStep:
    from_grade: str; to_grade: str; refine_req: int
    rate: Fraction; materials: tuple[tuple[str, int], ...]; fee: int
@dataclass
class CostRules:
    refine_tables: dict[str, list[RefineStep]]   # 已展開成逐級step, 依from_lv排序
    table_displays: dict[str, str]
    blessing_item: str
    grade_steps: list[GradeStep]                 # none→D→C→B→A順序
    exchange_recipes: dict[str, tuple[list[tuple[str, int]], int]]  # name→(inputs, fee)
def load_rules(path: str = "userdata/refine_rules.json") -> CostRules
def load_prices(path: str = "userdata/prices.json") -> dict[str, int]
```
驗證(違反→ValueError含中文訊息): rate∈(0,1]且為Fraction; fail為四值之一; steps連續無跳級(from_lv遞增且to_lv=from_lv+1); minus1不得出現在from_lv=0; 未知fail值報錯。

- [ ] Step 1: failing tests(載入真實userdata json斷言抽樣值: armor_lv1的7→8 rate==Fraction(2,5)/blessing 1/fail stay; ether_weapon5的14→15 fail break; grade B→A rate Fraction(2,5) 琥珀10 fee 2500000; 兌換乙太魔石=星塵5+fee 100000; 壞json各驗證路徑) → Step 2-4 TDD → **Step 5: Commit** `[feat] [RO配裝分析工具] [成本引擎] 新增成本規則載入與驗證`

---

### Task 3: materials.py(兌換鏈遞迴展開)

**Files:** Create `app/core/cost/materials.py`; Test `tests/test_cost_materials.py`

**Interfaces(binding):**
```python
@dataclass
class MaterialBreakdown:
    base: dict[str, Fraction]           # 基礎材料名→期望數量(遞迴到無配方為止)
    intermediates: dict[str, Fraction]  # 中間合成品名→期望數量(供參考, spec §7.3第2層)
    exchange_fee: Fraction              # 兌換手續費合計
def expand(quantities: dict[str, Fraction], recipes) -> MaterialBreakdown
    # quantities: 合成品或基礎材料的混合需求; 有配方者遞迴展開(乘量), 無配方者直入base
    # 循環配方偵測→ValueError
def price_total(breakdown: MaterialBreakdown, prices: dict[str, int],
                extra_fees: Fraction = Fraction(0)) -> tuple[Fraction, list[str]]
    # 回傳(Zeny總計=Σ base×單價+exchange_fee+extra_fees, warnings)
    # 材料不在prices → warnings加「材料X無價格, 以0計」(不默默)
```

- [ ] Step 1: failing tests(單層展開乙太鋁; 三層展開乙太琥珀→魔石→星塵含中間品計數與手續費傳導乘量; 混合輸入; 無配方直通; 循環偵測; price_total含缺價warning; 基準交叉: 546.43個魔石→星塵3083.97≒Fraction對齊練習算例4的值, 用Fraction精確斷言) → Step 2-4 TDD → **Step 5: Commit** `[feat] [RO配裝分析工具] [成本引擎] 新增材料兌換鏈遞迴展開與計價`

---

### Task 4: refine.py(精煉+升階期望求解) — 基準算例核心

**Files:** Create `app/core/cost/refine.py`; Test `tests/test_cost_refine.py`

**Interfaces(binding):**
```python
@dataclass
class RefineExpectation:
    materials: dict[str, Fraction]   # 精煉直接消耗(含祝福), 未展開兌換
    body_count: Fraction             # 期望本體件數(含初始1件)
def solve_refine(steps: list[RefineStep], target: int, blessing_item: str) -> RefineExpectation
def solve_grade_path(rules: CostRules, table_key: str,
                     grade_from: str, grade_to: str, final_refine: int) -> RefineExpectation2
@dataclass
class RefineExpectation2(RefineExpectation):
    grade_materials: dict[str, Fraction]  # 升階寶石(未展開)
    grade_fee: Fraction                   # 升階手續費期望
```
求解模型(spec §7.1, 練習驗證過的實作直接落地): 未知數E[0..target-1]每材料一組RHS, 高斯消去全程Fraction:
```python
# 係數矩陣構築(每step k):
# safe:   E[k] = C_k + E[k+1]                    → A[k][k]=1, A[k][k+1]-=1
# minus1: E[k] = C_k + p*E[k+1] + (1-p)*E[k-1]   → A[k][k+1]-=p, A[k][k-1]-=(1-p)
# stay:   E[k] = C_k/p + E[k+1]                  → RHS材料qty/p, 祝福blessing/p
# break:  E[k] = C_k + p*E[k+1] + (1-p)*(body+E[0]) → A[k][0]-=(1-p), RHS body+=(1-p)
# body_count = 解出後E[0]的body分量 + 1(初始件)
```
(實作參考: 本session練習腳本已驗證此構築+高斯消去, 5級武器+20等四例全對; 消去用partial pivot找非零列即可, Fraction無數值穩定性問題)
升階組合(spec §7.2規則5/6): grade路徑=Σ各階[solve_refine(0→refine_req=11)+幾何期望1/p次寶石與fee], 最後一階後再solve_refine(0→final_refine); 升階失敗保留+11可重試(spec §12假設2)。

- [ ] Step 1: failing tests — **四個基準算例全數入列(精確值)**:
```python
# 基準1 一級防具0→18(armor_lv1): body==Fraction(1000,441)+... 精確: body_count==Fraction(1000,441)+1? 
#   ——練習定案: 本體2.27件=1000/441「含初始1件」? 練習輸出「裝備本體(件): 2.27 (精確值 1000/441)」
#   且E0['body'] += 1後才印, 故1000/441已含初始件。斷言body_count==Fraction(1000,441)
#   鋁==Fraction(4000,441); 濃縮鋁==Fraction(6940,441); 鈣礦石==50; 特殊祝福的防具礦石==Fraction(400,7); 鐵匠的祝福==Fraction(845,2)
# 基準3 二級防具0→13(ether_armor2): body_count==1; 祝福==Fraction對齊135.83...(=163/1.2? 由解算), 斷言用solve結果與練習Zeny總計驗於Task 6報表層
# 基準2 五級武器0→20(ether_weapon5): body_count精確值斷言(練習值2,040,816.33=100/49e4級distr, 用Fraction比對solve輸出自身一致性+float≈2040816.33 rel 1e-6)
# 基準4 無階→A階+13組合: grade期望次數Σ(10/7+5/3+2+2.5), 寶石qty(天藍7.14=Fraction(50,7)等), grade_fee==Fraction對齊10,005,952.38...(=Σfee/p)
```
(基準1的分數是與使用者定案的錨點, 逐字用Fraction斷言; 基準2/4以solve輸出的Fraction與練習float值以`math.isclose(rel_tol=1e-9)`雙軌斷言; Zeny總計的個位數斷言在Task 6的報表層測試)
另加單元級: 純safe鏈; 單一stay; 單一break的E[0]自洽(手算小例); minus1耦合(3級小例手算)。
- [ ] Step 2-4 TDD → **Step 5: Commit** `[feat] [RO配裝分析工具] [成本引擎] 新增精煉與升階期望值求解, 四基準算例回歸鎖定`

---

### Task 5: enchant.py(附魔期望+require_cost解析)

**Files:** Create `app/core/cost/enchant.py`; Test `tests/test_cost_enchant.py`; Create `userdata/manual_enchants.json`(初始空殼含schema)

**Interfaces(binding):**
```python
def parse_require_cost(raw: str) -> tuple[int, list[tuple[str, int]]]
    # '100000, {"Ep18_Amethyst_Fragment", 15}, {"Force_of_Fullmoon", 1}' → (100000, [(name,15),(name,1)])
    # M3第一件事(M2 final review交辦): 多材料/零材料/空字串/None全處理, 壞格式→ValueError
@dataclass
class EnchantCostResult:
    expected_rounds: Fraction        # N=1/p
    zeny: Fraction                   # 附魔費+重置費期望合計(材料另列)
    materials: dict[str, Fraction]   # 內部名→期望數量(附魔材料+重置材料)
    warnings: list[str]
def solve_enchant(reader: DbReader, manual: dict, item_internal_name: str,
                  goal_slot_index: int, goal_option: str, strategy: str) -> EnchantCostResult
    # spec §7.5: p=goal option weight總和/該(table,slot)實際權重總和(分母資料驅動)
    # slot順序=該表實際slot_index降冪; strategy: "stop_when_hit"→前置slot=goal之前的slots;
    #   "last_slot_only"→前置=除goal外全部(goal必須是最末slot, 否則ValueError)
    # 期望總成本 = N×(前置slot費用Σ+goal slot費用) + (N-1)×重置期望費用
    # 重置規則來自manual["reset_rules"].get(table_index或internal_name): {"rate": "0.8", "zeny": int, "materials": [...]}
    #   查無重置規則→warnings「無重置規則, 以免費重置計」(不默默假設)
    # manual["manual_tables"]: 舊式附魔手動表(schema同enchant_tables列), item查無自動表時fallback查此處
    # manual["targeted"]/{item,slot,option}: 指定附魔固定成本 → 與隨機期望比價取便宜(spec §7.5), 採用時warnings註記「採指定附魔」
    # 升級鏈: manual["upgrade_chains"] M3只定schema不實作演算(YAGNI, spec允許後補) — 讀到時warnings「升級鏈暫不比價」
```
manual_enchants.json初始內容: `{"reset_rules": {}, "manual_tables": [], "targeted": [], "upgrade_chains": []}`+檔頭"_comment"欄位寫schema說明。

- [ ] Step 1: failing tests — parse_require_cost四形態(單材料/多材料/純zeny/壞格式); solve用tmp DB fixture(importer.db建enchant_tables): p計算分母用實際總和(fixture造非500000總和驗證); 兩策略的前置費用差異; 重置期望(0.8→期望1.25次)與(N-1)乘法; goal非末slot時last_slot_only報錯; manual fallback表; targeted比價(便宜採用/貴不採用兩例); 真實DB案例(月全蝕表10004 slot1威力星團Lv3: p=Fraction(400x?次數,總和)——實作者查真實DB取權重值寫死進測試斷言, 期望輪數與Zeny記入report)。≥12測項。
- [ ] Step 2-4 TDD → **Step 5: Commit** `[feat] [RO配裝分析工具] [成本引擎] 新增附魔期望成本與費用字串解析, 含手動附魔與指定附魔比價`

---

### Task 6: report.py(三層報表+配裝彙總)

**Files:** Create `app/core/cost/report.py`; Test `tests/test_cost_report.py`; Modify `app/core/build.py`(SlotConfig.cost_targets欄位), `docs/superpowers/specs/2026-09-03-robuildanalyzer-design.md`(§6 cost_targets補refine_table與enchant_goal兩欄位)

**Interfaces(binding):**
```python
# build.py擴充(spec §6): SlotConfig新增
#   cost_targets: CostTargets | None = None
# @dataclass CostTargets: refine_from: int = 0; grade_from: str = "none";
#   refine_table: str | None = None   # 必填才算精煉成本(哪張表), 缺→warning跳過
#   enchant_strategy: str = "last_slot_only"
#   enchant_goal: tuple[int, str] | None = None  # (slot_index, option內部名); 缺→取enchants最末非null並依表slot降冪對位
@dataclass
class ItemCostReport:
    slot_key: str; item_name: str
    direct: dict[str, Fraction]        # 第1層: 直接消耗(精煉材料+祝福+寶石+附魔材料)
    grade_fee: Fraction; enchant_zeny: Fraction
    intermediates: dict[str, Fraction] # 第2層
    base: dict[str, Fraction]          # 第3層基礎材料
    exchange_fee: Fraction
    body_count: Fraction
    zeny_total: Fraction
    warnings: list[str]
@dataclass
class BuildCostReport:
    items: list[ItemCostReport]
    zeny_total: Fraction
    warnings: list[str]
def evaluate_build_cost(build: Build, rules: CostRules, prices: dict[str, int],
                        reader: DbReader, manual: dict) -> BuildCostReport
```
流程: 每格有cost_targets才算(沒有→跳過不警告, 表示使用者不關心該格成本); 精煉/升階→refine.solve_grade_path或solve_refine; 附魔→enchant.solve_enchant(item internal_name查無自動表且無manual→warnings「舊式附魔未建檔, 不計入」, spec §9灰色不計入的資料源); 材料合併→materials.expand→price_total; 卡片成本: M3不計(卡片是市場購入無養成期望, 價格屬物價json的未來擴充)——report註明。

- [ ] Step 1: failing tests — CostTargets載入(含缺refine_table的warning路徑/enchant_goal預設推導); 單格精煉+升階+附魔的三層數字組裝; **基準Zeny總計入列**: armor_lv1 0→18用真實prices.json斷言zeny_total==651530187(個位數, Fraction轉int); ether路徑基準3==106289325、基準4==350978060(這三個是與使用者定案的錨點); 配裝彙總加總與warnings傳遞。≥10測項。
- [ ] Step 2-4 TDD → **Step 5: Commit** `[feat] [RO配裝分析工具] [成本引擎] 新增三層成本報表與配裝彙總, 規格書補cost_targets欄位`

---

### Task 7: parser衛生批次(M2交辦清單)

**Files:** Modify `app/core/parser.py`, `importer/db.py`, `importer/pipeline.py`; Create `scripts/parse_sweep.py`; Test更新對應檔

三件小事一包:
1. **KNOWN_PLUMBING**: `SetEquipTempValue(`開頭的行改進trace(非UNRECOGNIZED條目)——它是client暫存值管線呼叫, 本身無顯示意義; **GetEquipTempValue的消費端仍走原路徑**(表達式求值失敗→UNRECOGNIZED), 資訊不丟失。加註解與測試(SetEquipTempValue行→無條目有trace; 用到GetEquipTempValue的行→仍UNRECOGNIZED)。
2. **scripts/parse_sweep.py**(M2 final review建議4): 對data/ro_items.db全量items跑parse_effect_block(固定context: refine13/gradeA/slot依equip_type粗分), 輸出: 總數/例外數(必須0)/各kind計數/UNRECOGNIZED行的頻率排行前20。跑一次把結果貼report。
3. **DB索引**: importer/db.py DDL加`CREATE INDEX idx_enchant_table_slot ON enchant_tables(table_index, slot_index)`與`CREATE INDEX idx_items_internal ON items(internal_name)`; 真實重匯一次驗證report數字不變。

- [ ] Step 1-4 TDD(1與3有測試, 2為腳本+人工執行) → **Step 5: Commit** `[feat] [RO配裝分析工具] [效果解析] 1.暫存值管線呼叫改列追蹤不再視為無法辨識 2.新增全量解析健康掃描腳本 3.中間資料庫補查詢索引`

---

### Task 8: CLI cost指令+真實資料E2E

**Files:** Modify `app/cli.py`, `userdata/builds/sample_a.json`(補cost_targets示例); Test `tests/test_e2e_cost.py`

**Interfaces:**
```python
# py -3.12-64 -m app.cli cost <build.json>
# 輸出: 逐格三層報表(照spec §7.3: 直接消耗→中間合成品→基礎材料攤開含單價小計)
#   + 本體件數 + 兌換/升階手續費 + 該格Zeny + 配裝總Zeny + warnings
# 數字顯示: Fraction轉float保留2位, Zeny千分位
```
- [ ] Step 1: sample_a的armor格補cost_targets(refine_table="ether_armor2", grade_from none, enchant_goal取其詞條)。
- [ ] Step 2: E2E測試(需真實DB, 缺則skip): sample_a跑evaluate_build_cost無例外, armor格zeny>0, 附魔期望輪數>1; 手跑CLI貼輸出進report。
- [ ] Step 3: 全套件過 → **Step 4: Commit** `[feat] [RO配裝分析工具] [成本引擎] 新增配裝成本CLI與真實資料驗證`

---

## Self-Review紀錄

- Spec覆蓋(M3範圍): §7.1模型(T4)、§7.2十條規則(T1轉換/T4求解/T6報表逐條)、§7.3三層輸出(T6/T8)、§7.4四基準(T4分數+T6 Zeny)、§7.5附魔(T5)、excel轉json(T1)、M2交辦清單(T5的require_cost第一件事/T7三項)。升級鏈只定schema不實作演算(YAGNI, spec允許手動維護後補), T5明示。卡片市價成本不在M3(報表註明), M4/物價擴充再議。
- 型別一致: CostRules/RefineStep/MaterialBreakdown/EnchantCostResult/ItemCostReport在各task的Interfaces固定。
- 基準值來源: 本session練習與使用者逐一定案(memory「精煉/升階成本演算法」§驗證基準), prices用userdata/prices.json(=excel現值: 祝福725000/濃縮鋁150000/濃縮神之金屬137500/高濃縮系172500/特殊祝福礦6000000/魔石100000/天藍黃紫寶石4560/琥珀3420)。若使用者日後改prices.json, 基準測試用**測試內建的price fixture**(凍結上述值)而非live檔——T6測試明示此隔離。
- 無placeholder; refine表的json「...」處由T1腳本自excel全量展開, 非TBD。
