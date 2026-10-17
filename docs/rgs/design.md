# 設計與計畫：rgs-facet 併入 RGS

> 單一事實來源。每個里程碑合併後由 Claude 更新「狀態總覽」「追溯矩陣」「教訓清單」。

| 項目 | 內容 |
| :-- | :-- |
| 版本 | v1（修訂歷史見文末） |
| 需求 | `docs/rgs/requirements.md` |
| 查證基準 | agy 1.4.0（Windows 11，2026-10-17）；`skills/rgs-core/references/agy-cli.md`；Facet 的預檢結果與設計（`docs/origins/facet/`）；Claude Code 官方文件 skills、hooks |

M1–M6 依序對應使用者核准計畫中的 F1–F6。

## 狀態總覽

| 里程碑 | 狀態 | 分支／PR | 測試數 | 備註 |
| :-- | :-- | :-- | :-- | :-- |
| M1 | 未開始 | | | 搬入 rgs-facet 專屬模組 |
| M2 | 未開始 | | | `call_agy` 強化 |
| M3 | 未開始 | | | 封閉唯讀、快照、doctor |
| M4 | 未開始 | | | `facet_review.py` |
| M5 | 未開始 | | | rgs-facet skill 本體、安裝 |
| M6 | 未開始 | | | 文件與 RGS 整合 |

狀態只用：未開始、實作中、審查中、待合併、已合併、延後。

## 已查證事實

| 項目 | 結果 | 對實作的影響 |
| :-- | :-- | :-- |
| rgs-core 的 agy 呼叫點 | 全部經過 `rgs_common.call_with_fallback` → `call_agy`。`rgs.py` 的 implement／fix 傳 `mode='accept-edits'`，fix 另外傳 `conversation`；`review.py`、`batch.py`、`digest.py` 不傳 `mode`、`conversation`、`add_dirs` | R-4 的角色檢查：實作角色只有 implement／fix，其餘都是審查角色 |
| `call_agy` 的逾時 | `subprocess.run(..., timeout=timeout_s + 180)`，逾時時只結束 agy 本身 | R-4(a) 改用 `Popen` 並終止程序樹；外部終止的緩衝時間要能設定（rgs-facet 用 15 秒） |
| rgs-core 測試用的模型名稱 | `test_common.py` 用 `m1`、`m2`，`test_flow.py`、`test_github.py` 用 `m-impl`、`m-review` | R-4(b) 要求 `gemini-` 開頭後，這些測試資料要改名 |
| guard 的角色 | `implementer` 可寫清單內的檔案；`reviewer` 放行讀檔、唯讀 `run_command`、`invoke_subagent`、`send_message` 等中性工具；未知工具一律拒絕，例外也拒絕 | R-5 新增 `sealed`：只放行 `finish`、`wait` |
| `isolated_workspace` | 建立空的暫存資料夾、寫入指定檔案、裝上 reviewer guard；batch 與 digest 使用 | R-5 加選用參數，預設行為不變 |
| `doctor.py` | 一定要有 git repo（沒有就 fail）；`--flow main\|pr` | R-6 新增 `--flow facet` 與 `--model` |
| `secret_scan.py` | 只掃 staged 內容或檔案；內建 8 種樣式，可由 profile 追加 | R-3 新增 `scan_text(text)`；Facet 原本的樣式長度門檻和 rgs-core 不同，以 rgs-core 為準 |
| rgs-core 測試 | 79 個，全部跑一次約 4.6 分鐘（含建立暫存 repo 的整合測試） | quick 與 verify 都跑完整測試；跑在背景 |
| `install.ps1` | 目標已存在且不是指向本 repo 的連結時，只警告、不覆蓋 | R-10 不需要另寫名稱衝突腳本 |
| agy `--json-schema`（Facet 預檢 A5c） | `type`、`properties`、`required`、`enum`、`items` 組成的 schema 可用；結果在 `structured_output`；`response` 是兩段 JSON 接在一起 | schema 只用這個子集；只讀 `structured_output` |
| agy 寫檔行為（Facet 預檢 A5b） | 使用者的 agy 設定是 `toolPermission: always-proceed`；不加防護時能寫到工作目錄以外；`--sandbox`、`--mode plan` 擋不住；工作區 `.agents/hooks.json` 的 PreToolUse hook 能擋下寫檔工具與 `run_command`，hook 失敗也算拒絕 | 唯讀保障靠 guard |
| 模型（Facet 預檢 A2、A3） | ID 帶強度後綴（`gemini-3.8-flash-high`、`gemini-4-argon-high`）；使用者的 agy 預設模型是 Claude Opus；JSON 輸出沒有模型欄位，`--log-file` 有 `label="Gemini 4 Argon (High)"` 這類 agy 用戶端解析結果；`agy models` 沒有 JSON 輸出，每行是「ID〔Tab〕顯示名稱」 | R-4(b)(c)、R-6 |
| 傳入方式與耗時（Facet 預檢 A4、A6） | 放在 `-p` 參數最快最便宜；Windows 命令列上限約 32K 字元；一次審查 43–155 秒 | 計畫放在 `-p`，prompt 上限 30,000 字元；`AGY_TIMEOUT = 300` |
| 逾時行為（agy-cli.md） | `--print-timeout` 到期時 exit 0、`status: SUCCESS`、`response` 為空，stderr 有 `print timeout` | `classify` 已處理，判為 `timeout` |
| Claude Code skill（官方文件） | frontmatter 有 `allowed-tools`（只在呼叫 skill 的那一回合有效）與 `hooks`（skill 被呼叫後整個 session 有效）；skill 目錄可以是 symlink／junction；同名時企業層 > 個人層 > 專案層 | R-8、R-9；A7 在本機驗收時實測 |
| Claude Code PreToolUse hook（官方文件） | stdin 有 `tool_name`、`tool_input.command`；拒絕時 stdout 回 `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": …}}` 並 exit 0 | R-9 的輸入輸出格式 |

