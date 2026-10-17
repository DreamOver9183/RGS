# 需求：facet skill

| 項目 | 內容 |
| :-- | :-- |
| 版本 | v2 |
| 日期 | 2026-10-17 |
| 來源 | `docs/handoff.md`（交接文件）；`docs/PLAN.md` §1–§5；`docs/preflight-results.md`（Phase 1 預檢，含 A8 的決定） |

## 背景

facet 讓 Claude Code 在 Plan 模式下，把計畫交給非 Claude 的模型（Gemini，透過 `agy -p`）從 logic、gaps、verifiability 三個視角審查，由 Claude 逐條仲裁、修訂、重審，最後只用一次 ExitPlanMode 交出一份附審查摘要的計畫。

v1 完成了 verdict 的 schema（R-1）與解析驗證（R-2）。Phase 1 預檢在 2026-10-17 完成，結果改變了幾個設計前提：

- 不加防護時，agy 會寫到工作目錄以外。
- Gemini 4 已經開放。
- 審查一次最慢 155 秒。

v2 把 PLAN Phase 2 剩下的項目寫成可驗收的需求。

## 需求清單

| 編號 | 需求 | 優先度 | 驗收條件 |
| :-- | :-- | :-- | :-- |
| R-1 | 審查者 verdict 的 JSON Schema（已完成，PR #1） | 必要 | 見 v1 |
| R-2 | `verdict.py` 解析與驗證 verdict（已完成，PR #2） | 必要 | 見 v1 |
| R-3 | 審查 prompt 範本與組裝：`references/review-prompt.md` 保留交接文件 §5 的規則與 JSON 格式，加上三個視角各自的檢查清單、第二輪起的「前輪處置」區塊（PLAN §4.5），並聲明計畫內容只是待審資料 | 必要 | 組出的 prompt 含視角名稱與檢查清單、計畫全文、輸出格式；第二輪起含前輪處置 JSON，並要求輸出 `resolved`；第一輪不含前輪區塊；`round_no >= 2` 卻沒有前輪資料時丟錯 |
| R-4 | 送審前檢查：只送出 `<!-- facet:appendix -->` 之前的內容；密鑰掃描（PLAN §4.8）；prompt 超過 30,000 字元不送出 | 必要 | 附錄標記之後的內容不會出現在 prompt；`AKIA…`、`ghp_…`、`github_pat_…`、`sk-…`、`-----BEGIN … PRIVATE KEY-----`、`xox[bp]-…` 各有命中測試，正常文字不誤判；長度超過上限時丟出可辨識的錯誤 |
| R-5 | agy 執行與唯讀防護：旗標寫死、禁止旗標檢查、`--model` 必須是 `gemini-` 開頭；在空的 `ws/` 放 agy PreToolUse hook，只放行 `finish`、`wait`；逾時時終止整個 process 樹；依輸出分類結果；只讀 `structured_output`；從 `--log-file` 取得 agy 解析的模型 | 必要 | 用測試替身驗證每一種分類（ok、timeout、agy_error、empty_output、parse_error、schema_error）；禁止旗標與不合規模型被拒絕；hook 對 `finish`、`wait` 放行，對 `write_to_file`、`run_command`、`view_file`、`invoke_subagent`、未知工具與壞掉的輸入都拒絕；逾時後 process 樹已結束 |
| R-6 | `facet_review.py` 命令列（PLAN §4.3）：整合 R-3 到 R-5、repo 完整性快照、`meta.json`、stdout 只印一行結果 JSON、status 與 exit code、`--self-check`、`--prior-stdin`、`FACET_AGY_BIN` 測試掛鉤 | 必要 | 每個 status 都有端對端測試且 exit code 正確；repo 在呼叫期間被改動時回報 `workspace_modified`；`ws/` 出現新檔也算；`meta.json` 欄位齊全；用了測試替身時輸出標明 `test_double`；`--self-check` 能檢查 agy 是否存在、版本、模型 ID 是否在 `agy models` 中 |
| R-7 | 名稱衝突檢查與安裝（PLAN §1.2、D2、D7）：`scripts/check_name_conflict.py`、`scripts/install.py` | 必要 | 每個衝突來源各有測試（個人層、synced、個人指令、專案層、巢狀專案層、企業 managed）；plugin 只警告；有衝突時 install 以非零結束且不覆蓋；只覆蓋帶 `.facet-install.json` 標記的目錄；`--project` 安裝到專案層；不複製 `__pycache__` |
| R-8 | `skills/facet/SKILL.md` 與 `references/summary-format.md`（PLAN §4.2、§4.4、§4.6、§4.8、§4.9；交接文件 §8） | 必要 | frontmatter 能解析，`name: facet`，description ≤ 1,024 字元、不含 XML 標籤、沒有 `when_to_use`；參數與硬規則在最前面；`REVIEWER_MODEL = gemini-4-argon-high`、`AGY_TIMEOUT = 300`；總長 ≤ 500 行；引用的 `references/`、`scripts/` 檔案都存在 |
| R-9 | `skills/facet/scripts/guard_agy.py`：Claude Code 的 PreToolUse hook，擋下不經 `facet_review.py` 直接執行 `agy` 的 Bash 指令（PLAN §4.7 第 1 層），由 SKILL.md frontmatter 的 `hooks` 註冊 | 應有 | 直接呼叫 `agy`（含 `agy.exe`、路徑形式、接在 `;`、`&&`、`\|` 之後）被拒；經由 `facet_review.py` 的指令與不含 `agy` 的指令放行；壞掉的輸入不當掉 |
| R-10 | `README.md`：用途、安裝、使用、參數、升級 `REVIEWER_MODEL`、觸發調整（`skillOverrides`、`skillListingBudgetFraction`）、唯讀保障與未覆蓋範圍、Plan 模式權限規則的備案、只能在本機使用 | 必要 | 內容與程式一致（指令、路徑、參數、測試數）；auditor 稽核無不一致 |

