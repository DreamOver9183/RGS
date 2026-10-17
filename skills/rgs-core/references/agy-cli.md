# Antigravity CLI（agy）已驗證行為

驗證版本：**agy 1.4.0**（Windows 11，2026-10-17）。升級後先跑 `doctor.py`，有疑問時在拋棄式 repo 重做下面的實驗。腳本已經處理這些行為，這份文件是為了讓你看懂摘要與除錯。

## 呼叫方式（rgs_common.call_agy）

```
agy -p "<prompt>" --model <m> --output-format json --disable-slash-commands --print-timeout <N>s
    [--mode accept-edits] [--json-schema <file>] [--conversation <id>] [--add-dir <dir>]
    [--log-file <file>]
```

- stdin 一律接 DEVNULL；執行在目標 worktree（cwd 就是 agy 的工作區）。
- prompt 傳入方式：rgs 實作與 PR 審查因有 worktree，將檔案放在工作區內讀取；rgs-facet 審查者無檔案讀取權限，把整份內容放在 `-p` 參數最快最便宜（約 9 秒、1.7 萬 tokens；stdin 或讓它讀檔約 60 秒、6–8 萬 tokens）。Windows 命令列上限約 32K 字元（UTF-16），因此 prompt 超過 30,000 字元時由腳本擋下（`plan_too_long`），不送出。
- prompt 與參數不要出現主 checkout 的路徑：審查者曾從主 checkout 下的 run dir 路徑推測專案根目錄，跑去讀主 checkout（被 guard 擋下）。所以 rgs 不用 `--add-dir` 指向 run dir。
- 可用模型以 `agy models` 為準（沒有 JSON 輸出，每行是「ID〔Tab〕顯示名稱」）。2026-10-17 有：`gemini-4-argon-{low,medium,high}`、`gemini-3.8-flash-{low,medium,high}`、`claude-opus-5-5-*`、`claude-sonnet-5-5-*`、`gpt-oss-120b-medium`。`gemini-4-argon-*` 的額度和 3.8 分開；rgs 預設實作與審查用 `gemini-3.8-flash-high`（實戰驗證過），批次用 `gemini-3.8-flash-low`；rgs-facet 預設用 `gemini-4-argon-high`。
- 參數依角色檢查：在啟動 agy 之前由 `check_agy_args` 檢查。通用的禁止清單（`--dangerously-skip-permissions`、`--yolo`、`-i`、`--prompt-interactive`、`--remote-control`、`--sandbox`）對所有角色一律禁止；審查者（`reviewer`）禁止清單（`--mode`、`--add-dir`、`--conversation`、`-c`、`--continue`）；實作者（`implementer`）的 `--mode` 僅允許 `accept-edits`。不合規一律丟 `RgsError(code=2)`。
- `--model` 必須以 `gemini-` 開頭（大小寫須完全相符），否則丟 `RgsError(code=2)`。因為使用者的 agy 預設模型可能是 Claude，rgs 只用 Gemini 模型，必須明確指定。
- 逾時時終止整個程序樹：超過 `timeout_s + grace_s`（`grace_s` 預設 180 秒）未結束時，由 `kill_tree` 終止程序樹。Windows 使用 `taskkill /PID <pid> /T /F`，POSIX 使用 `os.killpg` 發送 `SIGTERM`（等待 10 秒）與 `SIGKILL`，確保父程序及其啟動的所有子程序全數終止。
- 每次呼叫一律帶 `--log-file <file>`。log 先寫在系統暫存目錄，agy 結束後才複製到 `save_as + '.log'`；agy 的參數不能出現主 checkout 的路徑。log 中包含 agy 用戶端解析後送出的模型名稱（`label="…"`，例如 `Gemini 4 Argon (High)`），這是用戶端解析的模型名稱，不是伺服器回報的。`AgyResult.reported_model` 會取出 log 中最後一個 label（無 label 或讀不到時為 `None`）。

## 輸出 JSON

`conversation_id`、`status`（`SUCCESS`／`ERROR`）、`response`、`duration_seconds`、`num_turns`、`usage{input_tokens, output_tokens, thinking_tokens, cache_read_tokens, total_tokens}`；有 `--json-schema` 時另有 `json_schema` 與 `structured_output`；`ERROR` 時有 `error`。

## 會騙人的情況（腳本都判定為失敗）

