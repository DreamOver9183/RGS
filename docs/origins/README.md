# 原始素材

整理 rgs 流程時參考的實戰紀錄，只供追溯與比對，skill 執行時不會讀取。本機路徑已換成佔位符：`<scratchpad>`（當時 session 的暫存資料夾）、`<repo>`（專案根目錄）、`<home>`、`<workspace>`。

| 位置 | 來源 | 對應的 rgs 檔案 |
| :-- | :-- | :-- |
| `android_class/m-series/gemini-rules.md` | android_class M0–M7：Gemini 實作者規則 | `templates/implementer-rules.md` |
| `android_class/m-series/opus-review-rules.md` | android_class 合併閘門審查規則 | `templates/reviewer-rules.md` |
| `android_class/m-series/m*-spec.md`、`m*-fix-*.md`、`pr*-note.md`、`m*-pr-body.md` | 里程碑規格、修正指示、審查備註、PR 內文 | `templates/milestone-spec.md`、`fix-notes.md`、`review-note.md`、`pr-body.md` |
| `android_class/m-series/*.sh` | 範圍比對與文件檢查腳本 | `scripts/scope_check.py`、`secret_scan.py` |
| `android_class/p-series/` | v1.1.0 的規格、agy prompt、release notes | `templates/prompts/`、`release-notes.md` |
| `android_class/memory-multi-agent-workflow.md` | 使用者確立的分工 | `roles.md` |
| `rimtainame/agy_review.py`、`agy_translate.py`、`name_rules.py` | PR 審查與大量翻譯腳本 | `scripts/review.py`、`batch.py` |
| `rimtainame/CLAUDE-sop-excerpt.md` | RimTaiName 的開發 SOP | `references/workflow.md` |
| `facet/handoff.md`、`PLAN.md`、`preflight-results.md`、`requirements.md`、`design.md` | Facet skill（另一個 repo）的交接文件、實作計畫、agy 預檢結果、需求與設計；併入 RGS 前的版本 | `skills/rgs-facet/`、`docs/rgs/` |
