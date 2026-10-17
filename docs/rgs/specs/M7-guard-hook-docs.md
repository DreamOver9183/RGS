# M7：依本機驗收修正 guard hook 與文件

> /rgs-pr 的里程碑規格。由 Claude 依 design.md 撰寫；PR 合併時一併存進 `docs/rgs/specs/`。

| 項目 | 內容 |
| :-- | :-- |
| 對應需求 | R-8、R-9、R-11（`docs/rgs/requirements.md`） |
| 相依 | M1–M6（都已合併） |
| 分支 | `fix/m7-guard-hook-docs` |

## 目標

本機驗收（2026-10-18）發現 Claude 端的 guard 沒有生效，也確認了幾個實測事實。這個里程碑修正 guard 的 hook 指令，補強 guard 的判斷（PR #5 延後的審查意見），並把驗收結果寫進文件。

已實測確認的事實（不用再驗證，照這些寫）：

1. skill frontmatter 的 hook **會執行**，但 hook 指令中的 `${CLAUDE_SKILL_DIR}` **不會被代入，也不是環境變數**（兩者都是空字串）。hook 執行時拿得到 `$CLAUDE_PROJECT_DIR`，工作目錄是專案資料夾。所以現在的 `python -I "${CLAUDE_SKILL_DIR}/scripts/guard_agy.py" || true` 會變成找不到 `/scripts/guard_agy.py`，被 `|| true` 吞掉，guard 等於沒有。
2. 改成 `python -I "$HOME/.claude/skills/rgs-facet/scripts/guard_agy.py" || true` 後，guard 成功擋下 `agy --version`（拋棄式 skill 實測）。這個寫法只在 rgs-facet 安裝在個人層（`install.ps1` 的預設位置 `~/.claude/skills/`）時有效。
3. SKILL.md **內文**的 `${CLAUDE_SKILL_DIR}` 會被代入，展開成 `C:/Users/<使用者>/.claude/skills/rgs-facet`（正斜線）。
4. Plan 模式試跑時，`doctor.py` 與三次 `facet_review.py` 都沒有跳出權限確認：審查迴圈在同一回合內完成，`allowed-tools` 就夠用。只有迴圈跨回合時才需要 settings 的權限規則。
5. 觸發測試（無頭模式，每句一個新 session）：`/rgs-facet` 觸發；9 句自然語句全部觸發；10 句不該觸發的 0 句誤觸發，其中「用 Gemini 寫」「讓 Gemini 寫、你審」載入 rgs-main，「照 SOP 開 PR」載入 rgs-pr。
6. Plan 模式完整試跑（sandbox 的 calc 專案）：三個角度第 1 輪都 APPROVED（Gemini 4 Argon (High)，各 32–53 秒），快照無變動；計畫檔照 `summary-format.md` 寫入審查摘要與附錄；原始紀錄在 `%TEMP%/rgs-facet/<session id>/`。

## 可修改的檔案

<!-- rgs.py 只讀取這個標題下的 `路徑` 清單，guard 會擋下清單以外的寫入。 -->

- `skills/rgs-facet/SKILL.md`：hook 指令與「備註」
- `skills/rgs-facet/scripts/guard_agy.py`：攔下子 shell 括號與 `command`、`eval` 前綴
- `skills/rgs-facet/tests/test_skill_md.py`：hook 路徑的檢查
- `skills/rgs-facet/tests/test_guard_agy.py`：新的真與假案例
- `README.md`：權限規則、guard 限制、已驗證範圍
- `README.en.md`：與中文版同步

## 設計與實作要點

1. **SKILL.md 的 hook 指令**改成（其他 frontmatter 不動）：
   ```yaml
   command: python -I "$HOME/.claude/skills/rgs-facet/scripts/guard_agy.py" || true
   ```
   「備註」第三點（目前寫「`${CLAUDE_SKILL_DIR}` 是否會被代入…待實測」）改寫成實測結果：hook 指令中的 `${CLAUDE_SKILL_DIR}` 不會被代入，所以 hook 用 `$HOME/.claude/skills/rgs-facet/...`；**guard 只在 rgs-facet 安裝於個人層（`install.ps1` 的預設位置）時生效**，裝在其他位置時 guard 不會生效，但也不會擋到其他指令。第一點（`allowed-tools` 只在當回合有效）補一句：審查迴圈通常在同一回合內完成，實測不會跳出確認。
2. **guard_agy.py**：
   - 在去除開頭前綴的迴圈中，也去掉開頭的 `(`（POSIX 子 shell，例如 `(agy -p x)`、`( agy -p x )`）與 `{`（群組指令，例如 `{ agy -p x; }`）。
   - `CALL_EXEC_ENV_PATTERN` 加上 `command`、`eval`、`time`、`nohup`、`sudo`，讓 `command agy -p x`、`eval agy -p x`、`time agy`、`nohup agy`、`sudo agy` 都被攔下。`eval "agy -p x"` 這種整段被引號包住的情況：去掉前綴後若片段以引號開頭，取引號內字串的第一個詞判斷（現有的引號處理已經這樣做，確認它涵蓋這個情況）。
   - 第一個詞去掉結尾的 `)`、`;`、`}`（現在只去 `)`）。
   - 不要改變現有的放行行為：`python -I .../facet_review.py ...`、`grep agy notes.md`、`echo agy`、`ls`、`git log`、`python agy_helper.py` 仍然放行；壞輸入仍然放行、exit 0。