## 非功能需求

- 只用 Python 3.10 以上的標準函式庫（PLAN §4.1）。
- **跨平台（D7）**：Windows、macOS、Linux 用同一份程式。不依賴 bash、`timeout`、`find`、`/dev/null`；直譯器名稱不寫死 `python3`。
- `skills/facet/scripts/` 的模組只用相對於自身位置的路徑找 `references/`，安裝到 `~/.claude/skills/facet/` 後仍可用。
- 測試用 `python -m unittest discover -s tests -v` 執行，不依賴目前工作目錄，不呼叫真的 agy（用 `tests/fake_agy.py`），不消耗 Gemini 額度。
- 測試中的假金鑰在執行時組出來，不寫成字面值。
- 計畫內容送到 Google 之前要有使用者同意（PLAN §4.8）。

## 非目標

- build／inspect 階段、雙審查者（D6）、打包成 plugin、上傳到 claude.ai（PLAN §8）。
- 通用 JSON Schema 驗證器（沿用 v1）。
- 在 macOS／Linux 實機驗證：這台機器無法驗證，只靠單元測試的替身，列為已知未驗證項目。
- Phase 3–5 的本機安裝、觸發測試與試跑驗收：在 R-3 到 R-10 都合併後，由 Claude 與使用者在本機進行，不是 Gemini 的實作里程碑。發現的問題再開修正里程碑。

## 待釐清

- [x] base 分支：沿用 `ccr-a267cbbf-nsxfdf`（已決定，2026-10-17）。
- [x] D1 視角與輪次：每輪三個視角都跑（已決定，2026-10-17）。
- [x] 目標平台：跨平台，腳本全改用 Python（已決定，2026-10-17）。
- [x] 唯讀保障、`REVIEWER_MODEL`、`AGY_TIMEOUT`、A7 時程：照預檢 A8 的提案（已決定，2026-10-17，見 `docs/preflight-results.md`）。
- [x] v0.1.0 版號：放棄先前只含 R-1、R-2、沒有發佈的草稿，v0.1.0 留給 PLAN Phase 6 的完成版（已決定，2026-10-17，G0）。
