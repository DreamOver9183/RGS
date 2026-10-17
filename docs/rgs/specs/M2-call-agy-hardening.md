# M2：`call_agy` 強化

> /rgs-pr 的里程碑規格。由 Claude 依 design.md 撰寫；PR 合併時一併存進 `docs/rgs/specs/`。

| 項目 | 內容 |
| :-- | :-- |
| 對應需求 | R-4、R-12（`docs/rgs/requirements.md`） |
| 相依 | 無 |
| 分支 | `feat/m2-call-agy-hardening` |

## 目標

rgs 的每一次 agy 呼叫都經過 `rgs_common.call_agy`。這個里程碑在那裡補上三件事（`docs/rgs/design.md` D-14、D-15）：

1. 逾時時終止 agy 的**整個程序樹**，不只是 agy 本身。
2. 呼叫 agy 之前，依角色檢查參數，並要求模型 ID 以 `gemini-` 開頭。
3. 用 `--log-file` 記下 agy 實際解析的模型（`reported_model`）。

## 可修改的檔案

<!-- rgs.py 只讀取這個標題下的 `路徑` 清單，guard 會擋下清單以外的寫入。 -->

- `skills/rgs-core/scripts/rgs_common.py`：`call_agy`、`AgyResult`、新增 `check_agy_args`、`kill_tree`、`reported_model_from_log`
- `skills/rgs-core/scripts/rgs.py`：`cmd_implement`、`cmd_fix` 傳 `role='implementer'`
- `skills/rgs-core/tests/fake_agy.py`：新情境 `sleep_child`、寫 `--log-file`
- `skills/rgs-core/tests/test_common.py`：模型名稱改成 `gemini-` 開頭、新增測試
- `skills/rgs-core/tests/test_flow.py`：只改檔案開頭 profile 的模型名稱
- `skills/rgs-core/tests/test_github.py`：只改檔案開頭 profile 的模型名稱
- `skills/rgs-core/references/agy-cli.md`：「呼叫方式」一節補上新行為
- `skills/rgs-core/references/scripts.md`：exit code 2 的說明

## 設計

### 新的 `call_agy` 簽章

```python
def call_agy(prompt, cwd, model, mode=None, schema_path=None, conversation=None, add_dirs=(),
             timeout_s=900, save_as=None, role='reviewer', grace_s=180):
```

- `role`：`'implementer'` 或 `'reviewer'`，其他值丟 `RgsError`。只有 `rgs.py` 的 implement 與 fix 是 implementer；review、batch、digest 不傳，維持預設的 reviewer。
- `grace_s`：外部終止的緩衝秒數。agy 自己的 `--print-timeout` 是 `timeout_s`，超過 `timeout_s + grace_s` 還沒結束，就終止程序樹。預設 180，和現在一樣。
- `call_with_fallback(models, **kwargs)` 不用改：`role`、`grace_s` 會隨 `**kwargs` 傳下去。

### 參數檢查 `check_agy_args`

```python
FORBIDDEN_ALWAYS = ('--dangerously-skip-permissions', '--yolo', '-i', '--prompt-interactive',
                    '--remote-control', '--sandbox')
FORBIDDEN_FOR_REVIEWER = ('--mode', '--add-dir', '--conversation', '-c', '--continue')
IMPLEMENTER_MODES = ('accept-edits',)
VALUE_FLAGS = ('-p', '--model', '--output-format', '--print-timeout', '--mode', '--json-schema',
               '--conversation', '--add-dir', '--log-file')


def check_agy_args(args, role, model):
    """Raise RgsError(code=2) when these agy arguments are not allowed for the role (design D-14).

    args is the argument list after the agy executable. The value after a flag in VALUE_FLAGS is
    not a flag: the prompt may well contain text such as "--yolo".
    """
```

規則：

