# Tool_ROBuildAnalyzer 整體設計規格書

日期: 2026-09-03
狀態: 設計定案, 待實作

## 1. 目標與非目標

### 目標
- RO(仙境傳說Online, DRO伺服器)配裝分析桌面工具, 兩大核心功能:
  1. **多組配裝素質比較**: 整套vs整套, 同屏固定比較2組, 並排顯示效果加總與差異高亮
  2. **成本統計**: 配裝中每件裝備/卡片/附魔的期望成本(精煉/升階/附魔期望值), 攤開到基礎材料層

### 非目標(明確排除)
- 不做完整角色面板模擬(總ATK/ASPD/最終傷害等面板公式), 只做「裝備加成的加總」; 角色資料僅作為效果條件判定的輸入
- 不做改造(reform)成本, 未來有需要再擴充
- 舊式NPC對話附魔裝備中未手動建檔者, 標示「不支援成本計算」, 不阻擋素質比較

## 2. 架構總覽(方案A: 單repo自包含, 兩段式資料流)

```
[匯入工具(CLI, 遊戲改版時跑)]
DRO client (data.grf)
  → GRF解包 + lub反編譯(luadec/unluac)
  → 中間資料庫 data/ro_items.db (SQLite)

[App(平常開)]
中間資料庫 + userdata/*.json(配裝/角色/物價/強化規則/手動附魔)
  → 效果解析(結構化輸出, 依配裝context即時計算, 不落地)
  → 比較引擎 / 成本引擎
  → GUI(PySide6)
```

- 技術棧: Python + PySide6
- 授權: **GPL-3.0**(因移植ROItemSearchApp的效果解析器程式碼, 該專案為GPL-3.0; repo須放LICENSE並保留原作者著作權聲明)
- 程式碼來源:
  - GRF解包/反編譯流程: 移植自 `D:\Git\SNShienRODataBase` 的 `grf.py`/`decompile.py`(該repo正式退役, 有用資產搬進本repo)
  - 效果解析: 移植自 ROItemSearchApp(`ro_core.py` 的 `parse_equipment_blocks`/`parse_lua_effects_with_variables`), 但輸出層改造為結構化(見§5)
- 已驗證: DRO data.grf內的`EquipmentProperties.lub`反編譯後格式與ROItemSearchApp資料檔完全一致(13963個OnStartEquip), 解析器可直接吃

## 3. repo結構

```
Tool_ROBuildAnalyzer/
├─ importer/            # 匯入工具(CLI): grf解包/反編譯/建中間DB
├─ app/
│   ├─ core/            # 效果解析 + 成本引擎 + 比較引擎(純邏輯, 不依賴Qt)
│   └─ ui/              # PySide6
├─ data/
│   ├─ ro_items.db      # 中間DB(匯入產出, gitignore, 隨時可刪掉重跑)
│   └─ tools/           # luadec.exe, unluac.jar
├─ userdata/            # 全部可手改json, 進git版控(這是使用者的配裝資產)
│   ├─ builds/          # 配裝存檔, 一個配裝一個json, 數量無上限
│   ├─ characters/      # 角色檔
│   ├─ prices.json      # 物價(材料+可計價項目), 手動維護
│   ├─ refine_rules.json    # 精煉/升階/兌換鏈規則(由RO強化表.xlsx轉換, 之後以json為準)
│   └─ manual_enchants.json # 舊式附魔手動建檔(schema同自動匯入)
├─ config.json          # 環境設定(DRO路徑/java路徑), gitignore
├─ config.example.json
└─ docs/
```

## 4. 資料層

### 4.1 中間DB(SQLite)

| 表 | 內容 |
|---|---|
| `items` | item_id / internal_name / display_name / description(道具完整敘述, tooltip用) / type / slot數(洞) / **effect_lua原文**(OnStartEquip整段) / Stat向量 / Combiitem清單(combo_id參照) |
| `combos` | combo_id / 套裝成員item_ids / **套裝效果lua原文**(套裝效果定義在獨立的Combiitem表, 不在個別item裡) |
| `enchant_tables` | table_index / 適用裝備internal_names / slot_index / 詞條internal_name / weight / 每次費用(Zeny+材料, 支援多材料) |
| `import_meta` | 匯入日期 / data.grf指紋(檔案大小+mtime) |

