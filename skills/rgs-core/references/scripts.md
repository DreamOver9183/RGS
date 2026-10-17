# 腳本參考

一律在專案目錄（主 checkout 或任務 worktree 內皆可）執行 `python -I <core>/scripts/<name>.py …`。每個指令都在 stdout 印出一個 JSON 摘要；先看 exit code，再看摘要。

## Exit code

| code | 意義 | 該怎麼做 |
| --: | :-- | :-- |
| 0 | 成功 | 繼續 |
| 2 | 參數錯誤（argparse），或 agy 參數／模型不合規（`call_agy` 的檢查） | 修正指令；檢查 profile 的模型是否以 `gemini-` 開頭 |
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
| `ship --task ID --message-file F [--title T --body-file B]` | /rgs-pr：commit、push 分支、開 PR（已有 PR 時只 push，不需要 `--title`／`--body-file`） | `--allow`、`--draft`、`--no-pr` |
| `retarget --task ID` | /rgs-pr：父任務的 PR 合併後，把堆疊的任務與它的 PR 改到 base 分支；squash／rebase 合併時先 rebase 再 `--force-with-lease` 推送 | `--force`（不檢查父 PR 是否已合併） |
| `cleanup --task ID` | 移除 worktree 與 guard | `--delete-branch` |
| `status [--task ID]` | 列出任務狀態，供中斷後續跑 | |

`implement` 與 `fix` 的摘要欄位：

- `agy.kind`：`ok`、`timeout`、`error`、`quota`、`empty`
- `agy.conversation_id`、`agy.usage`
- `response_file`：Gemini 的回覆全文（看它說做不到什麼）
- `guard_denials`：被 guard 擋下的操作（Gemini 想做但被禁止的事）
- `scope`：`changed`、`outside_allowed`、`formatting`
- `main_checkout_changed_during_run`：主 checkout 在執行期間被改動（應為 false）

`implement` 與 `fix` 每次執行前，會把輸入檔（`spec.md`、`implementer-rules.md`，`fix` 另有 `fix-<k>.md`，開新對話時還有 `before-fix-<k>.diff`）從 `.rgs/runs/<task>/` 複製到 worktree 內的 `.rgs-task/`（用 `.git/info/exclude` 排除），並重寫 guard 的設定。prompt、規則與 agy 參數只出現 worktree 內的路徑（不再 `--add-dir` run dir），guard 的讀取範圍也只有這個 worktree，實作者不會因為路徑而去讀主 checkout。`check` 的範圍檢查略過 `.rgs-task/`，`land`／`ship` 也不會把它 commit 進去；worktree 移除時它會一起刪掉。run dir 仍保留所有輸入檔、agy 輸出（`<label>.prompt.md`、`.json`、`.err`、`.response.md`）與這一輪的 `<label>.guard.log`（`<label>` 是 `implement` 或 `fix-<k>`）。要改規格就改 `.rgs/runs/<task>/spec.md`，下一次 `implement`／`fix` 會複製過去。

## review.py

```
review.py --pr N [--task ID] [--note FILE] [--ledger docs/rgs/reviews/PR-N.md] [--post]
review.py --task ID [--note FILE]                  # 尚未 commit 的任務變更（/rgs-main --gate）
review.py --diff-base REF [--head REF]             # 任意本地範圍
```

摘要：`verdict`（腳本依 findings 重算：有 blocker/major 就是 `CHANGES_REQUESTED`）、`model_verdict`、`counts`、`report`（Markdown）、`ledger`、`posted`／`comment_url`（`--post` 成功時）或 `post_error`（留言失敗；審查結果仍有效，exit 仍是 0）。exit 0 只代表審查有產出，**通過與否看 `verdict`**。

審查在 detached worktree `<repo>.rgs/review-<label>` 進行。輸入檔（`pr.diff`、`spec.md`、`note.md`、`reviewer-rules.md`、`schema.json`）放在 worktree 內的 `.rgs-review/`（用 `.git/info/exclude` 排除），prompt 與 agy 參數只出現 worktree 內的路徑，guard 的讀取範圍也只有這個 worktree，審查者不會因為路徑而去讀主 checkout。審查結束後 worktree 會被移除；輸入檔副本、agy 輸出（`agy.prompt.md`、`agy.json`、`agy.err`）、`guard.log`、`review.json`、`review.md` 都留在 `.rgs/runs/<task>/review-<n>/`。

## facet_review.py

完成**一次送審**（一份計畫、一個角度、一輪），把結果整理成一行 JSON 印在 stdout，並在 run 目錄留下完整紀錄。只做一次送審，重試與多輪迴圈由 SKILL.md 負責。

### 用法

