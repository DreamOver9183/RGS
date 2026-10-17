# M3：封閉唯讀、快照、doctor

> /rgs-pr 的里程碑規格。由 Claude 依 design.md 撰寫；PR 合併時一併存進 `docs/rgs/specs/`。

| 項目 | 內容 |
| :-- | :-- |
| 對應需求 | R-5、R-6（`docs/rgs/requirements.md`） |
| 相依 | M2（同樣修改 `rgs_common.py`；M2 未合併時堆疊在它的分支上） |
| 分支 | `feat/m3-sealed-snapshot-doctor` |

## 目標

替 rgs-facet（之後的 M4）準備三樣 rgs-core 的能力（`docs/rgs/design.md` D-8）：

1. **封閉的唯讀工作區**：guard 新增 `sealed` 角色，只放行 `finish`、`wait`；`isolated_workspace` 可以選用。
2. **資料夾快照**：呼叫 agy 前後各拍一次，比對專案或工作區有沒有被改動。
3. **不需要 repo 的環境檢查**：`doctor.py --flow facet --model <M>`。

## 可修改的檔案

<!-- rgs.py 只讀取這個標題下的 `路徑` 清單，guard 會擋下清單以外的寫入。 -->

- `skills/rgs-core/scripts/guard.py`：`sealed` 角色
- `skills/rgs-core/scripts/rgs_common.py`：`isolated_workspace` 加 `sealed` 參數；新增 `snapshot`、`snapshot_changes`
- `skills/rgs-core/scripts/doctor.py`：`--flow facet`、`--model`
- `skills/rgs-core/tests/fake_agy.py`：支援 `--version` 與 `models`
- `skills/rgs-core/tests/test_guard.py`：新增 sealed 測試
- `skills/rgs-core/tests/test_common.py`：新增 `isolated_workspace`、快照測試
- `skills/rgs-core/tests/test_doctor.py`：新增 `--flow facet` 測試
- `skills/rgs-core/references/scripts.md`：`doctor.py` 的參數說明
- `skills/rgs-core/references/agy-cli.md`：guard 角色說明加上 `sealed`

## 設計

### guard 的 `sealed` 角色

```python
SEALED_TOOLS = {'finish', 'wait'}
```

在 `decide(policy, call)` 的**最前面**（計算 `roots` 之前）：

```python
if policy.get('role') == 'sealed':
    if name in SEALED_TOOLS:
        return None
    return f'{name}: only finish and wait are allowed in a sealed run'
```

放在最前面的原因：sealed 的 policy 不一定有 `roots`，而且不論工具或參數長什麼樣子都要拒絕，不能落到 `NEUTRAL_TOOLS`（含 `invoke_subagent`、`send_message`）或唯讀工具的分支。`main()` 不用改：例外與缺少 policy 時本來就拒絕。更新檔案開頭 docstring 的 policy 說明，把 `"sealed"` 列進 `role`，並說明它只放行 `finish`（`--json-schema` 的結果經由它交回）與 `wait`。

### `isolated_workspace`

```python
def isolated_workspace(prefix, files=None, deny=(), read_commands=False, sealed=False):
    """An empty temp folder (plus the given files) guarded read-only, for agy calls that need no repo.

    sealed=True allows only finish and wait: the model cannot read, list, run commands or start subagents.
    """
```

`sealed=True` 時 policy 的 `role` 是 `'sealed'`，其他欄位照舊；`sealed=False` 的行為完全不變（batch、digest 用的就是這個）。

### `snapshot` 與 `snapshot_changes`

```python
def snapshot(path, ignore=()):
    """A comparable fingerprint of a folder (design D-8). Equal 'digest' values mean nothing changed.

    Inside a git work tree the whole work tree is fingerprinted: HEAD plus every path that
    `git status --porcelain -uall` reports, with a SHA-256 of its current content ('deleted' when gone).
    Files that .gitignore hides are not covered. Elsewhere every file is fingerprinted by size and
    mtime_ns (the .git folder is skipped). ignore: match_any() patterns on '/'-separated relative paths.
    Returns {'kind': 'git'|'files', 'root': <folder>, 'digest': <hex>, 'entries': {rel: fingerprint}}.
    """


def snapshot_changes(before, after):
    """Sorted relative paths whose fingerprint differs (added, removed or changed); '<HEAD>' when HEAD moved."""
```

細節：

- **判斷 git**：`run(['git', 'rev-parse', '--show-toplevel'], cwd=path, check=False)`，returncode 為 0 時是 git 模式，`root` 取它的輸出（`os.path.normpath`）；否則 `root = os.path.abspath(path)`，走檔案模式。
- **git 模式**：
  - `entries['<HEAD>']`：`git rev-parse HEAD` 的輸出；還沒有任何 commit 時是 `'none'`（`check=False`，returncode 不為 0 就當 `'none'`）。
  - 用既有的 `changed_files(root)` 取得 `(status, path)`；被 `ignore` 命中的路徑略過。每個路徑的 fingerprint 是 `f'{status}:{sha}'`，`sha` 是該檔內容的 SHA-256（`hashlib`，以二進位讀檔），檔案不存在時是 `'deleted'`，是資料夾時是 `'dir'`。
  - 這樣「本來就已修改的檔案又被改了一次」也偵測得到，因為內容雜湊變了。