- 效果解析結果**不落地**, App端依配裝context(精煉/階級/角色檔)即時計算
- 中間DB為純衍生物, 不進git

### 4.2 DRO路徑與再匯入時機
- DRO路徑存`config.json`的`dro_path`; 首次啟動無設定時GUI跳資料夾選擇對話框
- App啟動時比對data.grf指紋與`import_meta`, 不一致則提示「偵測到DRO資料已更新, 是否重新匯入?」, 使用者確認才跑(匯入需時, 不做背景自動); GUI另有手動「重新匯入」按鈕

### 4.3 匯入健康指標
沿用「不默默丟資料」原則: 匯入report留各表筆數、解析失敗計數、附魔表權重總和異常清單等健康指標。

## 5. 效果解析(結構化改造)

- 一格裝備的總效果 = 裝備本體OnStartEquip + 各卡片 + 各附魔詞條(詞條本身也是item, 有自己的效果lua), 各自解析後累加
- 解析邏輯移植ROItemSearchApp(逐行掃描/受限eval/if-elseif-else狀態機/GetRefineLevel等client函式代換), 但**輸出層改為結構化**:
  ```
  EffectEntry(key, value, unit, source_item, condition)
  ```
  加總/比較/顯示全部下游消費此結構; 顯示字串只在UI渲染的最後一步生成。**禁止任何一層重新解析上一層產生的顯示文字**(ROItemSearchApp的已知技術債, 本專案明確避免)

### 5.1 條件式效果
- 精煉值/階級/穿戴部位等配裝自帶條件: 直接判定
- 依賴角色的條件(base素質/職業/技能等級): 由**角色檔**提供context判定
- 缺context無法判定者: **不加進數值總表**, 在「未計入的條件效果」區塊顯示原文+缺什麼, 附「補進角色檔」快速動作; 條件不成立者也顯示已判定狀態

### 5.2 角色檔(userdata/characters/*.json)
```json
{
  "name": "主帳PD",
  "job": 4055,
  "base_lv": 260, "job_lv": 55,
  "stats":  { "STR": 130, "AGI": 90, "VIT": 100, "INT": 1, "DEX": 90, "LUK": 30 },
  "traits": { "POW": 100, "STA": 60, "WIS": 0, "SPL": 0, "CON": 80, "CRT": 20 },
  "skills": { "5015": 10 }
}
```
- 比較畫面選一個角色檔, 所有配裝套用同一角色(比較公平性)
- `skills`平常空著, 從未計入區塊一鍵補
- 此面板僅為條件判定輸入, 非面板模擬

## 6. 配裝(userdata/builds/*.json)

```json
{
  "name": "PD向物理配置",
  "slots": {
    "armor": {
      "item_id": 450263,
      "refine": 13, "grade": "A",
      "cards": [4140],
      "enchants": ["Star_Cluster_Of_Pow3", "Wolf_Orb_Str_2", null],
      "cost_targets": {
        "refine_from": 0, "grade_from": "none",
        "enchant_strategy": "last_slot_only"
      }
    }
  }
}
```
- 部位涵蓋: 一般裝備10格(上/中/下段頭飾、鎧甲、武器、盾牌、披肩、鞋子、飾品x2) + 服飾4格(上/中/下段、背飾, 可掛服飾強化石) + 影子裝備6格(鎧甲、手套、盾牌、鞋子、耳環、墜飾), 共20格
- `cost_targets`描述「從什麼狀態養到目前狀態」, 成本引擎據此計算
- `enchant_strategy`: `stop_when_hit`(中途附到目標詞條即停) / `last_slot_only`(只看最後一格)
- GUI操作為主, 存檔為可手改json

## 7. 成本引擎

