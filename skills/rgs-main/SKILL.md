---
name: rgs-main
description: 輕量的 Claude × Gemini（Antigravity CLI，agy）協作開發流程。Claude 寫任務規格，Gemini 在隔離的 worktree 中實作；Claude 審 diff 並跑測試，通過後直接 push 到 main，不通過就寫具體修正建議請 Gemini 再改。適用小型專案、單一功能或修 bug、單人 repo。只要使用者輸入 /rgs-main，或說「讓 Gemini 寫、你審」「叫 Antigravity 做完直接推 main」「這個小功能交給 Gemini」，就使用這個 skill。另有子指令：batch（大量資料交給 Gemini 批次處理）、digest（長文件或 log 交給 Gemini 摘要並核對引用）、status（用量或額度中斷後續跑）。需要需求文件、里程碑、PR 與人工合併的中大型工作，改用 rgs-pr。只想讓其他模型審查計畫、不實作時，改用 rgs-facet。
argument-hint: <任務描述> | status | batch … | digest …
---

# /rgs-main：Claude 指揮 → Gemini 實作 → Claude 審查 → push main

分工的理由：Gemini 便宜、能長時間寫程式，但不能執行建置或測試，偶爾會寫錯或越界；Claude 負責把任務講清楚、把關品質。所以 Claude 不直接寫產品程式碼，只寫規格與修正建議；Gemini 只能改規格列出的檔案，這由 guard hook 強制執行。審查通過的變更以 fast-forward 直接進 main，不開 PR。

## 開始前

1. 找到共用核心：`<core>` 是本 skill 基底目錄的同層資料夾 `rgs-core`（例如 `~/.claude/skills/rgs-core`）。
2. 讀 `<core>/roles.md`：角色、硬性規則、回報標記（🧩 ⚡ ⚠️）。這些規則適用於整個流程。
3. 依參數分流：
   - `status`：執行 `python -I <core>/scripts/rgs.py status`，對照每個任務的 `step`，從中斷處接著做（下面流程的對應步驟）。
   - `batch …`／`digest …`：讀 `<core>/references/delegation.md` 照做。
   - 其他：當成任務描述，走下面的流程。

腳本一律在專案目錄用 `python -I <core>/scripts/<name>.py` 執行，輸出 JSON 摘要；exit code 的意義見 `<core>/references/scripts.md`。

## 流程

### 0. 前置檢查

- 執行 `doctor.py --quick --flow main`，有 FAIL 就先處理。
- 沒有 `.rgs/profile.json` 時執行 `doctor.py --init`，把草稿中的 quick／verify 指令、知識庫檔名與機密檔清單給使用者確認，不確定的地方用 AskUserQuestion 詢問。`--init` 也會列出建議的權限規則，請使用者自行加入（Claude 不能修改自己的設定）。
- 從磁碟讀 profile 指定的知識庫檔案。
- 估一下範圍：如果需要多個里程碑、要先寫需求或設計，或者會動到很多模組，建議改用 `/rgs-pr`，讓使用者決定。

### 1. 寫規格

- 先讀相關程式碼（範圍大時用 Explore sub-agent），找出要改的檔案、可以重用的既有元件，以及專案慣例。
- 取一個任務 id（英數與 `-`，例如 `add-csv-export`），依 `<core>/templates/task-spec.md` 寫成 `.rgs/runs/<task>/spec.md`。
- 「可修改的檔案」要完整而精確：guard 只允許寫入這份清單，漏列的檔案 Gemini 改不到；多列的檔案則會讓範圍檢查失去作用。測試檔也要列進去。
- 把知識庫裡與這次任務相關的踩坑紀錄放進「先前的教訓」。Gemini 不能編譯，越具體的提示越能減少修正輪數。

### 2. 準備 worktree

```
python -I <core>/scripts/rgs.py prepare --task <task> --spec .rgs/runs/<task>/spec.md --flow main
```

這一步會從 `origin/main` 開分支 `rgs/<task>`，在 `<repo>.rgs/<task>` 建立 worktree，並裝好 guard。主 checkout 不會被動到。

