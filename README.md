# RGS skills：Claude × Gemini（Antigravity CLI）協作開發

把「Claude 規劃與審查、Gemini 實作、sub-agent 處理雜務」的開發流程做成 Claude Code skill。流程整理自兩個實際專案（Android App 與 RimWorld Mod）的做法，並把當時踩過的坑寫進腳本與規則裡。

## 兩個指令怎麼選

| | `/rgs-main` | `/rgs-pr` |
| :-- | :-- | :-- |
| 流程 | Claude 寫規格 → Gemini 實作 → Claude 審查與測試 → 通過後直接 push 到 main；不通過就由 Claude 寫修正建議給 Gemini | 需求與設計（使用者核准）→ 里程碑 → Gemini 實作 → Claude 審查 → sub-agent 驗證、更新文件、開 PR → agy 獨立審查並由 Claude 裁決 → **使用者手動合併** → 知識沉澱 → 發佈 |
| 適合 | 小型專案、單一功能或修 bug、單人 repo | 中大型專案、多個功能或畫面、需要人工把關 |
| 產出 | 一個 commit 直接進 main | 每個里程碑一個 PR；`docs/rgs/` 保存需求、設計、規格與審查裁決 |
| 子指令 | `status`、`batch`、`digest` | `init`、`plan`、`run M<n>`、`merged <PR#>`、`release <版本>`、`status`、`batch`、`digest` |

兩者都只用 A 模式：**Gemini 寫程式，Claude 審查**。Claude 不直接改產品程式碼。

## 需求

- [Claude Code](https://claude.com/claude-code)
- Antigravity CLI `agy` ≥ 1.4.0（已登入；目前在 1.4.0 驗證過）
- Python 3.10 以上（只用標準函式庫）、git
- `/rgs-pr` 另外需要已登入的 GitHub CLI `gh`
- Windows 上的 profile 指令預設用 Git Bash 執行

## 安裝

```
powershell -ExecutionPolicy Bypass -File install.ps1
```

這個指令會在 `~/.claude/skills/` 下建立 `rgs-core`、`rgs-main`、`rgs-pr` 三個 junction，指向本 repo，所以修改 repo 後會立即生效。移除時加上 `-Uninstall`。安裝後要重新開一個 Claude Code session。

第一次在專案中使用時，skill 會執行 `doctor.py --init`，產生 `.rgs/profile.json`（建置與測試指令、知識庫檔名、機密檔清單、模型等），並列出建議的權限規則。由於 Claude 不能修改自己的設定，這些規則需要你自行加入 `.claude/settings.json`，之後就不會反覆跳出權限確認。

## 使用範例

```
/rgs-main 在 calc.py 加上 div(a, b)，除以零時丟出 ValueError，並補上測試
/rgs-pr plan 新增收藏頁、餐廳詳細頁與分享功能（附上畫面描述）
/rgs-pr run M1
我已經在 GitHub 合併 PR #12，請接著做 M2
/rgs-pr release 1.2.0
/rgs-main digest app.log 當機前發生了什麼錯誤
/rgs-main status
```

## 運作方式

- **隔離**：每個任務在 `<repo>.rgs/<task>` 的獨立 git worktree 中實作，主 checkout 不受影響。合併閘門審查在另一個 detached worktree 中進行。
- **Guard**：agy 的全域設定會自動執行所有工具，`--mode plan` 也擋不住寫入，所以 rgs 在工作區放一個 PreToolUse hook（`.agents/hooks.json` → `rgs-guard.py`）。它的作用：
  - 只允許寫入規格列出的檔案
  - 禁止建置、測試與 git 指令，只放行唯讀的列目錄與搜尋指令
  - 禁止讀取機密檔
  - 子代理的工具呼叫同樣受限
- **不相信自我回報**：agy 在 timeout、工具被拒、子代理沒回報時都可能回報 SUCCESS。腳本以實際產出、git diff、範圍檢查與測試結果判定成敗，並用 exit code 區分失敗原因。
- **續跑**：任務狀態記錄在 `.rgs/state.json`，執行紀錄在 `.rgs/runs/`。Claude 用量或 Gemini 額度用完後，可以用 `status` 從中斷處繼續。

詳細規則見 [`skills/rgs-core/roles.md`](skills/rgs-core/roles.md)、[`workflow.md`](skills/rgs-core/references/workflow.md)、[`agy-cli.md`](skills/rgs-core/references/agy-cli.md)。

## 目錄

```
skills/
  rgs-main/SKILL.md         /rgs-main
  rgs-pr/SKILL.md           /rgs-pr
  rgs-core/                 共用核心（沒有 SKILL.md，不會變成指令）
    roles.md                角色與硬性規則
    references/             流程標準、agy 已驗證行為、sub-agent brief、委派、疑難排解、腳本參考
    templates/              規格、需求、設計、修正指示、審查備註、PR、release notes、知識庫骨架、prompts
    scripts/                rgs.py、review.py、guard.py、doctor.py、batch.py、digest.py、scope_check.py、secret_scan.py
    tests/                  單元與整合測試（以 fake_agy.py 代替 agy）
docs/origins/               整理流程時參考的原始素材（規則、spec、prompt、腳本）
install.ps1
```

## 測試

```
python -m unittest discover -s skills/rgs-core/tests
```

測試使用 `tests/fake_agy.py` 模擬 agy 的各種回應（成功、timeout、錯誤、額度用完、寫檔、審查、批次、摘要），不會消耗 Gemini 額度。整合測試會建立暫存 repo 與 bare remote，完整跑過 prepare → implement → fix → check → land，以及 review 與 ship。
