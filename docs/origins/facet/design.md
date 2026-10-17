# 設計與計畫：facet skill

> 單一事實來源。每個里程碑合併後由 Claude 更新「狀態總覽」「追溯矩陣」「教訓清單」。

| 項目 | 內容 |
| :-- | :-- |
| 版本 | v2（修訂歷史見文末） |
| 需求 | `docs/rgs/requirements.md` |
| 查證基準 | `docs/handoff.md`；`docs/PLAN.md`；`docs/preflight-results.md`（agy 1.4.0，Windows 11，2026-10-17）；Claude Code 官方文件 skills、hooks、managed-settings |

## 狀態總覽

| 里程碑 | 狀態 | 分支／PR | 測試數 | 備註 |
| :-- | :-- | :-- | :-- | :-- |
| M1 | 已合併 | `feat/m1-verdict-schema`／#1 | 6 | agy 合併閘門 PASS，無意見 |
| M2 | 已合併 | `feat/m2-verdict-parser`／#2 | 34（累計） | 原本堆疊在 M1 上，M1 合併後 retarget 到 base；合併閘門第 1 輪 4 個 minor 全部採納（fix-1），第 2 輪 PASS |
| M3 | 未開始 | | | |
| M4 | 未開始 | | | |
| M5 | 未開始 | | | |
| M6 | 未開始 | | | |
| M7 | 未開始 | | | |

狀態只用：未開始、實作中、審查中、待合併、已合併、延後。

## 已查證事實

| 項目 | 結果 | 對實作的影響 |
| :-- | :-- | :-- |
| agy 1.4.0 `--json-schema` | 用 `type`、`properties`、`required`、`enum`、`items` 組成的 schema 可用；結果在 JSON 外殼的 `structured_output`，經由 `finish` 工具交回；`response` 是兩段 JSON 接在一起，不能解析（預檢 A5c） | schema 只用這個子集（D-1）；只讀 `structured_output`（D-8）；hook 必須放行 `finish` |
| 交接文件 §5 的 verdict 格式 | 頂層 `verdict`、`findings`、`coverage`、`limitations`；finding 有 `id`、`severity`、`evidence`、`issue`、`suggestion` | R-1 的欄位 |
| PLAN §4.5 | 第二輪起多輸出 `resolved: [{id, status: resolved\|unresolved, note}]`，只在第二輪起必填 | `resolved` 在 schema 中選填，由 `verdict.py` 依輪次檢查（D-2） |
| agy 寫檔行為（預檢 A5b） | 使用者設定 `toolPermission: always-proceed`；不加防護時能寫到工作目錄以外；`--sandbox`、`--mode plan` 擋不住；工作區 `.agents/hooks.json` 的 PreToolUse hook 能擋下寫檔工具與 `run_command`，hook 失敗也算拒絕 | 唯讀保障改用 agy 端 hook（D-4） |
| agy hook 的執行方式（預檢 A5b；rgs 的 agy-cli 筆記） | Windows 以 `cmd /c` 執行，cwd 是 `<ws>/.agents`，stdin 是 `{"toolCall": {"name", "args"}, …}`，stdout 回 `{"decision": "allow"\|"deny", "reason": …}`；沒有空白的路徑加了引號時 hook 不會執行，agy 以 invalid UTF-8 錯誤結束 | hook 指令只在路徑含空白時加引號（教訓 4）；POSIX 的執行方式未驗證 |
| 模型（預檢 A2、A3） | ID 帶強度後綴（`gemini-3.8-flash-high`、`gemini-4-argon-high`）；使用者的 agy 預設模型是 Claude Opus 5.5；JSON 輸出沒有模型欄位，`--log-file` 有 `label="Gemini 4 Argon (High)"` 這類 agy 用戶端解析結果 | `--model` 必傳且必須是 `gemini-` 開頭；`reported_model` 取 log 的 label（D-5） |
| 傳入方式（預檢 A4） | 放在 `-p` 參數：9 秒、1.7 萬 tokens；stdin 或讀檔：約 60 秒、6–8 萬 tokens；Windows 命令列上限約 32K 字元 | 計畫放在 `-p`，prompt 上限 30,000 字元（D-7） |
| 耗時（預檢 A6） | 一次審查 43–155 秒 | `AGY_TIMEOUT = 300`（D-6） |
| 逾時行為（rgs 的 agy-cli 筆記） | `--print-timeout` 到期時 exit 0、`status: SUCCESS`、`response` 為空，stderr 有 `print timeout` | 這種情況判為 `timeout` |
| `agy models`（預檢 A2） | 沒有 `--output-format`；輸出每行「ID〔Tab〕顯示名稱」 | `--self-check` 解析文字輸出 |
| Claude Code skill（官方文件） | frontmatter 有 `allowed-tools`（`Bash(prefix *)`，可用 `${CLAUDE_SKILL_DIR}`，**只在呼叫 skill 的那一回合有效**）與 `hooks`（skill 被呼叫後整個 session 都有效）；skill 目錄可以是 symlink；同名時企業層 > 個人層 > 專案層，plugin 有命名空間；企業 managed 目錄：Windows `C:\Program Files\ClaudeCode\`、macOS `/Library/Application Support/ClaudeCode/`、Linux `/etc/claude-code/`，skill 放在其下 `.claude/skills/` | R-7 的檢查範圍；R-9 用 `hooks` 註冊；`allowed-tools` 跨回合會失效，A7 要驗證（D-11） |
| Claude Code 的 PreToolUse hook（官方文件） | stdin 有 `tool_name`、`tool_input.command`；拒絕時 stdout 回 `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": …}}` 並 exit 0；Windows 上 shell 形式的 hook 用 Git Bash 執行，沒有 Git Bash 時用 PowerShell | R-9 的輸入輸出格式 |
| repo 現況（v2 設計時） | `skills/facet/references/verdict.schema.json`、`skills/facet/scripts/verdict.py`、兩個測試檔，共 34 個測試 | M3 起新增模組沿用 `verdict.py` 的風格 |

