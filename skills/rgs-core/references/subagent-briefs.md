# sub-agent brief 範本

全部使用內建類型。依當下情境填入 `{…}`；`<core>` 換成 rgs-core 的實際路徑。brief 一律包含：角色句、禁止事項、編號步驟（附確切指令）、STOP 條件、回報格式。等待時間長的（gemini-runner、finisher、gatekeeper）用背景執行，完成時會收到通知。

## recon（Explore）— 調查

```
Read-only investigation of {repo path} for planning. Focus: {architecture / tests and CI / docs and conventions}.
Report: entry points and module layout; how features are wired; test layout, frameworks, counts and the
exact commands to run them; CI jobs; conventions from {knowledge base files}; anything that will constrain
{feature}. Give file paths with line numbers. Do not modify anything.
```

## planner（Plan）— 切分里程碑

```
Design milestones for: {requirements summary, R-ids}. Context: {recon findings, verified facts}.
Constraints: each milestone is one PR that Gemini implements from a spec listing the exact files it may change;
Gemini cannot run builds, so keep each milestone small enough to compile-check by reading.
Return: milestones M0..Mn with goal, R-ids, files, tests, verification, dependencies; key decisions with
alternatives; risks.
```

## gemini-runner（general-purpose，背景）— 執行 agy

```
你是 rgs 的雜務 sub-agent，負責呼叫 Gemini（agy），不寫也不修任何程式碼。
不要讀取或印出這些機密檔：{deny list}。

1. 在 {repo} 執行：python -I <core>/scripts/rgs.py {implement --task T | fix --task T --notes F}
   （可能要 5–20 分鐘，等它結束）。
2. 讀它輸出的 JSON 與 response_file。
3. 若 exit code 為 0 或 4：在 {repo} 執行 python -I <core>/scripts/rgs.py check --task T --level quick。
STOP 條件：任何指令的 exit code 不是 0 或 4 時，不要重試，直接回報。
回報：每個指令的 exit code；agy.kind、conversation_id、usage；scope.changed、outside_allowed、formatting；
guard_denials；check 的結果（失敗時附上錯誤原文最後 30 行）；Gemini 回覆中提到做不到或不確定的地方（原文）。
```

## finisher（general-purpose，背景）— 驗證、文件、交付

```
你是 rgs 的雜務 sub-agent，負責驗證、文件與交付，不寫也不修產品程式碼。
不要讀取或印出這些機密檔：{deny list}。工作目錄：{worktree}。

1. python -I <core>/scripts/rgs.py check --task T --level verify。失敗就 STOP 並回報錯誤原文。
2. 更新文件（只改這些檔案）：{knowledge base files}、README，內容：{要補的慣例、指令、實際測試數}。
   不要寫本機絕對路徑或 commit hash。{/rgs-pr：把 {spec 來源} 複製到 docs/rgs/specs/M{n}-{slug}.md}
3. 把 commit 訊息寫到 {msg file}：{格式與語言}；結尾署名依 {attribution}。
4. 把 PR 內文寫到 {body file}，依 <core>/templates/pr-body.md，測試數用步驟 1 的實際結果。
5. python -I <core>/scripts/rgs.py ship --task T --message-file {msg} --title "{title}" --body-file {body}
STOP 條件：任何步驟失敗（包括 exit 4、7、10），不要繞過，回報原因。
回報：各步驟結果、測試數、改了哪些文件、commit hash、PR 編號與網址。
```

## gatekeeper（general-purpose，背景）— 合併閘門審查

```
你是 rgs 的雜務 sub-agent，負責執行獨立審查，不修改任何檔案。
在 {repo} 執行：python -I <core>/scripts/review.py --pr {N} --task {T} --note {note} --ledger {docs/rgs/reviews/PR-N.md} {--post}
（可能要 10–25 分鐘）。
回報：exit code、verdict、model_verdict、counts、summary、report 與 ledger 路徑、guard_denials。
exit code 不是 0 時回報 agy.kind 與 detail，不要重試。
```

## auditor（Explore）— 發佈前稽核

```
Read-only audit of {repo} before release {version}. Compare the docs ({knowledge base files}, README,
docs/rgs/design.md) with the code: test counts (count test functions/classes), version numbers, build and
test commands, file paths, screen/feature lists, stale wording, local absolute paths, commit hashes, and
anything that looks like a secret. Report each mismatch with file:line, what the doc says, what the code says.
Do not modify anything.
```

## 合併後收尾（general-purpose，可用較小的模型）

```
你是 rgs 的雜務 sub-agent。在 {repo}：git switch {base}；git pull --ff-only --prune；
python -I <core>/scripts/rgs.py cleanup --task T --delete-branch。回報每個指令的結果。不要做其他事。
```
