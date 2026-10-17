# M4：`facet_review.py`

> /rgs-pr 的里程碑規格。由 Claude 依 design.md 撰寫；PR 合併時一併存進 `docs/rgs/specs/`。

| 項目 | 內容 |
| :-- | :-- |
| 對應需求 | R-7（`docs/rgs/requirements.md`） |
| 相依 | M1（`prompt.py`、`verdict.py`）、M3（`isolated_workspace(sealed=)`、`snapshot`）；M2 的 `call_agy(role=, grace_s=)` 與 `reported_model` |
| 分支 | `feat/m4-facet-review` |

## 目標

新增 `skills/rgs-facet/scripts/facet_review.py`：完成**一次送審**（一份計畫、一個角度、一輪），把結果整理成一行 JSON 印在 stdout，並在 run 目錄留下完整紀錄。rgs-facet 的 SKILL.md（M5）會在每輪對三個角度各呼叫它一次，再由 Claude 逐條決定採納或駁回。

## 可修改的檔案

<!-- rgs.py 只讀取這個標題下的 `路徑` 清單，guard 會擋下清單以外的寫入。 -->

- `skills/rgs-facet/scripts/facet_review.py`（新檔）：命令列
- `skills/rgs-facet/tests/test_facet_review.py`（新檔）：端對端測試
- `skills/rgs-core/tests/fake_agy.py`：新情境 `structured`、`ws_write` 與環境變數 `FAKE_AGY_TOUCH`
- `skills/rgs-core/references/scripts.md`：新增 `facet_review.py` 一節

## 設計

### 命令列

```text
python -I facet_review.py --plan-file <計畫檔> --lens logic|gaps|verifiability --round <N> --model <M>
                          [--timeout 300] [--session <ID>] [--run-dir <資料夾>] [--repo <專案資料夾>] [--prior-stdin]
```

| 參數 | 說明 |
| :-- | :-- |
| `--plan-file` | 必填。計畫檔；只送出 `<!-- facet:appendix -->` 之前的內容（`prompt.load_plan`） |
| `--lens` | 必填。`prompt.LENSES` 之一 |
| `--round` | 必填。從 1 起算的整數 |
| `--model` | 必填。agy 模型 ID（`call_agy` 會檢查必須是 `gemini-` 開頭） |
| `--timeout` | 秒，預設 300（D-10）。正整數 |
| `--session` | 預設取環境變數 `CLAUDE_SESSION_ID`，沒有時用 `'manual'`。只允許英數、`-`、`_`、`.`，而且不能是 `.` 或 `..`（第 1 輪審查後補上），其他情況是 `usage_error`（它會成為資料夾名稱）。SKILL.md 會用 Claude Code 代入的 `${CLAUDE_SESSION_ID}` 明確傳入 |
| `--run-dir` | 預設 `os.path.join(tempfile.gettempdir(), 'rgs-facet', <session>)`（D-12） |
| `--repo` | 預設目前工作目錄。用來做呼叫前後的快照比對 |
| `--prior-stdin` | 第二輪起必須加：從 stdin 讀前輪處置 JSON（格式見 `prompt.PRIOR_SCHEMA`），以 UTF-8 解碼 `sys.stdin.buffer` |

每次呼叫的紀錄放在 `<run-dir>/r<N>-<lens>/`（下稱 call 目錄），已存在就沿用（重試時會覆蓋同名檔案）。

### status 與 exit code（D-13）

| status | exit | 何時 |
| :-- | --: | :-- |
| `ok` | 0 | 拿到合法的 verdict |
| `timeout` | 2 | `AgyResult.kind == 'timeout'` |
| `agy_error` | 3 | `kind` 是 `error` 或 `quota`；或找不到 agy（`rc.find_agy()` 丟 `RgsError`） |
| `empty_output` | 4 | `kind == 'empty'`（沒有 `structured_output`） |
| `parse_error` | 5 | `structured_output` 是字串且 `verdict.parse_response` 失敗 |
| `schema_error` | 5 | `verdict.validate` 失敗 |
| `workspace_modified` | 6 | 呼叫期間 repo 或工作區有變動。**優先於呼叫 agy 之後的所有其他 status** |
| `secret_suspected` | 7 | `prompt.scan_secrets` 有命中；不呼叫 agy |
| `forbidden_flag` | 8 | `call_agy` 丟 `RgsError`（參數或模型不合規）；不呼叫 agy |
| `plan_too_long` | 9 | `PromptError('plan_too_long')`；不呼叫 agy |
| `usage_error` | 10 | 參數錯誤、計畫檔或 `--repo` 不存在、前輪資料缺漏或格式錯（`PromptError('invalid_prior')`、stdin 不是 JSON）；不呼叫 agy |