### 7.1 精煉/升階期望值模型
- 狀態=精煉度k, `E[k]`=期望成本向量(每種材料+本體件數各一分量), fractions精確分數解線性方程組(高斯消去, 多RHS):
  - safe(100%): `E[k] = C_k + E[k+1]`
  - minus1(失敗-1): `E[k] = C_k + p*E[k+1] + (1-p)*E[k-1]`
  - stay(祝福保護/特殊礦, 失敗原地): `E[k] = C_k/p + E[k+1]`
  - break(失敗裝備消失): `E[k] = C_k + p*E[k+1] + (1-p)*(body + E[0])`
- 升階=幾何分佈期望次數1/p, 每次嘗試消耗寶石+手續費(成敗都耗)

### 7.2 已裁決規則(不可自行更動)
1. +7~+14預設一律使用鐵匠的祝福(該區間有祝福選項時), 每次嘗試消耗規定數量
2. 鐵匠的祝福效果=失敗不消失不降級(原地重試)
3. 裝備本體不計價, 以「期望需要幾件本體」呈現
4. 升階失敗裝備不消失
5. 升階成功後精煉歸0(無→A = 4輪0→+11精煉+各階升階, 最後煉到目標)
6. 升階條件: 精煉+11
7. 價值表填0就是0
8. 兌換鏈遞迴展開到底(乙太寶石→乙太魔石→乙太星塵), 中間合成品數量另列供參考
9. 材料正名「乙太星塵」(excel的「乙太粉塵」為同一材料)
10. 乙太裝備+14以上無防護手段, 失敗即消失

### 7.3 輸出格式(三層)
1. 直接消耗(合成品層): 精煉材料+祝福+寶石+升階手續費+本體件數
2. 中間合成品(供參考)
3. 基礎材料攤開: 單價x數量小計、兌換手續費合計、升階手續費合計、總計Zeny

### 7.4 回歸基準算例(寫測試用, 依當時prices)
1. 一級防具+0→+18: 本體2.27件(精確1000/441), 祝福422.5(845/2), 總計651,530,187
2. 五級武器+0→+20: 本體2,040,816件, 總計約367.9兆(+14~+20連續break, 通關率4.9e-7, 理論值正確)
3. 二級防具+0→+13: 本體1件, 總計106,289,325
4. 二級防具無階+0→A階+13: 總計350,978,060(祝福332.5/魔石546.43/星塵3083.97)

### 7.5 附魔期望成本模型
- 資料源: `enchant_tables`(自動匯入, 覆蓋約201件新式附魔裝備) + `manual_enchants.json`(舊式NPC附魔手動建檔, 同schema, 用到哪件建哪件)
- 每slot=詞條池(weight)+固定費用; 附魔動作必成功(client資料success_rate全為100%), 出詞條看權重
- **機率分母資料驅動**: `p = 目標詞條weight總和 / 該(table,slot)實際權重總和`(實測有500000/100000/600000/514000四種, 不可寫死; 髒資料自動吸收)
- **slot順序資料驅動**: 依該表實際存在的slot_index由大到小依序附(實測有(1,2,3)/(2,3)/(3)/(2)/(0)五種形態, 不可寫死4→1)
- 統一公式(兩條停手路線只是目標slot位置參數差):
  ```
  期望總成本 = N x (前置slot費用總和 + 目標slot費用) + (N-1) x 重置期望費用
  N = 1/p
  ```
- 重置=全slot歸零, 重置成功率(如80%)也算期望(期望1/0.8次材料)
- 指定附魔/升級鏈(星團Lv1→Lv3等): 手動json維護, 引擎算完隨機路線後比價取便宜
- client資料沒有的裝備: 標「DRO未支援/未建檔」, 不計成本

## 8. 比較引擎

- N=2組配裝各自算`dict[(key,unit)] = total`, 取key聯集做對齊表, 每列一效果每欄一配裝, 優勢值高亮
- 素質比較與成本比較共用同一組配裝選擇

## 9. UI設計