## 決策紀錄

| 編號 | 決策 | 理由與替代方案 | 日期 |
| :-- | :-- | :-- | :-- |
| D-1 | verdict schema 只用 `type`、`properties`、`required`、`enum`、`items` | 這個子集已在 agy 1.4.0 驗證可用，`verdict.py` 也只需支援這些。沒採用：`$ref`、`oneOf`、`additionalProperties`（未驗證 agy 是否接受）；第三方 `jsonschema` 套件（違反只用標準函式庫） | 2026-10-17 |
| D-2 | `resolved` 在 schema 選填，「第二輪起必填」由 `validate(..., round_no)` 檢查 | 一份 schema 供每一輪使用；`facet_review.py` 在第二輪起於執行時把 `resolved` 加進 `required`，寫成 run 目錄中的暫存 schema 再傳給 agy。沒採用：兩份 schema 檔（重複維護） | 2026-10-17 |
| D-3 | `VerdictError` 帶 `kind`（`parse_error`、`schema_error`），對應 PLAN §4.3 的 status | `facet_review.py` 可直接把 `kind` 當 status 回報 | 2026-10-17 |
| D-4 | 唯讀保障：`ws/.agents/hooks.json` 的 PreToolUse hook 只放行 `finish`、`wait`，加上事後的 repo 快照比對與 `ws/` 新檔檢查；hook 程式 `agy_hook.py` 複製到 `ws/.agents/`，以 `<python> -I agy_hook.py` 執行 | 預檢 A5b 實測有效且 fail-closed；計畫放在 prompt，審查者不需要任何工具。沒採用：`--sandbox`、`--mode plan`（實測無效）；用低權限帳號執行（不跨平台） | 2026-10-17 |
| D-5 | `REVIEWER_MODEL = gemini-4-argon-high`；`--model` 必傳且必須以 `gemini-` 開頭；`reported_model` 取 `--log-file` 最後一個 `label="…"`，標明「agy 用戶端解析，伺服器端未確認」 | 交接文件「Gemini 4 開放後只改 `REVIEWER_MODEL`」；額度和 rgs 用的 3.8 分開。沒採用：雙審查者（D6，呼叫次數加倍） | 2026-10-17 |
| D-6 | `AGY_TIMEOUT = 300` 秒：`--print-timeout 300s`，外部在 300 + 15 秒時終止 process 樹；Claude 呼叫 Bash 時 `timeout` 設 360,000 毫秒 | 預檢最慢 155 秒，180 只剩 25 秒餘裕 | 2026-10-17 |
| D-7 | 計畫放在 `-p` 參數；整個 prompt 超過 30,000 字元時回傳 `plan_too_long`（exit 9），不送出 | 預檢 A4：最快最便宜；Windows 命令列上限約 32K。沒採用：讀檔（要開放 `view_file`，和 D-4 衝突，而且慢 6 倍）；stdin（慢 6 倍、貴 4 倍） | 2026-10-17 |
| D-8 | 只讀 `structured_output`；沒有這個欄位就是 `parse_error`，不退回去解析 `response` | 預檢 A5c：`response` 4 次都無法解析 | 2026-10-17 |
| D-9 | 跨平台（PLAN D7）：process 樹終止依作業系統分開；repo 工具用 Python；不依賴 shell 工具 | 使用者的主要環境是 Windows | 2026-10-17 |
| D-10 | 拆模組：`prompt.py`（R-3、R-4）、`agy_hook.py` 與 `agy_runner.py`（R-5）、`facet_review.py`（R-6，只做整合） | 每個里程碑的大小要讓 Gemini 不執行程式也能寫對；沿用 M2 把 `verdict.py` 獨立的做法。沒採用：PLAN §4.1 的單一 `facet_review.py`（太大，難審） | 2026-10-17 |
| D-11 | A7（Plan 模式下的核准方式）移到 Phase 3：SKILL.md 先寫 `allowed-tools`，README 附 settings 權限規則作為備案 | 要有安裝好的 skill 才測得出來；官方文件說 `allowed-tools` 只在呼叫的那一回合有效，審查迴圈跨回合時可能失效，必須實測 | 2026-10-17 |
| D-12 | argparse 的用法錯誤改回傳 status `usage_error`、exit 10；`--self-check` 失敗是 `self_check_failed`、exit 11 | argparse 預設用 exit 2，會和 PLAN 的 `timeout`（2）撞號 | 2026-10-17 |

