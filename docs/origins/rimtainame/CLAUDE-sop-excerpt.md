---

## 開發流程 SOP（每完成一個獨立模組或可測試單元，依序執行，不可跳過）

1.  **自我審查與測試：** 在功能分支（`feat/<短名>`、`fix/<短名>`）上執行 build（`-warnaserror`）、`dotnet format --verify-no-changes`、`dotnet test --project Source/RimTaiName.Tests`、`python -I Tools/check_keys.py`，以及變更檔案的 Python／PowerShell 語法檢查；改到 `Llm/` 時加跑即時 API 測試，改到打包腳本時跑 `test_package_mod.ps1`；自己讀一次 diff 做初步 Code Review。
2.  **發起 PR：** `git push -u origin <branch>`，`gh pr create --base main`。內文附變更摘要與測試結果，結尾加 `🤖 Generated with [Claude Code](https://claude.com/claude-code)`。
3.  **雙軌審核：**
    *   先請 Copilot 審查：`gh pr edit <PR#> --add-reviewer "@copilot"`，再以 `gh pr view <PR#> --json reviews,comments` 檢查是否完成。
    *   Copilot 回報額度耗盡、未回應或無法使用時，改用 `python -I Tools/agy_review.py <PR#> --post`（Antigravity CLI，`gemini-3.8-flash-high`，以子代理平行審查安全性、邊界條件、架構合規）。
4.  **修正與合併：** 審核意見僅供參考，自行判斷是否採納；修正推上同一分支後 `gh pr merge <PR#> --squash --delete-branch`，再 `git switch main`、`git pull`。
5.  **提煉更新知識庫：** 只把本次「新增的架構決策、新慣例、踩到的技術坑」寫進本檔，直接在 main commit 並 push。

其他慣例：
*   Commit 訊息用繁體中文，結尾加 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`。在 PowerShell 中先把訊息寫成檔案再 `git commit -F <file>`。
*   需要遊戲內驗證的項目，打包後交給使用者在測試機實測，`Player.log` 放進 `TestLog/` 再檢查。
*   雜事可交給 Antigravity CLI；呼叫 Gemini 時盡量讓它用子代理（`invoke_subagent`）平行處理。