已定案mockup: https://claude.ai/code/artifact/28317495-acca-4753-947e-ab6dcd10d72d (副本: `docs/mockups/robuildanalyzer_ui_mockup.html`)

- 版面: 頂部列(角色檔選擇/資料狀態/重新匯入) + 左半兩欄配裝面板(A/B) + 右半頁籤(效果結算/成本估算)
- 配裝面板: RO裝備介面風格部位排列, 每格顯示精煉/階級/裝備名, 下掛卡片chip/附魔chip/強化石chip
- **「+ 卡片」只在裝備有洞時顯示;「+ 附魔」只在可附魔時顯示**
- 套裝/套卡關聯: **hover高亮**(鼠標移到成員上同組一起亮), 不用拉線, 不在關聯上顯示效果文字
- 選擇清單: 按部位過濾(武器欄只列武器且依職業過濾、卡片分部位、強化石分部位、附魔列該槽詞條池含機率%), 頂部搜尋框; 清單項目只顯示名稱, **完整道具敘述用hover tooltip**顯示
- 效果結算頁: 對齊比較表(分組: 基礎素質/物理系/詠唱冷卻/減傷迴避等)+優勢高亮+底部「未計入的條件效果」區塊(含補進角色檔按鈕)
- 成本估算頁: 兩組總成本卡+逐件明細表(可展開三層材料格式), 舊式未建檔附魔顯示灰色「不計入」
- **硬性約束: 左側兩欄配裝區(各20格)在滿版視窗(基準1920x1080)內必須完整可見不捲動** — 對策: 單行式slot排版、必要時服飾/影子區雙欄排列

## 10. 測試策略

1. **成本引擎(最優先, 純邏輯零依賴)**: §7.4四個算例為回歸基準, fractions精確值驗證; 附魔模型另建測項(權重分母/兩條停手路線/重置期望)
2. **效果解析器**: 從DRO真實資料抽代表性裝備(if/elseif、GetRefineLevel、Combiitem、AddExtParam等pattern)建案例庫, 驗證結構化輸出; 移植時逐pattern確認
3. **匯入工具**: 對真實data.grf端到端, 驗證筆數/權重總和等健康指標
4. UI手動驗收, 不寫UI自動化測試

## 11. 開發里程碑

1. **M1 匯入工具**: GRF→中間DB打通
2. **M2 效果解析+結算**: 解析器移植改造(結構化輸出)、單件→整套加總, CLI可驗證
3. **M3 成本引擎**: 精煉/升階/附魔期望值, 強化表excel轉refine_rules.json, 回歸算例全過
4. **M4 GUI**: 配裝編輯→比較畫面→成本頁籤
5. **M5 收尾**: 角色檔/補條件流程/資料更新偵測

M2/M3順序可對調, 皆在M4之前。

## 12. 待確認假設(算例中使用者未糾正, 實作時如影響結果需再確認)

1. 一般裝備表+14~+20特殊祝福礦「失敗不消失」=也不降級(原地重試)
2. 升階失敗時精煉度保留+11, 可直接重試
3. 高密度乙太鈰鐳礦石兌換配方=兌換表「乙太鈽鐳礦石」行(「鈽鐳」視為「鈰鐳」typo)
4. 官網裝備名與client display_name不一致的約25件(II/括號後綴等), 匯入工具建別名對照層處理

## 13. 參考資料

- 效果解析器來源: ROItemSearchApp (`C:\Users\lithoshu\Desktop\ROItemSearchApp-0.7.17-260816`, GPL-3.0)
- GRF解包來源: SNShienRODataBase (`D:\Git\SNShienRODataBase`, 已退役)
- 強化規則原始表: `C:\Users\lithoshu\Desktop\強化表\RO強化表.xlsx`(轉json後以json為準)
- DRO client: `D:\倉庫\其他\DRO`
- 官方附魔說明: https://ro.gnjoy.com.tw/Notice/Guide_View?id=216543
- 官方精煉說明: https://ro.gnjoy.com.tw/Notice/Guide_View?id=216542
