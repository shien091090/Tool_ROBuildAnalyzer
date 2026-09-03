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

## 測試

```
py -3.12-64 -m pytest tests/ -v
```
