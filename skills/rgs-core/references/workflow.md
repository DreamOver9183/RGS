# 流程細節：閘門、審查標準與慣例

兩個指令的步驟寫在各自的 SKILL.md；這份是它們共用的品質標準。

## 品質閘門

| 閘門 | 內容 | 誰判定 | /rgs-main | /rgs-pr |
| :-- | :-- | :-- | :-- | :-- |
| G0 設計核准 | requirements 與 design 經使用者同意 | 使用者 | — | 必要 |
| G1 Spec 完整 | 有可修改檔案清單、驗收條件、必要測試、相關教訓 | Claude 自檢 | 必要 | 必要 |
| G2 範圍 | `scope.ok`、沒有被繞過的 guard 拒絕、主 checkout 沒被動到 | 腳本 | 必要 | 必要 |
| G3 建置與測試 | 每輪跑 quick；交付前跑 verify，全部通過 | 腳本／finisher | 必要 | 必要 |
| G4 Claude 審查 | diff 符合 spec 與知識庫，沒有未處理的問題 | Claude | 必要 | 必要 |
| G5 文件同步 | 知識庫與 README 和程式一致（測試數、指令、路徑） | finisher／auditor | 有新慣例時 | 必要 |
| G6 機密 | secret scan 通過 | 腳本（land／ship 內建） | 必要 | 必要 |
| G7 獨立審查 | agy 合併閘門沒有未裁決的 blocker／major | review.py + Claude 裁決 | `--gate` 時 | 必要 |
| G8 進入主幹 | fast-forward push／使用者手動合併 | 腳本／使用者 | push | 使用者合併 |

Definition of Done（/rgs-main）：G1–G4、G6 通過，`land` 成功，回報 commit 與未驗證項目。

Definition of Done（/rgs-pr 里程碑）：G1–G7 通過，PR 開好並交給使用者合併；合併後知識庫、design 狀態表、追溯矩陣、教訓清單都已更新。

## Claude 審查 diff 的標準（G4）

依序檢查，發現問題就記進修正指示：

1. **範圍**：只改了 spec 清單上的檔案；沒有順手重構、重新排版。
2. **正確性**：邏輯、邊界（null、空值、超長、Unicode）、錯誤處理、並行與生命週期、資源釋放。
3. **編譯風險**：Gemini 不能執行程式，特別檢查 import、簽章、具名參數、型別，以及是否用了不存在的 API。
4. **規格**：每條驗收條件都有對應實作，必要測試都有寫，而且測試真的驗證到該行為（不是只呼叫一下）。
5. **知識庫規範**：分層、字串與設定放置、機密處理、命名慣例。
6. **回歸**：既有行為與既有測試的意圖沒有被改壞。

風格偏好不要開修正輪；累積到下一份 spec 的「先前的教訓」即可。

修正指示的寫法（`templates/fix-notes.md`）：每條都要寫出檔案、位置、要改成什麼、原因；編譯或測試錯誤直接貼原文。指示越具體，Gemini 越少繞路。

## 審查意見的裁決（G7）

- `review.py` 會把每條意見寫進 ledger，狀態是「待裁決」。Claude 逐條改成：**採納**、**不採納**（寫理由）、**延後到 M<n>**（寫理由，並加進該里程碑 spec）。
- 審查意見只是參考。RimTaiName 的經驗是 Gemini 的建議約四成值得採納，所以要逐條判斷，不要全收。
- 採納的意見寫成修正指示交給 Gemini，修正後跑 `review.py`（附上 `--note`，列出上一輪的裁決）做複審。
- `verdict` 只要有未解決的 blocker／major 就不算 PASS；minor 可以延後。

## Commit 與 PR 慣例

- 訊息：Conventional Commits，`type(scope): 摘要`；語言依 profile `language.commits`。內文說明原因、審查輪數與測試結果；署名依當前 session 指示。
- 訊息先寫成檔案再交給 `land`／`ship`（`--message-file`），避免 shell 引號問題。
- 一個任務或里程碑一個 commit（/rgs-main）或一個 PR（/rgs-pr）。審查後的修正在同一分支追加 commit，例如「依審查意見修正 …」。
- PR 內文用 `templates/pr-body.md`：變更摘要、對應需求、測試結果（實際數字）、審查摘要、尚未驗證的項目。

## 知識沉澱

