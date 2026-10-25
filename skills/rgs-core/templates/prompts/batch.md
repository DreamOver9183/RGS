不要讀寫檔案或執行指令，直接依下列要求處理輸入；完成後呼叫 finish 工具交出結果，finish 是唯一可以使用的工具。

{{instructions}}

輸入（每行一筆 JSON）：

{{items}}

每一筆輸入都必須在 finish 的 `items` 中回傳一筆結果，`id` 必須與輸入完全相同，不可遺漏、不可新增。
