# M1：搬入 rgs-facet 專屬模組

> /rgs-pr 的里程碑規格。由 Claude 依 design.md 撰寫；PR 合併時一併存進 `docs/rgs/specs/`。

| 項目 | 內容 |
| :-- | :-- |
| 對應需求 | R-1、R-2、R-3（`docs/rgs/requirements.md`） |
| 相依 | 無 |
| 分支 | `feat/m1-facet-modules` |

## 目標

把 Facet skill 已完成的模組搬進 RGS 的新 skill 資料夾 `skills/rgs-facet/`，並讓它的密鑰掃描改用 rgs-core 的 `secret_scan.py`，不再自己維護一份樣式表。

**worktree 裡已經有下面七個檔案**，是 Claude 從 Facet repo 原樣複製過來的（只把行尾轉成 LF），內容還是 Facet 時的樣子：

- `skills/rgs-facet/references/verdict.schema.json`
- `skills/rgs-facet/references/review-prompt.md`
- `skills/rgs-facet/scripts/verdict.py`
- `skills/rgs-facet/scripts/prompt.py`
- `skills/rgs-facet/tests/test_verdict.py`
- `skills/rgs-facet/tests/test_verdict_schema.py`
- `skills/rgs-facet/tests/test_prompt.py`

你的工作是依下面的「實作要點」調整它們，並在 rgs-core 新增 `secret_scan.scan_text`。**先完整讀過這七個檔案再動手。**

## 可修改的檔案

<!-- rgs.py 只讀取這個標題下的 `路徑` 清單，guard 會擋下清單以外的寫入。 -->

- `skills/rgs-facet/references/verdict.schema.json`：不用改（列出來只是讓範圍檢查認得這個新檔）
- `skills/rgs-facet/references/review-prompt.md`：只改說明段落中的「依據」路徑
- `skills/rgs-facet/scripts/verdict.py`：只改 docstring 中的文件路徑
- `skills/rgs-facet/scripts/prompt.py`：匯入路徑、`scan_secrets` 改用 `secret_scan.scan_text`、docstring
- `skills/rgs-facet/tests/test_verdict.py`：路徑推算
- `skills/rgs-facet/tests/test_verdict_schema.py`：路徑推算
- `skills/rgs-facet/tests/test_prompt.py`：路徑推算、改寫 `TestScanSecrets`
- `skills/rgs-core/scripts/secret_scan.py`：新增 `scan_text`
- `skills/rgs-core/tests/test_scope_secret.py`：新增 `scan_text` 的測試

## 設計

### 資料夾關係

安裝後 `rgs-facet` 和 `rgs-core` 是 `~/.claude/skills/` 底下的同層資料夾，repo 裡也是 `skills/` 底下的同層資料夾。所以 rgs-facet 的腳本一律用自身位置推算 rgs-core：

```python
HERE = os.path.dirname(os.path.abspath(__file__))
CORE_SCRIPTS = os.path.normpath(os.path.join(HERE, '..', '..', 'rgs-core', 'scripts'))
```

### `secret_scan.scan_text`（新增）

```python
def scan_text(text, profile=None, name='<text>'):
    """Scan a string, e.g. a plan before it is sent to agy.

    Returns a list of hits shaped like scan()['hits']: {'file': name, 'line': n, 'kind': k, 'match': masked}.
    Patterns are the built-in ones plus profile secrets.patterns (profile defaults to rc.DEFAULT_PROFILE).
    """
```

- 行號從 1 起算，用 `text.split('\n')` 切行（不要用 `splitlines()`：它會把 ` ` 等字元也當成換行，行號就和檔案的行號對不上）。
- 實際比對沿用既有的 `scan_lines`，遮蔽沿用既有的 `mask`，所以結果不會含完整的命中內容。
- `scan()` 裡「內建樣式加上 profile 樣式」的組裝，抽成一個共用的小函式（例如 `patterns_for(profile)`），讓 `scan()` 與 `scan_text()` 都用它。**`scan()` 的行為與回傳格式不能改變。**
- 不要修改 `BUILTIN` 的樣式。

### `prompt.scan_secrets`（改寫）