1. `role` 不是 `'implementer'` 或 `'reviewer'` → 丟錯。
2. `model` 不是非空字串，或不以 `gemini-` 開頭（大小寫要完全符合）→ 丟錯，訊息說明「rgs 只用 Gemini 模型；agy 的預設模型可能是 Claude，所以必須明確指定 `gemini-…`」。
3. 逐一走訪 `args`：
   - 先把 `--flag=value` 拆成旗標與值。
   - 旗標在 `FORBIDDEN_ALWAYS` → 丟錯。
   - `role == 'reviewer'` 且旗標在 `FORBIDDEN_FOR_REVIEWER` → 丟錯。
   - `role == 'implementer'` 且旗標是 `--mode`，值不在 `IMPLEMENTER_MODES` → 丟錯。
   - 旗標在 `VALUE_FLAGS` 而且沒用 `=` 帶值時，下一個元素是它的值，跳過、不當成旗標檢查。
4. 錯誤一律 `raise RgsError(message, code=2)`，訊息要指出是哪個參數、哪個角色。

`call_agy` 在組好參數之後、啟動 agy 之前呼叫 `check_agy_args(cmd[len(prefix):], role, model)`，其中 `prefix = find_agy()`（測試替身的 prefix 是 `[python, fake_agy.py]`，所以不能從 `cmd[1:]` 開始算）。檢查失敗時不啟動 agy，也不寫任何輸出檔。

### 終止程序樹 `kill_tree`

```python
def popen_kwargs():
    """Start a process in its own group so kill_tree() can stop everything it starts."""
    if os.name == 'nt':
        return {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
    return {'start_new_session': True}


def kill_tree(proc):
    """Stop proc and every process it started (design D-15)."""
```

- Windows：`subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True, stdin=subprocess.DEVNULL)`，忽略它的 exit code（程序可能已經結束）。
- POSIX：`os.killpg(proc.pid, signal.SIGTERM)`；`proc.wait(timeout=10)`；之後不論父程序是否已結束，都再 `os.killpg(proc.pid, signal.SIGKILL)`，因為子程序可能還在同一個群組。每次 `killpg` 都要接住 `ProcessLookupError`（群組已經沒有程序）。`import signal` 放在函式內或檔案開頭皆可。

`call_agy` 改用 `subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, env=env, **popen_kwargs())`：

```python
try:
    out, err = proc.communicate(timeout=timeout_s + grace_s)
except subprocess.TimeoutExpired:
    kill_tree(proc)
    try:
        out, err = proc.communicate(timeout=30)
    except subprocess.TimeoutExpired:
        # A grandchild may still hold the pipes open; give up on the output.
        proc.kill()
        out, err = b'', b''
    # 結果是 AgyResult('timeout', model, None, stderr, None, detail=f'killed after {秒數}s')，和現在一樣
```

正常結束時照舊解碼成 UTF-8（`errors='replace'`）並呼叫 `classify`。`MSYS_NO_PATHCONV` 等環境變數設定保持不變。

### 實際模型 `reported_model`

- `call_agy` 一律加上 `--log-file <path>`：
  - 有 `save_as` 時，`path = save_as + '.log'`，保留下來。
  - 沒有 `save_as` 時，用 `tempfile.mkstemp(prefix='rgs_agy_', suffix='.log')` 建暫存檔（記得關掉 fd），讀完後在 `finally` 刪除。
- `reported_model_from_log(path)`：用 UTF-8（`errors='replace'`）讀檔，找出所有 `label="…"`（regex `label="([^"]*)"`），回傳**最後一個**；檔案不存在、讀不到或沒有 label 時回傳 `None`。
- `AgyResult.__init__` 新增 `reported_model=None` 參數與屬性；`summary()` 加上 `'reported_model'`。正常結束與逾時兩種情況都要填（逾時時 log 可能已有 label）。
- 這是 agy 用戶端解析後送出的模型名稱（例如 `Gemini 4 Argon (High)`），不是伺服器回報的；在 `agy-cli.md` 寫明這點。

