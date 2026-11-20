# Antigravity CLI（agy）已驗證行為

驗證版本：**agy 1.4.0**（Windows 11，2026-10-17）；1.4.7、1.5.2、1.5.9、1.5.12／1.5.13 的補充在文末，**1.5.9 改了檔案工具的名稱**（見「agy 1.5.9 補充」；1.5.13 沿用）。升級後先跑 `doctor.py`，有疑問時在拋棄式 repo 重做下面的實驗。腳本已經處理這些行為，這份文件是為了讓你看懂摘要與除錯。

## 呼叫方式（rgs_common.call_agy）

```
agy -p "<prompt>" --model <m> --output-format json --disable-slash-commands --print-timeout <N>s
    [--mode accept-edits] [--json-schema <file>] [--conversation <id>] [--add-dir <dir>]
    [--log-file <file>]
```

- stdin 一律接 DEVNULL；執行在目標 worktree（cwd 就是 agy 的工作區）。
- prompt 傳入方式：rgs 實作與 PR 審查因有 worktree，將檔案放在工作區內讀取；rgs-facet 審查者無檔案讀取權限，把整份內容放在 `-p` 參數最快最便宜（約 9 秒、1.7 萬 tokens；stdin 或讓它讀檔約 60 秒、6–8 萬 tokens）。Windows 命令列上限約 32K 字元（UTF-16），因此 prompt 超過 30,000 字元時由腳本擋下（`plan_too_long`），不送出。
- prompt 與參數不要出現主 checkout 的路徑：審查者曾從主 checkout 下的 run dir 路徑推測專案根目錄，跑去讀主 checkout（被 guard 擋下）。所以 rgs 不用 `--add-dir` 指向 run dir。
- 可用模型以 `agy models` 為準（沒有 JSON 輸出，每行是「ID〔Tab〕顯示名稱」）。2026-11-21（agy 1.5.13）有：`gemini-4-neon-{low,medium,high,xhigh}`、`gemini-4-hydrogen-{low,medium,high,xhigh}`、`gemini-4-argon-{low,medium,high}`、`gemini-pro-orchestrator-neon`、`gemini-pro-orchestrator-g1-pro`、`gemini-3.8-flash-{low,medium,high}`、`claude-opus-5-5-{low,medium,high}`、`claude-sonnet-5-5-{low,medium,high}`、`gpt-oss-120b-medium`。**GPT-OSS 只有 medium**：`--model gpt-oss-120b --effort high` 會以 `gpt-oss-120b has no "high" effort (available: medium)` 結束。額度分三池：`gemini-4-argon-*` 自己一池；`gemini-4-neon-*`、`gemini-4-hydrogen-*` 和 `gemini-3.8-flash-*` 共用「Gemini Models」；Claude 與 GPT 共用一池。rgs 預設實作與審查用 `gemini-3.8-flash-high`（實戰驗證過），批次用 `gemini-3.8-flash-low`；rgs-facet 依序用 `gemini-4-neon-high`、`gemini-4-hydrogen-xhigh`、`gemini-4-argon-high`、`gemini-3.8-flash-high`、`gpt-oss-120b-medium`、`claude-opus-5-5-high`（D-22、D-23、D-24）。
- 參數依角色檢查：在啟動 agy 之前由 `check_agy_args` 檢查。通用的禁止清單（`--dangerously-skip-permissions`、`--yolo`、`-i`、`--prompt-interactive`、`--remote-control`、`--sandbox`）對所有角色一律禁止；審查者（`reviewer`）禁止清單（`--mode`、`--add-dir`、`--conversation`、`-c`、`--continue`）；實作者（`implementer`）的 `--mode` 僅允許 `accept-edits`。不合規一律丟 `RgsError(code=2)`。
- `--model` 必傳，且必須是完整的模型 ID（大小寫須完全相符）：實作角色只能是 `gemini-` 開頭；審查角色（含 rgs-facet、批次、摘要）可以是 `gemini-`、`gpt-oss-`、`claude-` 開頭（D-22）。否則丟 `RgsError(code=2)`。使用者的 agy 預設模型可能是 Claude，所以不能省略 `--model`。
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
- hook 的輸入：`{"toolCall": {"name", "args"}, "stepIdx", "conversationId", "workspacePaths", "transcriptPath", "artifactDirectoryPath", "modelName"}`；1.5.9 另有 `hookEventName`、`cwd`、`lastUserInput`。guard 只讀 `toolCall`。
- 除了 implementer 與 reviewer，還有 `sealed` 角色，只放行 `finish` 與 `wait`，給把全部內容放在 prompt 裡、審查者不需要任何工具的呼叫（rgs-facet）使用。

