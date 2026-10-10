# 開發進度

最後更新: 2026-10-10

## 下一步

- M4 GUI 在 `m4-gui` 分支手動驗收中, 使用者逐項回饋、逐項修
- 最近一次回饋已修(2026-09-29): 套裝綠框高亮改為懸停裝備名只亮本體的套裝、懸停卡片 chip 只亮該卡的套裝; 裝備名/卡片 tooltip 最上方列「成立套裝: 名稱(部位) + 名稱(部位)」。起因是鎧甲懸停時披肩也亮(實為鎧甲上監視者卡片 + 披肩千年老妖卡片的卡片套裝), 混在一起看不出來。**待使用者確認新行為 OK**
- 驗收完 → 跑全測試 → merge 進 main → 移除 worktree(`git worktree remove .worktrees/m4-gui`)
- 驗收清單與量測數字: `docs/superpowers/notes/2026-09-05-m4-acceptance.md`

## 里程碑

- **M1 匯入工具**(PR #1): `importer/`, DRO client `data.grf` → `data/ro_items.db`(items/combos/enchant_tables/skills/import_meta + 索引)。真實基準: items 20799 / effects 8842 / enchant 18083 / 81 表 / skills 1604 / combos 4849 / duplicates 263
- **M2 效果解析 + 結算**(PR #2)+ 四組分類(PR #3): `app/core/`(68 handlers)+ `app.cli`。分類 = 傷害/抗性/能力/次要能力 + 其他(handler 層直接標); `get(N)` 已接角色檔; 缺 context 走 UNRESOLVED/UNRECOGNIZED 誠實呈現
- **M3 成本引擎**: `app/core/cost/`(rules/materials/refine/enchant/report)+ cost CLI。強化表 xlsx → `userdata/refine_rules.json` + `prices.json`(`scripts/convert_refine_rules.py`); Fraction 全程精確; `scripts/parse_sweep.py` 全量健康掃描。同腳本內 SetEquipTempValue/GetEquipTempValue 可算(跨腳本維持無法辨識)
- **M4 GUI**(`m4-gui` 分支, 驗收中): 9 task SDD + 全分支 review + 修正, 之後依驗收回饋陸續修

## CLI

- `py -3.12-64 -m app.cli effects <build.json> <character.json>`
- `py -3.12-64 -m app.cli compare <a.json> <b.json> <character.json>`
- `py -3.12-64 -m app.cli cost <build.json>`(部位需設 cost_targets: refine_from/grade_from/refine_table/enchant_strategy/enchant_goal)

## 已定案裁決

M3:
- 升階路徑僅支援 0→refine_req 無爆件的表(= 乙太表), 其他表設 grade → 警告略過(spec §7.2 第 11 條)
- 升階後高精煉 break 的補貨 = 素體 + 整條升階鏈成本 ×(1+R)
- 高密度乙太礦石兌換 = 星塵×3 + 高密度X礦石(172500)+ 5 萬, 使用者已證實(spec §12 假設 3)
- 附魔材料以 display_name 轉譯後計價; `prices.json` 目前只有強化材料, 附魔 Zeny 誠實為 0 + 警告, 要算附魔錢需使用者補中文材料價
- 影子裝備每精煉 +1 MHP+10 是 client 編在每件腳本裡的系統通則, 非解析錯誤

M4 執行者裁決(使用者可推翻):
1. 缺 SCALAR_KEYS 的 handler 行也歸未計入
2. 變數重賦值先清舊歸因
3. JOB_TABLE = 20 職業, 4262 血統用 4005
4. 已裝備格精煉恆顯示 +0, 右鍵設定精煉/階級
5. 換裝清空 cost_targets
6. GUI 一律經 AnalyzerSession wrapper
7. 「$」= 有成本目標標記, 使用者裁決保留

## 已知資料層事實(已向使用者解釋, 非 bug)

- 描述有但腳本未編碼: 機率 proc 類(塔奧群卡 DEF/MDEF-50%、生命力戰靴 VIT proc 等), 處理方式 = tooltip 顯示描述 + 全域註記
- 「依比例減少 DEF50%」類乘算面板效果超出裝備加成加總範圍, 不做面板

## 掛置中(等使用者)

- 元素鬼火(綠)卡片 `GetRefineLevel(5)` 綁披肩疑點: 待遊戲內實測, 若證實綁自身部位 → 建 override 修正表
- 月全蝕魔力外袍-LT 第 2 槽附魔池全是戰狼結晶體(55 種): client enchantlist.lub Table[10004] 明寫(另 10006、10010 也有), 非解析錯。使用者質疑, 待 NPC 實測; 若證實錯誤需新增附魔池排除/覆寫機制(目前 manual_enchants 只在查無表時 fallback)

## Parked / 留 M5

- `test_gui_smoke` 缺「目錄未分類」字串斷言(實作正確, 補一行測試); `session.search_entries` 未被 GUI 使用
- 702 件 `(服飾)` 道具敘述缺系列/位置無法歸類(頂部列顯示未分類件數)
- if 條件依賴未解變數時 missing 為空(if-handler 接 unresolved_vars)
- 角色檔編輯 / 補進角色檔 / 重新匯入 + 過期偵測
- CostTargetsDialog 自動測試; PySide6 改 optional-dependency
- enchantlist 的 SetEnchant 第一參數是階級(0~4), `importer/parsers/enchant.py` 忽略它把 5 份合併(權重 ×5 比例不變)。2026-09-08 全檔 199 槽無任何一槽各階級選項不同, 目前無害, 日後 client 出現按階級不同的池就會算錯
