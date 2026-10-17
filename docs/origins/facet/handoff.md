# 交接文件：facet skill

> 給 Claude Code 讀。請依「執行步驟」完成：預檢 → 建立 skill → 試跑驗收。

## 1. 目標

在 Claude Code 的 Plan 模式中，讓 Claude 當規劃者與仲裁者，呼叫 Antigravity CLI（`agy`）上的其他模型當審查者，反覆審查並修訂計畫。**審查全部在交付前完成，最終只用 ExitPlanMode 呈現一份計畫給使用者。**

參考來源：GitHub `chaseai-yt/claudex-loop` 的「計畫審查」階段。本 skill **只做計畫硬化，不含 build / inspect**。

## 2. 已決定事項

| 項目 | 決定 |
|---|---|
| Skill 名稱 | `facet` |
| 規劃者 / 仲裁者 | 目前 Claude Code 的 Claude session |
| 審查者 | 透過 `agy -p` 呼叫的非 Claude 模型 |
| 目前審查模型 | Gemini 3.8 Flash（Antigravity 目前只開放這個） |
| 未來升級 | Gemini 4 開放後，只改 `REVIEWER_MODEL` 參數，必要時改為雙審查者 |
| 輪數上限 | 預設 3 輪 |
| 交付形式 | 單一計畫，附「審查摘要」 |

**名稱由來**：Facet 即鑽石的「切面」。同一個專案，每個 Agent（審查視角）負責不同切面，合起來才是最耀眼的成品。對應本 skill 的 logic / gaps / verifiability 三個審查視角，Claude 負責仲裁與最後拋光。

### 名稱的兩個提醒（請務必處理）

1. **名稱看不出用途，觸發要靠 description。** Claude 是依 SKILL.md 的 description 判斷何時載入，所以 description 必須明確寫出觸發情境：使用者要求計畫「經跨模型審查再交付」、在 Plan 模式下要用其他模型審查計畫，或明確呼叫 `/facet`。description 要同時寫「做什麼」與「何時用」，並註明「只做計畫審查，不含 build / inspect」。若日後覺得名稱仍不夠直觀，可改用 `facet-plan-review`，並在擴充 build / inspect 時拆成 `facet-plan`、`facet-build` 等。
2. **`facet` 是通用字，可能與既有 skill 或 plugin 同名。** 建立前先檢查 `~/.claude/skills/`、專案的 `.claude/skills/`，以及已安裝 plugin 的 skill 名稱與 slash command，若有衝突要先回報使用者，不可直接覆蓋。

為什麼審查者不用 Opus / Sonnet：同為 Claude 家族，盲點相近，獨立性低。Gemini 是不同供應商，更符合 claudex-loop「建造者不給自己打分」的精神。

## 3. 流程

1. **偵察**：讀程式碼與相關文件，列出假設清單。
2. **釐清**：只問會改變結果的問題，並批次提問。
3. **起草 v1**：包含目標、步驟、驗收條件、proof 指令、風險。
4. **送審**：每輪用不同視角（見 §5）呼叫 `agy -p`，要求輸出結構化 verdict。
5. **仲裁**：Claude 逐條 finding 決定「採納 / 駁回」，並寫明理由。
6. **修訂**：只有 Claude 能改計畫，審查者不能改。
7. **重審**：計畫一改，先前的 APPROVED 作廢，必須重審。
8. **收斂**：審查者回 APPROVED，或到輪數上限就停。
9. **交付**：ExitPlanMode 呈現最終計畫，附審查摘要。

## 4. 參數

| 參數 | 預設 | 說明 |
|---|---|---|
| `REVIEWER_MODEL` | `gemini-3.8-flash`（待預檢確認實際 ID） | 所有 `agy --model` 都讀這個值 |
| `MAX_ROUNDS` | 3 | 已完成的審查輪數上限 |
| `REVIEW_LENSES` | `logic,gaps,verifiability` | 每輪的審查視角 |
| `AGY_TIMEOUT` | 180（秒） | 每次呼叫的 `timeout` |

## 5. 審查視角與 prompt 範本

三個視角：
- **logic**：邏輯矛盾、步驟順序錯誤、不成立的假設。
- **gaps**：遺漏的邊界條件、依賴、失敗情境、回滾方式。
- **verifiability**：驗收條件與 proof 指令能否客觀驗證。

範本（`{LENS}` 與 `{PLAN}` 由 Claude 代入）：

```text
你是獨立的計畫審查者，只讀不改。請從「{LENS}」角度審查以下計畫。
規則：
- 每條 finding 必須引用計畫中的具體段落或條目作為證據，沒有證據就不要提。
- 沒有問題就回 APPROVED，不要為了湊數挑小毛病。
- 無法判斷（資訊不足）回 BLOCKED，並說明缺什麼。
- 只輸出下列 JSON，不要其他文字。

{"verdict":"APPROVED|REVISE|BLOCKED",
 "findings":[{"id":"F1","severity":"high|medium|low","evidence":"引用的段落","issue":"問題","suggestion":"建議"}],
 "coverage":"本次審查實際檢查了哪些部分",
 "limitations":"未能檢查或不確定之處"}

===== 計畫開始 =====
{PLAN}
===== 計畫結束 =====
```