保留函式名稱與回傳格式，內部改成：

```python
def scan_secrets(text):
    """回傳命中清單，每項是 {'kind': 名稱, 'line': 從 1 起算的行號, 'match': 遮蔽後的字串}。沒有命中回傳 []。

    樣式來自 rgs-core 的 secret_scan（內建樣式）。
    """
    hits = secret_scan.scan_text(text)
    return sorted(({'kind': h['kind'], 'line': h['line'], 'match': h['match']} for h in hits),
                  key=lambda h: (h['line'], h['kind']))
```

刪掉 `SECRET_PATTERNS`。種類名稱因此變成 rgs-core 的名稱（例如 `aws-access-key`、`github-token`、`openai-key`、`private-key`、`slack-token`），長度門檻也以 rgs-core 為準。

## 實作要點

1. **`prompt.py` 的匯入**：在檔案開頭的 import 區，把 `HERE` 與 `CORE_SCRIPTS` 兩個資料夾加進 `sys.path`（已存在就不重複加），然後 `import secret_scan` 與 `import verdict`。不能依賴呼叫端事先設好 `sys.path`：rgs 的腳本一律用 `python -I` 執行，Python 3.11 起 `-I` 不會把腳本所在資料夾放進 `sys.path`。`re` 仍然用在佔位符替換，保留。
2. **docstring 與範本中的文件路徑**（Facet 的文件已搬到 `docs/origins/facet/`）：
   - `verdict.py` 第 1 行：`(docs/handoff.md §5, docs/PLAN.md §4.3)` 改成 `(docs/origins/facet/handoff.md §5, docs/origins/facet/PLAN.md §4.3)`。
   - `verdict.py` 的 `VerdictError` docstring：`（對應 PLAN §4.3 的 status）` 改成 `（對應 facet_review.py 的 status，見 docs/rgs/design.md D-13）`。
   - `prompt.py` 的模組 docstring：`docs/PLAN.md §4.3 步驟 1–2、§4.5、§4.8` 改成 `docs/origins/facet/PLAN.md §4.3 步驟 1–2、§4.5、§4.8`。
   - `prompt.py` 的 `PromptError` docstring：`（M5 會把前兩個當 status 回報）` 改成 `（facet_review.py 會把前兩個當 status 回報）`。
   - `review-prompt.md` 說明段落：`` `docs/handoff.md` §5、`docs/PLAN.md` §4.5 `` 改成 `` `docs/origins/facet/handoff.md` §5、`docs/origins/facet/PLAN.md` §4.5 ``。**`text` 區塊的內容一個字都不要動。**
3. **測試的路徑推算**：測試檔現在在 `skills/rgs-facet/tests/`，腳本在同層的 `scripts/`，範本在同層的 `references/`。
   - `test_verdict.py`、`test_prompt.py`：`SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")`，刪掉不再需要的 `REPO_ROOT`。
   - `test_verdict_schema.py` 的 `get_schema_path()`：回傳 `os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "references", "verdict.schema.json")`。
   - 測試只把 `SCRIPTS_DIR` 加進 `sys.path`，`import prompt` 必須靠 `prompt.py` 自己找到 rgs-core（這正是要點 1 要驗證的事）。
4. **改寫 `test_prompt.py` 的 `TestScanSecrets`**：
   - 命中測試：每種內建樣式各放一行假金鑰（執行時用字串相加組出來，不要寫成字面值），斷言每一行至少有一筆命中、該行的 `kind` 集合包含預期的種類、`match` 等於 `secret_scan.mask` 的結果、`json.dumps(hits)` 不含任何完整金鑰、結果依 `(line, kind)` 排序、每筆只有 `kind`、`line`、`match` 三個鍵。注意 `sk-ant-…` 同時符合 `anthropic-key` 與 `openai-key`，所以用「包含」而不是「等於」。
   - 不誤判測試：沿用原本的正常計畫文字與相似字串，但要依 rgs-core 的門檻挑選（例如 `"AK" + "IA" + "1" * 10`、`"s" + "k-" + "x" * 5`、`"gh" + "p_" + "a" * 10`、`"請勿把 PRIVATE KEY 貼進計畫"`），斷言回傳 `[]`。
   - 委派測試：同一段文字，`prompt.scan_secrets(text)` 的 `(line, kind, match)` 集合等於 `secret_scan.scan_text(text)` 的。
   - 其他測試類別（附錄截斷、範本、組裝、前輪資料、長度上限、參數檢查）不要改。
