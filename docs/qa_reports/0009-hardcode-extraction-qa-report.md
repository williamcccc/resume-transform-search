# QA 實測驗收報告 (QA Acceptance Report)

## 1. 測試環境與設定
* **作業系統**：Windows 11 (Python 3.13)
* **測試套件**：`unittest`
* **測試範疇**：
  * 白箱單元測試：`tests/unit/test_app_config.py`, `tests/unit/test_hardcode_extractions.py` 等共 92 個測試。
  * 黑箱/端到端整合測試：`tests/e2e/test_cli_workflow.py`, `tests/e2e/test_token_optimization_e2e.py` 共 6 個測試。
* **Redis 測試隔離**：使用 `REDIS_TEST_URL=redis://localhost:6379/15`。

---

## 2. 測試矩陣與驗收結果 (RTM)

| 案例編號 | 測試項目 | 驗收情境 | 實測結果 | 狀態 |
| :--- | :--- | :--- | :--- | :--- |
| **TC-01** | `AppConfig` 預設值驗證 | 離線未配置任何環境變數時，正確退回安全預設值 (溫度 0.2, Token 8192, INITIAL_CAP 1000 等) | 預設值全部符合規格 | **PASS** |
| **TC-02** | `AppConfig` 自訂值載入 | 模擬傳入全部自訂環境變數，包含 list、float、int 型別 | 100% 正確解析並賦值 | **PASS** |
| **TC-03** | `AppConfig` 非法型別容錯 | 傳入非數字字串 (如 `"bad_temp"`, `"not_int"`) | 安全回退預設值，零例外崩潰 | **PASS** |
| **TC-04** | `PdfHealthProbe` 自訂門檻 | 動態調整 `scanned_min_chars`、`ufffd_threshold` | 建構子與探測邏輯正確套用自訂閥值 | **PASS** |
| **TC-05** | `MarkdownChunker` 技能擴充 | 傳入 `extra_skill_patterns=["flutter", "solidity", "rust"]` | 成功由 Markdown 正則比對提取自訂技術標籤 | **PASS** |
| **TC-06** | `RedisVectorStore` 容量與過濾 | 設定 `hnsw_initial_cap=5000` 與 `query.min_score=0.5` | 成功過濾低相似度切片，僅保留高分結果 | **PASS** |
| **TC-07** | `GeminiTransformer` 參數與提示詞 | 載入 `prompts/text_convert.md` 與自訂溫度 0.0 | 提示詞成功載入且無任何代碼寫死字串 | **PASS** |
| **TC-08** | E2E CLI 轉檔與入庫整合 | 實測真實 CLI 轉檔流程與 Redis 隔離庫寫入 | 6/6 端到端情境全部通過 | **PASS** |

---

## 3. 測試執行統計彙總
* **單元測試 (Unit Tests)**：`Ran 92 tests in 2.728s ... OK`
* **端到端測試 (E2E Tests)**：`Ran 6 tests in 25.354s ... OK`
* **瑕疵數量**：0 P0 / 0 P1 / 0 P2
* **驗收結論**：全數達標，放行進入 Gate 2 對抗式代碼審查。
