# M4 GUI 驗收清單

M4(GUI)開發完成後的手動驗收筆記。程式化測試(pytest)已覆蓋單元/smoke層級, 但實際操作手感、版面是否真的不捲動、顏色/文字讀起來是否合理, 需要使用者親自跑一次GUI逐條勾選。

## 環境與啟動

1. 已完成M1匯入(`data/ro_items.db` 存在)與 `config.json` 設定。
2. 安裝GUI依賴:
   ```
   py -3.12-64 -m pip install "PySide6>=6.8"
   ```
3. 啟動:
   ```
   py -3.12-64 -m app.gui
   ```
4. 建議先把 `userdata/characters/` 底下放至少一個角色檔(例如手動複製既有的 `test_rk.json` 或既有sample角色檔), 否則頂部角色檔下拉會停用, 效果/成本頁的角色相關功能無法驗收。

## 手動驗收清單

- [ ] 1920x1080滿版下, 兩欄各20格全部可見, 不需捲動
- [ ] 「+ 卡片」chip只在該格有卡片洞且未插滿時出現
- [ ] 「+ 附魔」chip只在該格有可附魔洞且未插滿時出現
- [ ] 職業過濾勾選/不勾選時, 選擇清單內容有合理差異(例如角色職業為盧恩騎士RK, 勾選「只顯示本職業可裝備」後清單看不到拳刃專用武器)
- [ ] 附魔清單同一槽位的機率%加總約等於100
- [ ] 選擇清單項目hover時, tooltip敘述完整顯示且色碼(如增益/減益顏色)有正確上色
- [ ] 套裝其中一件hover時, 同組已裝備的其他部位一併高亮(用 `test_build_rk.json` 的影子君主套裝驗證)
- [ ] 效果結算頁傷害/抗性/能力/次要能力/其他五組分類對齊呈現(「未計入」是分類表以外的獨立區塊), 且優勢方向色碼正確(例如減傷數值更負的一側顯示為優勢/亮色)
- [ ] 「未計入」區塊裡, 缺技能等級資料的條目文字可讀(格式為「技能「X」等級」, 不是原始變數名或報錯)
- [ ] 成本估算頁, A配裝的期望總Zeny與 `py -3.12-64 -m app.cli cost <build.json>` 印出的總Zeny一致
- [ ] GUI存的配裝json可以被CLI讀取(`app.cli effects`/`compare`/`cost` 對同一份GUI存檔皆能正常執行, 不報格式錯誤)
- [ ] 右鍵部位可以打開「設定精煉…」「設定階級…」並且設定後畫面即時更新
- [ ] 已裝備的一般/影子格, 精煉值恆顯示(即使精煉為0也顯示為`+0`, 不是空白)
- [ ] 「另存」為新檔名後, 頂部檔案下拉會出現新檔名, 且原檔內容不變(可重新開舊檔確認)
- [ ] 換角色檔或切換面板檔案時, 若配裝有未存修改, 彈出的儲存詢問若選「取消」, 不會丟失未存的配裝內容(切換被中止, 停留在原畫面)
- [ ] 效果結算頁在計算過程出錯時(例如刻意選一個資料異常的配裝), 畫面會清空舊的結算表格, 不會殘留上一次的正確結果造成誤讀

## 量測數字

### Task 1: parse_sweep 解析健康對照(修復「技能等級型變數缺角色資料時應歸未判定條件, 不是無法辨識」前後)

| | items unresolved_condition | items unrecognized | combos unresolved_condition | combos unrecognized |
|---|---|---|---|---|
| **修復前** | 1392 | 1458 | 302 | 443 |
| **修復後** | 2825 | 25 | 742 | 3 |

兩次執行(`py -3.12-64 -m scripts.parse_sweep --top 10`)均為 **0 exceptions**。`unrecognized`(無法辨識)在items降約98%、combos降約99%, 幾乎全數轉入`unresolved_condition`(未判定條件), 符合修復目標——這些效果行本身依賴角色技能等級等資料, 缺角色檔時本就該標示「未判定」而非「解析器看不懂」。

### Task 3: 真實資料庫目錄統計

`unclassified_count() = 735`(equip_type=armor但描述尾段的「系列」欄位沒有命中任何規則的件數; debug用數字, 約等於防具類裡沒能歸類部位/系列的行數)。

各slot分類數量(equipment / cards / stones):

