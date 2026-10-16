---
name: rgs-pr
description: 中大型專案的 Claude × Gemini（Antigravity CLI，agy）× sub-agent 協作開發流程，關鍵節點由使用者把關。流程是：需求與設計文件經使用者核准 → 切成里程碑 → 每個里程碑由 Gemini 依規格實作、Claude 審 diff → sub-agent 驗證、更新知識庫並開 PR → agy 以新對話做唯讀的合併閘門審查，Claude 逐條裁決 → 使用者在 GitHub 手動合併 → 知識沉澱 → 發佈 release。只要使用者輸入 /rgs-pr，或提到「照 SOP 開 PR」「Gemini 寫 code、Claude 審核、我自己合併」「多個畫面或功能的開發計畫」「里程碑」「發佈一版 release」，或回報「已合併 PR #N，請繼續」，就使用這個 skill。另有 batch、digest、status 子指令。單一小任務、可以直接 push main 的情境改用 rgs-main。
argument-hint: init | plan <需求> | run M<n> | merged <PR#> | release <版本> | status | batch … | digest …
---

# /rgs-pr：人工把關的 PR 開發流程

分工的理由：
- **Claude**：規劃與審查。品質靠它把關。
- **Gemini**：依規格寫程式。成本低、能長時間工作，但不能建置或測試，偶爾會寫錯或越界。
- **sub-agent**：處理耗時的雜務（跑 agy、驗證、文件、git），讓主對話保持精簡。
- **agy 獨立審查**：開新對話，用另一個角度攔下漏網的問題。
- **使用者**：核准設計、決定什麼進主幹。

## 開始前

1. 找到共用核心：`<core>` 是本 skill 基底目錄的同層資料夾 `rgs-core`（例如 `~/.claude/skills/rgs-core`）。
2. 讀 `<core>/roles.md`（角色、硬性規則、回報標記），以及 `<core>/references/workflow.md`（閘門 G0–G8、審查標準、裁決方式、commit／PR 慣例、堆疊）。這兩份規則適用於所有子指令。
3. 每個子指令開始時，都要從磁碟重讀 profile 指定的知識庫，以及 `docs/rgs/design.md`（若存在）。
4. 依參數分流到下面的小節。使用者用自然語言表達時也要對應，例如「已經合併 PR #5，請接著做 M6」= `merged 5` + `run M6`；「用量恢復了，請繼續」= `status`。

腳本一律在專案目錄用 `python -I <core>/scripts/<name>.py` 執行；exit code 見 `<core>/references/scripts.md`。sub-agent 的 brief 範本在 `<core>/references/subagent-briefs.md`。

## init

1. `doctor.py --init --flow pr`：產生 `.rgs/profile.json` 草稿，並檢查 agy、模型、額度、gh 登入、remote、知識庫。
2. 把草稿中的 quick／verify 指令、`worktree_copy`（例如 `local.properties`）、機密清單、知識庫檔名、語言給使用者確認；不確定的地方用 AskUserQuestion。
3. 知識庫不存在時，依 `<core>/templates/knowledge-base-skeleton.md` 建立。
4. 把 `--init` 列出的權限規則交給使用者，請使用者自行加入。
5. 把 profile 與知識庫 commit 進 base 分支（直接 commit，或開一個 `chore:` PR）之前，先問使用者。

## plan <需求>

1. 釐清需求。不清楚的地方一次問完（AskUserQuestion），然後依 `<core>/templates/requirements.md` 寫 `docs/rgs/requirements.md`，每條需求都要有 R-編號與可驗證的驗收條件。
2. 調查：最多兩個 recon（Explore）sub-agent，分別看架構，以及測試／CI／文件。
3. 規劃：一個 planner（Plan）sub-agent 把需求切成里程碑。每個里程碑對應一個 PR，大小要讓 Gemini 不必執行程式也能寫對。
4. Claude 依 `<core>/templates/design.md` 寫 `docs/rgs/design.md`，內容包括：
   - 已查證事實、決策紀錄、架構、風險
   - 里程碑（各自對應的需求、檔案、測試、驗證、相依）
   - 追溯矩陣、狀態總覽
5. 選用：設計牽涉不熟的領域時，可以請 agy 唯讀審查設計：`review.py --diff-base <base> --spec docs/rgs/design.md`，或先 commit 到一個分支再審。逐條裁決意見。
6. **G0**：把需求與設計摘要給使用者，取得核准後才開始 `run`。

## run M<n>（一個里程碑）

1. **規格**：依 `<core>/templates/milestone-spec.md` 寫 `.rgs/runs/m<n>/spec.md`，內容包括：
   - 對應的需求、可修改檔案的精確清單
   - 設計與實作要點、不要做的事
   - 驗收條件、必要測試
   - design.md 的教訓清單

   「可修改的檔案」決定 guard 允許寫入的範圍，測試檔也要列進去。

2. **準備**：
   ```
   python -I <core>/scripts/rgs.py prepare --task m<n> --spec .rgs/runs/m<n>/spec.md --flow pr --branch <feat|fix|chore>/m<n>-<slug>
   ```
   依賴前一個尚未合併的里程碑時，加上 `--stack-on m<n-1>`。

