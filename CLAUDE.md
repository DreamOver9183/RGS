# RGS skills 知識庫

> Claude、Gemini 與 sub-agent 共用的專案規範。每段工作完成後只補「新的架構決策、新慣例、踩到的坑」，不要寫進度或流水帳。不要寫本機絕對路徑或 commit hash。

## 文件指引

| 想知道 | 看哪裡 |
| :-- | :-- |
| 使用方式、安裝、repo 結構 | `README.md`（英文版 `README.en.md`，兩份內容要同步） |
| 進行中工作的需求、設計、進度 | `docs/rgs/requirements.md`、`docs/rgs/design.md` |
| 各里程碑規格與審查裁決 | `docs/rgs/specs/`、`docs/rgs/reviews/` |
| agy 1.4.0 的實測行為（旗標、hook、輸出、逾時） | `skills/rgs-core/references/agy-cli.md` |
| 腳本參數與 exit code | `skills/rgs-core/references/scripts.md` |
| 角色與硬性規則 | `skills/rgs-core/roles.md` |
| 整理流程時參考的原始素材 | `docs/origins/` |

## 環境

| 項目 | 值 |
| :-- | :-- |
| 語言 | Python 3.10 以上，**只用標準函式庫** |
| 測試框架 | `unittest` |
| 安裝腳本 | `install.ps1`（Windows PowerShell 5.1） |
| 必要的本機設定 | 無 |

## 架構規範

- 每個 skill 是 `skills/` 下的一個資料夾，由 `install.ps1` 以 junction 連到 `~/.claude/skills/`。`rgs-core` 沒有 `SKILL.md`，不會變成指令，只放共用的規則、範本、腳本與測試。
- `SKILL.md` 保持精簡：流程步驟寫在 `SKILL.md`，行為與規則放在 `rgs-core` 的腳本、範本與 references。
- 腳本只用相對於自身位置（`os.path.dirname(__file__)`）的路徑找範本與其他腳本，不依賴目前工作目錄或安裝位置。其他 skill 的腳本以 `<skill>/../rgs-core/scripts` 匯入 `rgs_common`。
- 每個腳本在 stdout 印出一個 JSON 摘要，以 exit code 表示結果。新增或改變 exit code 時，同步更新 `references/scripts.md`。
- 所有 agy 呼叫都經過 `rgs_common.call_agy`；guard（`guard.py`）預設拒絕，遇到未知工具、壞掉的輸入或例外都輸出拒絕。
- 跨平台：腳本不依賴 bash、`timeout`、`find`、`/dev/null`；子程序的 stdin 用 `subprocess.DEVNULL`；直譯器名稱不寫死 `python3`。
- 給 `agy --json-schema` 的 schema 只用已驗證的關鍵字：`type`、`properties`、`required`、`enum`、`items`。

## 機密規則（不可違反）

- 本 repo 沒有機密檔。任何 agent 都不得讀取、列印或 commit `.env`、`*.pem`、`*.key` 等檔案。
- 測試中的假金鑰（例如密鑰掃描測試）在執行時組出來，不要寫成字面值。
- repo 是公開的：文件與範本不得含本機絕對路徑、帳號資訊或私人專案內容。

## 常用指令

| 目的 | 指令 |
| :-- | :-- |
| 快速檢查 | `python -m unittest discover -s skills/rgs-core/tests`，有 `skills/rgs-facet/tests` 時再跑一次該資料夾 |
| 完整驗證 | 同上 |

## 慣例

- Commit：`type(scope): 摘要`（繁體中文）；內文說明原因。scope 用 skill 或模組名稱，例如 `rgs-core`、`rgs-pr`、`review`。
- 分支：`feat/…`、`fix/…`、`chore/…`。
- 測試：放在各 skill 的 `tests/`，檔名 `test_<模組>.py`，用 `unittest.TestCase`。測試用 `os.path.dirname(__file__)` 推算路徑，把腳本資料夾加進 `sys.path`（見 `rgs-core/tests/helpers.py`）。
- 測試不呼叫真的 agy 或 gh：用 `tests/fake_agy.py`（環境變數 `RGS_AGY`）與 `tests/fake_gh.py`（`RGS_GH`），不消耗額度。
- `install.ps1` 只用 ASCII：Windows PowerShell 5.1 會用 ANSI 字碼頁讀沒有 BOM 的腳本。
- `.gitattributes` 強制 LF。

## 設計模式

- 驗證器分兩段：先靜態檢查整個 schema（不支援的關鍵字、型別名稱、結構），再比對資料。
- guard 與 hook 一律 fail-closed：程式當掉或逾時也算拒絕。

## 踩坑紀錄

<!-- 依領域分組；每條寫「現象 → 原因 → 做法」。agy 的完整實測結果在 references/agy-cli.md。 -->

### agy

- agy 回報 `status: SUCCESS` 但其實沒完成 → timeout、工具被拒、子代理沒回報時都可能回 SUCCESS → 只看腳本的分類結果、guard 紀錄與實際 diff。
- `--json-schema` 的結果不能從 `response` 解析 → `response` 是模型自己寫的 JSON 加上 `finish` 工具參數兩段接在一起 → 只讀 `structured_output`。
- agy hook 沒有執行、agy 以 `invalid UTF-8` 錯誤結束 → Windows 上 hook 以 `cmd /c` 執行，沒有空白的路徑加了引號就會失敗 → 執行檔路徑只在含空白時加引號。
- 少傳 `--model` 時呼叫的是 Claude → 使用者的 agy 預設模型是 Claude Opus → `--model` 必傳，且必須以 `gemini-` 開頭。

### Windows 終端機

- 在 Git Bash 用 `python -c` 讀含中文的管道輸出會變亂碼 → 預設用系統編碼（cp950）解碼 → 讀 `sys.stdin.buffer` 再用 UTF-8 解碼，輸出前 `sys.stdout.reconfigure(encoding="utf-8")`。