## 工具名稱與參數（guard 依此判斷）

檔案工具在 1.5.9 改了名稱與參數，guard 兩組都認得；不在下表的工具一律拒絕。

| 用途 | 1.4.0 | 1.5.9 |
| :-- | :-- | :-- |
| 讀檔 | `view_file`（`AbsolutePath`） | `read_file`（`Path`，另有 `StartLine`、`EndLine`、`ByteOffset`）；傳資料夾會回 `path is a directory` |
| 編輯 | `replace_file_content`（`TargetFile`，另有 `TargetContent`、`ReplacementContent`、`StartLine`、`EndLine`） | `edit_file`（`Path`、`Target`、`Replacement`）；一次只改一段連續內容 |
| 建立／覆寫 | `write_to_file`（`TargetFile`、`CodeContent`、`Overwrite`） | `write_file`（`Path`、`Content`、`Overwrite`、`Append`） |
| shell（Windows 上是 PowerShell） | `run_command`（`Cwd`、`CommandLine`） | `run_command`（`CommandLine`、`WaitMsBeforeAsync`、`IsDaemon`、`toolSummary`；沒有 `Cwd`） |
| 建立子代理 | `invoke_subagent` | 同左 |
| 子代理回報主代理（**必須放行**，否則主代理等不到結果） | `send_message` | 同左 |
| 主代理查看或管理子代理 | `manage_subagents` | 同左 |
| 流程控制 | `finish`、`wait` | 同左 |

**沒有獨立的列目錄／搜尋工具**（1.4.0 與 1.5.9 都是）：模型用 `run_command` 執行 `Get-ChildItem`、`Select-String`。所以 guard 放行一組唯讀指令（每段 pipeline 都必須以唯讀動詞開頭，禁止 `; & > < { } $( @( ..\ --output --pre`，絕對路徑必須在允許的資料夾內，指令中不得出現受保護檔名）。預設的「研究型」子代理本身就是唯讀的。

## 對話續寫

- `--conversation <id>` 可續寫（修正輪），`--model` 可在續寫時更換。
- **usage 會累積**：續寫兩輪的小任務就累計約 17 萬 input tokens；android_class 的修正輪曾跑 74–80 分鐘、累積到約 100 萬 tokens。超過 `fresh_after_input_tokens`（預設 40 萬）時 `rgs.py fix` 會自動改開新對話，並附上 spec、目前 diff 與修正指示。

## 其他

