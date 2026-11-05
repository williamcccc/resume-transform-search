# PRD 與 DDD 技術實作規格書 (系統技術日誌與 API 請求耗時日誌)

## 一、產品需求文件 (PRD)

### 1. 商業與維運背景
在生產環境與批次處理中，原先僅依賴 stdout 終端輸出與 CSV 審計檔案，難以在系統發生異常、網路超時、API 速率限制（429 RPM / RPD）或 Redis 檢索緩慢時進行深度的技術排錯（Troubleshooting）。因此需要建立**集中式系統技術日誌**與**外部 API 請求毫秒級耗時監控**，兼顧可觀測性（Observability）與 Twelve-Factor 配置治理。

### 2. 範疇界定 (Scope)
* **In-Scope**:
  1. **集中式系統技術日誌 (`src/infrastructure/logging.py`)**：
     - 基於 Python 內建 `logging` 與 `RotatingFileHandler` 實作。
     - 支援日誌輪轉（預設 10MB，備份 5 份）、UTF-8 編碼與延遲開啟（`delay=True` 防 Windows 檔案鎖死）。
     - 格式標準化：`[時間戳] [等級] [模組名稱:行號] - [訊息]`。
  2. **API 請求耗時與重試日誌 (`src/infrastructure/transformers/utils.py`)**：
     - 擴充 `retry_call` 支援操作標識（`op_name`）。
     - 每次 API 呼叫（成功、重試、失敗）精確記錄 `time.perf_counter()` 耗時毫秒數與重試退避資訊。
     - 全面涵蓋：Gemini 轉檔、自我審核、Gemini Embedding 向量化、LLM Judge 獨立評判。
  3. **Redis 資料庫操作延遲日誌 (`src/infrastructure/stores/redis_vector_store.py`)**：
     - 記錄向量索引切片寫入（Upsert）與 KNN 檢索之耗時。
  4. **Twelve-Factor 配置貫通 (`src/infrastructure/config.py` & `.env.example`)**：
     - 新增 `LOG_LEVEL`（預設 INFO）、`LOG_FILE`（預設 `logs/app.log`）、`LOG_MAX_BYTES`、`LOG_BACKUP_COUNT`。
  5. **日誌零洩漏安全 (Zero-Leak Logging)**：
     - 絕不明文印出未脫敏履歷全文、身分證號、手機號碼或 API Authorization Header。
* **Out-of-Scope**:
  - 不引入第三方 heavyweight 監控代理（如 Prometheus / OpenTelemetry Agent）。
  - 不破壞既有 CLI 終端輸出風格（向後相容）。

### 3. 驗收標準 (Acceptance Criteria)
* **AC-1 (File & Console Logging)**: 呼叫 `setup_logging()` 後能正確初始化 Logger，寫入 `logs/app.log`，並支援輪轉。
* **AC-2 (API Latency Tracking)**: 所有經由 `retry_call` 的 Gemini API 呼叫均記錄包含 `op_name`、耗時秒數（保留 3 位小數）與嘗試次數之日誌。
* **AC-3 (Redis Latency Tracking)**: Redis 向量寫入與檢索均能記錄操作耗時與筆數。
* **AC-4 (Configuration Decoupling)**: 支援由環境變數或 `AppConfig` 覆寫 `LOG_LEVEL` 與 `LOG_FILE`。
* **AC-5 (Zero PII Leakage)**: 日誌內容中絕不含原始個人身分證或 API Key。
* **AC-6 (AST Code Review)**: `audit_guardrails.py` AST 掃描 100% 通過（零 P0 違規），全套單元測試綠燈。

---

## 二、8 大架構維度前審 (Gate 1 審查)

1. **PII 個資隱私**：日誌僅記錄檔名、候選人 ID、操作名稱與耗時，嚴禁記錄履歷內文明文。
2. **容量與極限**：使用 `RotatingFileHandler` 限制日誌總佔用空間（預設 50MB 內），防磁碟爆滿。
3. **依賴反轉 (DIP)**：日誌設定與時間監測實作於 Infrastructure 層，Domain 層維持純潔無外部相依。
4. **資源生命週期**：檔案 Handler 採用 `delay=True`，杜絕 Windows `[WinError 32]` 檔案控制代碼鎖死。
5. **Token 能效**：計時僅在 Python 原生層執行，0 外部 API / Token 額外開銷。
6. **配置解耦 (12-Factor)**：所有日誌路徑、大小與等級均透過 `AppConfig` 與 `.env` 注入。
7. **向下相容性**：CLI 介面 100% 維持原樣，終端標籤風格不變。
8. **測試覆蓋**：單元測試以 100% 離線 Mock 驗證日誌記錄與計時邏輯。
* **Gate 1 結論**：**PASS (審查通過)**。

---

## 三、DDD 技術規格書 (Tech Spec)

### 1. 模組變更清單
* `src/infrastructure/logging.py` (新增)：提供 `setup_logging` 與 `get_logger`。
* `src/infrastructure/config.py`：新增 `log_level`, `log_file`, `log_max_bytes`, `log_backup_count`。
* `src/infrastructure/transformers/utils.py`：擴充 `retry_call` 加入耗時監測日誌。
* `src/infrastructure/transformers/gemini_transformer.py`：呼叫 `retry_call` 時傳入明確的 `op_name`。
* `src/infrastructure/embeddings/gemini_embedding.py`：呼叫 `retry_call` 時傳入 `gemini_embedding_batch`。
* `src/infrastructure/validators/llm_judge.py`：呼叫 `retry_call` 時傳入 `gemini_judge_eval`。
* `src/infrastructure/stores/redis_vector_store.py`：加入 `upsert_chunks` 與 `search_knn` 的耗時記錄。
* `src/interfaces/cli/runner.py`：在 CLI 啟動時依 `AppConfig` 初始化日誌。
* `.env.example`：新增 `LOG_LEVEL` 與 `LOG_FILE` 範例設定。
* `tests/unit/test_logging_and_latency.py` (新增)：單元測試。

---

## 四、QA 驗收測試案例矩陣 (Test Matrix)

| 測試編號 | 測試名稱 | 測試方式 | 預期結果 |
| :--- | :--- | :--- | :--- |
| **TC-LOG-01** | 日誌模組初始化測試 | 傳入自訂 Config 與暫存日誌檔路徑 | 成功建立記錄器，日誌檔正確寫入指定格式 |
| **TC-LOG-02** | API 耗時日誌記錄測試 | Mock 呼叫 `retry_call` 成功與失敗情境 | 驗證日誌正確輸出包含耗時秒數、操作名稱與重試次數 |
| **TC-LOG-03** | Redis 操作耗時日誌測試 | Mock Redis pipeline 與搜尋 | 驗證日誌輸出寫入與檢索之毫秒級耗時 |
| **TC-LOG-04** | Twelve-Factor 日誌配置測試 | 驗證 `AppConfig.load()` 讀取 `LOG_LEVEL` 與 `LOG_FILE` | 預設為 INFO 與 `logs/app.log`，支援覆寫與異常退回 |
| **TC-LOG-05** | AST 代碼防線掃描 | 執行 `audit_guardrails.py` | 100% 通過，零 P0 違規 |
| **TC-LOG-06** | 全套單元測試回歸驗證 | 執行 `unittest discover` | 100+ 項測試全數綠燈 |
