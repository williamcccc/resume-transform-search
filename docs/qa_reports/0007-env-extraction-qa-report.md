# QA 實測驗收報告：全盤硬編碼參數提取至 .env 與 Twelve-Factor App 治理

## 1. 測試執行總結 (Executive Summary)

- **測試日期**：2026-11-04
- **測試目標**：驗證系統 17 項配置參數全數提取至 `.env` 與 `AppConfig`，各組件支援依賴注入，且在缺失或非法環境變數下平穩退回預設值。
- **測試範圍**：
  1. 白箱單元測試 (`tests/unit/`)
  2. 黑箱/灰箱 E2E 端到端測試 (`tests/e2e/`)（使用獨立 `REDIS_TEST_URL` DB 15）
  3. CLI 工具互動與引數覆寫驗證 (`convert_to_md.py`, `search_resumes.py`, `index_to_redis.py`)
- **測試結果**：**100% 通過 (PASS)**，零功能回歸，零未預期例外。

---

## 2. 測試矩陣與覆蓋結果 (Test Matrix & Results)

| 測試編號 | 測試模組 / 項目 | 驗證情境 | 測試結果 | 備註 |
| :--- | :--- | :--- | :--- | :--- |
| **TC-ENV-01** | `test_app_config.py` | 預設值加載驗證 (17 項參數) | **PASS** | 離線 mock 驗證 100% 預設相容 |
| **TC-ENV-02** | `test_app_config.py` | 自訂環境變數載入與型別解析 | **PASS** | `_safe_int`, `_safe_float` 正常運作 |
| **TC-ENV-03** | `test_app_config.py` | 非法字串容錯降級回退 | **PASS** | 遭遇非數字字串時平穩退回預設值 |
| **TC-ENV-04** | `test_security_quotas.py` | 自訂 `max_file_size_mb` 注入防禦 | **PASS** | 精準觸發 `FileQuotaExceededError` |
| **TC-ENV-05** | `test_security_quotas.py` | 自訂 `max_pages` PDF 頁數防禦 | **PASS** | 精準觸發 `FileQuotaExceededError` |
| **TC-ENV-06** | `test_security_quotas.py` | 自訂 `max_expansion_ratio` 膨脹比防禦 | **PASS** | 成功阻擋模擬 Zip Bomb |
| **TC-ENV-07** | `test_token_optimization_e2e.py` | Redis DB 15 隔離庫入庫與增量比對 | **PASS** | 零 Token 增量命中，完全隔離 DB 0 |
| **TC-ENV-08** | `search_resumes.py` | 連動 `SEARCH_DEFAULT_TOP_K` 與 `EMBEDDING_DIM` | **PASS** | CLI 自然語言檢索回傳吻合 |

---

## 3. 測試執行數據摘要

```text
======================================================================
1. 單元測試 (Unit Tests):
   Ran 85 tests in 2.814s (OK)
   - 85/85 綠燈，外部相依 100% 隔離

2. E2E 端到端測試 (Integration & E2E):
   Ran 6 tests in 26.305s (OK)
   - 6/6 綠燈，Redis DB 15 自動建立與銷毀

3. CLI 實測 (Live Search):
   python search_resumes.py "Golang 微服務" --top 2
   - 成功檢索 2 筆高相關切片，最高相似度 65.4%
======================================================================
```
