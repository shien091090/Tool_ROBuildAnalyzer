# Tool_ROBuildAnalyzer

RO配裝分析工具的M1匯入層 — 從《DRO》遊戲client資料檔(GRF封包、iteminfo lub)解包、反編譯並解析道具/附魔/組合套裝資料, 合併寫入中間SQLite資料庫, 供後續里程碑(配裝分析、效果解析)使用。

## 授權

本專案採用 **GPL-3.0** 授權。

原因: 後續里程碑計畫移植 ROItemSearchApp 的效果解析程式碼(GPL-3.0授權), 為維持授權相容性, 本專案整體採用GPL-3.0。

## 程式碼移植來源

以下模組移植自 SNShienRODataBase:

- `importer/grf.py` — GRF封包格式解析與解壓
- `importer/lua_scan.py` — Lua語法掃描輔助(括號/區塊配對)
- `importer/decompile.py` — 呼叫luadec/unluac反編譯.lub檔
- `importer/parsers/*` — 各Lua資料表解析器(iteminfo、itemdbname、equipment_properties、enchant)

以上模組為忠實移植, 未變更行為邏輯; 本次最終審查修復不觸碰這些檔案。

## 執行方式

首次執行前, 複製設定檔範本並填入DRO遊戲資料夾路徑:

```
copy config.example.json config.json
```

編輯 `config.json`, 填入 `dro_path`(DRO遊戲安裝資料夾, 需含 `data.grf` 與 `System\iteminfo_new.lub`)。

必須在repo根目錄執行(使用模組方式啟動, 確保相對匯入路徑正確):

```
py -3.12-64 -m importer.cli
```

執行完成後, 中間資料庫預設輸出至 `data/ro_items.db`(可由`config.json`的`db_path`欄位調整), 並在終端印出各項資料健康指標(道具數、附魔規則數、重複計數、靜默丟棄計數等)。

## M2: 效果結算與比較 CLI

效果解析與比較是M2功能(讀取M1匯入的中間資料庫, 對單一配裝結算效果或比較兩套配裝), GUI是M4——本節只涵蓋M2的命令列驗證面, 尚無視覺化介面。

需先完成上方「執行方式」的M1匯入步驟, 產出 `data/ro_items.db`。同樣須在repo根目錄以模組方式執行:

```
py -3.12-64 -m app.cli effects <build.json> <character.json>
py -3.12-64 -m app.cli compare <a.json> <b.json> <character.json>
```

`effects` 印單一配裝的分類效果加總、其他效果(敘述性技能解鎖/狀態觸發/無法辨識)、未計入的條件效果、warnings；`compare` 印兩套配裝的對齊比較表(依 physical→magical→other 分類排序)。

範例配裝檔在 `userdata/builds/`(如 `sample_a.json`、`sample_b.json`), 範例角色檔在 `userdata/characters/`(如 `sample.json`)。例如:

```
py -3.12-64 -m app.cli effects userdata/builds/sample_a.json userdata/characters/sample.json
py -3.12-64 -m app.cli compare userdata/builds/sample_a.json userdata/builds/sample_b.json userdata/characters/sample.json
```

Windows終端機輸出中文若出現亂碼, 可加上 `PYTHONIOENCODING=utf-8` 環境變數。

## M3: 成本引擎規則資料

`userdata/refine_rules.json`(精煉/升階/兌換規則)與 `userdata/prices.json`(材料單價)以使用者維護的《RO強化表.xlsx》為權威來源, 由 `scripts/convert_refine_rules.py` 一次性轉換產生; json產出後即為成本引擎的權威資料, 平時不再讀excel。若強化表內容更新, 重新執行以下指令(需先安裝dev extras的openpyxl)即可重轉並覆蓋兩份json:

```
py -3.12-64 scripts/convert_refine_rules.py
```

預設讀取路徑為 `C:\Users\lithoshu\Desktop\強化表\RO強化表.xlsx`, 可用 `--excel PATH` 覆寫。

## M3: 成本結算 CLI

成本結算(讀取M1匯入的中間資料庫+上一節產出的規則/價格資料, 對單一配裝逐格計算精煉/升階/附魔養成期望成本)也是M3功能, GUI仍是M4——本節只涵蓋M3的命令列驗證面。