## 決策紀錄

| 編號 | 決策 | 理由與替代方案 | 日期 |
| :-- | :-- | :-- | :-- |
| D-1 | rgs-facet 是 RGS 的第三個入口，共用 rgs-core；入口獨立，不做成 rgs-main／rgs-pr 的子指令 | 執行環境不同（Plan 模式、只寫計畫檔、一次 ExitPlanMode），也要能用在非 RGS 專案。沒採用：維持獨立 repo（兩份 agy 程式碼會漂移，agy 改版要重驗兩次）；做成 rgs-pr 子指令（觸發詞混雜、需要 profile） | 2026-10-17 |
| D-2 | 名稱 `rgs-facet` | 使用者決定；在 `/` 選單和 rgs-main、rgs-pr 排在一起 | 2026-10-17 |
| D-3 | 程式跨平台，安裝沿用 `install.ps1`（只支援 Windows），macOS／Linux 列為未驗證 | 使用者決定。Facet 原本的 D7 要求跨平台安裝；agy 在 POSIX 上執行 hook 的方式本來就無法在這台機器驗證 | 2026-10-17 |
| D-4 | 在 RGS repo 用 /rgs-pr 開發；profile、知識庫與合併後的知識沉澱直接 commit 到 main，push 前由使用者確認 | 使用者決定；符合「Claude 不寫產品程式碼」 | 2026-10-17 |
| D-5 | verdict schema 只用 `type`、`properties`、`required`、`enum`、`items`（原 Facet D-1） | 已在 agy 1.4.0 驗證；驗證器只需支援這些 | 2026-10-17 |
| D-6 | `resolved` 在 schema 選填，「第二輪起必填」由 `validate(..., round_no)` 檢查；`facet_review.py` 第二輪起寫出把 `resolved` 設為必填的暫存 schema 給 agy（原 Facet D-2） | 一份 schema 供每一輪使用 | 2026-10-17 |
| D-7 | `VerdictError`、`PromptError` 帶 `kind`，直接對應 `facet_review.py` 的 status（原 Facet D-3） | 不用再翻譯錯誤種類 | 2026-10-17 |
| D-8 | 審查者唯讀：`isolated_workspace(..., sealed=True)` 裝上 `sealed` guard（只放行 `finish`、`wait`），加上呼叫前後的 repo 快照比對與工作區新檔檢查（原 Facet D-4） | 計畫放在 prompt 裡，審查者不需要任何工具；hook 實測有效且 fail-closed。改放在 rgs-core，batch／digest 日後也能用 | 2026-10-17 |
| D-9 | `REVIEWER_MODEL = gemini-4-argon-high`；rgs-facet 直接呼叫 `call_agy`，不走 `call_with_fallback`（原 Facet D-5） | Facet 的原則是失敗不偷換模型；Gemini 4 的額度和 RGS 實作用的 3.8 分開 | 2026-10-17 |
| D-10 | `AGY_TIMEOUT = 300` 秒：`--print-timeout 300s`，外部在 300 + 15 秒時終止程序樹；Claude 呼叫 Bash 時 `timeout` 設 360,000 毫秒（原 Facet D-6） | 預檢最慢 155 秒 | 2026-10-17 |
| D-11 | 計畫放在 `-p` 參數；整個 prompt 超過 30,000 字元時回報 `plan_too_long`，不送出（原 Facet D-7） | 最快最便宜；Windows 命令列上限約 32K | 2026-10-17 |
| D-12 | rgs-facet 的原始輸出放在系統暫存目錄 `<temp>/rgs-facet/<session>/`，路徑寫在計畫附錄；`roles.md` 規則 7 加註例外 | Plan 模式只能寫計畫檔；rgs-facet 要能用在沒有 `.rgs/` 的專案。沒採用：寫進 `.rgs/runs/`（會在非 RGS 專案建立 `.rgs/`） | 2026-10-17 |
| D-13 | `facet_review.py` 的 status 與 exit code：`ok` 0、`timeout` 2、`agy_error` 3、`empty_output` 4、`parse_error`／`schema_error` 5、`workspace_modified` 6、`secret_suspected` 7、`forbidden_flag` 8、`plan_too_long` 9、`usage_error` 10（原 Facet PLAN §4.3 與 D-12）。環境檢查改由 `doctor.py --flow facet` 負責，不再有 `--self-check` | 沿用已核准的表；argparse 預設的 exit 2 會和 `timeout` 撞號，所以用法錯誤自行處理 | 2026-10-17 |
| D-14 | agy 參數依角色檢查（`call_agy` 新增 `role`，預設 `reviewer`；implement／fix 傳 `implementer`）。所有角色禁止 `--dangerously-skip-permissions`、`--yolo`、`-i`、`--prompt-interactive`、`--remote-control`、`--sandbox`；審查角色另外禁止 `--mode`、`--add-dir`、`--conversation`、`-c`、`--continue`；實作角色的 `--mode` 只能是 `accept-edits`。`--model` 必傳且以 `gemini-` 開頭。違反時不呼叫 agy，丟出 `RgsError` | 參數由程式組出來，這是防止程式改錯的最後一道關；模型前綴則防止 profile 設成 Claude（使用者的 agy 預設就是 Claude） | 2026-10-17 |
| D-15 | 終止程序樹：`Popen` 啟動；Windows 用 `CREATE_NEW_PROCESS_GROUP`，逾時時 `taskkill /PID <pid> /T /F`；POSIX 用 `start_new_session=True`，逾時時 `os.killpg` 先送 SIGTERM，10 秒後 SIGKILL。`call_agy` 新增 `grace_s`（預設 180，維持現行行為） | agy 會在背景重試、消耗額度（agy issue #594）；只結束父程序會留下子程序 | 2026-10-17 |
| D-16 | 測試替身一律用 `RGS_AGY`；rgs-facet 的測試共用 `rgs-core/tests/fake_agy.py`，需要的新情境加在那裡 | 不維護第二個替身；原 Facet 的 `FACET_AGY_BIN` 取消 | 2026-10-17 |
| D-17 | 不另寫名稱衝突檢查腳本：`install.ps1` 已不覆蓋非本 repo 的資料夾，再加上 `~/.claude/commands/rgs-facet.md` 的警告 | 原 Facet M6 的大部分工作已經存在 | 2026-10-17 |
| D-18 | Claude 端 guard（`guard_agy.py`）只放在 rgs-facet | rgs 的腳本用 subprocess 呼叫 agy，不經過 Bash 指令字串，不受影響；先在 rgs-facet 驗證 | 2026-10-17 |
| D-19 | 里程碑依序執行，同一時間只有一個 Gemini；相依的里程碑在前一個未合併時堆疊 | agy 同時多個會卡住（agy issue #573）；所有里程碑共用本檔的狀態 | 2026-10-17 |
| D-20 | M1 的搬檔方式：`prepare` 之後，Claude 把 Facet 已合併的 M1／M2 檔案與 M3 worktree 的 3 個檔案原樣複製進任務 worktree（不改內容），所有調整交給 Gemini；Claude 審查時讀完全部內容 | 讓 Gemini 重打上千行既有程式容易出錯；原樣複製不算撰寫產品程式碼。M3 的檔案從沒審過，所以要全文審查 | 2026-10-17 |