argparse 預設的錯誤 exit code 是 2，會和 `timeout` 撞號：用 `ArgumentParser` 的子類別覆寫 `error(message)`，丟出自訂例外，由 `main()` 轉成 `usage_error`。`--help` 照常 exit 0。

### 流程

```python
HERE = os.path.dirname(os.path.abspath(__file__))
CORE_SCRIPTS = os.path.normpath(os.path.join(HERE, '..', '..', 'rgs-core', 'scripts'))
# 兩個資料夾都加進 sys.path（已存在就不重複），再 import rgs_common as rc、prompt、verdict
```

`main()` 一開始呼叫 `rc.setup_stdio()`。之後依序：

1. 解析參數；檢查 `--plan-file` 是檔案、`--repo` 是資料夾、`--round >= 1`、`--timeout >= 1`，不符合就 `usage_error`。
2. 建立 call 目錄。
3. `plan_text = prompt.load_plan(plan_file)`。
4. `hits = prompt.scan_secrets(plan_text)`：有命中 → `secret_suspected`，輸出帶 `secret_hits`（已遮蔽）。
5. `--prior-stdin` 時讀 stdin 並 `json.loads`，失敗 → `usage_error`；沒加時 `prior = None`。把 prior 寫進 call 目錄的 `prior.json`。
6. `text = prompt.build_prompt(plan_text, lens, round_no, prior)`：`PromptError` 的 `kind` 是 `plan_too_long` → `plan_too_long`；`invalid_prior` → `usage_error`。把 prompt 寫進 call 目錄的 `prompt.md`。
7. schema：第一輪用 `verdict.SCHEMA_PATH`；第二輪起讀 `verdict.load_schema()`，在 `required` 加上 `'resolved'`（不重複），寫成 call 目錄的 `schema.json` 再用它（D-6）。
8. `rc.find_agy()`：`RgsError` → `agy_error`。
9. `repo_before = rc.snapshot(repo)`。
10. `ws = rc.isolated_workspace('rgs_facet_', sealed=True)`；`ws_before = rc.snapshot(ws, ignore=('.agents/**',))`。
11. 呼叫：
    ```python
    result = rc.call_agy(prompt=text, cwd=ws, model=model, schema_path=schema_path, timeout_s=timeout,
                         grace_s=15, save_as=os.path.join(call_dir, 'agy'), role='reviewer')
    ```
    `RgsError` → `forbidden_flag`（這時 agy 沒被啟動，但仍要做第 13、14 步的清理與紀錄）。
12. 依 `result.kind` 決定 status：`ok` 繼續；`timeout`、`error`／`quota`、`empty` 依上表。
    `kind == 'ok'` 時：
    - `data = result.structured`；是字串時先 `data = verdict.parse_response(data)`。
    - `verdict.validate(data, round_no=round_no)`；`VerdictError` 的 `kind` 就是 status（D-7）。
    - 每條 finding 複製一份並加上 `evidence_found = verdict.evidence_found(f['evidence'], plan_text)`。
13. 比對：`repo_changes = rc.snapshot_changes(repo_before, rc.snapshot(repo))`；`ws_new = rc.snapshot_changes(ws_before, rc.snapshot(ws, ignore=('.agents/**',)))`。任一個不是空的 → status 改成 `workspace_modified`。
14. guard 紀錄：`entries, _ = rc.guard_log_since(ws, 0)`；`guard_denials` 是 `decision == 'deny'` 的項目。把 `ws/.agents/rgs-guard.log` 複製成 call 目錄的 `guard.log`，然後 `shutil.rmtree(ws, ignore_errors=True)`。這一步放在 `finally`，確保第 11 步之後無論成功或失敗都會清掉工作區。
15. 寫 call 目錄的 `meta.json`（見下），stdout 印一行結果 JSON，回傳 exit code。

### stdout 的結果 JSON

用 `json.dumps(obj, ensure_ascii=False)` 印成**單獨一行**，欄位：