### 3. Gemini 實作（背景）

用 Bash 的 `run_in_background` 執行，等完成通知；通常要 5–20 分鐘，等待期間不要輪詢：

```
python -I <core>/scripts/rgs.py implement --task <task>
```

讀摘要：`agy.kind` 不是 `ok`（exit 3／5）時，依 roles.md 第 6 條用 ⚠️ 回報；`guard_denials` 代表 Gemini 想做被禁止的事；`scope` 是實際變更；`response_file` 是 Gemini 自己的說明（特別看它說做不到的部分）。

### 4. Claude 審查

1. `rgs.py diff --task <task>` 產生 diff 檔，完整讀一遍。
2. 依 `<core>/references/workflow.md` 的「Claude 審查 diff 的標準」逐項檢查：範圍、正確性、編譯風險、規格與測試、知識庫規範、回歸。
3. `rgs.py check --task <task> --level quick`；判 PASS 前再跑一次 `--level verify`（耗時就放背景）。
4. 判定：
   - **PASS**：範圍檢查通過、測試全綠、沒有未解決的問題 → 到步驟 6。
   - **REJECT**：任何正確性、規格、測試或範圍問題 → 到步驟 5。風格上的小偏好不需要退回，記下來當之後的教訓即可。

### 5. REJECT：寫修正建議交給 Gemini

- 依 `<core>/templates/fix-notes.md` 寫 `.rgs/runs/<task>/fix-notes-<k>.md`：每條都寫出檔案、位置、要改成什麼、原因；建置或測試錯誤直接貼原文。
- 需要改清單外的檔案時，確認理由充分，再加上 `--allow <path>`。
- 在背景執行 `rgs.py fix --task <task> --notes .rgs/runs/<task>/fix-notes-<k>.md`，完成後回到步驟 4。
- exit 6 代表修正輪數已達上限：停下來向使用者說明卡在哪裡，以及有哪些選項（換模型、拆小任務、由 Claude 接手）。

### 6. PASS：進入 main

1. 選用 `--gate`（使用者指定，或變更涉及安全、資料遷移等高風險）時，先跑 `python -I <core>/scripts/review.py --task <task>`，依 workflow.md 裁決每條意見；有採納的意見就回到步驟 5。
2. 依 profile 的語言寫 commit 訊息到 `.rgs/runs/<task>/commit-message.txt`。格式是 `type(scope): 摘要`，內文寫原因、修正輪數與測試結果，署名依當前 session 的指示。
3. 執行 `rgs.py land --task <task> --message-file .rgs/runs/<task>/commit-message.txt`。它會依序：
   - 範圍檢查與 secret scan
   - 建立 commit
   - 遠端已前進時 rebase，並重跑 quick
   - fast-forward push 到 `origin/main`
   - 主 checkout 乾淨時同步本地 main
   - 移除 worktree
4. 處理失敗：
   - exit 7：有機密，查明來源，不要繞過。
   - exit 8：rebase 衝突，commit 留在 `rgs/<task>`，回報使用者。
   - exit 9：rebase 後測試失敗，回到步驟 5。
   - exit 10：push 被拒，讀 stderr。是分支保護就建議改用 `/rgs-pr`；**絕不 force push**。

### 7. 知識沉澱

這次若有新的慣例、架構決策，或踩到的坑（包括 Gemini 反覆犯的錯），在主 checkout 更新知識庫，寫成「現象 → 原因 → 做法」。另外做一個 `docs:` commit 並 push 到 main。沒有新東西就跳過，不要寫流水帳。

### 8. 回報

開頭加標記（🧩／⚡／⚠️），內容包括：

- commit hash
- 改了哪些檔案、各做了什麼
- 修正輪數，以及每輪的重點
- 測試結果（指令與數字）
- ⚠️ 尚未驗證的項目，例如需要實機或手動測試的部分

如果 `.rgs/profile.json` 還沒進版本控制，提醒使用者可以加進去。
