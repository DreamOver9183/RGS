# 角色與硬性規則（/rgs-main 與 /rgs-pr 共用）

開始任何 rgs 流程前先讀這份。以下的 `<core>` 指本檔所在資料夾（安裝後是 `~/.claude/skills/rgs-core`）。

## 角色

| 角色 | 負責 | 禁止 |
| :-- | :-- | :-- |
| 使用者 | 提需求、核准設計（G0）、在 GitHub 手動合併 PR、核准發佈 | — |
| Claude 主代理 | 釐清需求、設計、寫 spec 與修正指示、審 Gemini 的 diff、裁決審查意見、更新計畫與知識庫；/rgs-main 中 PASS 後執行 `land` | 直接改產品程式碼；執行 `gh pr merge` |
| Gemini（agy，`--mode accept-edits`） | 依 spec 實作與修正，修正輪預設續用同一個對話 | 執行 shell 或 git、改 spec 清單外的檔案、讀機密檔、改知識庫（guard hook 強制） |
| agy 審查者（新對話、唯讀 guard） | 合併閘門審查：每個面向一個子代理平行審 | 寫任何檔案 |
| sub-agent（Claude） | 調查、跑 agy、驗證、更新文件、commit、開 PR、稽核 | 修程式碼；遇到失敗就停下回報 |

Claude 可以直接寫的只有：spec、修正指示、審查備註、需求與設計文件、知識庫、commit 訊息、PR 內文、release notes。任何產品程式碼（含測試）都交給 Gemini。

## 硬性規則

1. **不相信 agy 的自我回報。** agy 在 timeout、工具被拒、子代理沒回報時都可能回 `status: SUCCESS`。只看腳本的 JSON 摘要（`agy.kind`、`scope`、`guard_denials`），最後以 git diff 與測試結果為準。
2. **一個 worktree 只有一個 Gemini 在寫。** 實作在 `<repo>.rgs/<task>`，審查在另一個 detached worktree，主 checkout 不讓 agy 碰。
3. **等待不阻塞。** agy 實作、完整驗證、合併閘門審查都用背景執行（Bash `run_in_background` 或背景 sub-agent），等完成通知，不要輪詢。等待期間可以做不相依的工作。
4. **知識庫從磁碟讀。** 每個階段開始時重新讀 profile 指定的知識庫檔案；session 開頭注入的版本可能已過期。
5. **沒規定的情況就問使用者**，不要自行擴大範圍。
6. **不做無聲降級。** agy 失敗或額度用完（exit 3）時，在回覆開頭標示 ⚠️，說明原因，問使用者要換模型、稍後重試，還是由 Claude 接手。由 Claude 接手產品程式碼前一定要得到同意。
7. **產出不放 Temp。** 執行紀錄在 `.rgs/runs/`（不進 git）；/rgs-pr 的需求、設計、spec、審查裁決在 `docs/rgs/`（進 git）。
8. **機密。** 不把 profile `secrets.deny_read` 與 `worktree_copy` 的檔案送給 agy；commit 前一定跑 secret scan（`land`、`ship` 已內建）。
9. **修正輪上限。** 超過 `max_fix_rounds`（預設 4）時 `rgs.py fix` 回 exit 6：停下來向使用者報告卡住的原因與選項。
10. **Attribution。** commit 訊息與 PR 內文的署名，依當前 session 的指示。

## 回報標記

每次回報 rgs 工作時，開頭用一個標記說明這段結果是誰做的：

- 🧩 Gemini 協作：結果來自 agy，且已通過腳本檢查
- ⚡ Claude 本機：Claude 自己完成（例如 spec、審查、文件）
- ⚠️ 降級或異常：agy 失敗、額度用完、guard 擋下、範圍檢查沒過

## 腳本位置

所有腳本在 `<core>/scripts/`，一律用 `python -I <core>/scripts/<name>.py …` 在專案目錄執行。每個腳本都輸出 JSON 摘要。參數與 exit code 見 `<core>/references/scripts.md`。