- **檔案模式**：`os.walk(root)`，從 `dirnames` 移除 `.git`；每個檔案的相對路徑轉成 `/` 分隔，被 `ignore` 命中就略過；fingerprint 是 `f'{st.st_size}:{st.st_mtime_ns}'`。
- **`digest`**：`hashlib.sha256(json.dumps(entries, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()`。
- **`snapshot_changes`**：兩邊 `entries` 的鍵取聯集，fingerprint 不同（或只出現在一邊）的鍵，排序後回傳。`<HEAD>` 也照同樣規則出現在結果裡。兩份快照的 `kind` 或 `root` 不同時丟 `RgsError`。
- 檔案開頭 import 加上 `hashlib`（若還沒有）。

### `doctor.py --flow facet --model <M>`

- `--flow` 的 choices 加上 `facet`；新增 `--model`（預設 `None`）。
- `--flow facet` 搭配 `--init` 時用 `ap.error('--init is not used with --flow facet')`。
- `--flow facet` 時的檢查（依序加入 `checks`）：
  1. `python`、`agy`：和現在一樣。
  2. `model`：`--model` 沒給 → `fail`（detail 說明要傳 `--model`）；不以 `gemini-` 開頭 → `fail`（detail 說明 agy 的預設模型可能是 Claude）；否則 `ok`。
  3. `agy models`：只要 agy 存在且有給 `--model`，**不論有沒有 `--quick`** 都執行 `agy models`。逐行取第一個欄位（以空白或 Tab 切開的第一個字串）當模型 ID，`--model` 完全等於其中一個才是 `ok`，否則 `fail`（detail 列出 `not listed: <M>`）。不能用子字串比對：`gemini-4-argon` 不能因為輸出有 `gemini-4-argon-high` 就算通過。`agy models` 的 exit code 不是 0 也是 `fail`。
  4. `agy quota`：沒有 `--quick` 時照現在的方式執行（`warn`／`ok`）。
- `--flow facet` 時**完全不做** git repo、profile、remote、base branch、current branch、git identity、working tree、knowledge base、worktree root、gh 的檢查，所以在非 git 資料夾也能執行。
- `--flow main`／`pr` 的行為完全不變。
- 更新 docstring 的 Usage。

### 測試替身 `fake_agy.py`

在 `main()` 的最前面（讀任何環境變數或寫 `calls/` 之前）：

- `sys.argv[1:] == ['--version']`：印出 `agy 1.4.0`，exit 0。
- `sys.argv[1:2] == ['models']`：印出模型清單，每行 `ID\t顯示名稱`，exit 0。清單取環境變數 `FAKE_AGY_MODELS`（以 `;` 分隔的 ID，顯示名稱用 `'Fake ' + ID`）；沒設定時用 `gemini-4-argon-high`、`gemini-3.8-flash-high`、`gemini-3.8-flash-low` 三個。

更新檔案開頭 docstring。

## 實作要點

1. `guard.py`：只加 `SEALED_TOOLS` 與 `decide` 最前面那段，再更新 docstring。其他判斷不要動。
2. `rgs_common.py`：`isolated_workspace` 只改簽章、docstring 與 `role` 的選擇；`snapshot`、`snapshot_changes` 放在 `isolated_workspace` 附近。重用既有的 `run`、`changed_files`、`match_any`。
3. `doctor.py`：把「repo 相關的檢查」整段包在 `if args.flow != 'facet':` 裡；`if not args.quick:` 底下原本的 `agy models` 檢查依賴 profile，`facet` 時改走上面第 3 點的分支。注意 `profile` 變數在 facet 流程不存在，不要在 facet 分支用到它。
4. 測試：
   - `test_guard.py`：新增 `SealedTest`：
     - `finish`、`wait` 放行（`decide` 回 `None`）。
     - `write_to_file`、`view_file`、`list_dir`、`grep_search`、`run_command`（即使是 `Get-ChildItem`）、`invoke_subagent`、`send_message`、`task_boundary`、未知工具都被拒，訊息含工具名稱。
     - 沒有 `roots` 的 sealed policy 也能判斷。
     - 用 `HookProcessTest` 的方式真的執行 `rgs-guard.py`：sealed policy 下 `finish` 是 allow、`view_file` 是 deny，而且兩筆都寫進 `rgs-guard.log`。
   - `test_common.py`：
     - `isolated_workspace(..., sealed=True)` 的 `.agents/rgs-guard.json` 的 `role` 是 `sealed`，指定的檔案有寫入；不傳 `sealed` 時仍是 `reviewer`。
     - `SnapshotTest`（檔案模式，在 `TempDir` 底下建一般資料夾）：沒變動時 `digest` 相同、`snapshot_changes` 是 `[]`；新增、刪除、修改（內容長度改變，以及長度不變但用 `os.utime` 改了修改時間）各自出現在 `snapshot_changes`；`ignore=('.agents/**',)` 時 `.agents/` 底下的變動不算；`.git` 資料夾被略過。
     - `SnapshotTest`（git 模式，用 `helpers.make_repo`）：沒變動時相同；修改追蹤中的檔案、新增未追蹤檔、刪除追蹤中的檔案，各自出現在結果裡；已修改的檔案再改一次內容也偵測得到；新的 commit 讓結果含 `<HEAD>`；`kind` 是 `git`。
     - `snapshot_changes` 遇到 `kind` 不同的兩份快照丟 `RgsError`。
   - `test_doctor.py`：新增 `DoctorFacetTest`，在 `TempDir` 底下的**一般資料夾（不是 git repo）**用 `run_script('doctor.py', [...], folder)` 執行：
     - `--flow facet --model gemini-4-argon-high --quick --json`：exit 0；`checks` 有 `python`、`agy`、`model`、`agy models`，狀態都不是 `fail`；沒有 `git repo` 這一項。
     - `--model gemini-9-x`：exit 1，`agy models` 是 `fail`。
     - `FAKE_AGY_MODELS=gemini-4-argon-high` 而 `--model gemini-4-argon`：exit 1（不是子字串比對）。
     - `--model claude-opus-5-5`：exit 1，`model` 是 `fail`。
     - 沒有 `--model`：exit 1，`model` 是 `fail`。
     - `--flow facet --init`：exit 2。
     - 既有的 `DoctorTest`、`PermissionRulesTest` 不要改。
