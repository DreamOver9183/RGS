# 腳本參考

一律在專案目錄（主 checkout 或任務 worktree 內皆可）執行 `python -I <core>/scripts/<name>.py …`。每個指令都在 stdout 印出一個 JSON 摘要；先看 exit code，再看摘要。

## Exit code

| code | 意義 | 該怎麼做 |
| --: | :-- | :-- |
| 0 | 成功 | 繼續 |
| 2 | 參數錯誤（argparse） | 修正指令 |
| 3 | 所有模型都額度用完 | ⚠️ 回報使用者，問要換模型或稍後再試 |
| 4 | 有檔案超出允許清單，或格式問題 | 看 `scope.outside_allowed`／`formatting`；寫修正指示，或用 `fix --allow` 擴充清單（要有理由） |
| 5 | agy 沒有可用結果（timeout、錯誤、空回應、沒有改任何檔案） | 看 `agy.kind`、`agy.detail` 與 `.rgs/runs/<task>/*.err`；可重跑一次，再失敗就回報 |
| 6 | 修正輪數超過上限 | 停下來問使用者 |
| 7 | 偵測到機密或受保護檔案被 stage | 不要 commit；查明來源並移除 |
| 8 | rebase 衝突 | commit 仍保留在任務分支；回報使用者 |
| 9 | 建置或測試失敗 | 看 `commands[].log`，把錯誤原文寫進修正指示 |
| 10 | push 或 `gh pr create` 被拒 | 看 `stderr`；不要 force push |

## rgs.py

| 子指令 | 用途 | 重要參數 |
| :-- | :-- | :-- |
| `prepare --task ID --spec FILE` | 開 worktree 與分支、安裝 guard、記錄 state | `--flow main\|pr`、`--branch`（pr 流程用 `feat/m1-x`）、`--base`、`--stack-on TASK` |
| `implement --task ID` | Gemini 依 spec 實作（背景執行） | `--model`、`--timeout` |
| `diff --task ID` | 把目前所有變更（含新檔）寫成 diff 檔供審查 | |
| `fix --task ID --notes FILE` | Gemini 依修正指示修改 | `--allow PATH`（擴充可改檔案）、`--fresh`（開新對話）、`--force`（超過上限仍執行） |
| `check --task ID` | 範圍檢查 + profile 指令 | `--level quick\|verify\|all`、`--ignore GLOB` |
| `land --task ID --message-file F` | /rgs-main：commit、必要時 rebase 並重跑 quick、fast-forward push 到 base、同步主 checkout、移除 worktree | `--skip-tests` |
| `ship --task ID --message-file F --title T --body-file B` | /rgs-pr：commit、push 分支、開 PR（已有 PR 時只 push） | `--allow`、`--draft`、`--no-pr` |
| `cleanup --task ID` | 移除 worktree 與 guard | `--delete-branch` |
| `status [--task ID]` | 列出任務狀態，供中斷後續跑 | |

`implement` 與 `fix` 的摘要欄位：

- `agy.kind`：`ok`、`timeout`、`error`、`quota`、`empty`
- `agy.conversation_id`、`agy.usage`
- `response_file`：Gemini 的回覆全文（看它說做不到什麼）
- `guard_denials`：被 guard 擋下的操作（Gemini 想做但被禁止的事）
- `scope`：`changed`、`outside_allowed`、`formatting`
- `main_checkout_changed_during_run`：主 checkout 在執行期間被改動（應為 false）

## review.py

```
review.py --pr N [--task ID] [--note FILE] [--ledger docs/rgs/reviews/PR-N.md] [--post]
review.py --task ID [--note FILE]                  # 尚未 commit 的任務變更（/rgs-main --gate）
review.py --diff-base REF [--head REF]             # 任意本地範圍
```

摘要：`verdict`（腳本依 findings 重算：有 blocker/major 就是 `CHANGES_REQUESTED`）、`model_verdict`、`counts`、`report`（Markdown）、`ledger`。exit 0 只代表審查有產出，**通過與否看 `verdict`**。

## 其他

| 腳本 | 用途 |
| :-- | :-- |
| `doctor.py [--quick] [--flow main\|pr] [--init] [--json]` | 環境檢查；`--init` 產生 `.rgs/profile.json` 草稿並列出可加的權限規則 |
| `scope_check.py --task ID` | 單獨跑範圍檢查 |
| `secret_scan.py [--cwd DIR] [--files …]` | 掃描 staged diff 或指定檔案 |
| `batch.py …` | 大量資料批次，見 `delegation.md` |
| `digest.py …` | 長文件／log 摘要，見 `delegation.md` |

## 測試

```
python -m unittest discover -s <core>/tests
```

測試用 `tests/fake_agy.py` 代替 agy（環境變數 `RGS_AGY`），不會消耗 Gemini 額度。
