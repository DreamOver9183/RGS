# M6：文件與 RGS 整合

> /rgs-pr 的里程碑規格。由 Claude 依 design.md 撰寫；PR 合併時一併存進 `docs/rgs/specs/`。

| 項目 | 內容 |
| :-- | :-- |
| 對應需求 | R-11（`docs/rgs/requirements.md`） |
| 相依 | M5（rgs-facet 的 SKILL.md、guard、install.ps1 已存在） |
| 分支 | `feat/m6-facet-docs` |

## 目標

讓 rgs-facet 成為 RGS 文件中正式的第三個指令：使用者讀 README 就知道它做什麼、何時用、怎麼裝、有什麼限制；rgs-core 的規則與參考文件、rgs-main／rgs-pr 的 description 都和它一致、互相區隔。

**先讀這些檔案再動手**：`skills/rgs-facet/SKILL.md`、`skills/rgs-facet/scripts/facet_review.py`（docstring 的 status 表）、`skills/rgs-facet/references/summary-format.md`、`install.ps1`、`README.md`、`README.en.md`、`skills/rgs-core/roles.md`、`skills/rgs-core/references/scripts.md`、`skills/rgs-core/references/agy-cli.md`、`skills/rgs-pr/SKILL.md`、`skills/rgs-main/SKILL.md`、`docs/origins/facet/preflight-results.md`。

## 可修改的檔案

<!-- rgs.py 只讀取這個標題下的 `路徑` 清單，guard 會擋下清單以外的寫入。 -->

- `README.md`：加入 rgs-facet
- `README.en.md`：與中文版同步
- `skills/rgs-core/roles.md`：角色表與規則 7
- `skills/rgs-core/references/agy-cli.md`：補上 Facet 預檢的實測結果
- `skills/rgs-core/references/scripts.md`：確認 `facet_review.py` 一節與實際程式一致（M4 已加，只修不一致處）
- `skills/rgs-pr/SKILL.md`：plan 第 5 步、description
- `skills/rgs-main/SKILL.md`：description

## 設計與實作要點

### README.md（繁體中文）

1. 開頭一段：從「兩個 skill」改成「三個 skill」，一句話說明 rgs-facet 是在 Plan 模式下讓 Gemini 審查 Claude 的計畫。
2. 目錄加上新章節的連結；章節「兩個指令怎麼選」改名為「三個指令怎麼選」（連結一併更新）。
3. 「這是什麼」的角色表加一列：**agy 計畫審查者（rgs-facet）**：在空的暫存工作區、只能交回結果（sealed guard），從 logic、gaps、verifiability 三個角度審查計畫；不能讀寫任何檔案。
4. 「三個指令怎麼選」的比較表加一欄 `/rgs-facet`：適合「要動手之前，先讓另一家模型把計畫挑過一遍」；流程「Plan 模式起草 → 三個角度送審 → Claude 逐條裁決、修訂、重審（最多 3 輪）→ 一次 ExitPlanMode 交出附審查摘要的計畫」；產出「Plan 模式的計畫檔（含審查摘要與附錄）」；子指令「無」。表後補一句：rgs-facet 只審計畫、不寫程式；計畫核准後可以接著用 `/rgs-main` 或 `/rgs-pr` 實作。
5. 「安裝」：`install.ps1` 現在連結三個資料夾加上 rgs-core；說明 `~/.claude/commands/rgs-facet.md` 存在時會警告。
6. 新章節「教學三：用 /rgs-facet 審查計畫」（放在教學二之後、委派之前），內容：
   - 什麼時候用、會把計畫全文送到 Google（Gemini）以及同意的規則。
   - 步驟：輸入 `/rgs-facet <任務>` → Claude 進 Plan 模式、偵察、釐清、起草 → 每輪三個角度依序送審（每次約 1–3 分鐘）→ 裁決與修訂 → 交出計畫。
   - 參數（`REVIEWER_MODEL` 等）在 `skills/rgs-facet/SKILL.md` 開頭，換模型只改一行；升級模型後先跑 `doctor.py --flow facet --model <M>`。
   - 審查失敗、逾時、偵測到改檔時的行為（不算核准、不換模型、最多重試 1 次、會問你要不要不經審查直接交付）。
   - 原始紀錄的位置（系統暫存目錄的 `rgs-facet/<session>/`）。
   - **Plan 模式的權限**：skill 的 `allowed-tools` 只在呼叫那一回合有效，之後每次送審可能都要確認；附上可加進 `.claude/settings.json` 的 `permissions.allow` 規則範例（`Bash(python -I <你的家目錄>/.claude/skills/rgs-facet/scripts/facet_review.py:*)` 這類寫法，用佔位符，不要寫本機絕對路徑）。
   - **觸發**：description 被 skill 清單預算拿掉時不會自動觸發，`/rgs-facet` 一定可用；可用 `skillOverrides` 或 `skillListingBudgetFraction` 調整（附官方 skills 文件連結 `https://code.claude.com/docs/en/skills`）。
