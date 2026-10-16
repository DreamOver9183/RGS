---
name: multi-agent-workflow
description: android_class 的開發分工：Gemini（agy）寫程式、Claude 主代理規劃與審查、sub-agent 做雜項；PR 由 agy（gemini-3.8-flash-high）唯讀審查 PASS 後，使用者自己在 GitHub 手動合併
metadata:
  node_type: memory
  type: feedback
  originSessionId: 975bd9c1-db05-4e4f-b9b5-e6f592bab7fe
  modified: 2026-10-15T11:22:05.828Z
---

在 android_class 做功能開發時，使用者指定的分工與流程（2026-10-15 確立）：

- **寫程式**：Gemini，透過 Antigravity CLI：`agy -p ... --model gemini-3.8-flash-high --mode accept-edits --add-dir <scratchpad> --output-format json`。只給改檔權限；從 JSON 取 `conversation_id`，修正輪用 `--conversation <id>` 續寫。不用 `--dangerously-skip-permissions`。
- **主代理（Claude）**：寫規格檔、審 Gemini 的 diff、決定修正意見；不自己改寫程式。
- **sub-agent**：呼叫 agy、跑建置與測試（含模擬器）、更新 AGENTS.md/README、commit、push、開 PR、跑 agy 審查（不合併，合併由使用者手動做）。
- **每段進度**：commit＋更新知識庫（AGENTS.md、README）＋開一個 PR。
- **合併條件**：Copilot 審查額度用完後，改由 agy 唯讀審查 PR diff（`--mode plan`，每次開新對話、不沿用寫程式的對話），判定 PASS 後由使用者手動在 GitHub 合併（2026-10-15 起：sub-agent 的 `gh pr merge` 會被權限系統擋下，使用者選擇自己合併），不等 GitHub Actions CI（CI 仍會自動跑；事後失敗再處理）。審查模型原本是 `claude-opus-5-5-high`；Antigravity 的 Opus 額度用完後（2026-10-15），使用者指定改用 `gemini-3.8-flash-high` 審查。
- 等待中的工作（CI、審查）不阻塞：先做下一段。
- 沒提到的情況要先問使用者。

**Why:** 使用者希望多用 sub-agent 與外部 CLI 分攤工作，Claude 專注在規劃與審查；Copilot 額度用完後改由 agy 把關（先 Opus，額度用完後改 Gemini Flash High）。

**How to apply:** 開新功能時照這個分工；PR 要有 agy 審查 PASS，之後請使用者手動合併（不要跑 `gh pr merge`）。2026-10-16 已完成 M0–M7 全部 10 個畫面的計畫。相關：[[follow-agents-md]]、[[android-build-env]]