- 費用：最小的呼叫也有約 1.2 萬 input tokens（agent 系統提示）。
- 時間：小任務 15–30 秒；一個里程碑 5–20 分鐘；`invoke_subagent` 平行審查 10–15 分鐘；rgs-facet 一次計畫審查：`gemini-4-neon-high` 約 1.5–2 分鐘、`gemini-4-hydrogen-xhigh` 約 2 分鐘（2026-11-21）、`gemini-4-hydrogen-high` 約 40 秒（2026-11-15）；`gemini-4-argon-high` 原本約 43–155 秒，2026-10-25 起約 5–8 分鐘（見下一節）。
- 大量資料：多個 agy process 平行比單一對話內的 `invoke_subagent` 快（RimTaiName 實測 4 process 152 秒，對照 4 子代理 202 秒、循序 649 秒），所以 `batch.py` 用 process 平行。
- 召回：一次餵約 11 萬 tokens 的 log，三個錯誤只找到兩個，卻宣稱全部找到；`digest.py` 因此先 grep、再切塊，並核對每個引用。
- Git Bash 會把 `/` 開頭的參數改成路徑：手動跑 `agy -p "/usage"` 要設 `MSYS_NO_PATHCONV=1`（腳本已設定）。
- 額度：`MSYS_NO_PATHCONV=1 agy -p "/usage"` 會印出額度表（`doctor.py` 會跑）。

## agy 1.4.7 補充（2026-10-25 實測）

- `--json-schema` 會讓 agy 加入 `finish` 工具，`structured_output` 只來自 `finish` 的參數。prompt 寫「不要使用任何工具」「只輸出 JSON」時，模型有時照字面用文字輸出；agy 會再送一則「You did not call any tools … call the finish tool」，模型把整份結果重新產生一次（實測多 45–60 秒）。所以 prompt 要明說用 `finish` 交出結果。
- 串流閒置：伺服器 5 分鐘沒有送資料時，agy 會中斷並自動重試（log：`Run: attempt 1 failed (stream reading error: stream idle timeout (5m0s) …), retrying in 4s`）。即使重試成功，仍回 `status: ERROR`、`error: The stream was interrupted…`，但 `structured_output` 有值；rgs 判為 `error`。
- `--effort`（`low|medium|high|xhigh|max`）和模型 ID 的強度後綴是同一個設定：`--model gemini-4-argon-high --effort medium` 會以 `invalid model selection … conflicts with --effort=medium` 結束；`--effort high` 和不加的結果相同。
- 思考量會在沒有版本變更的情況下改變：同一份 prompt，Gemini 4 Argon High 在 2026-10-23～24 輸出 2,758～12,989 token（55～145 秒）；2026-10-25 起變成 25,000～47,000 token（314～485 秒）。產出速度（每秒 80～97 token）與 input tokens 都沒變。判斷是不是「想太久」要看 output_tokens，不要只看耗時；同樣設定重跑通常會再逾時。
- 逾時的時候，`agy.json` 的 usage 全是 0。實際用量要看 agy 的對話紀錄 `~/.gemini/antigravity-cli/brain/<conversation_id>/.system_generated/logs/transcript.jsonl`：`PLANNER_RESPONSE` 的 `output_tokens`，有沒有 `tool_calls`（`finish`）。thinking 文字會被截斷。

## agy 1.5.2 補充（2026-11-07 實測）

- GPT-OSS 只有 `gpt-oss-120b-medium`。`--model gpt-oss-120b-medium --effort high` 回 `conflicts with --effort=high`；`--model gpt-oss-120b --effort high` 回 `gpt-oss-120b has no "high" effort (available: medium)`。兩者都在送出前就結束（`duration_seconds` 0）。
- 額度用完：`status: ERROR`，`error` 是 `Individual quota reached … Resets in <時間>`，stderr 另有 `AGY_ERROR: {"status":"RESOURCE_EXHAUSTED","error_code":429,…}`，約 3–4 秒結束；rgs 判為 `quota`。當天 `gpt-oss-120b-medium` 與 `claude-opus-5-5-high` 同時額度用完、重置時間相同（約 67 小時），兩者可能共用同一個額度；Gemini 的額度不受影響。
- 不存在的模型 ID：約 3 秒以 `invalid model selection … is not recognized as a known model` 結束，rgs 判為 `error`。這時 `--log-file` 的 label 是另一個模型（當天是 `Gemini 3.8 Flash (High)`），失敗那次的 `reported_model` 不可信。
- rgs-facet 替補實測：第一個模型（不存在的 ID）失敗後，`facet_review.py` 換到 `gemini-3.8-flash-high`，22 秒取得有效 verdict，快照無變動、guard 無拒絕。`gpt-oss-120b-medium`、`claude-opus-5-5-high` 能否經由 `finish` 交出結構化結果，因額度用完尚未實測。
- 1.5.2 新增的旗標：`--agent`、`--remote-agent`、`--project`、`--new-project`、`--settings`、`--input-format`。rgs 不使用，也還沒加進禁止清單。

