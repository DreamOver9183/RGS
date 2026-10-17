# rgs-facet 審查摘要與附錄格式

本文定義跨模型計畫審查完成時，寫入計畫檔的「審查摘要」與「附錄」格式規範。

- **審查摘要**：放在 `<!-- facet:appendix -->` 標記之前、計畫正文的最後。ExitPlanMode 呈現時使用者第一眼可見。
- **附錄**：放在 `<!-- facet:appendix -->` 標記之後。送審時會被 `prompt.load_plan` 截除，不會送給審查者。

---

## 1. 審查摘要格式（放在 `<!-- facet:appendix -->` 之前）

```text
## 審查摘要
- 審查者／模型：Gemini（要求：<requested_model>／agy 回報：<reported_model 或「未確認」>）
- 輪數：N / MAX_ROUNDS
- 最終 verdict：logic <…>、gaps <…>、verifiability <…>
- 收斂方式：三個角度都 APPROVED／仲裁收斂（沒有採納任何 finding）／達到輪數上限／未審查（原因）
- 採納的 findings：<id：一句話>
- 駁回的 findings 與理由：<id：理由>
- 剩餘風險與未覆蓋範圍：<審查者的 limitations 加上 Claude 的判斷>
- 原始紀錄：<raw_dir 的上層資料夾>
- 註：APPROVED 只表示審查者未發現問題，不代表計畫正確。
```

### 說明
- **審查者／模型**：要求的模型（`requested_model`）與 agy 回報的模型（`reported_model`）分開列出；若 `reported_model` 為 `null`，寫「未確認」。
- **收斂方式**：
  - `三個角度都 APPROVED`：本輪三個角度皆通過。
  - `仲裁收斂（沒有採納任何 finding）`：審查者雖有 findings 但全部經 Claude 仲裁駁回，計畫內容無須修改。
  - `達到輪數上限`：已達 `MAX_ROUNDS`（預設 3 輪）。若最後一版有修訂，必須加註「v{n} 是第 {MAX_ROUNDS} 輪後的修訂，未經審查」。
  - `未審查（原因）`：例如審查迴圈失敗或中斷，使用者選擇不經跨模型審查直接交付，須註明未審查原因。

---

## 2. 附錄格式（放在 `<!-- facet:appendix -->` 之後）

```text
<!-- facet:appendix -->

# 附錄：跨模型計畫審查紀錄

## 逐輪審查結果

### 第 1 輪
- logic：verdict = <APPROVED|REVISE|BLOCKED>
  - coverage：<本次檢查範圍>
  - limitations：<限制與未覆蓋之處>
- gaps：verdict = <APPROVED|REVISE|BLOCKED>
  - coverage：<本次檢查範圍>
  - limitations：<限制與未覆蓋之處>
- verifiability：verdict = <APPROVED|REVISE|BLOCKED>
  - coverage：<本次檢查範圍>
  - limitations：<限制與未覆蓋之處>

## 逐輪處置表

| 輪次 | 角度 | ID | 嚴重度 | 摘要 | 處置（採納／駁回） | 理由 | 對應的計畫修改 |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| 1 | logic | F1 | high | 步驟 2 順序錯誤 | 採納 | 修正相依性順序 | 調換步驟 2 與 3 |
| 1 | gaps | F1 | low | 未定義回滾方案 | 駁回 | 本階段為唯讀探索無須回滾 | 無 |
```