| 欄位 | 內容 |
| :-- | :-- |
| `status` | 上表之一 |
| `verdict` | `APPROVED`／`REVISE`／`BLOCKED`；沒有合法 verdict 時 `null` |
| `findings` | 加上 `evidence_found` 的 findings；沒有時 `[]` |
| `resolved` | 第二輪起的 `resolved`；沒有時 `[]` |
| `coverage`、`limitations` | 來自 verdict；沒有時 `null` |
| `lens`、`round` | 參數 |
| `requested_model` | `--model` |
| `reported_model` | `result.reported_model`；沒有時 `null` |
| `raw_dir` | call 目錄的絕對路徑 |
| `test_double` | 環境變數 `RGS_AGY` 有值時 `true` |
| `detail` | 錯誤說明（`usage_error`、`agy_error` 等）；成功時 `''` |
| `secret_hits` | 只在 `secret_suspected` 時出現 |
| `repo_changes`、`workspace_new_files` | 只在 `workspace_modified` 時出現 |

### `meta.json`

`json.dumps(..., ensure_ascii=False, indent=2)`，欄位至少有：`status`、`exit_code`、`lens`、`round`、`plan_file`、`plan_chars`、`prompt_chars`、`requested_model`、`reported_model`、`reported_model_note`（固定字串 `"agy 用戶端解析，伺服器端未確認"`）、`agy_executable`（`find_agy()` 的最後一個元素）、`agy_version`（`[*find_agy(), '--version']` 的輸出，`stdin=DEVNULL`、逾時 30 秒，失敗時 `null`）、`agy`（`result.summary()`，沒有呼叫時 `null`）、`repo`、`repo_snapshot_kind`、`repo_changes`、`workspace_new_files`、`guard_denials`、`test_double`、`started`、`finished`（ISO 時間字串）、`duration_s`。在第 9 步之前就結束的情況，沒有的欄位填 `null` 或空清單。

### 測試替身 `fake_agy.py` 的新功能

- 環境變數 `FAKE_AGY_TOUCH`：有值時（絕對路徑），在處理任何情境之前，對該檔案附加一行文字（模擬 agy 寫到工作區以外）。
- 情境 `structured`：`structured_output` 直接用 `json.loads(os.environ['FAKE_AGY_STRUCTURED'])`，不看 schema 的內容；其餘輸出和成功時一樣。
- 情境 `ws_write`：在目前工作目錄建立 `probe.txt`，然後和 `structured` 一樣輸出。
- 不要改既有情境的行為；更新檔案開頭 docstring。

## 實作要點

1. 只用標準函式庫；跨平台（不依賴 shell，子程序 stdin 用 `DEVNULL`）。
2. 重用：`prompt.load_plan`、`scan_secrets`、`build_prompt`、`PromptError`、`LENSES`；`verdict.SCHEMA_PATH`、`load_schema`、`parse_response`、`validate`、`evidence_found`、`VerdictError`；`rc.setup_stdio`、`find_agy`、`snapshot`、`snapshot_changes`、`isolated_workspace`、`call_agy`、`guard_log_since`、`write_text`、`RgsError`。不要重寫這些功能。
3. 不要用 `call_with_fallback`：rgs-facet 不換模型（D-9）。
4. 檔案開頭 docstring 寫用法、status 與 exit code 表，以及「只做一次送審，重試與多輪迴圈由 SKILL.md 負責」。
5. 測試（`test_facet_review.py`）用 `subprocess.run([sys.executable, '-I', <facet_review.py>, ...])` 執行，`env` 設 `RGS_AGY=<rgs-core/tests/fake_agy.py>`、`FAKE_AGY_DIR=<暫存>`、`FAKE_AGY_SCENARIO`，`--run-dir` 指到暫存資料夾，`--repo` 指到暫存資料夾（有的案例用 `git init` 建一個 repo）。每個測試自己建立與清除暫存資料夾。fake agy 的路徑用 `os.path.dirname(__file__)` 推算：`<tests>/../../rgs-core/tests/fake_agy.py`。替身記錄的呼叫在 `FAKE_AGY_DIR/calls/*.json`（含 `argv`、`cwd`、`guard`）。
6. `scripts.md` 新增「`facet_review.py`」一節：用法、參數表、status 與 exit code 表、call 目錄的檔案（`prompt.md`、`prior.json`、`schema.json`、`agy.json`、`agy.err`、`agy.log`、`agy.prompt.md`、`guard.log`、`meta.json`）。

## 不要做

- 不要修改上面清單以外的檔案，包括 `prompt.py`、`verdict.py`、`rgs_common.py`、知識庫、README。
- 不要在腳本裡做重試或多輪迴圈。
- 不要把工作區放在 repo 裡，也不要用 `--add-dir`。
- 不要重新排版無關程式碼。