## 架構

```text
skills/
├── rgs-core/
│   ├── roles.md                      # M6：rgs-facet 角色列、規則 7 例外
│   ├── references/                   # M6：scripts.md、agy-cli.md 補充
│   ├── scripts/
│   │   ├── rgs_common.py             # M2：call_agy（role、grace_s、程序樹終止、參數檢查、reported_model）
│   │   │                             # M3：isolated_workspace(sealed=)、snapshot
│   │   ├── rgs.py                    # M2：implement／fix 傳 role='implementer'
│   │   ├── guard.py                  # M3：sealed 角色
│   │   ├── doctor.py                 # M3：--flow facet、--model
│   │   └── secret_scan.py            # M1：scan_text
│   └── tests/
│       ├── fake_agy.py               # M2：子程序 sleep、log label、記錄參數；M4：指定 structured_output、寫檔
│       └── test_*.py
├── rgs-facet/
│   ├── SKILL.md                      # M5
│   ├── references/
│   │   ├── verdict.schema.json       # M1（原 Facet M1）
│   │   ├── review-prompt.md          # M1（原 Facet M3）
│   │   └── summary-format.md         # M5
│   ├── scripts/
│   │   ├── verdict.py                # M1（原 Facet M2）
│   │   ├── prompt.py                 # M1（原 Facet M3，密鑰掃描改用 secret_scan.scan_text）
│   │   ├── facet_review.py           # M4
│   │   └── guard_agy.py              # M5
│   └── tests/                        # M1、M4、M5
├── rgs-main/SKILL.md                 # M6：description 區隔
└── rgs-pr/SKILL.md                   # M6：plan 第 5 步、description 區隔
install.ps1                           # M5
README.md、README.en.md               # M6
```

