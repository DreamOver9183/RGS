# 疑難排解

## agy

| 現象 | 原因 | 做法 |
| :-- | :-- | :-- |
| `agy.kind: timeout`，response 是空的 | `--print-timeout` 到期；agy 仍回報 SUCCESS | 看 `.rgs/runs/<task>/*.err`。實作任務太大就拆小 spec；確實需要更久時用 `--timeout` |
| `agy.kind: empty`，response 說「在等子代理」 | 主代理沒等子代理回報就結束 | 重跑一次；仍失敗就換模型（`--model`），或減少 lenses |
| `agy.kind: quota`（exit 3） | 額度用完；fallback 鏈也用完 | ⚠️ 回報使用者。`doctor.py` 會顯示額度表；可在 profile 的 `models` 加備援模型 |
| `agy.kind: error`，detail 是 `Authentication expired` | agy 登入過期 | 請使用者在終端機執行 `agy` 重新登入 |
| `guard_denials` 有東西 | Gemini 想做被禁止的事 | 看 reason：要改清單外的檔案（判斷是否合理，合理就 `fix --allow`）、要跑指令（由 Claude 跑並把結果寫進修正指示）、要讀機密（不允許） |
| Gemini 宣稱完成，但 `scope.changed` 是空的（exit 5） | 寫入被擋，或模型只是描述沒動手 | 看 `guard_denials` 與 response_file，修正 spec 後重跑 |
| `main_checkout_changed_during_run: true` | 有東西寫進了主 checkout | 立刻檢查 `git status`。可能是使用者自己在改，也可能是 guard 失效，查明前不要繼續 |
| 修正輪很慢、很貴 | 續寫的對話累積了大量 tokens | `fix --fresh` 開新對話（超過門檻時會自動開） |
| 同樣的錯一直出現 | 規則或 spec 不夠明確 | 寫進 spec 的「先前的教訓」和知識庫；修正指示要指出檔案、行號與正確寫法 |

## git 與 worktree

| 現象 | 原因 | 做法 |
| :-- | :-- | :-- |
| worktree 放在 `%TEMP%` 時測試顯示「總計 0」 | Smart App Control 擋下暫存資料夾裡的測試 DLL，0 個測試看起來像通過 | 預設 worktree 在 `<repo>.rgs/`；不要把 `worktree_root` 設到 Temp。`doctor.py` 會警告 |
| `land` exit 8（rebase 衝突） | 遠端 main 在任務期間有人改到同一處 | commit 仍在 `rgs/<task>` 分支上。回報使用者；必要時把衝突內容寫進新的修正指示 |
| `land` exit 10（push 被拒） | 分支保護、沒有權限，或遠端又前進了 | 重跑 `land`。若是分支保護，改用 /rgs-pr。**不要 force push** |
| 堆疊的 PR 被自動關閉 | base PR 合併時刪除了分支 | 合併前 `gh pr edit <N> --base main`；已關閉就 rebase 後重開 |
| 移除 worktree 時出現 `Filename too long` | Windows 路徑長度限制 | `git config core.longpaths true`；手動刪除時用 `\\?\` 前綴 |
| 主 checkout 不是乾淨的，`land` 後沒有同步 | 使用者有自己的改動，或不在 base 分支上 | 正常現象，告訴使用者手動 `git pull --ff-only` |
| `git worktree prune` 被權限系統擋下 | 自動模式分類器把它當成破壞性操作 | 用 `rgs.py cleanup`（`git worktree remove`），不需要 prune |

## Windows 與 shell

| 現象 | 做法 |
| :-- | :-- |
| 中文亂碼、`UnicodeDecodeError: 'cp950'` | 讀寫檔案一律指定 `encoding='utf-8'`；腳本已 reconfigure stdout。`python -I` 會忽略 `PYTHONIOENCODING` |
| Git Bash 把 `/usage` 變成 `C:/Program Files/Git/usage` | 設 `MSYS_NO_PATHCONV=1`（腳本已設定） |
| 用 Bash heredoc 寫的檔案反斜線少一半 | 含反斜線的內容用 Write 工具寫檔 |
| PowerShell 中 native 指令的 stderr 變成 NativeCommandError | 用 Bash 執行腳本，或不要重新導向 stderr |
| 指令太長被截斷 | 內容放進檔案，傳路徑（腳本已這樣做） |
| profile 指令在 Windows 上找不到 `./gradlew` | `shell` 設 `bash`（Git Bash），或指令改成 `gradlew.bat …` 並把 `shell` 設成 `cmd` |

## Claude Code 權限

| 現象 | 做法 |
| :-- | :-- |
| 把程式碼送給 agy 被當成「資料外洩」擋下 | 由使用者把 `doctor.py --init` 列出的規則加進 `.claude/settings.json` 的 `permissions.allow`（Claude 不能修改自己的設定） |
| `gh pr merge` 被擋 | 設計如此：/rgs-pr 由使用者手動合併 |
| `land` 的 push 被擋 | 請使用者允許，或由使用者自己執行 `rgs.py land` |
| Claude 用量達上限、session 中斷 | 用量恢復後執行 `/rgs-main status` 或 `/rgs-pr status`，從 `.rgs/state.json` 的步驟接著做 |
