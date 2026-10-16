# 委派：batch 與 digest

這兩個子指令和開發流程無關，用來把「量大、雜訊多、只需要結論」的工作交給 Gemini，Claude 只看經過檢查的結果。兩者都在空的暫存資料夾中執行 agy，並套用唯讀 guard，agy 碰不到專案。

## 什麼時候委派

| 情況 | 做法 |
| :-- | :-- |
| 上百到上萬筆同性質資料（翻譯、分類、抽取、改寫） | `batch` |
| 很長的 log、規格、文件，只需要回答一個問題 | `digest` |
| 幾百行以內、或需要精確推理的內容 | Claude 自己讀，不委派 |
| 包含機密或個資 | 不委派 |

委派前先告訴使用者要送出哪些檔案或資料，以及大概的量。

## batch

1. 準備 `items.jsonl`（每行一個 JSON，必須有唯一的 `id`），以及說明要怎麼處理每一筆的 `instructions.md`。
2. 需要特定輸出欄位時，寫 `schema.json`：頂層 `items` 陣列，每筆含 `id` 與輸出欄位，必填欄位放進 `required`。
3. 只送需要的欄位：`--fields id,text,...`，例如官方答案這類不該讓模型看到的欄位就不要送。
4. 有規則可以自動檢查時，寫 validator：`def validate(item, result) -> list[str]`。
5. 執行（量大時用背景執行）：

   ```
   python -I <core>/scripts/batch.py --input items.jsonl --prompt instructions.md --out <dir>
          [--schema schema.json] [--fields id,text] [--batch 40] [--workers 8] [--validator check.py]
   ```

6. exit 3 代表額度用完，稍後用同一個指令重跑，會從 `raw/` 續跑；exit 5 代表還有 id 缺結果，同樣重跑即可。
7. 使用結果前：讀 `summary.json`，抽樣檢查 `results.jsonl`（每 100 筆至少看 5 筆，有 warnings 的全部看）。品質要求高的資料要安排人工校對：同樣輸入跑三次，結果一致率只有 76–84%。

先用 `--limit 20` 試跑，確認 prompt 與 schema 沒問題再跑全量。

## digest

```
python -I <core>/scripts/digest.py --question "<問題>" <檔案…> [--grep <regex> …] [--context 3] [--chunk-lines 800]
```

- **盡量用 `--grep` 先過濾**（錯誤關鍵字、函式名、ID），只送相關的行與前後文。這比整份送出便宜，也更可靠。
- 每個片段各自一次 agy 呼叫，回傳的每個結論都附檔案、行號與逐字引用；腳本會回原檔核對引用（`verified`）。
- **只根據 ✓ 的結論行動。** ✗ 的結論要自己打開引用的行確認；Gemini 曾經漏掉一個錯誤，卻宣稱全部找到。
- 「沒有找到」不等於「不存在」：重要的否定結論要用 grep 自己再確認一次。
- 結果在 `digest.md`（表格）與 `digest.json`。回報時標示 🧩，並說明有幾條核對通過。