rgs-facet 的腳本以 `os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'rgs-core', 'scripts')` 匯入 `rgs_common` 與 `secret_scan`。

一次送審的資料流（`facet_review.py`，一個角度、一輪）：

1. `prompt.load_plan`：讀計畫檔並截掉附錄。
2. `prompt.scan_secrets`（內部呼叫 `secret_scan.scan_text`）：有命中就回 `secret_suspected`，不送出。
3. `prompt.build_prompt`：組出 prompt；超過上限就回 `plan_too_long`。
4. `rgs_common.snapshot(repo)`。
5. `rgs_common.isolated_workspace('rgs_facet_', sealed=True)`。
6. `rgs_common.call_agy(..., role='reviewer', schema_path=…, timeout_s=AGY_TIMEOUT, grace_s=15)`：參數不合規時 `RgsError` → `forbidden_flag`。
7. 依 `AgyResult.kind` 分類：`timeout`、`error`／`quota` → `agy_error`、`empty` → `empty_output`。
8. `verdict.validate(structured_output, round_no=…)`，再對每條 finding 呼叫 `evidence_found`。
9. 再快照比對，並檢查工作區有沒有 guard 檔以外的新檔：有變動就回 `workspace_modified`，優先於 `ok`。
10. 寫 `meta.json`（要求的模型、`reported_model`、agy 版本、kind、耗時、conversation_id、快照結果、工作區新檔、guard 紀錄、是否為測試替身），stdout 印一行結果 JSON。

