# CLAUDE.md

RO配裝分析工具。接手前先讀:

- 設計權威: `docs/superpowers/specs/2026-09-03-robuildanalyzer-design.md`(所有設計決策, 不要重新 brainstorm 已定案事項)
- 目前進度與下一步: `docs/superpowers/notes/progress.md`
- 動成本引擎前: `docs/superpowers/notes/refine-cost-algorithm.md`
- 效果解析移植依據: `docs/superpowers/notes/2026-09-03-effect-parser-inventory.md`

## 開發環境

- Python 一律 `py -3.12-64`; 中文輸出時前綴 `PYTHONIOENCODING=utf-8`
- 測試: repo 根目錄 `py -3.12-64 -m pytest tests/`
- GUI: `py -3.12-64 -m app.gui`
- 未版控、新機器要自己備: `config.json`(`dro_path` 指向 DRO client 目錄、`java_exe`、`db_path`)、`data/ro_items.db`(用 `py -3.12-64 -m importer.cli` 從 client 重匯, 真實基準數字見 progress.md)

## 開發模式

每個里程碑: 寫 plan(`docs/superpowers/plans/`)→ worktree(`.worktrees/<branch>`)+ subagent-driven 執行 → 最終 review → merge。新 worktree 要從主目錄複製 `data/ro_items.db` 與 `config.json`。

## 與使用者協作

- **重開/關掉 GUI 前先請使用者存檔**: 曾直接 kill 舊視窗弄丟使用者未存的配裝。使用者電腦記憶體吃緊, 背景開的 GUI 會被回收, GUI 建議由使用者自己開
- `userdata/builds/test_build*.json`、`userdata/characters/test_rk.json` 是使用者的實測檔, 未版控, 不要動