```text
python -I <facet>/scripts/facet_review.py --plan-file <計畫檔> --lens logic|gaps|verifiability --round <N> --model <M>
                                         [--timeout 300] [--session <ID>] [--run-dir <資料夾>] [--repo <專案資料夾>] [--prior-stdin]
```

### 參數表

| 參數 | 說明 |
| :-- | :-- |
| `--plan-file` | 必填。計畫檔；只送出 `<!-- facet:appendix -->` 之前的內容 |
| `--lens` | 必填。`prompt.LENSES` 之一（`logic`、`gaps`、`verifiability`） |
| `--round` | 必填。從 1 起算的整數 |
| `--model` | 必填。agy 模型 ID（必須是 `gemini-` 開頭） |
| `--timeout` | 秒，預設 300。正整數 |
| `--session` | 預設取環境變數 `CLAUDE_SESSION_ID`，沒有時用 `'manual'`。只允許英數、`-`、`_`、`.` |
| `--run-dir` | 預設 `os.path.join(tempfile.gettempdir(), 'rgs-facet', <session>)` |
| `--repo` | 預設目前工作目錄。用來做呼叫前後的快照比對 |
| `--prior-stdin` | 第二輪起必須加：從 stdin 讀前輪處置 JSON |

### status 與 exit code

| status | exit | 說明 |
| :-- | --: | :-- |
| `ok` | 0 | 拿到合法的 verdict |
| `timeout` | 2 | agy 執行逾時 |
| `agy_error` | 3 | agy 回報錯誤或 quota 用盡；或找不到 agy |
| `empty_output` | 4 | agy 沒有回傳 structured_output |
| `parse_error` | 5 | structured_output 是字串且解析 JSON 失敗 |
| `schema_error` | 5 | verdict schema 驗證失敗 |
| `workspace_modified` | 6 | 呼叫期間 repo 或工作區有變動（優先於呼叫 agy 之後的所有其他 status） |
| `secret_suspected` | 7 | 計畫內容疑含機密；不呼叫 agy |
| `forbidden_flag` | 8 | agy 參數或模型不合規；不呼叫 agy |
| `plan_too_long` | 9 | 計畫內容組出之 prompt 超過長度限制；不呼叫 agy |
| `usage_error` | 10 | 命令列參數錯誤、檔案不存在或前輪資料格式錯誤；不呼叫 agy |

### call 目錄的檔案

每次呼叫的紀錄放在 `<run-dir>/r<N>-<lens>/`：

- `prompt.md`：送給審查者的 prompt 全文
- `prior.json`：前輪處置資料（第二輪起由 `--prior-stdin` 讀入）
- `schema.json`：該輪審查使用的 JSON schema（第二輪起將 `resolved` 設為必填）
- `agy.prompt.md`：實際傳給 agy 的 prompt
- `agy.json`：agy 的 stdout 輸出
- `agy.err`：agy 的 stderr 輸出
- `agy.log`：agy 的 log 檔副本（解析出的模型 label）
- `guard.log`：sealed 工作區中的 guard 決策紀錄
- `meta.json`：本次呼叫的完整中繼資料（狀態、exit code、模型、耗時、快照變更等）

## 其他

| 腳本 | 用途 |
| :-- | :-- |
| `doctor.py [--quick] [--flow main\|pr\|facet] [--model <M>] [--init] [--json]` | 環境檢查（含 git 身分：沒有 user.name／user.email 時 `land`／`ship` 無法 commit）；`--init` 產生 `.rgs/profile.json` 草稿並列出可加的權限規則；`--flow facet --model <M>` 不需要 git repo，檢查 Python、agy、模型 ID 與額度，給 rgs-facet 用 |
| `scope_check.py --task ID` | 單獨跑範圍檢查 |
| `secret_scan.py [--cwd DIR] [--files …]` | 掃描 staged diff 或指定檔案 |
| `batch.py …` | 大量資料批次，見 `delegation.md` |
| `digest.py …` | 長文件／log 摘要，見 `delegation.md` |

`doctor.py --init` 列出的權限規則是指令前綴，例如 `Bash(python -I C:/tools/rgs-core/scripts/rgs.py:*)`。`<core>` 路徑含空白時（例如 `D:/Claude Code/…`），規則裡的路徑會加上雙引號：`Bash(python -I "D:/Claude Code/…/scripts/rgs.py":*)`。這時執行腳本也要寫成 `python -I "<core>/scripts/<name>.py" …`（雙引號、正斜線），和規則一字不差，否則規則對不上，每次仍會詢問權限。

## 測試

```
python -m unittest discover -s <core>/tests
```

測試用 `tests/fake_agy.py` 代替 agy（環境變數 `RGS_AGY`），不會消耗 Gemini 額度；用 `tests/fake_gh.py` 代替 GitHub CLI（環境變數 `RGS_GH`），以本機 bare remote 模擬 PR、留言與改 base。