## 驗收條件

- [ ] 1. 每個 status 都能由端對端測試觸發，exit code 符合上表。
- [ ] 2. `secret_suspected`、`plan_too_long`、`usage_error`、`forbidden_flag` 的情況下 agy 沒有被呼叫；`secret_suspected` 的輸出不含完整金鑰。
- [ ] 3. agy 在 sealed 的暫存工作區執行（替身記錄的 guard `role` 是 `sealed`），結束後工作區已刪除，`guard.log` 留在 call 目錄。
- [ ] 4. repo 被改動或工作區出現新檔時回報 `workspace_modified`，即使 verdict 合法也一樣；`repo_changes`／`workspace_new_files` 列出路徑。
- [ ] 5. 第二輪沒有 `--prior-stdin` 是 `usage_error`；有前輪資料時傳給 agy 的 schema 把 `resolved` 設為必填，verdict 缺 `resolved` 是 `schema_error`。
- [ ] 6. 附錄標記之後的內容不在送給 agy 的 prompt 裡。
- [ ] 7. stdout 只有一行 JSON，欄位符合上表；`meta.json` 欄位齊全；用替身時 `test_double` 是 `true`。
- [ ] 8. `python -m unittest discover -s skills/rgs-facet/tests` 與 `skills/rgs-core/tests` 全部通過。

## 必要測試

| 測試檔 | 案例 | 對應驗收條件 |
| :-- | :-- | :-- |
| `skills/rgs-facet/tests/test_facet_review.py` | `ok`（含 `evidence_found` 一真一假、參數含 `--json-schema` 與 `--model`、沒有 `--mode`） | 1、3、7 |
| 同上 | `timeout`、`error`、`quota`、`no_struct`、schema 不合、`structured_output` 是無法解析的字串 | 1 |
| 同上 | 假金鑰（執行時組出）、超過 30,000 字元、`--model claude-x`、缺參數、錯的 `--lens`、計畫檔不存在：都沒有呼叫 agy | 1、2 |
| 同上 | `ws_write`、`FAKE_AGY_TOUCH` 指向 repo 內的檔案（git repo 與一般資料夾各一次） | 4 |
| 同上 | 第二輪：沒有 `--prior-stdin`、有前輪資料且 verdict 有 `resolved`、verdict 缺 `resolved`、stdin 不是 JSON | 5 |
| 同上 | 附錄之後的文字不在替身收到的 `-p` 值裡 | 6 |
| 同上 | 不給 `--run-dir` 時：有 `--session abc-1` 落在 `<暫存>/rgs-facet/abc-1/`；沒有 `--session` 時用環境變數 `CLAUDE_SESSION_ID`；都沒有時是 `manual`；`--session ../x` 是 `usage_error`（測試把子程序的 `TEMP`、`TMP`、`TMPDIR` 指到測試自己的暫存資料夾） | 7 |

## 先前里程碑的教訓

1. 錯誤案例的測試要同時斷言錯誤種類與訊息內容，不要只斷言有丟例外（出處：Facet PR #2）。
2. 程式刻意區分的邊界要有專屬測試，例如「workspace_modified 優先於 ok」（出處：Facet PR #2）。
3. 測試中的假金鑰在執行時用字串相加組出來，不要寫成字面值（知識庫「機密規則」）。
4. Gemini 不能執行程式：特別檢查 import、函式簽章與呼叫是否和 M1–M3 的實際程式一致（先讀 `prompt.py`、`verdict.py`、`rgs_common.py` 再寫）。
5. 每個測試情境都要真的觸發到，規格要求的次要路徑也要有斷言（出處：PR #2 fix-1、fix-2）。
6. 測試的 `setUp` 要先建立它用到的資料夾：`helpers.make_repo(root)` 會以 `root` 當工作目錄執行 git，`root` 不存在時 Windows 回報 `WinError 267`（出處：PR #3 fix-1）。
7. 交給 agy 的參數不能出現主 checkout 的路徑；`facet_review.py` 的工作區用 `isolated_workspace`（系統暫存目錄），不要用 `--add-dir`（出處：PR #2 fix-1）。
8. 本分支堆疊在 M3 之上：`rgs_common` 已有 `call_agy(role=, grace_s=)`、`snapshot`、`snapshot_changes`、`isolated_workspace(sealed=)`；`fake_agy.py` 已有 `--version`、`models`、`sleep_child`、`FAKE_AGY_LABEL`。測試資料的模型名稱用 `gemini-` 開頭。