### 測試替身 `fake_agy.py`

- 有 `--log-file` 參數時，寫入一行 `I1017 00:00:00.000000 1 model.go:1] Propagating selected model override to backend: label="<label>"`，`<label>` 取環境變數 `FAKE_AGY_LABEL`，沒設定時用 `'Fake ' + str(model)`；`FAKE_AGY_LABEL` 設成空字串時不寫這一行（但仍建立檔案）。在處理任何情境之前就寫，所以每個情境都有。
- 新情境 `sleep_child`：
  1. 用 `subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)` 啟動子程序。
  2. 把 `{"parent": os.getpid(), "child": child.pid}` 寫進 `os.path.join(FAKE_AGY_DIR, 'pids.json')`。
  3. `time.sleep(120)`。
- 更新檔案開頭 docstring 的情境清單與環境變數說明。

## 實作要點

1. `rgs.py`：`cmd_implement` 與 `cmd_fix` 的 `rc.call_with_fallback(...)` 各加上 `role='implementer'`，其他不動。
2. 測試資料的模型名稱：
   - `test_common.py`：`'m1'` → `'gemini-test-1'`，`'m2'` → `'gemini-test-2'`（含 `FAKE_AGY_QUOTA_MODEL` 與 `tried` 的斷言）。
   - `test_flow.py`、`test_github.py`：檔案開頭 profile 的 `'m-impl'` → `'gemini-test-impl'`，`'m-review'` → `'gemini-test-review'`。這兩個檔案其他地方不要動。
3. 新增測試（`test_common.py`）：
   - `CheckAgyArgsTest`（直接呼叫 `rc.check_agy_args`，不需要替身）：
     - `FORBIDDEN_ALWAYS` 的每個旗標，兩種角色都被拒；`--sandbox=true` 這種 `=` 形式也被拒。
     - reviewer 對 `FORBIDDEN_FOR_REVIEWER` 每個旗標都拒；implementer 允許 `--mode accept-edits`、`--conversation <id>`、`--add-dir <dir>`，拒絕 `--mode auto` 與 `--mode=plan`。
     - `-p` 後面的 prompt 含 `--yolo`、`--sandbox` 文字時不會被拒。
     - 模型 `None`、`''`、`'claude-opus-5-5'`、`'Gemini-4'` 被拒；`'gemini-3.8-flash-high'` 通過。
     - 未知角色被拒。
     - 每個被拒的案例都斷言 `RgsError` 的 `code == 2`，而且訊息含出問題的旗標或模型。
   - `CallAgyTest` 補充：
     - 模型不合規時 `call_agy` 丟 `RgsError`，而且替身完全沒被呼叫（`FAKE_AGY_DIR/calls` 不存在或是空的）。
     - `role='reviewer'` 加 `mode='accept-edits'` 丟 `RgsError`；`role='implementer'` 加 `mode='accept-edits'` 正常回傳。
     - 每次呼叫的 argv（替身記在 `calls/*.json`）含 `--log-file`。
     - `reported_model`：預設是 `'Fake gemini-test-1'`；`FAKE_AGY_LABEL='Gemini 4 Argon (High)'` 時是該值；`FAKE_AGY_LABEL=''` 時是 `None`；`summary()` 含 `reported_model`。
     - 有 `save_as` 時 `save_as + '.log'` 存在；沒有 `save_as` 時，替身收到的 `--log-file` 路徑在呼叫結束後已不存在。
   - `KillTreeTest`：用 `sleep_child` 情境呼叫 `rc.call_agy(..., timeout_s=1, grace_s=2)`，斷言：
     - 回傳 `kind == 'timeout'`，整個呼叫在 30 秒內結束；
     - 讀 `pids.json`，父程序與子程序在 10 秒內都不再存在。
     - 判斷程序是否存在的測試輔助函式：Windows 用 `subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/NH'], capture_output=True, text=True)`，輸出中出現該 PID 的數字欄位就算存在；POSIX 用 `os.kill(pid, 0)`，`ProcessLookupError` 表示不存在、`PermissionError` 表示存在。**不要在 Windows 用 `os.kill(pid, 0)`**：Windows 上它會直接結束那個程序。
     - `tearDown` 若子程序還在，用同樣的平台分支把它清掉，避免測試留下殘留程序。