第二輪起，prompt 要附上上一輪的 findings 與 Claude 的處置（採納 / 駁回及理由），請審查者確認是否已解決。

## 6. 仲裁規則

- 無證據或引用不存在內容的 finding：駁回。
- 與使用者明確要求衝突的 finding：駁回，並記入審查摘要。
- 會改變結果的重大決策：不自行決定，回頭問使用者。
- 不為了讓審查者點頭而過度修改計畫。
- APPROVED 只代表「審查者未發現問題」，不代表計畫正確，審查摘要須如實寫出。

## 7. 守則

- 審查者只讀不改：呼叫 `agy` 時**不要**加 `--yolo`；評估是否可用 `--sandbox`。
- `agy` 失敗、逾時、輸出無法解析成 JSON，一律**不算核准**，要明講，**不可默默換模型**。
- Bash 呼叫一律加 `timeout "$AGY_TIMEOUT"`。
- Plan 模式只能改計畫檔：審查紀錄放在計畫檔的附錄；若 `/tmp` 可寫，原始輸出放在 repo 外的暫存目錄。
- 記錄「要求的模型」與「實際回報的模型」，兩者分開寫；無法確認就如實寫「未確認」。

## 8. 審查摘要格式（附在最終計畫末尾）

```text
## 審查摘要
- 審查者 / 模型：…（要求：… / 實際：…）
- 輪數：N / MAX
- 最終 verdict：…
- 採納的 findings：…
- 駁回的 findings 與理由：…
- 剩餘風險與未覆蓋範圍：…
```

## 9. 已知事項（請預檢確認）

資料來自第三方文件與 GitHub issue，**未經本人在你的環境實測**：
- `agy -p "<prompt>"` 可作為非互動子代理；`--model` 可選模型；安裝：`curl -fsSL https://antigravity.google/cli/install.sh | bash`。
- 某第三方 adapter 文件列出 `--output-format stream-json`、`--non-interactive`，但它自己說明旗標可能要依實際 `agy --help` 修正。
- GitHub issue #318（版本 1.0.6）：`agy -p` 在非 TTY 環境（子程序、輸出導到管道）會無限卡住；可能已修，需實測。
- 首次需人工登入，token 存在 `~/.gemini/antigravity-cli/antigravity-oauth-token`。

## 10. 執行步驟

**步驟 A：預檢（先做，結果決定後續設計）**
0. **名稱衝突檢查**（見 §2 提醒 2）：搜尋 `~/.claude/skills/`、`.claude/skills/` 與已安裝 plugin 中是否已有 `facet`；有衝突先回報。
1. `agy --help`：確認非互動旗標、輸出格式、模型選項、是否有 sandbox / 唯讀模式。
2. 列出可用模型，確認 Gemini 3.8 Flash 的實際 ID。
3. 在 Bash 中實測：`timeout 60 agy -p "回覆 OK" --model <id> < /dev/null`，確認不卡住、輸出可解析。
4. 測試能否傳入長文字（計畫約數千字）：用 stdin、檔案路徑，或直接放進 prompt，選出可行方式。
5. 測試是否支援續接 session；若不支援，改為每輪新 session，並在 prompt 附上前輪 findings 與處置。
6. 把預檢結果回報給使用者，若有與本文件假設不符之處，先停下來討論再繼續。

**步驟 B：建立 skill**
- 位置：`~/.claude/skills/facet/SKILL.md`（預設放使用者層級；若使用者想綁定專案則放 `.claude/skills/`）。
- frontmatter 的 description 要寫清觸發情境：使用者要求「計畫需經跨模型審查再交付」，或明確呼叫 `/facet`。
- 內容依本文件 §3–§8。審查 prompt 範本和審查摘要格式可放 `references/` 子目錄。
- 參數集中在 SKILL.md 開頭，方便日後改 `REVIEWER_MODEL`。

**步驟 C：試跑驗收**
用一個小任務（例如「新增一個 CLI 參數」）在 Plan 模式跑完整流程，確認：
- [ ] 審查者真的被呼叫，且能解析出 JSON verdict
- [ ] findings 被逐條處置並記錄
- [ ] 計畫修改後，先前的 APPROVED 被視為作廢並重審
- [ ] `agy` 逾時或失敗時，有明確回報，且不會被當成核准
- [ ] 最終只呈現一份計畫，附審查摘要
- [ ] 全程沒有任何檔案被審查者修改

## 11. 未決問題（請與使用者確認）

- `agy` 是否支援唯讀 / sandbox 模式？若不支援，如何確保審查者不改檔？
- Gemini 4 開放後，是否改為「雙審查者」（Gemini 4 對抗式 + 3.8 Flash 快速掃描）？
- 審查摘要要放在計畫檔裡，還是另存檔案？
