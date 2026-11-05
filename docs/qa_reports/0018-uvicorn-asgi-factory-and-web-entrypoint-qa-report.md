# QA 實測驗收報告（QA Report 0018）

> **功能名稱**：支援 Uvicorn 標準 ASGI 啟動、App Factory 與 Web 依賴注入組裝收斂
> **關聯規格書**：[Spec 0018](../specs/0018-uvicorn-asgi-factory-and-web-entrypoint-spec.md)
> **關聯 ADR**：[ADR-0018](../adr/0018-uvicorn-standard-asgi-entrypoint-and-di-bootstrap.md)
> **測試日期**：2026-11-05
> **簽核狀態**：✅ **PASS**

---

## 一、需求追溯矩陣（Requirements Traceability Matrix, RTM）

| 驗收標準 (AC) | 對應測試案例 | 預期結果 | 實測結果 |
| :--- | :--- | :--- | :--- |
| **AC-1（ASGI App Factory 啟動）** | `TC-18-02` (`test_create_default_app_factory_with_custom_config`)、`TC-18-04` (`test_e2e_uvicorn_import_from_string_and_factory`) | `create_default_app()` 能自動載入 `AppConfig` 並建立綁定好路由與 Use Case 的 `FastAPI` 實例，支援 `uvicorn ...:create_default_app --factory` | ✅ **PASS** |
| **AC-2（Uvicorn 頂層 `app` 延遲載入）** | `TC-18-03` (`test_lazy_module_app_attribute_and_invalid_attribute_error`)、`TC-18-04` | 存取 `src.interfaces.web.fastapi_server:app` 與 `web_dashboard:app` 時透過 PEP 562 `__getattr__` 自動回傳 `FastAPI` 實例並回應 200 OK；非法屬性拋出 `AttributeError` | ✅ **PASS** |
| **AC-3（依賴組裝收斂與容錯降級）** | `TC-18-01` (`test_build_web_use_cases_normal_and_fault_degradation`) | `build_web_use_cases(config)` 正常組裝雙 Use Case；當向量庫初始化拋出異常時優雅降級回傳 `search_use_case=None` 且保留錯誤原因 | ✅ **PASS** |
| **AC-4（CLI 100% 向下相容）** | `test_web_dashboard.py` & `test_web_dashboard_e2e.py` 全集 | `web_dashboard.py` 與既有雙引擎（`FastAPI` / `ThreadingHTTPServer`）所有 API 端點 100% 相容無退化 | ✅ **PASS** |

---

## 二、對抗式與邊界情境實測

1. **故障注入與優雅降級（Fault Injection）**：於 `TC-18-01` 模擬 `RedisVectorStore` 初始化拋出 `RuntimeError`，驗證 `build_web_use_cases` 捕獲例外並降級為僅提供轉檔儀表板（`search_use_case=None`），不導致 Web 伺服器崩潰。
2. **模組匯入零副作用與非法屬性攔截（PEP 562 Boundary）**：於 `TC-18-03` 驗證未存取 `.app` 前不觸發預設實例化；當存取不存在的屬性時正確拋出標準 `AttributeError`。
3. **真實 Uvicorn Importer 端到端加載**：於 `TC-18-04` 使用 `uvicorn.importer.import_from_string` 實測 `"src.interfaces.web.fastapi_server:create_default_app"`、`"src.interfaces.web.fastapi_server:app"` 與 `"web_dashboard:app"` 三種啟動字串，對 `/`, `/docs`, `/api/stats`, `/api/audit`, `/api/logs` 發送 HTTP 請求皆為 `200 OK`。

---

## 三、測試執行統計摘要

* **白箱單元測試**：`python -m unittest discover -s tests/unit -p "test_*.py"` ➔ **Ran 135 tests in 7.526s — OK**
* **黑箱/灰箱 E2E 實測**：`python -m unittest discover -s tests/e2e -p "test_*.py"` ➔ **Ran 20 tests in 35.528s — OK**
* **架構防線靜態掃描**：`python .agents/skills/code-review/scripts/audit_guardrails.py` ➔ **100% PASSED（零 P0 違規）**