4. `tearDown` 要清掉新加的環境變數（`FAKE_AGY_LABEL`）。
5. `agy-cli.md` 的「呼叫方式」：參數列加上 `--log-file <file>`；補三點：參數依角色檢查（列出兩份禁止清單與實作角色允許的 mode）、`--model` 必須是 `gemini-` 開頭、逾時時終止整個程序樹（說明兩個平台的做法與 `grace_s`）；`label="…"` 是 agy 用戶端解析的模型。
6. `scripts.md` 的 exit code 表：2 的意義改成「參數錯誤（argparse），或 agy 參數／模型不合規（`call_agy` 的檢查）」，處理方式加上「檢查 profile 的模型是否以 `gemini-` 開頭」。

## 不要做

- 不要修改上面清單以外的檔案，包括知識庫、README、`review.py`、`batch.py`、`digest.py`、`guard.py`。
- 不要改 `classify` 的判斷規則、`call_with_fallback` 的換模型邏輯、`AgyResult` 既有屬性的意義。
- 不要改預設 profile 的模型清單。
- 不要重新排版無關程式碼。

## 驗收條件

- [ ] 1. 逾時時父程序與它啟動的子程序都被終止（Windows 用 `taskkill /T /F`，POSIX 用 `killpg`）；`grace_s` 可設定，預設 180。
- [ ] 2. 禁止的參數、角色不允許的參數、不合規的模型，都在啟動 agy 之前被拒，`RgsError.code == 2`；prompt 文字不會被誤判成旗標。
- [ ] 3. implement 與 fix 以 implementer 角色呼叫，其餘呼叫是 reviewer 角色，既有流程都照常運作。
- [ ] 4. 每次呼叫都帶 `--log-file`；`AgyResult.reported_model` 與 `summary()['reported_model']` 是 log 中最後一個 label，沒有就是 `None`；沒有 `save_as` 時暫存 log 會被刪除。
- [ ] 5. `python -m unittest discover -s skills/rgs-core/tests` 全部通過：原本的測試只改了模型名稱，新增的測試涵蓋上面四點。
- [ ] 6. `agy-cli.md`、`scripts.md` 與程式一致。

## 必要測試

| 測試檔 | 案例 | 對應驗收條件 |
| :-- | :-- | :-- |
| `skills/rgs-core/tests/test_common.py` | `CheckAgyArgsTest` 全部案例 | 2 |
| `skills/rgs-core/tests/test_common.py` | `CallAgyTest`：不合規模型不呼叫替身、角色與 mode、`--log-file`、`reported_model`、暫存 log 刪除 | 2、3、4 |
| `skills/rgs-core/tests/test_common.py` | `KillTreeTest`：父子程序都被終止、30 秒內回傳 | 1 |
| `skills/rgs-core/tests/test_flow.py`、`test_github.py` | 既有案例（只改模型名稱） | 3、5 |

## 先前里程碑的教訓

1. 錯誤案例的測試要同時斷言錯誤種類與訊息內容，不要只斷言有丟例外（出處：Facet PR #2）。
2. 程式刻意區分的邊界要有專屬測試，例如「`-p` 的值」與「真正的旗標」（出處：Facet PR #2）。
3. Gemini 不能執行程式：特別檢查 import（`signal`、`tempfile`）、簽章與呼叫是否一致、平台分支兩邊都寫到。
4. 跨平台：子程序的 stdin 一律 `subprocess.DEVNULL`；直譯器用 `sys.executable`，不寫死 `python3`（知識庫「架構規範」）。