7. 「安全機制」加上 rgs-facet 的四層防護：參數由腳本寫死並檢查、審查者的工作區是空的暫存資料夾、sealed guard 只放行 `finish`／`wait`、呼叫前後比對專案與工作區快照；Claude 端的 `guard_agy.py` 擋下直接執行 `agy`。寫明**未覆蓋範圍**：`.gitignore` 的檔案、專案以外的檔案不在快照比對範圍；你自己同時改檔會被當成改動。
8. 「repo 結構與開發」的樹狀圖加上 `skills/rgs-facet/`（`SKILL.md`、`references/`、`scripts/`、`tests/`）與 `docs/origins/facet/`；測試指令改成兩行（`skills/rgs-core/tests` 與 `skills/rgs-facet/tests`）。
9. 「已驗證範圍與限制」：加上 rgs-facet 的實測狀態——單元測試與 sealed 工作區的真 agy 呼叫已驗證；Plan 模式完整流程、觸發測試待本機驗收；macOS／Linux 未驗證；hook 指令中 `${CLAUDE_SKILL_DIR}` 是否會被代入待實測。
10. 所有測試數、指令、路徑必須和程式一致；不要寫本機絕對路徑或 commit hash。

### README.en.md

和中文版逐節同步（同樣的章節、表格、範例），用自然的英文。章節錨點依英文標題。

### roles.md

- 標題的「（/rgs-main 與 /rgs-pr 共用）」改成也涵蓋 /rgs-facet，或加註 rgs-facet 另有 SKILL.md 中的硬規則。
- 角色表加一列：**agy 計畫審查者（rgs-facet，新對話、sealed guard）**：從一個角度審查計畫並以 JSON 回報；禁止使用任何工具、讀寫任何檔案。
- 規則 7「產出不放 Temp」補上例外：rgs-facet 在 Plan 模式下只能寫計畫檔，而且要能用在沒有 `.rgs/` 的專案，所以原始紀錄放在系統暫存目錄，路徑寫在計畫附錄（`docs/rgs/design.md` D-12）。

### agy-cli.md

在合適的位置補上（來源：`docs/origins/facet/preflight-results.md`）：
- 模型：`gemini-4-argon-{low,medium,high}` 的額度和 3.8 分開；rgs-facet 預設用 `gemini-4-argon-high`。
- 把整份內容放在 `-p` 參數最快最便宜（約 9 秒、1.7 萬 tokens；stdin 或讓它讀檔約 60 秒、6–8 萬 tokens）；Windows 命令列上限約 32K 字元。
- 一次計畫審查約 43–155 秒。
- `agy models` 沒有 JSON 輸出，每行是「ID〔Tab〕顯示名稱」。
- `--log-file` 中的 `label="…"` 是 agy 用戶端解析的模型（若 M2 已寫就不要重複）。

### scripts.md

對照 `facet_review.py` 的 docstring 與 argparse，確認參數表、status／exit code 表、call 目錄檔案清單一致；只修正不一致處。

### rgs-pr/SKILL.md

- `plan <需求>` 第 5 步改成：設計牽涉不熟的領域或風險較高時，可以先用 `/rgs-facet` 讓 Gemini 從 logic、gaps、verifiability 審查設計（在 Plan 模式下進行，結果附在設計文件），或照舊用 `review.py --diff-base <base> --spec docs/rgs/design.md`。逐條裁決意見。
- description 結尾加一句：只想讓其他模型審查計畫、不實作時，改用 rgs-facet。總長仍要合理（不超過 1,536 字元）。

### rgs-main/SKILL.md

- description 結尾加一句：只想讓其他模型審查計畫、不實作時，改用 rgs-facet。

## 不要做

- 不要修改上面清單以外的檔案，包括程式、測試、`install.ps1`、`skills/rgs-facet/` 底下的任何檔案、知識庫 `CLAUDE.md`、`docs/rgs/`。
- 不要改變 rgs-main／rgs-pr 的流程步驟（除了 rgs-pr plan 第 5 步）。
- 不要寫本機絕對路徑、使用者名稱或 commit hash。

## 驗收條件

- [ ] 1. README 中英文版都有 rgs-facet 的用途、比較表欄位、安裝、教學三、安全機制與未覆蓋範圍、Plan 模式權限備案、觸發調整、repo 結構、已驗證範圍，兩版內容一致。
- [ ] 2. `roles.md` 有 rgs-facet 計畫審查者的角色列與規則 7 的例外。
- [ ] 3. `agy-cli.md` 補上 Gemini 4 模型、`-p` 長度與耗時、`agy models` 格式。
- [ ] 4. `scripts.md` 的 `facet_review.py` 一節與程式一致。
- [ ] 5. rgs-pr plan 第 5 步提到 `/rgs-facet`；三個 skill 的 description 互相區隔。
- [ ] 6. 文件中的指令、路徑、測試數和程式一致；沒有本機絕對路徑。
- [ ] 7. `python -m unittest discover -s skills/rgs-core/tests` 與 `skills/rgs-facet/tests` 仍全部通過（本里程碑不改程式）。

## 必要測試

本里程碑只改文件，沒有新測試；以 auditor 稽核與兩個測試指令確認沒有破壞既有行為。

## 先前里程碑的教訓

1. 文件與程式要一致：測試數、指令、路徑、參數名稱都以程式為準（R-11）。
2. repo 是公開的：不要寫本機絕對路徑、帳號或私人專案內容（知識庫「機密規則」）。
3. 交給 agy 的參數不能出現主 checkout 的路徑（PR #2 fix-1）——在文件描述 rgs-facet 的工作區時要寫對。