## 風險

| 風險 | 機率／影響 | 對策 |
| :-- | :-- | :-- |
| M2 改動所有 agy 呼叫，讓 rgs-main／rgs-pr 壞掉 | 中／高 | 79 個測試加上 sandbox 真 agy 實測；合併後出問題由使用者 `git revert` 該合併 commit |
| 改的是正在使用的 RGS 本身 | 低／中 | Gemini 在另一個 worktree 實作；要等使用者合併、主 checkout pull 之後才生效 |
| Gemini 寫錯跨平台的程序終止程式（不能執行） | 中／中 | spec 寫明兩個平台的 API；用會產生子程序的替身在 Windows 上實跑驗證 |
| M1 搬入的 M3 程式碼從沒審過 | 中／中 | M1 審查時讀完全部內容 |
| 模型前綴檢查讓既有使用者的 profile 失效 | 低／中 | 預設 profile 都是 `gemini-`；錯誤訊息寫明原因與做法 |
| `allowed-tools` 只在呼叫 skill 的那一回合有效，Plan 模式下審查迴圈跨回合後每次都要確認 | 高／中 | 本機驗收時實測（A7）；README 附 settings 權限規則 |
| macOS／Linux 上 agy 執行 hook 與 `killpg` 的行為 | 中／高 | 無法在這台機器驗證；列為未驗證項目 |
| agy 改版後 hook 格式、工具名稱或輸出欄位改變 | 中／高 | `meta.json` 記錄 agy 版本；guard 預設拒絕；README 規定升級後先跑 `doctor.py` |

## 里程碑

### M1：搬入 rgs-facet 專屬模組

- 需求：R-1、R-2、R-3
- 相依：無
- 主要檔案：`skills/rgs-facet/references/{verdict.schema.json, review-prompt.md}`、`skills/rgs-facet/scripts/{verdict.py, prompt.py}`、`skills/rgs-facet/tests/{test_verdict.py, test_verdict_schema.py, test_prompt.py}`、`skills/rgs-core/scripts/secret_scan.py`、`skills/rgs-core/tests/test_scope_secret.py`
- 做法：依 D-20 原樣複製後，由 Gemini 調整：
  - 測試的路徑推算改成 `skills/rgs-facet/scripts`
  - 註解與範本裡引用的 Facet 文件改成 `docs/origins/facet/` 或 rgs-facet 內的位置
  - `prompt.scan_secrets` 改成呼叫 `secret_scan.scan_text`，刪掉自己的樣式表
  - 測試的密鑰樣式依 rgs-core 的門檻調整
- 測試：原本的 34 個 verdict 測試與 M3 的 prompt 測試在新位置通過；`scan_text` 每種內建樣式命中、正常文字不誤判、行號正確、遮蔽後不含原值
- 驗證：`python -m unittest discover -s skills/rgs-facet/tests`、`python -m unittest discover -s skills/rgs-core/tests`

### M2：`call_agy` 強化