| 情況 | agy 的表現 | rgs 的判定 |
| :-- | :-- | :-- |
| `--print-timeout` 到期 | exit 0、`SUCCESS`、`response` 空字串；stderr：`[agy] print timeout after Ns with turn in progress; returning partial output` | `timeout` |
| 子代理還沒回報主代理就結束 | `SUCCESS`，response 是「我在等子代理回報」，沒有 `structured_output` 欄位 | `empty` |
| 工具被 hook 拒絕 | 仍然 `SUCCESS`；模型通常會照實說被擋，但不保證 | 看 `guard_denials` 與 `scope` |
| 串流中斷 | `ERROR`，但 response 可能含「PASS」 | `error` |
| 額度用完 | `ERROR`，訊息含 `Individual quota reached` / `RESOURCE_EXHAUSTED` | `quota`，換 fallback 模型 |

## 權限與唯讀

- 使用者的全域設定 `~/.gemini/antigravity-cli/settings.json` 是 `"toolPermission": "always-proceed"`：agy 會自動執行所有工具。
- **`--mode plan` 擋不住寫入**（1.4.0 實測：plan 模式照樣建立了檔案）。`--sandbox` 在 1.2.17 也擋不住。
- **唯一可靠的限制是 PreToolUse hook**：工作區的 `.agents/hooks.json` 會被載入（log：`loaded 1 named hooks from 1 hooks.json file(s)`），回 `{"decision":"deny"}` 就會擋下，**子代理的工具呼叫也會經過同一個 hook**。hook 以 `cmd /c` 執行，cwd 是 `.agents`；hook 程式當掉也會擋下（fail-closed）。
- hook 的輸入：`{"toolCall": {"name", "args"}, "stepIdx", "conversationId", "workspacePaths", "transcriptPath", "artifactDirectoryPath", "modelName"}`。
- 除了 implementer 與 reviewer，還有 `sealed` 角色，只放行 `finish` 與 `wait`，給把全部內容放在 prompt 裡、審查者不需要任何工具的呼叫（rgs-facet）使用。

## 1.4.0 的工具名稱與參數（guard 依此判斷）

| 工具 | 用途 | 路徑參數 |
| :-- | :-- | :-- |
| `view_file` | 讀檔 | `AbsolutePath` |
| `replace_file_content` | 編輯 | `TargetFile`（另有 `TargetContent`、`ReplacementContent`、`StartLine`、`EndLine`） |
| `write_to_file` | 建立／覆寫 | `TargetFile`（`CodeContent`、`Overwrite`） |
| `run_command` | shell（Windows 上是 PowerShell） | `Cwd`、`CommandLine` |
| `invoke_subagent` | 建立子代理 | — |
| `send_message` | 子代理回報主代理（**必須放行**，否則主代理等不到結果） | — |
| `manage_subagents` | 主代理查看或管理子代理 | — |
| `finish`、`wait` | 流程控制 | — |

**1.4.0 沒有獨立的列目錄／搜尋工具**：模型用 `run_command` 執行 `Get-ChildItem`、`Select-String`。所以 guard 放行一組唯讀指令（每段 pipeline 都必須以唯讀動詞開頭，禁止 `; & > < { } $( @( ..\ --output --pre`，絕對路徑必須在允許的資料夾內，指令中不得出現受保護檔名）。預設的「研究型」子代理本身就是唯讀的。

## 對話續寫

- `--conversation <id>` 可續寫（修正輪），`--model` 可在續寫時更換。
- **usage 會累積**：續寫兩輪的小任務就累計約 17 萬 input tokens；android_class 的修正輪曾跑 74–80 分鐘、累積到約 100 萬 tokens。超過 `fresh_after_input_tokens`（預設 40 萬）時 `rgs.py fix` 會自動改開新對話，並附上 spec、目前 diff 與修正指示。

## 其他

- 費用：最小的呼叫也有約 1.2 萬 input tokens（agent 系統提示）。
- 時間：小任務 15–30 秒；一個里程碑 5–20 分鐘；`invoke_subagent` 平行審查 10–15 分鐘；rgs-facet 一次計畫審查約 43–155 秒。
- 大量資料：多個 agy process 平行比單一對話內的 `invoke_subagent` 快（RimTaiName 實測 4 process 152 秒，對照 4 子代理 202 秒、循序 649 秒），所以 `batch.py` 用 process 平行。
- 召回：一次餵約 11 萬 tokens 的 log，三個錯誤只找到兩個，卻宣稱全部找到；`digest.py` 因此先 grep、再切塊，並核對每個引用。
- Git Bash 會把 `/` 開頭的參數改成路徑：手動跑 `agy -p "/usage"` 要設 `MSYS_NO_PATHCONV=1`（腳本已設定）。
- 額度：`MSYS_NO_PATHCONV=1 agy -p "/usage"` 會印出額度表（`doctor.py` 會跑）。