## 架構

```text
skills/facet/
├── SKILL.md                          # M7：參數、硬規則、流程 checklist；frontmatter 註冊 guard_agy.py
├── references/
│   ├── verdict.schema.json           # M1
│   ├── review-prompt.md              # M3：§5 範本 + 三視角清單 + 第二輪區塊
│   └── summary-format.md             # M7：§8 審查摘要 + 附錄格式
└── scripts/
    ├── verdict.py                    # M2：parse_response → validate → evidence_found
    ├── prompt.py                     # M3：load_plan（附錄截斷）、scan_secrets、build_prompt（長度上限）
    ├── agy_hook.py                   # M4：agy 端 PreToolUse hook（只放行 finish、wait）
    ├── agy_runner.py                 # M4：組指令、禁止旗標、裝 hook、執行與逾時、分類、取 structured_output 與模型
    ├── facet_review.py               # M5：命令列；快照、meta.json、status／exit code、--self-check
    └── guard_agy.py                  # M7：Claude Code 端 PreToolUse hook（擋直接呼叫 agy）
scripts/
├── check_name_conflict.py            # M6
└── install.py                        # M6
tests/
├── fake_agy.py                       # M4：agy 測試替身（M5、Phase 5 共用）
├── test_prompt.py                    # M3
├── test_agy_hook.py、test_agy_runner.py   # M4
├── test_facet_review.py              # M5
├── test_install.py                   # M6
└── test_skill_md.py、test_guard_agy.py    # M7
README.md                             # M7
```