5. **`test_scope_secret.py` 新增 `ScanTextTest`**（不需要 `TempDir` 或 git repo）：
   - `BUILTIN` 的 8 種樣式各一個執行時組出的樣本，各放一行，斷言該行的命中種類包含預期種類、`file` 是預設的 `'<text>'`、行號正確、`str(hits)` 不含完整樣本。
   - 正常文字回傳 `[]`。
   - `name='plan.md'` 時每筆的 `file` 是 `'plan.md'`。
   - profile 的自訂樣式（例如 `r'corp-\d{10}'`）會命中；沒給 profile 時不會。
   - 行號以 `'\n'` 計算：文字中有 `' '` 時，後面那一行的行號不會被多算。
   - 檔案開頭已有的 `SecretScanTest` 不要改。

## 不要做

- 不要修改上面清單以外的檔案，包括知識庫、README、`rgs_common.py`、其他測試。
- 不要改 `verdict.py`、`verdict.schema.json` 的任何邏輯或資料，也不要改 `prompt.py` 中 `scan_secrets` 以外的邏輯（附錄截斷、範本解析、前輪驗證、組裝、長度上限）。
- 不要修改 `secret_scan.BUILTIN`、`scan()` 的行為與回傳格式、命令列介面。
- 不要重新排版無關程式碼，也不要把 rgs-facet 的程式改成 rgs-core 的程式風格。

## 驗收條件

- [ ] 1. `python -m unittest discover -s skills/rgs-facet/tests` 全部通過；`test_verdict.py` 與 `test_verdict_schema.py` 的測試數和 Facet 時相同（合計 34）。
- [ ] 2. `prompt.py` 沒有自己的密鑰樣式；`scan_secrets` 經由 `secret_scan.scan_text` 取得結果，回傳 `{'kind', 'line', 'match'}`，依 `(line, kind)` 排序，不含完整命中內容。
- [ ] 3. 測試只把 `skills/rgs-facet/scripts` 加進 `sys.path` 就能 `import prompt`；`prompt.py` 不依賴目前工作目錄。
- [ ] 4. `secret_scan.scan_text(text, profile=None, name='<text>')` 依設計回傳命中；`scan()` 的既有測試不變且通過。
- [ ] 5. 要點 2 列出的文件路徑都已更新，`review-prompt.md` 的 `text` 區塊與 Facet 原本的內容完全相同。
- [ ] 6. `python -m unittest discover -s skills/rgs-core/tests` 全部通過（原本 79 個加上新增的）。

## 必要測試

| 測試檔 | 案例 | 對應驗收條件 |
| :-- | :-- | :-- |
| `skills/rgs-facet/tests/test_prompt.py` | 每種內建樣式命中、遮蔽、排序、只有三個鍵；不誤判；與 `scan_text` 一致 | 2、3 |
| `skills/rgs-facet/tests/test_verdict.py`、`test_verdict_schema.py` | 既有案例在新位置通過 | 1 |
| `skills/rgs-core/tests/test_scope_secret.py` | `ScanTextTest`：8 種樣式、正常文字、`name`、profile 樣式、` ` 行號 | 4、6 |

## 先前里程碑的教訓

1. 錯誤案例的測試要同時斷言錯誤種類與訊息內容，不要只斷言有丟例外（出處：Facet PR #2）。
2. 程式刻意區分的邊界要有專屬測試，否則重構時容易被改壞（出處：Facet PR #2）。
3. 測試中的假金鑰在執行時用字串相加組出來，不要寫成字面值；repo 是公開的，commit 前的密鑰掃描也會擋下字面值（知識庫「機密規則」）。
4. Gemini 不能執行程式：特別檢查 import 是否存在、函式簽章與呼叫是否一致、測試真的斷言到該行為。
