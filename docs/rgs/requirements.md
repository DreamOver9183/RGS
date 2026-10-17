# 需求：rgs-facet 併入 RGS

| 項目 | 內容 |
| :-- | :-- |
| 版本 | v1 |
| 日期 | 2026-10-17 |
| 來源 | 使用者核准的合併計畫（2026-10-17）；Facet 原始需求與設計：`docs/origins/facet/`（`handoff.md`、`PLAN.md`、`preflight-results.md`、`requirements.md`、`design.md`） |

## 背景

Facet 是另一個 repo 正在開發的 skill：在 Claude Code 的 Plan 模式下，把 Claude 寫的計畫交給 Gemini（透過 `agy -p`）從 logic、gaps、verifiability 三個角度審查，Claude 逐條決定採納或駁回、修訂、重審，最後只用一次 ExitPlanMode 交出一份附審查摘要的計畫。

它和 RGS 的定位不衝突（審的是計畫、不是程式碼；Gemini 只讀不改），但剩下的工作有一大半是在重寫 rgs-core 已經有、也實測過的東西：agy 呼叫、唯讀 guard、密鑰掃描、測試替身、環境檢查。使用者決定把它併進 RGS，成為第三個入口 `rgs-facet`，共用 rgs-core；同時把 Facet 設計得比較嚴謹的地方補回 rgs-core。

Facet 已完成的部分：verdict 的 JSON Schema 與解析器（原 R-1、R-2，已合併），以及 Gemini 已實作、尚未審查的審查 prompt 與送審前檢查（原 R-3、R-4）。

## 需求清單

| 編號 | 需求 | 優先度 | 驗收條件 |
| :-- | :-- | :-- | :-- |
| R-1 | verdict 的 JSON Schema 與解析驗證搬入 `skills/rgs-facet/`（原 Facet R-1、R-2） | 必要 | `verdict.schema.json`、`verdict.py` 與兩個測試檔在新位置全部通過，測試數不少於原本的 34 個；程式行為不變 |
| R-2 | 審查 prompt 範本與組裝（原 Facet R-3）：保留交接文件 §5 的規則與 JSON 格式，加上三個角度各自的檢查清單、第二輪起的「前輪處置」區塊，並聲明計畫內容只是待審資料 | 必要 | 組出的 prompt 含角度名稱與檢查清單、計畫全文、輸出格式；第二輪起含前輪處置 JSON 並要求輸出 `resolved`；第一輪不含前輪區塊；`round_no >= 2` 卻沒有前輪資料時丟錯；範本缺區塊時丟錯 |
| R-3 | 送審前檢查（原 Facet R-4）：只送出 `<!-- facet:appendix -->` 之前的內容；用 rgs-core 的密鑰掃描檢查計畫文字；prompt 超過 30,000 字元不送出 | 必要 | 附錄標記之後的內容不會出現在 prompt；`secret_scan.scan_text(text)` 回傳命中的種類、行號、遮蔽後的字串，rgs-core 內建的每種樣式各有命中測試，正常文字不誤判；長度超過上限時丟出可辨識的錯誤 |
| R-4 | rgs-core 的 agy 呼叫強化：(a) 逾時時終止整個程序樹；(b) 依角色檢查 agy 參數，`--model` 必傳且以 `gemini-` 開頭；(c) 用 `--log-file` 記錄 agy 實際解析的模型 | 必要 | (a) 會產生子程序的替身逾時後，父子程序都已結束；(b) 禁止的參數與不合規的模型在呼叫 agy 之前就被拒絕，並回報可辨識的錯誤；實作角色可以用 `--mode accept-edits` 與 `--conversation`，審查角色不行；(c) `AgyResult` 與摘要有 `reported_model`，log 沒有 label 時是 `null` |
| R-5 | 封閉的唯讀工作區與 repo 快照：guard 新增只放行 `finish`、`wait` 的模式；`isolated_workspace` 可以選用；提供呼叫前後的 repo 快照比對 | 必要 | 封閉模式對 `finish`、`wait` 放行，對寫檔、讀檔、`run_command`、`invoke_subagent`、`send_message`、未知工具與壞掉的輸入都拒絕；git repo 與非 git 資料夾的快照，在檔案被新增、修改、刪除時都偵測得到，沒變動時相同 |
| R-6 | 不需要 repo 的環境檢查：`doctor.py --flow facet --model <M>` | 必要 | 在非 git 資料夾也能執行；檢查 Python 版本、agy 是否存在與版本、模型 ID 是否出現在 `agy models`、是否以 `gemini-` 開頭；不檢查 profile、remote、gh；任何一項失敗時 exit 1 |
| R-7 | `facet_review.py` 命令列（原 Facet R-6）：整合 R-1 到 R-5，完成一次「一個角度、一輪」的送審 | 必要 | 每個 status 都有端對端測試且 exit code 正確；repo 在呼叫期間被改動、或工作區出現新檔時回報 `workspace_modified`；`meta.json` 欄位齊全；stdout 只印一行 JSON；第二輪起需要前輪處置並把 `resolved` 設為必填；用了測試替身時輸出標明 `test_double` |
| R-8 | `skills/rgs-facet/SKILL.md` 與 `references/summary-format.md`（原 Facet R-8） | 必要 | frontmatter 能解析，`name: rgs-facet`，description ≤ 1,024 字元、不含 XML 標籤、沒有 `when_to_use`；參數與硬規則在最前面，`REVIEWER_MODEL = gemini-4-argon-high`、`MAX_ROUNDS = 3`、`AGY_TIMEOUT = 300`；總長 ≤ 500 行；引用的檔案都存在 |
| R-9 | Claude 端 guard `guard_agy.py`（原 Facet R-9）：擋下不經 `facet_review.py` 直接執行 `agy` 的 Bash 指令，由 SKILL.md frontmatter 的 `hooks` 註冊 | 應有 | 直接呼叫 `agy`（含 `agy.exe`、路徑形式、接在 `;`、`&&`、`\|` 之後）被拒；經由 `facet_review.py` 的指令與不含 `agy` 的指令放行；壞掉的輸入不會當掉 |
| R-10 | 安裝：`install.ps1` 加入 `rgs-facet`（取代原 Facet R-7 的衝突檢查與安裝腳本） | 必要 | 安裝後 `~/.claude/skills/rgs-facet` 是指向 repo 的 junction；目標已存在且不是指向本 repo 的連結時不覆蓋並警告；`~/.claude/commands/rgs-facet.md` 存在時警告；`-Uninstall` 能移除；腳本仍只用 ASCII |
| R-11 | 文件與 RGS 整合（原 Facet R-10，加上整合）：README 中英文版、`roles.md`、`references/scripts.md`、`references/agy-cli.md`、rgs-pr 的 plan 第 5 步、rgs-main 與 rgs-pr 的 description | 必要 | README 兩個語言版本都有 rgs-facet 的用途、使用方式、參數、唯讀保障與未覆蓋範圍、Plan 模式權限規則的備案；`roles.md` 有 rgs-facet 的角色與規則 7 的例外；`scripts.md` 有 `facet_review.py` 的 status 與 exit code；description 互相區隔；auditor 稽核無不一致 |
| R-12 | 既有行為不回歸 | 必要 | rgs-core 原本的 79 個測試持續通過（只允許為了新規則調整測試資料，例如模型名稱）；改動 agy 呼叫的里程碑在判定通過前，用真的 agy 在 sandbox 跑過一次實作與一次 digest |

