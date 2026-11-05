# QA 實測驗收報告：集中式系統技術日誌與 API 請求耗時監控 (ADR-0012)

## 一、驗收摘要 (Executive Summary)
* **關聯需求與規格**：[`docs/specs/0012-centralized-logging-and-api-latency-spec.md`](../specs/0012-centralized-logging-and-api-latency-spec.md)
* **關聯架構決策**：[`docs/adr/0012-centralized-system-logging-and-api-latency-tracking.md`](../adr/0012-centralized-system-logging-and-api-latency-tracking.md)
* **驗收結果**：**100% 通過 (PASS)**
* **缺陷統計**：P0: 0 | P1: 0 | P2: 0

---

## 二、需求追溯與驗收測試矩陣 (RTM)

| 測試案例編號 | 驗收條件 (AC) | 測試情境說明 | 實測結果 | 備註 |
| :--- | :--- | :--- | :---: | :--- |
| **TC-LOG-01** | AC-1 日誌初始化與輪轉 | 成功建立滾動日誌檔案 `logs/app.log`，支援輪轉與延遲釋放 | **PASS** | `test_setup_logging_file_creation_and_formatting` |
| **TC-LOG-02A** | AC-2 API 耗時記錄 (成功) | API 成功呼叫時精準記錄毫秒耗時與 `op_name` 標籤 | **PASS** | `test_retry_call_latency_logging_on_success` |
| **TC-LOG-02B** | AC-2 重試退避耗時記錄 | API 遇到暫態失敗重試時記錄嘗試次數與各輪耗時 | **PASS** | `test_retry_call_latency_logging_on_retry_and_failure` |
| **TC-LOG-03** | AC-3 Redis 延遲監控 | Redis 寫入（Upsert）與 KNN 檢索之耗時記錄 | **PASS** | `test_redis_vector_store_latency_logging` |
| **TC-LOG-04** | AC-4 零洩漏脫敏驗證 | 驗證日誌中絕無明文金鑰、手機、身分證等敏感個資洩漏 | **PASS** | `test_zero_leak_logging_no_raw_pii_or_api_keys` |

---

## 三、執行成果
* 白箱單元測試：`tests/unit/test_logging_and_latency.py` 5/5 綠燈。
* 靜態代碼審查：`audit_guardrails.py` 零違規。
* 驗收簽核：放行正式合併。