- 需求：R-4、R-12
- 相依：無
- 主要檔案：`skills/rgs-core/scripts/rgs_common.py`、`skills/rgs-core/scripts/rgs.py`、`skills/rgs-core/tests/{fake_agy.py, test_common.py, test_flow.py, test_github.py}`
- 要點：D-14、D-15；`--log-file` 存在 `save_as + '.log'`，沒有 `save_as` 時用暫存檔、解析後刪除；`reported_model` 取最後一個 `label="…"`；測試資料的模型名稱改成 `gemini-` 開頭
- 測試：程序樹終止（替身產生子程序並寫出 PID，逾時後兩個 PID 都不存在）；每個禁止參數與角色組合；模型空白或非 `gemini-`；`reported_model` 有 label／沒有 label；原本 79 個測試全過
- 驗證：兩個測試指令；判定通過前用 worktree 的腳本在 sandbox 跑一次真的 implement 與 digest，再用很短的逾時強制結束一次，用 `tasklist` 確認沒有殘留的 agy 程序

### M3：封閉唯讀、快照、doctor

- 需求：R-5、R-6
- 相依：M2（同樣改 `rgs_common.py`；M2 未合併時堆疊）
- 主要檔案：`skills/rgs-core/scripts/{guard.py, rgs_common.py, doctor.py}`、`skills/rgs-core/tests/{test_guard.py, test_common.py, test_doctor.py}`
- 要點：`sealed` 角色只放行 `finish`、`wait`；`isolated_workspace(prefix, files=None, deny=(), read_commands=False, sealed=False)`；`snapshot(path)` 回傳可比較的值（git repo：`status --porcelain=v1 -uall`、`diff HEAD --binary`、未追蹤檔內容的雜湊；非 git：走訪目錄比對相對路徑、大小、修改時間，略過 `.git`）；`doctor.py --flow facet --model M`
- 測試：sealed 對各類工具的決定；快照對新增、修改、刪除、未追蹤檔的偵測，非 git 資料夾也一樣；doctor 在非 git 資料夾執行、模型存在／不存在／非 `gemini-`
- 驗證：兩個測試指令；用真的 agy 在 sealed 工作區跑一次 `--json-schema` 呼叫，確認 `finish` 被放行、結果能取得

### M4：`facet_review.py`

- 需求：R-7
- 相依：M1、M3
- 主要檔案：`skills/rgs-facet/scripts/facet_review.py`、`skills/rgs-facet/tests/test_facet_review.py`、`skills/rgs-core/tests/fake_agy.py`
- 要點：介面 `--plan-file`、`--lens`、`--round`、`--model`、`--timeout`、`--run-dir`、`--repo`、`--prior-stdin`；資料流見「架構」；status 與 exit code 依 D-13；`RUN_DIR` 預設 `tempfile.gettempdir()/rgs-facet/<session>`；`fake_agy.py` 新增「指定 structured_output」與「在工作目錄寫檔」情境
- 測試：用 `fake_agy.py` 端對端跑過每個 status 與 exit code；`workspace_modified`（repo 被改、工作區有新檔）；第二輪需要前輪資料、暫存 schema 把 `resolved` 設為必填；`meta.json` 欄位；`test_double` 標記；用法錯誤是 exit 10
- 驗證：兩個測試指令；用真的 agy 對一份小計畫跑一次 logic 角度

### M5：rgs-facet skill 本體與安裝

- 需求：R-8、R-9、R-10
- 相依：M4
- 主要檔案：`skills/rgs-facet/SKILL.md`、`skills/rgs-facet/references/summary-format.md`、`skills/rgs-facet/scripts/guard_agy.py`、`skills/rgs-facet/tests/{test_skill_md.py, test_guard_agy.py}`、`install.ps1`
- 要點：description 用原 Facet PLAN §1.1 的草稿，名稱改成 rgs-facet；SKILL.md 依原 Facet PLAN §4.2、§4.4、§4.6、§4.8、§4.9，參數用 D-9、D-10，環境檢查改用 `doctor.py --flow facet`；frontmatter `hooks` 的確切寫法在寫 spec 時查官方文件
- 測試：frontmatter 解析與限制；引用的檔案存在；guard 的放行與拒絕
- 驗證：兩個測試指令；在拋棄式的 `-Target` 資料夾實跑 `install.ps1` 與 `-Uninstall`