## agy 1.5.9 補充（2026-11-15 實測）

- **檔案工具改名**（不分模型，`gemini-3.8-flash-high` 與 `gemini-4-hydrogen-high` 都一樣）：`read_file`、`write_file`、`edit_file`，路徑參數都是 `Path`；`run_command` 不再傳 `Cwd`。對照表見「工具名稱與參數」。changelog 沒有記載這項變更，1.5.2 當時只測了不需要檔案工具的 rgs-facet，所以不確定是哪一版改的。舊版 guard 不認得新名稱，全部拒絕（fail-closed）：實作者寫不進任何檔案、審查者讀不到檔案，agy 仍回 `SUCCESS`，看起來像「Gemini 宣稱完成但 `scope.changed` 是空的」。guard 現在新舊名稱都認得。
- 新增的工具：`run_workflow`（執行 Python workflow 腳本，等於任意程式碼）、`swarm`、`schedule`、`search_web`、`define_subagent`、`manage_task`、`ask_question`。guard 都不認得，一律拒絕；實測審查者呼叫 `run_workflow` 被擋下。`manage_task` 用來查看或結束移到背景的指令（`run_command` 超過 `WaitMsBeforeAsync`，預設 5 秒，會移到背景）：唯讀指令很慢時，模型可能因此拿不到輸出，這種情況會出現在 `guard_denials`，還沒遇過。
- 無頭模式（`-p`）的預設 Agent Mode 從 1.5.7 起是 Auto。PreToolUse hook 照樣執行，guard 的判定不受影響（審查者不傳 `--mode`，實測寫檔與非唯讀指令都被擋下）。
- Gemini 4 Hydrogen：`gemini-4-hydrogen-{low,medium,high,xhigh}`，`--log-file` 的 label 是 `Gemini 4 Hydrogen (High)` 這類字串。額度算在「Gemini Models」（和 3.8 Flash 同一池），不是 Argon 那一池：幾次 Hydrogen 呼叫後，Gemini Models 的週額度從 90% 降到 87%，Argon 維持 88%。
- rgs-facet 用 Hydrogen 的實測（同一份約 1,500 字元的計畫）：`gemini-4-hydrogen-high` 40–55 秒、輸出約 7,000 token，回 3–4 條 finding；`gemini-4-hydrogen-xhigh` 118 秒、輸出約 21,000 token，回 5 條。都經由 `finish` 交出有效 verdict，sealed guard 無拒絕、快照無變動。對照 `gemini-4-argon-high` 的 5–8 分鐘。
- Hydrogen 習慣在 `evidence` 把多段引用接在一起（「步驟 1：「…」；步驟 3：「…」」，或用 `...` 隔開），逐字比對全部失敗（8 條 finding 的 `evidence_found` 都是 `false`）。審查 prompt 改成要求只放一段連續的原文後，8 條都是 `true`。
- 實作者實測（`call_agy`、`--mode accept-edits`、implementer guard）：`gemini-4-hydrogen-high` 與 `gemini-3.8-flash-high` 都用 `read_file` 加 `edit_file` 改了清單內的檔案，清單外的 `write_file` 與 `python -c` 被擋下，各約 25 秒。另在拋棄式 repo 跑過 `rgs.py prepare` → `implement --model gemini-4-hydrogen-high` → `check`：29 秒完成，guard 無拒絕，只改了清單內的兩個檔案，寫出的測試通過。`rgs.py land`／`ship`、修正輪（`fix`、`--conversation` 續寫）、`review.py` 的子代理平行審查、batch 與 digest 還沒在 1.5.9 重跑。
- 模型會去讀 `~/.gemini/antigravity-cli/builtin/skills/<名稱>/SKILL.md`（agy 內建 skill 的說明）；在工作區之外，guard 會擋下，屬於正常現象。