一次送審的資料流（`facet_review.py`）：

1. `prompt.load_plan`：讀計畫檔並截掉附錄。
2. `prompt.scan_secrets`：有命中就回 `secret_suspected`。
3. `prompt.build_prompt`：組出 prompt；超過上限就回 `plan_too_long`。
4. 做 repo 快照。
5. `agy_runner.prepare_workspace`：建立 `ws/`，放好 hook。
6. `agy_runner.build_command`、`check_forbidden`：組指令，有禁止旗標或不合規模型就回 `forbidden_flag`。
7. `agy_runner.run`：執行並處理逾時。
8. `agy_runner.classify`：依輸出分類，取出 `structured_output`。
9. `verdict.validate`，再對每條 finding 呼叫 `evidence_found`。
10. 重新快照比對，並檢查 `ws/` 有沒有新檔：有變動就回 `workspace_modified`，優先於 `ok`。
11. 寫 `meta.json`，stdout 印一行結果 JSON。

## 風險

| 風險 | 機率／影響 | 對策 |
| :-- | :-- | :-- |
| agy 不接受某些 schema 關鍵字 | 低／中 | D-1 只用已驗證的子集 |
| 子集驗證器漏掉 schema 中新增的關鍵字 | 中／中 | `validate` 先靜態檢查整棵 schema，遇到不支援的關鍵字直接丟錯 |
| agy 改版後 hook 格式、工具名稱或輸出欄位改變 | 中／高 | `meta.json` 記錄 agy 版本；hook 預設拒絕（未知工具也拒）；README 規定升級 agy 後重跑預檢 A3、A5b、A5c |
| macOS／Linux 上 agy 執行 hook 的方式不同 | 中／高 | 無法在這台機器驗證；hook 指令格式集中在 `agy_runner` 的一個函式；列為未驗證項目，README 註明 |
| Gemini 寫錯跨平台的 process 終止程式（不能執行） | 中／中 | spec 寫明兩個平台的 API；測試用會產生子 process 的替身驗證逾時後 process 樹已結束（在 Windows 上實跑） |
| `allowed-tools` 只在呼叫 skill 的那一回合有效，跨回合後 Plan 模式每次都要確認 | 高／中 | D-11：Phase 3 實測；README 附 settings 權限規則 |
| Gemini 4 Argon 的週額度用完 | 低／中 | 依交接文件不自動換模型；`agy_error` 的 detail 標明額度訊息，由使用者決定 |
| `guard_agy.py` 在 skill 被呼叫後整個 session 都有效，會擋到使用者自己手動執行的 `agy` | 中／低 | 只擋 Bash 指令中直接出現的 `agy`；README 說明 |

## 里程碑

每個里程碑一個 PR，base 是 `ccr-a267cbbf-nsxfdf`。M3、M4、M6 互不相依；M5 需要 M3、M4；M7 需要 M5（SKILL.md 要寫實際的命令列）。同一時間只讓一個 Gemini 執行，順序是 M3 → M4 → M6 → M5 → M7。M5 開始時 M3 或 M4 若還沒合併，就堆疊在還沒合併的那一個上（兩個都沒合併時先等）。

### M3：審查 prompt 與送審前檢查