### M6：文件與 RGS 整合

- 需求：R-11
- 相依：M5
- 主要檔案：`README.md`、`README.en.md`、`skills/rgs-core/roles.md`、`skills/rgs-core/references/{scripts.md, agy-cli.md}`、`skills/rgs-pr/SKILL.md`、`skills/rgs-main/SKILL.md`
- 要點：README 兩個語言版本同步；`agy-cli.md` 補上 Gemini 4 的模型 ID、`-p` 長度上限、耗時、log label；rgs-pr 的 plan 第 5 步改成建議用 `/rgs-facet` 硬化設計；三個 description 互相區隔
- 驗證：auditor 稽核文件與程式一致

### M6 之後：本機驗收

不是 Gemini 的實作里程碑，由 Claude 與使用者進行：

1. `install.ps1`，開新 session，`/skills` 確認 `rgs-facet` 出現、description 沒被截斷。
2. A7：Plan 模式下分別試只有 `allowed-tools`、另外加 settings 權限規則，確認會跳確認、被擋，還是直接執行；依結果定案 README。
3. 觸發測試：10 句該觸發、10 句不該觸發；`/rgs-facet` 100% 觸發，自然語句至少 8/10，誤觸發最多 1/10。
4. 試跑：小型 CLI「新增 `--verbose` 參數」，Plan 模式跑完整流程；真的 agy 一次，再用 `RGS_AGY` 注入逾時、亂碼、寫檔、假密鑰。

發現的問題開修正里程碑（M7 起），之後用 `/rgs-pr release` 發佈。

## 追溯矩陣

| 需求 | 里程碑 | 測試 | PR |
| :-- | :-- | :-- | :-- |
| R-1、R-2、R-3 | M1 | `rgs-facet/tests/test_verdict*.py`、`test_prompt.py`；`rgs-core/tests/test_scope_secret.py` | |
| R-4 | M2 | `rgs-core/tests/test_common.py` | |
| R-5、R-6 | M3 | `rgs-core/tests/test_guard.py`、`test_common.py`、`test_doctor.py` | |
| R-7 | M4 | `rgs-facet/tests/test_facet_review.py` | |
| R-8、R-9、R-10 | M5 | `rgs-facet/tests/test_skill_md.py`、`test_guard_agy.py` | |
| R-11 | M6 | auditor 稽核 | |
| R-12 | M1–M6 | `rgs-core/tests/*`；M2、M3 的 sandbox 實測 | |

## 教訓清單

<!-- 審查中反覆出現的錯誤，寫進之後每份 spec 的「先前的教訓」。前四條來自 Facet 的審查紀錄。 -->

1. 驗證設定或 schema 時，先靜態走訪整個結構，不要只檢查資料剛好走到的分支；否則選填欄位底下的錯誤會被默默略過（出處：Facet PR #2）。
2. 錯誤案例的測試要同時斷言錯誤種類與訊息內容（例如 `__cause__` 與原始說明），不要只斷言有丟例外（出處：Facet PR #2）。
3. 程式刻意區分的邊界（例如 `bool` 與 `int`）要有專屬測試，否則重構時容易被改壞（出處：Facet PR #2）。
4. agy hook 指令中，沒有空白的執行檔路徑不要加引號：Windows 上 `cmd /c` 會執行失敗，agy 以 `invalid UTF-8` 錯誤結束（出處：Facet 預檢 A5b）。

## 修訂歷史

| 版本 | 日期 | 變更 |
| :-- | :-- | :-- |
| v1 | 2026-10-17 | 初版：依使用者核准的合併計畫 |
