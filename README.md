# RGS skills：Claude × Gemini 協作開發

**繁體中文** | [English](README.en.md)

讓 Claude Code 指揮 Gemini（透過 Antigravity CLI `agy`）寫程式的兩個 skill。Claude 負責規劃與審查，Gemini 負責實作，Claude 的 sub-agent 處理測試、文件、git 等雜務。每個步驟都有品質閘門，中斷後也能從原處接著做。

流程整理自兩個實際專案（一個 Android App、一個 RimWorld Mod）的協作經驗，當時踩過的坑都寫進了腳本與規則。

## 目錄

- [這是什麼](#這是什麼)
- [兩個指令怎麼選](#兩個指令怎麼選)
- [事前準備](#事前準備)
- [安裝](#安裝)
- [第一次在專案中使用](#第一次在專案中使用)
- [教學一：用 /rgs-main 完成一個小任務](#教學一用-rgs-main-完成一個小任務)
- [教學二：用 /rgs-pr 開發多個里程碑](#教學二用-rgs-pr-開發多個里程碑)
- [委派：batch 與 digest](#委派batch-與-digest)
- [中斷與續跑](#中斷與續跑)
- [什麼時候需要你介入](#什麼時候需要你介入)
- [安全機制](#安全機制)
- [專案裡會出現的檔案](#專案裡會出現的檔案)
- [設定參考：.rgs/profile.json](#設定參考rgsprofilejson)
- [疑難排解](#疑難排解)
- [repo 結構與開發](#repo-結構與開發)
- [已驗證範圍與限制](#已驗證範圍與限制)

## 這是什麼

| 角色 | 做什麼 | 不做什麼 |
| :-- | :-- | :-- |
| 你 | 提需求、核准設計、在 GitHub 合併 PR、核准發佈 | — |
| Claude（主對話） | 釐清需求、寫規格與修正指示、審查 Gemini 的 diff、裁決審查意見、維護知識庫 | 不直接改產品程式碼 |
| Gemini（agy） | 依規格實作、依修正指示修改 | 不能跑 shell 或 git、不能改規格以外的檔案、不能讀機密檔 |
| agy 審查者 | 開新對話、唯讀，從安全、正確性、架構、規格四個面向平行審查 | 不能寫任何檔案 |
| Claude sub-agent | 跑 agy、跑測試、更新文件、commit、開 PR | 不修程式碼，失敗就停下回報 |

為什麼這樣分工：Gemini 便宜、能長時間寫程式，但不能執行建置或測試，偶爾會寫錯或越界；Claude 的強項是把需求講清楚和把關品質。所以 Claude 只寫規格和審查，Gemini 能改哪些檔案由 hook 強制限制，而不只是寫在 prompt 裡請它遵守。

## 兩個指令怎麼選

| | `/rgs-main` | `/rgs-pr` |
| :-- | :-- | :-- |
| 適合 | 小功能、修 bug、單人 repo | 多個功能或畫面、需要需求與設計文件、需要人工把關 |
| 流程 | 規格 → Gemini 實作 → Claude 審查與測試 → 通過就 push 到 main | 需求 → 設計（你核准）→ 里程碑 → Gemini 實作 → Claude 審查 → 開 PR → agy 獨立審查 → **你合併** → 知識沉澱 → 發佈 |
| 不通過時 | Claude 寫修正建議，Gemini 修改，再審一次 | 同左；agy 審查的每條意見都由 Claude 裁決並記錄 |
| 產出 | main 上的一個 commit | 每個里程碑一個 PR，`docs/rgs/` 保存需求、設計、規格與審查紀錄 |
| 子指令 | `status`、`batch`、`digest` | `init`、`plan`、`run M<n>`、`merged <PR#>`、`release <版本>`、`status`、`batch`、`digest` |

不確定時從 `/rgs-main` 開始。Claude 判斷任務需要多個里程碑時，會建議你改用 `/rgs-pr`。

## 事前準備

| 需要 | 確認方式 |
| :-- | :-- |
| [Claude Code](https://claude.com/claude-code)（CLI 或桌面版） | — |
| Antigravity CLI `agy` 1.4.0 以上，且已登入 | `agy --version`；第一次執行 `agy` 會引導登入 |
| Python 3.10 以上（只用標準函式庫） | `python --version` |
| git，並設定好 `user.name`／`user.email` | `git config user.name` |
| 專案有 git remote | `git remote -v` |
| `/rgs-pr` 另外需要已登入的 GitHub CLI | `gh auth status` |

在 Windows 上，profile 裡的建置／測試指令預設用 Git Bash 執行。

## 安裝

1. 取得這個 repo：

   ```bash
   git clone https://github.com/DreamOver9183/RGS.git
   ```

2. 執行安裝腳本：

   ```bash
   powershell -ExecutionPolicy Bypass -File RGS/install.ps1
   ```

   它會在 `~/.claude/skills/` 下建立 `rgs-core`、`rgs-main`、`rgs-pr` 三個 junction，指向這個 repo，所以之後 `git pull` 更新 repo，skill 也會跟著更新。三個資料夾都要安裝：`rgs-main` 與 `rgs-pr` 會用到同層的 `rgs-core`。

3. **開一個新的 Claude Code session。** skill 只在 session 開始時載入。輸入 `/` 應該能看到 `/rgs-main` 與 `/rgs-pr`。

移除：`powershell -ExecutionPolicy Bypass -File RGS/install.ps1 -Uninstall`。這只會刪除 junction，不會刪除 repo。

macOS／Linux 沒有安裝腳本，可以手動建立符號連結（尚未在這些平台驗證）：

```bash
ln -s "$PWD/RGS/skills/rgs-core" "$PWD/RGS/skills/rgs-main" "$PWD/RGS/skills/rgs-pr" ~/.claude/skills/
```

## 第一次在專案中使用

在專案目錄開啟 Claude Code，第一次執行任一指令時，Claude 會先跑環境檢查：

```
/rgs-pr init          ← /rgs-pr 的專案
/rgs-main <任務>      ← /rgs-main 會自動做精簡版的檢查
```

會發生這些事：

1. **環境檢查**：確認 agy 版本與模型、Gemini 額度、git 身分、remote、工作樹是否乾淨；`/rgs-pr` 還會檢查 `gh` 登入。
2. **產生 `.rgs/profile.json`**：自動偵測建置與測試指令（Gradle、npm、dotnet、cargo、go、pytest／unittest）、知識庫檔名（`CLAUDE.md`／`AGENTS.md`）以及機密檔。Claude 會把草稿給你確認，例如：「quick 指令用 `./gradlew testDebugUnitTest` 對嗎？」
3. **知識庫**：專案沒有 `CLAUDE.md` 或 `AGENTS.md` 時，Claude 會依範本建立一份，內容包括架構規範、機密規則、常用指令、慣例與踩坑紀錄。
4. **權限規則**：Claude 會列出建議的規則，例如：

   ```
   Bash(python -I "D:/My Tools/RGS/skills/rgs-core/scripts/rgs.py":*)
   ```

   把它們加進專案 `.claude/settings.json` 的 `permissions.allow`，之後就不會每一步都跳出權限確認。Claude 不能修改自己的設定，所以這一步要由你來做。

## 教學一：用 /rgs-main 完成一個小任務

以「在 `calc.py` 加上除法」為例。

**1. 交辦任務**

```
/rgs-main 在 calc.py 加上 div(a, b)，除以零時丟出 ValueError("division by zero")，並補上測試
```

**2. Claude 寫規格。** Claude 先讀相關程式碼與知識庫，寫出 `.rgs/runs/add-div/spec.md`，內容包括目標、**可修改的檔案**（例如只有 `calc.py` 與 `tests/test_calc.py`）、實作要點、驗收條件、必要測試，以及過去踩過的坑。Gemini 只能寫入這份清單上的檔案。

**3. Gemini 實作。** Claude 在專案旁的 `<專案名>.rgs/add-div` 開一個獨立的 worktree 與分支 `rgs/add-div`，在背景啟動 Gemini。小任務大約 1–3 分鐘，一個里程碑大約 5–20 分鐘。你的主 checkout 不會被動到，等待期間可以繼續做自己的事。

**4. Claude 審查。** 完成後，Claude 會依序：

- 檢查 Gemini 是否只改了允許的檔案，以及是否有被 guard 擋下的操作
- 完整讀過 diff，檢查正確性、編譯風險、規格與測試、專案慣例
- 跑 profile 裡的 quick 與 verify 測試

**5. 不通過就修正。** 例如 Claude 發現測試沒涵蓋負數與 `0.0`，就會寫出具體的修正指示（檔案、位置、要改成什麼），交回同一個 Gemini 對話修改，再審一次。最多 4 輪，超過就停下來問你。

**6. 通過就進 main。** Claude 寫好 commit 訊息，然後依序：

- 跑 secret scan
- 建立 commit
- 如果遠端 main 在這段期間有新 commit，先 rebase 並重跑測試
- fast-forward push 到 `origin/main`
- 同步你的本地 main
- 移除 worktree 與分支

**7. 回報。** Claude 會列出 commit hash、改了哪些檔案、修正輪數、測試結果，以及還沒驗證的項目。回報開頭的標記表示結果是誰做的：🧩 Gemini 完成並通過檢查、⚡ Claude 自己完成、⚠️ 有異常或降級。

想多一道把關時，可以要求「這個改動先讓 agy 獨立審查再推」（`--gate`），適合安全性或資料遷移這類高風險變更。

## 教學二：用 /rgs-pr 開發多個里程碑

**1. 初始化（每個專案一次）**

```
/rgs-pr init
```

這一步會完成環境檢查、`profile.json`、知識庫與權限規則（見上一節）。要把這些檔案 commit 進 base 分支之前，Claude 會先問你。

**2. 需求與設計**

```
/rgs-pr plan 新增收藏頁、餐廳詳細頁與分享功能；收藏要能離線保存
```

Claude 會依序：

- 一次問完不清楚的地方
- 寫 `docs/rgs/requirements.md`，每條需求都有編號（R-1、R-2…）與驗收條件
- 派 sub-agent 調查程式架構與測試／CI
- 寫 `docs/rgs/design.md`：已查證的事實、決策紀錄、風險、里程碑 M0…Mn、追溯矩陣、狀態總覽

**你要做的**：讀過設計，回覆「核准」或提出修改。核准之前不會開始寫程式。

**3. 執行一個里程碑**

```
/rgs-pr run M1
```

1. Claude 寫 M1 的規格。
2. sub-agent 啟動 Gemini 實作並跑快速測試。
3. Claude 審查 diff，不通過就寫修正指示，再交給 Gemini 修改。
4. sub-agent 跑完整驗證、更新知識庫與 README（含實際測試數）、把規格存進 `docs/rgs/specs/`，然後 push 分支並開 PR。
5. agy 以新對話、唯讀的方式做合併閘門審查，四個面向各由一個子代理負責。審查報告會貼在 PR 留言。
6. Claude 在 `docs/rgs/reviews/PR-<N>.md` 逐條裁決：採納、不採納（附理由）或延後到某個里程碑（附理由）。採納的意見交給 Gemini 修正，再複審。
7. 沒有未解決的 blocker／major 時，Claude 會告訴你「PR #N 可以合併」，並附上判定、裁決摘要、測試數與未驗證項目。

**你要做的**：到 GitHub 看 PR 與審查留言，**自己按合併**。Claude 永遠不會執行 `gh pr merge`。

**4. 合併後告訴 Claude**

```
我已經合併 PR #12，請接著做 M2
```

Claude 會依序：

- 同步 base 分支，清掉 M1 的 worktree 與分支
- 把新的決策、慣例與踩坑寫進知識庫
- 更新設計文件的狀態總覽與追溯矩陣
- 開始 M2

**堆疊的里程碑**：M2 依賴還沒合併的 M1 時，Claude 會把 M2 疊在 M1 的分支上（`--stack-on`），不用等你合併 M1 才開工。M1 合併後，Claude 會先執行 `retarget`，把 M2 的 PR 改到 base 分支（squash 合併時會先 rebase），然後才刪 M1 的分支。

**5. 發佈**

```
/rgs-pr release 1.2.0
```

1. sub-agent 稽核文件與程式是否一致（測試數、版本號、指令、路徑、機密）。
2. 修正稽核出的問題。
3. 版本號變更照一般流程開 PR，由你合併。
4. 從合併後的 commit 建置產物，計算 SHA-256，撰寫 release notes。
5. **建立 GitHub release 前，Claude 會先給你確認**，你也可以選擇只建 draft。

## 委派：batch 與 digest

這兩個子指令不改程式碼，而是把「量大、雜訊多、只需要結論」的工作交給 Gemini。執行時 agy 在一個空的暫存資料夾裡、以唯讀方式運作，碰不到你的專案。

**digest：長文件或 log 摘要**

```
/rgs-main digest logs/app.log 當機前發生了哪些錯誤？各自的原因是什麼？
```

- 會先用關鍵字過濾（例如 `ERROR|WARN`），再切塊平行處理。
- 每條結論都附檔案、行號與逐字引用，腳本會回原檔核對，標成 ✓（通過）或 ✗（需人工確認）。
- 這樣做是因為 Gemini 一次讀太長的內容時曾經漏掉錯誤，卻宣稱全部找到。

**batch：大量資料**

```
/rgs-main batch 把 data/names.jsonl 的英文名字音譯成繁體中文
```

- 輸入是 JSONL，每行一筆、要有唯一的 `id`。可以只送需要的欄位，也可以附上自動檢查用的 validator。
- 預設用 8 個 agy process 平行處理，每批 40 筆。
- 每筆回應都會存檔：額度用完或中斷後重跑同一個指令，只會補送缺少的部分。
- Claude 會建議先用少量資料試跑，並在使用結果前抽樣檢查。

## 中斷與續跑

Claude 用量到上限、Gemini 額度用完、或電腦重開機之後：

```
/rgs-main status
/rgs-pr status
```

Claude 會讀 `.rgs/state.json`（每個任務的 worktree、分支、Gemini 對話 ID、修正輪數、目前步驟），以及 `/rgs-pr` 的設計狀態表，從中斷的步驟接著做。說「用量恢復了，請繼續」也可以。

## 什麼時候需要你介入

| 時機 | 你要做的 |
| :-- | :-- |
| 第一次在專案中使用 | 確認 profile 的指令與機密清單，加入權限規則 |
| `/rgs-pr` 設計完成 | 核准或修改設計 |
| `/rgs-pr` PR 準備好 | 在 GitHub 審閱並合併，然後告訴 Claude |
| 修正超過 4 輪 | 決定要換模型、拆小任務，還是同意由 Claude 接手 |
| Gemini 額度用完 | 決定要換模型、稍後再試，還是由 Claude 接手 |
| push 被拒（分支保護等） | 改用 `/rgs-pr`，或自行處理權限 |
| 建立 GitHub release | 確認版本號、產物與 notes |

Claude 不會在沒有你同意的情況下親手寫產品程式碼，也不會 force push。

## 安全機制

- **隔離的 worktree**：Gemini 在專案旁的 `<專案名>.rgs/<任務>` 工作，合併閘門審查在另一個 detached worktree 進行，你的主 checkout 不受影響。worktree 刻意不放在 `%TEMP%`，因為 Windows 的 Smart App Control 會擋下那裡的測試 DLL，造成「0 個測試」看起來像通過。
- **Guard hook**：agy 的全域設定會自動執行所有工具，而且 `--mode plan` 也擋不住寫入。所以 rgs 在 worktree 裡放了一個 PreToolUse hook（`.agents/hooks.json` → `rgs-guard.py`），規則如下：
  - 只允許寫入規格列出的檔案
  - shell 只放行唯讀的列目錄與搜尋指令，禁止串接與重新導向
  - 禁止讀取機密檔
  - 子代理的工具呼叫同樣受限
  - hook 本身出錯時一律拒絕
- **不相信自我回報**：agy 在 timeout、工具被拒、子代理沒回報時都可能回報 SUCCESS。腳本以實際產出、git diff、範圍檢查與測試結果判斷成敗。
- **Secret scan**：commit 前掃描 staged diff 中的金鑰樣式與受保護檔名；命中就不 commit。
- **不自動合併、不 force push**：`/rgs-pr` 的 PR 一律由你合併；`/rgs-main` 只做 fast-forward push。

## 專案裡會出現的檔案

| 位置 | 內容 | 進 git |
| :-- | :-- | :-- |
| `.rgs/profile.json` | 專案設定 | 建議納入 |
| `.rgs/.gitignore` | 排除下面兩項 | 建議納入 |
| `.rgs/state.json` | 任務狀態（續跑用） | 否 |
| `.rgs/runs/<任務>/` | 規格草稿、prompt、agy 原始輸出、測試 log、審查報告 | 否 |
| `docs/rgs/` | `/rgs-pr` 的需求、設計、里程碑規格、審查裁決 | 是 |
| `<專案名>.rgs/`（專案旁） | 進行中的 worktree，任務結束後移除 | — |

## 設定參考：.rgs/profile.json

`doctor.py --init` 會產生草稿，沒寫的欄位用預設值。完整範例見 [`templates/profile.example.json`](skills/rgs-core/templates/profile.example.json)。

| 欄位 | 預設 | 說明 |
| :-- | :-- | :-- |
| `language.docs`／`commits` | `zh-TW` | Claude 寫的文件與 commit 訊息、agy 審查報告與摘要使用的語言（給 Gemini 的 prompt 範本固定是繁中，可用 `.rgs/templates/` 覆蓋） |
| `knowledge_base` | `["CLAUDE.md"]` | 專案知識庫檔案，每個階段開始時都會重讀 |
| `remote`／`base_branch` | `origin`／`main` | 推送與開 PR 的目標 |
| `docs_dir` | `docs/rgs` | `/rgs-pr` 文件的位置 |
| `worktree_root` | 專案旁的 `<專案名>.rgs` | worktree 放哪裡 |
| `worktree_copy` | `[]` | 需要複製進 worktree 的未追蹤檔案，例如 `local.properties`；這些檔案同時會被視為機密 |
| `shell`／`env` | `bash`／`{}` | 執行建置指令的 shell 與環境變數，例如 `JAVA_HOME` |
| `secrets.deny_read` | `.env*`、`*.pem`、`*.key`、`*_KEY_*`、`*.keystore`、`*.jks` | Gemini 不能讀、不能 commit 的檔案 |
| `secrets.patterns` | `[]` | 額外的機密正規表示式 |
| `commands.quick`／`verify` | 依偵測 | 每輪必跑的快速測試，以及交付前的完整驗證 |
| `agy.implementer.models` | `gemini-3.8-flash-high` | 實作用模型；可列多個，額度用完時依序改用下一個 |
| `agy.reviewer.models`／`lenses` | `gemini-3.8-flash-high`／四個面向 | 合併閘門審查的模型與面向 |
| `agy.batch`／`agy.digest` | flash-low、8 workers／flash-high、4 workers | 委派任務的模型與平行度 |
| `agy.max_fix_rounds` | `4` | 修正輪數上限 |
| `agy.fresh_after_input_tokens` | `400000` | 續寫對話累積超過這個量時，自動改開新對話 |
| `pr.post_review_comment` | `true` | 是否把審查報告貼到 PR |

## 疑難排解

| 狀況 | 原因與處理 |
| :-- | :-- |
| 輸入 `/` 看不到指令 | 安裝後要開新 session；確認 `~/.claude/skills/` 下有三個資料夾 |
| 每一步都跳出權限確認 | 把 `doctor.py --init` 列出的規則加進 `.claude/settings.json`；規則與指令的路徑寫法（引號、斜線）必須一字不差 |
| ⚠️ agy 額度用完 | 等額度恢復後用 `status` 續跑，或在 profile 的 `models` 加上備援模型 |
| Gemini 一直被 guard 擋 | 看回報中的 `guard_denials`：要改清單外的檔案就請 Claude 判斷是否擴充；要跑指令則由 Claude 代跑 |
| `land` 被拒（分支保護） | 這個 repo 不允許直接推 main，改用 `/rgs-pr` |
| 中文輸出變亂碼 | Windows 主控台是 cp950；腳本已處理。自己寫腳本時記得指定 `encoding='utf-8'` |

更多情況見 [`references/troubleshooting.md`](skills/rgs-core/references/troubleshooting.md)。

## repo 結構與開發

```
skills/
  rgs-main/SKILL.md      /rgs-main 的流程
  rgs-pr/SKILL.md        /rgs-pr 的流程與子指令
  rgs-core/              共用核心（沒有 SKILL.md，不會變成指令）
    roles.md             角色與硬性規則
    references/          品質閘門與審查標準、agy 已驗證行為、sub-agent brief、委派、疑難排解、腳本參考
    templates/           規格、需求、設計、修正指示、審查備註、PR、release notes、知識庫骨架、prompts
    scripts/             rgs.py、review.py、guard.py、doctor.py、batch.py、digest.py、scope_check.py、secret_scan.py
    tests/               單元與整合測試（fake_agy.py 代替 agy，fake_gh.py 代替 gh）
docs/origins/            整理流程時參考的原始素材（本機路徑已去除）
install.ps1
```

執行測試：

```bash
python -m unittest discover -s skills/rgs-core/tests
```

測試不會呼叫真的 agy 或 GitHub，也不會消耗額度。整合測試會建立暫存 repo 與 bare remote，完整跑過：

- prepare → implement → fix → check → land
- ship、開 PR、堆疊 PR、審查留言、retarget

想調整流程時：
- 規則與標準改 `skills/rgs-core/` 下的文件
- 給 Gemini 的指示改 `templates/` 與 `templates/prompts/`；單一專案也可以把同名檔案放在 `<專案>/.rgs/templates/` 覆蓋
- 改完腳本後重跑測試

## 已驗證範圍與限制

- 在 Windows 11 與 agy 1.4.0 上，用真的 Gemini 跑過以下流程：
  - `/rgs-main`：實作、修正輪、遠端前進時 rebase 後推送
  - `/rgs-pr`：在 GitHub 上開 PR、堆疊 PR、審查留言、retarget、draft release
  - batch 與 digest
- agy 升級後，行為可能改變（工具名稱、hook 格式、輸出欄位）。已驗證的行為記錄在 [`references/agy-cli.md`](skills/rgs-core/references/agy-cli.md)，升級後建議先跑 `doctor.py` 再使用。
- macOS／Linux 尚未驗證。
- Gemini 的審查意見只是參考，最後都由 Claude 逐條裁決；最終要不要合併，由你決定。