3. **test_skill_md.py**：`test_frontmatter_fields` 加上兩個斷言：frontmatter 含 `$HOME/.claude/skills/rgs-facet/scripts/guard_agy.py`；frontmatter 的 hook 指令**不含** `${CLAUDE_SKILL_DIR}`（`allowed-tools` 那一行仍然可以有，所以只檢查 `command:` 那一行）。斷言都附上指出是哪一項檢查的訊息。
4. **test_guard_agy.py**：
   - `test_direct_agy_true_cases` 加上：`(agy -p x)`、`( agy -p x )`、`{ agy -p x; }`、`command agy -p x`、`eval agy -p x`、`eval "agy -p x"`、`time agy --version`、`nohup agy -p x`、`sudo agy --version`。
   - `test_direct_agy_false_cases` 加上：`(cd sub && ls)`、`command -v python`、`eval echo hi`、`time python -I x.py`。
   - 真的執行 hook 的測試（`test_direct_agy_denied`）加一個子 shell 的案例：`(agy -p x)` 要回拒絕的 JSON，並斷言 `permissionDecisionReason` 含 `facet_review.py`。
5. **README.md／README.en.md**（兩版同步）：
   - 「教學三」的「Plan 模式的權限」：改成實測結果——審查迴圈通常在同一回合內完成，`allowed-tools` 已預先核准，不會跳出確認；只有迴圈跨回合（例如中途停下來問你）時才可能要確認，這時可以把下列規則加進 `.claude/settings.json` 的 `permissions.allow`：`"Bash(python -I C:/Users/<使用者>/.claude/skills/rgs-facet/scripts/facet_review.py:*)"`（`${CLAUDE_SKILL_DIR}` 實測展開成這種正斜線路徑；macOS／Linux 換成對應的家目錄路徑）。刪掉「確切格式尚待本機驗收確認」那句。
   - 「安全機制」的 rgs-facet 第 4 層（Claude 端 guard）補上限制：只在 rgs-facet 安裝於個人層（`~/.claude/skills/`，`install.ps1` 的預設）時生效；它是第二道防線，agy 端的唯讀由 sealed guard 保證。
   - 「已驗證範圍與限制」的 rgs-facet 一點改寫成本機驗收結果：安裝、觸發測試（`/rgs-facet` 觸發、自然語句 9/9、誤觸發 0/10）、Plan 模式完整試跑、guard（修正後以 `$HOME` 路徑實測擋下）都已在 Windows 驗證；macOS／Linux 未驗證。刪掉「待本機驗收」「`${CLAUDE_SKILL_DIR}` 是否會被代入待實測」的字樣。

## 不要做

- 不要修改上面清單以外的檔案，包括 `facet_review.py`、rgs-core、`install.ps1`、知識庫、`docs/rgs/`。
- 不要改 guard 的 fail-open 行為與輸出格式。
- 不要在文件寫本機的完整使用者名稱或 commit hash（用 `<使用者>`、`<user>` 佔位）。

## 驗收條件

- [ ] 1. SKILL.md 的 hook 指令是 `python -I "$HOME/.claude/skills/rgs-facet/scripts/guard_agy.py" || true`，不含 `${CLAUDE_SKILL_DIR}`；備註寫明實測結果與個人層安裝的限制。
- [ ] 2. `is_direct_agy` 攔下子 shell、群組指令與 `command`、`eval`、`time`、`nohup`、`sudo` 前綴；既有的放行案例不變。
- [ ] 3. README 中英文版的權限說明、guard 限制、已驗證範圍符合實測事實，兩版一致。
- [ ] 4. `python -m unittest discover -s skills/rgs-facet/tests` 與 `skills/rgs-core/tests` 全部通過。

## 必要測試

| 測試檔 | 案例 | 對應驗收條件 |
| :-- | :-- | :-- |
| `skills/rgs-facet/tests/test_skill_md.py` | hook 指令用 `$HOME` 路徑、不含 `${CLAUDE_SKILL_DIR}` | 1 |
| `skills/rgs-facet/tests/test_guard_agy.py` | 新增的真與假案例；子 shell 案例的真實 hook 執行 | 2 |

## 先前里程碑的教訓

1. 錯誤案例要斷言訊息內容（PR #2、#3）：拒絕案例斷言 `permissionDecisionReason` 含 `facet_review.py`。
2. 程式刻意區分的邊界要有專屬測試：「agy 是指令」與「agy 只是參數」（例如 `command -v python`、`eval echo hi` 要放行）。
3. 文件與程式要一致，不寫本機絕對路徑（R-11、知識庫）。