| slot_key | equipment_for_slot | cards_for_slot | stones_for_slot |
|---|---|---|---|
| head_top | 1123 | 127 | - |
| head_mid | 261 | 127 | - |
| head_low | 260 | 127 | - |
| armor | 467 | 145 | - |
| shield | 128 | 65 | - |
| garment | 314 | 124 | - |
| shoes | 267 | 147 | - |
| acc_r | 637 | 118 | - |
| acc_l | 636 | 119 | - |
| shadow_armor | 157 | - | - |
| shadow_gauntlet | 187 | - | - |
| shadow_shield | 133 | - | - |
| shadow_shoes | 133 | - | - |
| shadow_earring | 114 | - | - |
| shadow_pendant | 110 | - | - |
| costume_top | 942 | - | 63 |
| costume_mid | 487 | - | 60 |
| costume_low | 539 | - | 62 |
| costume_garment | 190 | - | 62 |
| weapon | 1898 | 248 | - |

(`-`表示該欄位對此slot_key沒有意義: cards只對10個一般slot有效, stones只對4個costume slot有效)

### Task 5: 面板版面量測

用真實DB建構MainWindow後, `panel_a.sizeHint().height()` = **672px**(20格 x 28px高 + 3個section標題 + margins/spacing), 遠低於1080螢幕下的940px可用高度上限, 確認雙面板並排不需捲動。

### Task 8: GUI與CLI成本計算一致性

用 `userdata/builds/test_build_rk.json`(20件裝備、11格掛cost_targets)驗證:

- GUI成本估算頁A卡 `total_a` 顯示: **1,490,201,607**
- CLI `py -3.12-64 -m app.cli cost userdata/builds/test_build_rk.json` 印出的配裝總Zeny: **1,490,201,607**

兩者完全一致。

## 本次執行中的裁決

以下是實作期間controller做出、偏離原計畫書字面或補充規格未明訂細節的裁決, 列出供使用者檢視, 如認為不妥可要求調整:

(a) **Task 1**: handler參數裡直接使用缺角色資料的SCALAR_KEYS(如`total_STR`), 原本落「無法辨識」, 現改為統一路由到「未計入」(未判定條件), 並因此連帶重新斷言了10個舊測試(原本斷言`KIND_UNRECOGNIZED`, 改斷言`KIND_UNRESOLVED`)。

(b) **Task 1**: 同一變數被重新賦值時, 一律清除該變數先前殘留的「缺角色資料」歸因記錄, 避免用舊的缺項誤判新的賦值結果。

(c) **Task 2**: `job_dict`實際只有20個非零職業, 因此`JOB_TABLE`收錄20筆(原計畫書寫21筆); 另職業4262在來源資料裡對應的血統職業碼是4005, 不是規劃時假設的4006。

(d) **Task 6**: 已裝備的一般/影子格恆顯示精煉標籤(即使精煉為0也顯示`+0`), 且右鍵選單新增「設定精煉…」「設定階級…」——這覆蓋了原計畫書「精煉>0才顯示」的字面規定。

(e) **Task 7/8**: 修正負零(`-0`)格式化顯示問題; 效果頁在結算出錯時清空舊表格(避免殘留舊結果誤導使用者); 成本頁每格的成本計算例外各自隔離, 一格出錯不影響其他格。

## 已知延後項目

以下是尚未處理、留給後續(下一次review或M5)評估的小事項, 不影響本次驗收但供知悉:

- `app/gui/build_panel.py` 目前約457行, 略高於原本估計的~450行門檻, 若後續還要往這個檔案加功能建議屆時評估拆檔。
- `GRADE_LABEL` 常數在 `cost_tab.py` 與 `cost_targets_dialog.py` 兩處重複定義, 未抽共用模組。
- `CostTargetsDialog`(成本設定對話框)本身欄位邏輯與成本頁「無成本目標」提示列(`report.items==[]`分支)沒有自動化測試覆蓋, 僅手動/程式碼審閱確認過。
- 選擇清單的搜尋框比對是區分大小寫的(case-sensitive)。
- `build_panel.py` 部分combo box的`blockSignals`呼叫沒有用`try/finally`包起來, 理論上例外發生時可能讓訊號維持被阻塞的狀態。
- 目錄(catalog)掃描真實DB時有18筆道具因缺`display_name`而被直接跳過、未被計入任何統計數字。
- 702件服飾道具敘述缺系列/位置無法歸類, 已在頂部列顯示未分類件數, `(服飾)`名稱前綴fallback留M5。
- if條件依賴未解變數時missing為空(1256/2372), if-handler接unresolved_vars留M5。

## 對照指令

驗收時可交互比對GUI畫面與以下CLI指令的輸出:

```
py -3.12-64 -m app.cli cost userdata/builds/test_build_rk.json
py -3.12-64 -m app.cli compare userdata/builds/sample_a.json userdata/builds/sample_b.json userdata/characters/sample.json
py -3.12-64 -m app.cli effects userdata/builds/sample_a.json userdata/characters/sample.json
py -3.12-64 -m scripts.parse_sweep --top 10
```