合併（/rgs-pr）或 push（/rgs-main）之後，只把下列內容寫進知識庫，每條寫成「現象 → 原因 → 做法」：

- 新的架構決策（同時記進 design.md 決策紀錄）
- 新引入的慣例
- 踩到的技術坑，包括 Gemini 反覆犯的錯

不要寫進度、流水帳、本機絕對路徑或 commit hash。審查中反覆出現的錯誤也要加進 design.md 的「教訓清單」，之後每份 spec 都帶上。

## 平行與堆疊（/rgs-pr）

- 互不相依的里程碑可以各自 `prepare`（各自一個 worktree），但同時只讓一個 Gemini 執行，避免額度與注意力分散。
- 相依的里程碑用 `prepare --stack-on <前一個任務>`，PR 的 base 會是前一個分支，PR 內文要註明先合併哪一個。
- 前一個 PR 合併後，對每個堆疊在上面的任務執行 `rgs.py retarget --task <子任務>`：
  - 它先確認父 PR 已經 MERGED（沒合併就拒絕），再用 `gh pr edit` 把子 PR 的 base 改成 profile 的 `base_branch`，並把任務的 base 改成 `<remote>/<base_branch>`，之後 `diff`、`fix --fresh` 就不再依賴父分支。
  - 父 PR 用 merge commit 合併時，子分支不用動。用 squash 或 rebase 合併時，父分支原本的 commit 不在 base 裡，子 PR 的 diff 會重複出現父 PR 的變更；retarget 會只把子任務自己的 commit rebase 到 base，再用 `--force-with-lease` 推回同一個分支（只有遠端還停在上次 ship 的位置時才會覆蓋）。
  - 一定要做：父分支沒刪時，子 PR 仍指向已合併的父分支，這時直接合併子 PR 只會合進父分支，不會進 base。
- GitHub 的行為（[官方文件](https://docs.github.com/en/pull-requests/how-tos/commit-changes/managing-branches-within-your-repository)）：父 PR 合併**之後**刪除父分支，GitHub 會把以它為 base 的開啟中 PR 自動改到父 PR 的 base；但在父 PR 還開著時刪除分支，會把相關的 PR 關掉。所以遠端的父分支要等合併並 retarget 之後才刪。

## 需求追溯

- 需求編號 R-n（requirements.md）→ 里程碑 M-n（design.md）→ spec（docs/rgs/specs）→ PR → 審查 ledger（docs/rgs/reviews）。
- 每個里程碑合併後更新 design.md 的追溯矩陣與狀態總覽，填入測試數與 PR 編號。

## 發佈（/rgs-pr release）

1. auditor sub-agent 唯讀稽核文件與程式是否一致：測試數、版本號、指令、路徑、機密、過時描述。
2. 稽核出的問題由 finisher 修正；版本號變更由 Gemini 依小型 spec 實作（屬於產品檔案）。專案沒有版本號檔案（版本只存在 tag）時略過這步與下一步。
3. 版本 PR 經 `review.py` 審查後，交給使用者合併。
4. 從合併後的 commit 建置產物，計算 SHA-256（`certutil -hashfile <檔案> SHA256` 或 `sha256sum`），依 `templates/release-notes.md` 撰寫 release notes，並用 `secret_scan.py --files` 掃描 notes 與實際發佈的檔案（掃整個 repo 可能命中文件裡刻意寫的假金鑰）。
   - 沒有建置步驟的專案（例如 skill、腳本），產物用 `git archive --format=zip --prefix=<名稱>/ -o <zip> <commit>:<資料夾>`；同一個 commit 產生的 zip 位元組相同，SHA-256 可重現。
   - 產物與 notes 放在 `.rgs/runs/release-<版本>/`，不要放 Temp。
5. **`gh release create` 會對外公開：執行前先把版本號、產物、SHA-256 與 notes 給使用者確認。**
   - 一律加 `--target <完整 SHA>`：不要依賴預設分支（預設分支不一定是 base，也可能已經前進）。
   - `--target` 只接受完整的 40 字元 SHA，先用 `git rev-parse <合併後的 commit>` 取得；給短 SHA 時 GitHub API 回 HTTP 422 `Release.target_commitish is invalid`。
   - 使用者還不想公開，或版本號已經保留給之後的里程碑時，用 `--draft`：只有協作者看得到，按下發佈前不會建立 tag。建立後用 `gh release download` 下載產物，比對 SHA-256。