需先完成上方「執行方式」的M1匯入步驟(產出 `data/ro_items.db`)與上一節的規則轉換步驟。同樣須在repo根目錄以模組方式執行:

```
py -3.12-64 -m app.cli cost <build.json>
```

逐格印三層報表: [直接消耗(合成品層)](精煉材料+祝福+升階寶石+附魔材料) → [中間合成品(供參考)] → [基礎材料攤開](單價x數量小計), 之後印兌換/精煉/升階/附魔手續費、本體件數(純顯示不計價)、該格Zeny小計, 逐格印完後印配裝總Zeny與warnings。

固定讀取 `userdata/refine_rules.json`、`userdata/prices.json`、`userdata/manual_enchants.json` 三份資料(精煉/升階/兌換規則、材料單價、舊式NPC附魔手動建檔), 均為repo根目錄相對路徑, 不開放CLI參數覆寫。

配裝json裡每一格的 `cost_targets` 欄位描述「從什麼狀態養到目前狀態」, 是M3成本引擎的計算輸入(見上方「配裝(userdata/builds/*.json)」章節§6格式); 該格若缺這個欄位, 代表使用者不關心這格的養成成本, CLI會直接跳過、不產生任何警告。

例如:

```
py -3.12-64 -m app.cli cost userdata/builds/sample_a.json
```

Windows終端機輸出中文若出現亂碼, 可加上 `PYTHONIOENCODING=utf-8` 環境變數。

## M4: GUI

需先完成上方「執行方式」的M1匯入步驟(產出 `data/ro_items.db` 與 `config.json`)。

安裝PySide6:

```
py -3.12-64 -m pip install "PySide6>=6.8"
```

啟動(同樣須在repo根目錄以模組方式執行):

```
py -3.12-64 -m app.gui
```

角色檔請先手動放在 `userdata/characters`(角色檔編輯UI為M5)。

### 操作要點

- **頂部**: 角色檔下拉選單(讀 `userdata/characters` 底下的角色檔; 清單為空時停用並提示手動放置檔案); 資料匯入日期旁同時顯示目錄未分類件數(`目錄未分類 N 件`, N為`AnalyzerSession.unclassified_count()`)。啟動時即自動重算一次(不需先做任何編輯), 兩側面板/效果頁/成本頁一開窗就有內容。
- **A/B配裝面板**(各20格): 點裝備名開選擇清單換裝(換裝會清掉該格原有的成本目標, 見下); 精煉/階級數字可點擊或右鍵「設定精煉…」「設定階級…」調整(已裝備的一般/影子格恆顯示精煉值, 例如`+0`, 未裝備才隱藏); 卡片洞未滿時格內出現「+ 卡片」chip、可附魔洞未滿時出現「+ 附魔」chip、服飾格則以cards欄位掛服飾強化石(「+ 強化石」); 右鍵部位可選「清空此格」或「成本設定…」(未裝備的格「成本設定…」停用)。
- **選擇清單**: 有搜尋框(輸入裝備名篩選)與「只顯示本職業可裝備」勾選(依角色職業過濾武器/防具); 項目hover可看完整敘述tooltip。同組套裝的其他已裝備部位會一併高亮。
- **效果結算頁**: 傷害/抗性/能力/次要能力/其他五組分類對齊表, 兩側數值優勢方向以顏色標示; 「未計入」是分類表以外的獨立區塊, 把缺角色資料的條件效果轉成可讀文字(如「技能「地雷散布」等級」); 底部有全域註記。
- **成本估算頁**: 需先對想計算養成成本的部位用右鍵「成本設定…」設定成本目標(精煉/階級起點、附魔策略等), 才會列入計算; 兩側「期望總成本」大字Zeny與 `py -3.12-64 -m app.cli cost <build.json>` 印出的總Zeny一致。
- **存檔**: 「儲存」/「另存」寫回 `userdata/builds/*.json`, 產出的檔案可直接被 `app.cli` 讀取(effects/compare/cost共用同一份配裝json格式); 若切換到的配裝檔格式有誤, 會彈提示訊息而不中止程式, 面板保留原本的配裝。
- **M4尚未包含(留待M5)**: 重新匯入資料按鈕、匯入資料過期偵測、角色檔編輯介面、缺角色資料項目的「補進角色檔」一鍵補值。

## 測試

```
py -3.12-64 -m pytest tests/ -v
```
