# QA 實測驗收報告：轉檔日誌與統計摘要 Web 查詢儀表板 (ADR-0014 / 規格 0014)

## 一、驗收摘要 (Executive Summary)
* **關聯需求與規格**：[`docs/specs/0014-conversion-web-dashboard-spec.md`](../specs/0014-conversion-web-dashboard-spec.md)
* **關聯架構決策**：[`docs/adr/0014-web-dashboard-and-audit-observability.md`](../adr/0014-web-dashboard-and-audit-observability.md)
* **實體入口點**：[`web_dashboard.py`](../../web_dashboard.py)
* **驗收結果**：**100% 通過 (PASS)**
* **缺陷統計**：P0: 0 | P1: 0 | P2: 0

---

## 二、需求追溯與驗收測試矩陣 (RTM)

| 測試案例編號 | 驗收條件 (AC) | 測試情境與斷言說明 | 實測結果 | 備註 |
| :--- | :--- | :--- | :---: | :--- |
| **TC-WD-01** | AC-1 零資料防禦 | CSV/Log 檔案不存在或空檔時，統計指標優雅回傳 0 值與空陣列，零崩潰 | **PASS** | `test_empty_audit_and_logs` |
| **TC-WD-02** | AC-1 統計指標聚合 | 正確聚合總檔數、成功數、隔離數、錯誤數、成功率%、平均分與模型分佈 | **PASS** | `test_metrics_calculation_and_aggregation` |
| **TC-WD-03** | AC-2 狀態與關鍵字過濾 | 依 `QUARANTINE` 狀態精確過濾，關鍵字搜尋比對檔名、警示與模型 | **PASS** | `test_status_and_keyword_filtering` |
| **TC-WD-04** | AC-2 分頁支援 | 驗證 `offset` 與 `limit` 切片正確，總筆數統計完整 | **PASS** | `test_pagination` |
| **TC-WD-05** | AC-3 系統日誌過濾 | 依日誌等級（ERROR / WARNING / INFO）與關鍵字正確過濾 | **PASS** | `test_system_log_filtering` |
| **TC-WD-06** | AC-1 CSV 讀取器實體 | `CsvAuditLogReader` 解析實體 CSV 檔案，支援 UTF-8-sig 與反向排序 | **PASS** | `test_csv_audit_reader_real_file` |
| **TC-WD-07** | AC-3 日誌讀取器實體 | `FileAppLogReader` 正則解析標準格式日誌，支援多行堆疊回退容錯 | **PASS** | `test_file_log_reader_real_file` |
| **TC-WD-08** | AC-5 Twelve-Factor 配置 | `AppConfig.load` 支援 `WEB_HOST` 與 `WEB_PORT` 覆寫 | **PASS** | `test_app_config_web_settings` |
| **TC-WD-09** | AC-4 FastAPI 引擎與端點 | 驗證 FastAPI 應用實例路由、OpenAPI 文件與端點回應 | **PASS** | `test_fastapi_app_endpoints` |
| **E2E-01** | AC-4 靜態儀表板渲染 | 透過 HTTP GET `/` 取得 200 OK，包含完整現代化 UI 與 Glassmorphism 樣式 | **PASS** | `test_e2e_serve_dashboard_html` |
| **E2E-02** | AC-1 API 統計端點實測 | 透過 HTTP GET `/api/stats` 取得即時 JSON 指標資料 | **PASS** | `test_e2e_api_stats` |
| **E2E-03** | AC-2 API 稽核查詢實測 | 透過 HTTP GET `/api/audit?status=QUARANTINE` 實測狀態篩選 | **PASS** | `test_e2e_api_audit_with_filters` |
| **E2E-04** | AC-3 API 日誌查詢實測 | 透過 HTTP GET `/api/logs?level=ERROR` 實測日誌端點 | **PASS** | `test_e2e_api_logs` |
| **E2E-05** | AC-4 404 例外防禦 | 未知路徑優雅回傳 404 JSON 格式錯誤訊息 | **PASS** | `test_e2e_404_not_found` |
| **E2E-06** | AC-4 Swagger UI 整合 | 透過 TestClient 驗證 `/docs` (Swagger) 與 `/redoc` 頁面正常渲染 | **PASS** | `test_e2e_fastapi_swagger_and_app` |

---

## 三、執行成果
* **白箱單元測試**：`tests/unit/test_web_dashboard.py` 9/9 全數綠燈 (1.334s)。
* **端到端實測**：`tests/e2e/test_web_dashboard_e2e.py` 6/6 全數綠燈 (3.683s)。
* **CLI 實測**：`tests/e2e/test_cli_workflow.py` 5/5 全數綠燈 (16.516s)。
* **Gate 2 代碼審查**：`audit_guardrails.py` AST 靜態稽核 100% 通過（零 P0/P1 違規）。
* **驗收簽核**：雙引擎自適應架構與 Swagger UI 成功落地，簽核放行。