## 非功能需求

- 只用 Python 3.10 以上的標準函式庫。
- 程式跨平台（Windows、macOS、Linux 用同一份程式）：不依賴 bash、`timeout`、`find`、`/dev/null`；子程序的 stdin 用 `subprocess.DEVNULL`；直譯器名稱不寫死 `python3`；終止程序樹依作業系統分開處理。安裝與實機驗證只做 Windows。
- 腳本只用相對於自身位置的路徑找範本與其他腳本；rgs-facet 以 `../rgs-core/scripts` 匯入共用模組。
- 測試不呼叫真的 agy 或 gh，不消耗額度；假金鑰在執行時組出來。
- 計畫內容送到 Google 之前要有使用者同意（使用者明確呼叫 `/rgs-facet` 或要求跨模型審查視為同意；自動載入時先確認一次）。

## 非目標

- build／inspect 階段、雙審查者、打包成 plugin、上傳到 claude.ai。
- 通用的 JSON Schema 驗證器。
- 跨平台的安裝腳本，以及 macOS／Linux 實機驗證。
- 把 review、batch、digest 改用封閉工作區或 repo 快照（這次只提供能力）。
- 本機驗收（安裝、Plan 模式權限實測、觸發測試、試跑）：在所有里程碑合併後由 Claude 與使用者進行，不是 Gemini 的實作里程碑。

## 待釐清

- [x] 合併方式：第三個入口，共用 rgs-core（已決定，2026-10-17）。
- [x] 名稱：`rgs-facet`（已決定，2026-10-17）。
- [x] 平台：程式跨平台、安裝只做 Windows（已決定，2026-10-17）。
- [x] 開發方式：在 RGS repo 跑 /rgs-pr；設定、知識庫與合併後的知識沉澱直接 commit 到 main，push 前由使用者確認（已決定，2026-10-17）。