- 需求：R-3、R-4
- 相依：無
- 主要檔案：`skills/facet/references/review-prompt.md`、`skills/facet/scripts/prompt.py`、`tests/test_prompt.py`
- 要點：
  - `review-prompt.md` 用固定的標題加 ```` ```text ```` 區塊，讓 `prompt.py` 能取出：基本範本、三個視角的檢查清單、第二輪區塊。
  - 第二輪的前輪資料格式：`{"changes_summary": str, "prior_findings": [{"id", "severity", "issue", "disposition": "accepted"|"rejected", "reason"}]}`，由 `build_prompt` 驗證結構。
  - 密鑰樣式見 R-4；`MAX_PROMPT_CHARS = 30000`。
  - 錯誤用 `PromptError`，帶 `kind`：`secret_suspected`、`plan_too_long`、`invalid_prior`。
- 測試：附錄截斷（有、沒有標記，標記出現兩次）；各密鑰樣式命中與不誤判；每個視角的 prompt 內容；第一、二輪差異；前輪資料缺漏或格式錯；長度剛好在上限與超過上限；範本檔缺區塊時丟錯
- 驗證：`python -m unittest discover -s tests -v`

### M4：agy 執行器與唯讀 hook

- 需求：R-5
- 相依：無
- 主要檔案：`skills/facet/scripts/agy_hook.py`、`skills/facet/scripts/agy_runner.py`、`tests/fake_agy.py`、`tests/test_agy_hook.py`、`tests/test_agy_runner.py`
- 要點：
  - `agy_hook.py` 讀 stdin 的工具呼叫，只放行 `finish`、`wait`，每次都寫 `guard.log`（JSON Lines），任何例外都輸出拒絕。
  - `agy_runner`：
    - `resolve_agy()`：`FACET_AGY_BIN` 優先；是 `.py` 時用 `[sys.executable, path]`；回傳是否為測試替身。
    - `build_command(prompt, model, timeout, schema_path, log_path)` 與 `check_forbidden(argv, model)`。
    - `prepare_workspace(ws)`：建立 `.agents/hooks.json`，複製 `agy_hook.py`；指令只在路徑含空白時加引號。
    - `run(argv, cwd, timeout)`：stdin 為 DEVNULL；Windows 用 `CREATE_NEW_PROCESS_GROUP` 加 `taskkill /T /F`，POSIX 用 `start_new_session` 加 `killpg`。
    - `classify(...)`：見 R-5 的分類規則。
    - `reported_model_from_log(path)`。
  - `fake_agy.py` 用環境變數選行為：`approve`、`revise`、`by_lens`、`garbage`、`empty`、`error`、`print_timeout`、`no_structured`、`bad_schema`、`sleep`（含子 process）、`touch`、`ws_write`；另外支援 `--version`、`models`，給了 `--log-file` 時寫入 label 行，並把收到的 argv 寫到指定檔供斷言。
- 測試：hook 的各種工具與壞輸入；指令組裝與禁止旗標；模型 ID 檢查；`prepare_workspace` 產生的檔案與引號規則；每一種分類；逾時後 process 樹已結束；log 解析
- 驗證：`python -m unittest discover -s tests -v`

### M5：`facet_review.py` 命令列

- 需求：R-6
- 相依：M3、M4
- 主要檔案：`skills/facet/scripts/facet_review.py`、`tests/test_facet_review.py`
- 要點：
  - 介面依 PLAN §4.3（2026-10-17 版）。
  - repo 快照：git repo 用 `git status --porcelain=v1 -uall`、`git diff HEAD --binary` 與未追蹤檔內容的雜湊；不是 git repo 時走訪目錄比對大小與修改時間。
  - 第二輪起寫出把 `resolved` 設為必填的暫存 schema（D-2）。
  - 輸出：`meta.json` 欄位依 PLAN §4.3 第 6 點；stdout 只印一行 JSON。
  - status 與 exit code 依 PLAN §4.3 加上 D-12；`--self-check`。
- 測試：用 `fake_agy.py` 端對端跑過每個 status 與 exit code；`workspace_modified`（repo 被改、`ws/` 有新檔）；第二輪需要 `--prior-stdin`；`meta.json` 欄位；`test_double` 標記；`--self-check` 成功與失敗；用法錯誤是 exit 10
- 驗證：`python -m unittest discover -s tests -v`

### M6：名稱衝突檢查與安裝

- 需求：R-7
- 相依：無
- 主要檔案：`scripts/check_name_conflict.py`、`scripts/install.py`、`tests/test_install.py`
- 要點：
  - 兩支腳本都接受 `--home`、`--managed-dir`、`--project` 覆寫，方便測試。
  - 衝突時輸出 JSON 摘要並以 exit 1 結束。
  - 標記檔 `.facet-install.json` 記錄來源與 commit。
  - 安裝用複製，略過 `__pycache__`、`*.pyc`。
  - `--dry-run`。
- 測試：每個衝突來源；plugin 只警告；有標記可覆蓋、沒標記拒絕；`--project`；不複製快取檔
- 驗證：`python -m unittest discover -s tests -v`；在拋棄式的暫存 HOME 中實跑一次安裝

### M7：SKILL.md、摘要格式、Claude 端 guard 與 README

- 需求：R-8、R-9、R-10
- 相依：M5
- 主要檔案：`skills/facet/SKILL.md`、`skills/facet/references/summary-format.md`、`skills/facet/scripts/guard_agy.py`、`README.md`、`tests/test_skill_md.py`、`tests/test_guard_agy.py`
- 要點：
  - description 用 PLAN §1.1 的草稿。
  - SKILL.md 依 PLAN §4.2、§4.4，參數用 D-5、D-6。
  - `guard_agy.py` 的輸入輸出依 Claude Code 官方格式；frontmatter `hooks` 的確切寫法在寫 spec 時再查官方文件。
  - README 依 R-10。
- 測試：frontmatter 解析與限制（R-8）；引用檔存在；guard 的放行與拒絕（R-9）
- 驗證：`python -m unittest discover -s tests -v`；之後的 Phase 3 用 `claude plugin validate` 驗證 frontmatter

### M7 之後：本機驗收（PLAN Phase 3–6）

不是 Gemini 的實作里程碑，由 Claude 與使用者在本機進行：

- Phase 3：安裝，以及 A7 的 Plan 模式實測。
- Phase 4：觸發測試。
- Phase 5：試跑驗收。
- Phase 6：`/rgs-pr release v0.1.0`。

發現的問題開修正里程碑（M8 起）。

## 追溯矩陣

| 需求 | 里程碑 | 測試 | PR |
| :-- | :-- | :-- | :-- |
| R-1 | M1 | `tests/test_verdict_schema.py` | #1 |
| R-2 | M2 | `tests/test_verdict.py` | #2 |
| R-3、R-4 | M3 | `tests/test_prompt.py` | |
| R-5 | M4 | `tests/test_agy_hook.py`、`tests/test_agy_runner.py` | |
| R-6 | M5 | `tests/test_facet_review.py` | |
| R-7 | M6 | `tests/test_install.py` | |
| R-8、R-9、R-10 | M7 | `tests/test_skill_md.py`、`tests/test_guard_agy.py` | |

## 教訓清單

<!-- 審查中反覆出現的錯誤，寫進之後每份 spec 的「先前的教訓」。 -->

1. 驗證設定或 schema 時，先靜態走訪整個結構，不要只檢查資料剛好走到的分支；否則選填欄位底下的錯誤會被默默略過（出處：PR #2）。
2. 錯誤案例的測試要同時斷言錯誤種類與訊息內容（例如 `__cause__` 與原始說明），不要只斷言有丟例外（出處：PR #2）。
3. 程式刻意區分的邊界（例如 `bool` 與 `int`）要有專屬測試，否則重構時容易被改壞（出處：PR #2）。
4. agy hook 指令中，沒有空白的執行檔路徑不要加引號：Windows 上 `cmd /c` 會執行失敗，agy 以 `invalid UTF-8` 錯誤結束（出處：預檢 A5b）。

## 修訂歷史

| 版本 | 日期 | 變更 |
| :-- | :-- | :-- |
| v1 | 2026-10-17 | 初版 |
| v1.1 | 2026-10-17 | M1、M2 已合併；補上教訓清單 |
| v2 | 2026-10-17 | 納入 Phase 1 預檢結果與決定（D-4 到 D-12）；新增 M3–M7 |
