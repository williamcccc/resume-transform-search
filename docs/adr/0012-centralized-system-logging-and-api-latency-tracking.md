# ADR-0012: 集中式系統技術日誌與外部 API 請求耗時可觀測性治理

## 1. 狀態
已採納 (Accepted)

## 2. 背景與問題陳述 (Context & Problem Statement)
原先系統在處理文件轉換與履歷向量檢索時，主要依賴終端 `print()` 標籤輸出與業務級的 CSV 審計檔案。當系統遭遇非預期網路抖動、Google API 429 速率限制（RPM）或配額用罄（RPD）、Redis KNN 搜尋緩慢等技術問題時，缺乏標準的系統技術日誌（Technical Log）與毫秒級 API 耗時（Latency）監控，導致排錯不易且難以量化各外部服務的效能瓶頸。

## 3. 評估選項 (Options Evaluated)
* **選項 A (維持現狀)**：僅依賴終端輸出與 CSV 審計報表。
  - *缺點*：無標準記錄等級（DEBUG/INFO/WARNING/ERROR），難以進行自動化 log parsing 或長期滾動保存。
* **選項 B (引入重型第三方 APM / OpenTelemetry)**：
  - *缺點*：過度設計，增加外部套件依賴與維運成本，違背輕量化原則。
* **選項 C (Python 標準庫 `logging` 滾動日誌 + `retry_call` 耗時探針 - 最終採納)**：
  - 於 Infrastructure 層建立集中式 `setup_logging`，使用 `RotatingFileHandler` 進行滾動備份與 UTF-8 編碼。
  - 支援 `delay=True` 與 `close_logging()`，根除 Windows 檔案鎖死 (`[WinError 32]`) 隱患。
  - 在 `retry_call` 與 `RedisVectorStore` 注入高精度 `time.perf_counter()` 耗時量測，自動輸出請求耗時、重試退避與錯誤堆疊。
  - 嚴格遵守 Twelve-Factor 原則，所有日誌參數（等級、路徑、大小、備份數）由 `AppConfig` 與 `.env` 統一注入。

## 4. 架構決策 (Decision Outcome)
採納 **選項 C**。

## 5. 8 大架構維度衝擊評估 (Architecture Guardrails)
1. **PII 個資隱私**：日誌僅輸出檔名、候選人 ID 與耗時統計，嚴禁印出原始履歷全文或金鑰，符合 Zero-Leak 原則。
2. **容量與極限**：使用 `RotatingFileHandler` 限制最大檔案大小與備份數（預設 10MB x 5 份），杜絕磁碟暴滿。
3. **依賴反轉 (DIP)**：日誌配置與計時封裝於 Infrastructure 層，Domain 層零外部依賴。
4. **資源管理安全**：支援延遲開啟與顯式資源釋放，杜絕檔案控制代碼洩漏與鎖死。
5. **Token 能效**：計時與日誌為本機原生操作，零額外 Token 消耗。
6. **配置解耦 (12-Factor)**：`LOG_LEVEL`、`LOG_FILE`、`LOG_MAX_BYTES`、`LOG_BACKUP_COUNT` 全面納入配置治理。
7. **測試覆蓋率**：新增 `test_logging_and_latency.py`，全套 104 項單元測試 100% 綠燈。
8. **代碼治理**：`audit_guardrails.py` AST 靜態掃描 100% 通過（零 P0 違規、零警告）。