5. `scripts.md`：在 `doctor.py` 的說明加上 `--flow facet --model <M>`：不需要 git repo，檢查 Python、agy、模型 ID 與額度，給 rgs-facet 用。
6. `agy-cli.md`：在說明 guard 的地方補一句：除了 implementer 與 reviewer，還有 `sealed` 角色，只放行 `finish` 與 `wait`，給把全部內容放在 prompt 裡、審查者不需要任何工具的呼叫（rgs-facet）使用。

## 不要做

- 不要修改上面清單以外的檔案，包括知識庫、README、`rgs.py`、`review.py`、`batch.py`、`digest.py`。
- 不要改 `call_agy`、`classify`，也不要讓 batch、digest、review 改用 sealed 或快照（這次只提供能力）。
- 不要改 `install_guard`、`remove_guard` 的行為。
- 不要重新排版無關程式碼。

## 驗收條件

- [ ] 1. `sealed` 角色只放行 `finish`、`wait`，其他一律拒絕，沒有 `roots` 也能判斷；真的執行 hook 時有寫紀錄。
- [ ] 2. `isolated_workspace(sealed=True)` 裝上 sealed guard；預設行為不變。
- [ ] 3. `snapshot` 在 git 與非 git 資料夾都能偵測新增、修改、刪除；沒變動時 `digest` 相同；`ignore` 有效；git 模式偵測得到 HEAD 移動與已修改檔案的再次修改。
- [ ] 4. `doctor.py --flow facet --model <M>` 在非 git 資料夾可執行，依設計檢查並以 exit code 表示結果；模型比對是完全相等。
- [ ] 5. `python -m unittest discover -s skills/rgs-core/tests` 全部通過，既有測試沒有被修改。
- [ ] 6. `scripts.md`、`agy-cli.md` 與程式一致。

## 必要測試

| 測試檔 | 案例 | 對應驗收條件 |
| :-- | :-- | :-- |
| `skills/rgs-core/tests/test_guard.py` | `SealedTest`：放行、拒絕、無 roots、hook 程序與紀錄 | 1 |
| `skills/rgs-core/tests/test_common.py` | `isolated_workspace` 的 sealed 與預設；`SnapshotTest` 檔案模式與 git 模式 | 2、3 |
| `skills/rgs-core/tests/test_doctor.py` | `DoctorFacetTest` 六個案例 | 4 |

## 先前里程碑的教訓

1. 驗證設定或結構時，先走訪整個結構，不要只檢查資料剛好走到的分支（出處：Facet PR #2）。
2. 錯誤案例的測試要同時斷言錯誤種類與訊息內容，不要只斷言有丟例外（出處：Facet PR #2）。
3. 程式刻意區分的邊界要有專屬測試，例如「完全相等」與「子字串」（出處：Facet PR #2）。
4. Gemini 不能執行程式：特別檢查 import（`hashlib`）、變數在每個分支都有定義（例如 doctor 的 `profile`）、測試真的斷言到該行為。
5. 每個測試情境都要真的觸發到：M2 第 1 輪有個測試聲稱檢查「不帶 save_as」，卻從沒做過那次呼叫（出處：M2 第 1 輪）。
6. 本分支堆疊在 M2 之上：`rgs_common.py` 已有 M2 的 `check_agy_args`、`kill_tree`、`reported_model_from_log` 與新的 `call_agy`，不要動它們；測試資料的模型名稱用 `gemini-` 開頭（M2 起 `call_agy` 會拒絕其他名稱）。