## agy 1.5.12／1.5.13 補充（2026-11-21 實測）

- agy 會自己在背景升版：同一天的實測開始時是 1.5.12，跑到一半變成 1.5.13（rgs-facet 的 `meta.json` 記下 `agy_version: 1.5.13`）。第一次工具實測無法確定跑在哪一版，發現升版後在 1.5.13 重跑，結果相同；以下以 1.5.13 為準。
- Gemini 4 Neon：1.5.12 起提供 `gemini-4-neon-{low,medium,high,xhigh}`（changelog 寫的是 `GEMINI_API_KEY` 登入；1.5.13 補上 ADC 與企業閘道）。`--log-file` 的 label 是 `Gemini 4 Neon (High)` 這類字串。另有 `gemini-pro-orchestrator-neon`，rgs 不使用。`/usage` 仍只有三池（Gemini Models、Claude and GPT models、Gemini 4 Argon），一批 Neon 呼叫後 Gemini Models 的週額度從 96% 降到 92%，所以 Neon 應算在「Gemini Models」，和 Hydrogen、3.8 Flash 同一池（同一批還有一次 Hydrogen XHigh，沒有單獨量測）。
- **檔案工具名稱沒有再變**：`gemini-4-neon-high` 當審查者用 `read_file` 讀檔，`write_file` 被擋；當實作者用 `read_file` 加 `edit_file` 改了清單內的檔案，清單外的 `write_file`、`edit_file` 被擋；各約 20–40 秒。`run_command` 照舊用於列目錄與搜尋。
- 1.5.13 的模型會把相關的 shell 指令串成一條：要「列出所有檔案、算行數、找出含某字的檔案」時，Neon 先送出一段多行 PowerShell（`$files = Get-ChildItem …` 加 `foreach`），被 guard 擋下（含 `$`、`{`），接著改用 `Get-ChildItem -Recurse -File`、`rg -n`、`Select-String` 與 `read_file`，57 秒完成且答案正確。這類拒絕會出現在 `guard_denials`，屬於正常現象；guard 不放寬。
- rgs-facet 實測（和 1.5.9 同一份約 1,500 字元的計畫）：`gemini-4-neon-high` 的 logic 131 秒、輸出 16,376 token，gaps 106 秒、輸出 13,436 token，各回 4、5 條 finding；`gemini-4-hydrogen-xhigh` 的 verifiability 105 秒、輸出 20,660 token，回 6 條。三次都經由 `finish` 交出有效 verdict，15 條 finding 的 `evidence_found` 都是 `true`，sealed guard 只有 `finish`、快照無變動。Neon 兩個角度都抓到「`calc.py` 與 `__main__.py` 放在同一層時 `python -m calc` 不會執行 `__main__.py`」這個真問題（1.5.9 的 Hydrogen High 也抓到）。
- 1.5.13 changelog：`--output-format json` 在 CLI 重試模型請求後成功時，`status` 改回 `SUCCESS`（以前是 `ERROR` 加上失敗那次的錯誤，見「agy 1.4.7 補充」的串流閒置）。沒有實測；rgs 的判定照舊。
- 1.5.13 changelog：模型不再自行啟動 swarm（`/swarm` 仍可用）。guard 本來就拒絕 `swarm`。
- 還沒在 1.5.12／1.5.13 重跑：`rgs.py` 的完整流程（prepare → implement → fix → land／ship）、合併閘門審查、batch、digest；`gemini-4-neon-*` 當實作者只跑過上面的最小呼叫。
