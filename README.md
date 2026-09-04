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

## 測試

```
py -3.12-64 -m pytest tests/ -v
```
