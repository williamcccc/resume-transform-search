# QA 測試個案設計範本 (Test Case Specification Template)

> **使用說明**：**選用**的補充格式。一般案例以 Tech Spec 範本第 7 節「QA 驗收案例矩陣」與 QA 報告第 4 節執行矩陣記錄即可；只有併發競態、跨服務整合等步驟複雜、需要詳述前置條件與清理方式的案例，才依本範本另寫說明。

---

# QA Test Case: [TC-XXXX 案例名稱]

## 1. 案例基本資訊與需求追溯 (Traceability)
* **案例識別碼**：`TC-001`
* **對應 PRD 驗收條款 (AC Mapping)**：`PRD AC 1.1 (條件篩選正向流程)` / `PRD AC 2.3 (檔案毀損提示)`
* **測試層級**：端到端整合測試 (E2E) / CLI 介面測試 / 實體儲存整合 (Integration)
* **情境分類 (Scenario Category)**：
  - [ ] **Happy Path (標準流程)**
  - [ ] **Edge Case (極限邊界)**：0-byte 空檔案、超大檔案、超長字串、特殊符號
  - [ ] **Concurrency (併發競態)**：多執行緒/Worker 同時操作同一筆資料
  - [ ] **Idempotency (操作冪等性)**：重跑批次處理與重複寫入資料庫
  - [ ] **Fault Injection (故障注入)**：資料庫斷線、API 429 配額用罄、超時中斷
  - [ ] **Security (惡意輸入防禦)**：壓縮炸彈、超大輸入；使用 LLM 者加測提示詞注入攻擊
* **優先級**：`P0 (阻斷)` / `P1 (核心)` / `P2 (次要)`

## 2. 前置條件與防 Flaky 設計 (Preconditions & Anti-Flaky)
* **隔離工作目錄**：強制使用獨立的 `tempfile.TemporaryDirectory`，避免跨測試相互污染。
* **相依服務狀態**：確認測試所需之相依服務（如本機資料庫容器）已就緒，並使用測試專用的資料庫或鍵前綴。
* **獨立測試資料**：使用專屬命名（如 `test_<uuid>`），避免與既有歷史資料衝突。

## 3. 測試步驟 (Test Steps)
1. 準備輸入檔案或測試 Payload。
2. 調用目標模組或執行 CLI 命令：
   ```bash
   python <cli_entry>.py <sample_path> --flags
   ```
3. 捕獲執行回傳碼（Exit Code）、標準輸出（stdout）與標準錯誤（stderr）。
4. 檢查輸出目錄之產出檔案。
5. 檢查資料庫狀態（如確認舊資料已清除，新資料正確寫入）。

## 4. 斷言與預期結果 (Assertions & Expected Outcomes)
* **功能行為**：Exit Code 為 0，產出內容完整符合驗收標準。
* **冪等性驗證**：連續執行兩次相同指令，資料總筆數保持恆定，無重複資料堆積。
* **檔案防鎖定**：測試結束後檔案控制代碼（File Handle）100% 釋放，暫存目錄可順暢刪除，無 `PermissionError: [WinError 32]`。

## 5. 清理與復原 (Teardown)
* 乾淨移除暫存檔案與目錄。
* 清理測試專用的資料庫資料或鍵值（如 `<prefix>:test_*`）。
