# QA 測試個案設計範本 (Test Case Specification Template)

> **使用說明**：在 Step 1 規格化與 Step 4 實測階段，AI 對照 PRD 的驗收標準 (AC)，進行**需求追溯**與**極端邊界挖掘**，產出本測試個案設計。

---

# QA Test Case: [TC-XXXX 案例名稱]

## 1. 案例基本資訊與需求追溯 (Traceability)
* **案例識別碼**：`TC-001`
* **對應 PRD 驗收條款 (AC Mapping)**：`PRD AC 1.1 (工作年資正向篩選)` / `PRD AC 2.3 (檔案毀損提示)`
* **測試層級**：端到端整合測試 (E2E) / CLI 介面測試 / 實體儲存整合 (Integration)
* **情境分類 (Scenario Category)**：
  - [ ] **Happy Path (標準流程)**
  - [ ] **Edge Case (極限邊界)**：0-byte 空檔案、超大檔案、超長字串、特殊符號
  - [ ] **Concurrency (併發競態)**：多執行緒/Worker 同時操作同候選人
  - [ ] **Idempotency (操作冪等性)**：重跑批次轉檔與 Redis 重複切片入庫
  - [ ] **Fault Injection (故障注入)**：Redis 斷線、API 429 配額用罄、超時中斷
  - [ ] **Security (惡意輸入防禦)**：Zip Bomb、Prompt 提示詞注入攻擊
* **優先級**：`P0 (阻斷)` / `P1 (核心)` / `P2 (次要)`

## 2. 前置條件與防 Flaky 設計 (Preconditions & Anti-Flaky)
* **隔離工作目錄**：強制使用獨立的 `tempfile.TemporaryDirectory`，避免跨測試相互污染。
* **相依服務狀態**：確認本機 Docker Redis 服務運行於 `localhost:6379`。
* **獨立測試資料**：使用專屬命名（如 `test_candidate_uuid`），避免與既有歷史資料衝突。

## 3. 測試步驟 (Test Steps)
1. 準備輸入檔案或測試 Payload。
2. 調用目標模組或執行 CLI 命令：
   ```bash
   python convert_to_md.py <sample_path> --flags
   ```
3. 捕獲執行回傳碼（Exit Code）、標準輸出（stdout）與標準錯誤（stderr）。
4. 檢查輸出目錄之產出 Markdown 檔案與隔離檔案（quarantine）。
5. 檢查 Redis 資料庫狀態（如確認舊切片已清除，新切片正確入庫）。

## 4. 斷言與預期結果 (Assertions & Expected Outcomes)
* **功能行為**：Exit Code 為 0，產出內容完整符合驗收標準。
* **冪等性驗證**：連續執行兩次相同指令，Redis 總切片數保持恆定，無重複資料堆積。
* **Windows 檔案防鎖定**：測試結束後檔案控制代碼（File Handle）100% 釋放，暫存目錄可順暢刪除，無 `PermissionError: [WinError 32]`。

## 5. 清理與復原 (Teardown)
* 乾淨移除暫存檔案與目錄。
* 清理測試專用的 Redis 鍵值（`resume:chunk:test_*`）。