3. **實作**：用背景 sub-agent（brief：gemini-runner）執行 `rgs.py implement`，再執行 `check --level quick`。等完成通知，期間可以做不相依的工作，例如寫下一個里程碑的規格。

4. **Claude 審查**：
   - 讀 runner 的回報，以及 `rgs.py diff` 產生的 diff。
   - 依 workflow.md 的標準審查。
   - 有問題就依 `<core>/templates/fix-notes.md` 寫修正指示，交給 gemini-runner 執行 `rgs.py fix`，再回到這一步。
   - 超過上限（exit 6）就停下來問使用者。

5. **交付**：用背景 sub-agent（brief：finisher）完成以下工作：
   - `check --level verify`
   - 更新知識庫與 README（含實際測試數）
   - 把 spec 複製到 `docs/rgs/specs/M<n>-<slug>.md`
   - 依 `<core>/templates/pr-body.md` 寫 PR 內文
   - 執行 `rgs.py ship`

   任何一步失敗就回到步驟 4。

6. **合併閘門**：
   - 依 `<core>/templates/review-note.md` 寫審查備註（刻意的偏離、預期測試數、上一輪裁決）。
   - 用背景 sub-agent（brief：gatekeeper）執行：
     ```
     review.py --pr <N> --task m<n> --note <note> --ledger docs/rgs/reviews/PR-<N>.md [--post]
     ```
     是否加 `--post` 依 profile 的 `pr.post_review_comment` 決定。
   - 在主 checkout 執行，ledger 寫在主 checkout 的 `docs/rgs/reviews/`：它不進 PR，合併後在 `merged` 的知識沉澱一起 commit。報告貼在 PR 留言，ledger 會記下留言網址。
   - agy 沒有可用結果（exit 3／5）時，用 ⚠️ 回報，**不能當成 PASS**。摘要有 `post_error` 時，表示審查有結果但留言沒貼上：照常裁決，並回報使用者。

7. **裁決**：
   - 在 ledger 裡把每條意見改成「採納」「不採納（附理由）」或「延後到 M<k>（附理由）」。
   - 採納的意見寫成修正指示，回到步驟 4；修正後由 finisher 重跑 `ship` 推到同一個 PR，再做一次複審，審查備註中要附上上一輪的裁決。
   - 沒有未解決的 blocker／major 才算通過。

8. **交給使用者**：回報 PR 網址、判定、裁決摘要、測試數、尚未驗證的項目，請使用者在 GitHub 手動合併。**不要執行 `gh pr merge`。**

   不需要等使用者合併，可以接著 `run` 下一個里程碑（相依的就堆疊）。CI 不阻塞流程，但開下一個 PR 前看一次上一個 PR 的 CI；失敗就把錯誤寫成修正指示。

## merged <PR#>

使用者回報已合併後：

1. 有任務堆疊在這個里程碑上（`prepare --stack-on m<n>`）時，先對每個子任務執行 `rgs.py retarget --task m<k>`。它會確認這個 PR 已合併，把子 PR 的 base 改成 profile 的 `base_branch`；如果是 squash／rebase 合併，還會把子任務自己的 commit rebase 到 base 再推送。細節見 workflow.md「平行與堆疊」。exit 8（衝突）或 10（PR 已關閉、推送被拒）時停下來回報。
2. 用 sub-agent（brief：合併後收尾）執行：切到 base 分支、`git pull --ff-only --prune`、`rgs.py cleanup --task m<n> --delete-branch`。遠端的父分支要在 retarget 之後才刪。
3. 知識沉澱：
   - 只把新的決策、慣例、技術坑寫進知識庫。
   - 更新 `design.md` 的狀態總覽、追溯矩陣與教訓清單。
   - commit 這些文件，以及這個 PR 的 ledger（`docs/rgs/reviews/PR-<N>.md`）。直接 commit 到 base 分支或另開 PR，依 init 時與使用者的約定。

## release <版本>

照 workflow.md 的「發佈」小節進行：

1. auditor 稽核（brief：auditor）。
2. 修正文件。
3. 版本號由 Gemini 依小型 spec 實作，經審查後交給使用者合併。沒有版本號檔案的專案略過。
4. 從合併後的 commit 建置產物（沒有建置步驟就用 `git archive`），計算 SHA-256，寫 release notes，並用 `secret_scan.py --files` 掃描 notes 與發佈的檔案。
5. **建立 GitHub release 會對外公開：執行 `gh release create --target <commit>` 前，先把版本號、產物、SHA-256 與 release notes 給使用者確認，並提供 `--draft`（不公開、不建 tag）的選項。**

## status

執行 `rgs.py status`，對照 `docs/rgs/design.md` 的狀態總覽，列出每個里程碑的 `step`、PR 與下一步，然後從中斷處接著做。worktree 不存在但狀態還沒結束時，重跑 `prepare` 即可恢復，同一個分支會被重用。

## batch／digest

讀 `<core>/references/delegation.md` 照做。
