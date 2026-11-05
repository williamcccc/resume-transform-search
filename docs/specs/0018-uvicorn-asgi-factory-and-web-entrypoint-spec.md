# PRD 與 DDD 技術實作規格書（Spec 0018）

> **關聯 ADR**：[ADR-0018](../adr/0018-uvicorn-standard-asgi-entrypoint-and-di-bootstrap.md)
> **QA 報告**：[QA Report 0018](../qa_reports/0018-uvicorn-asgi-factory-and-web-entrypoint-qa-report.md)

## 一、產品需求文件（PRD）

### 1. 背景與目標
目前專案透過根目錄 `web_dashboard.py` 啟動 Web 儀表板與智能履歷搜尋服務，其依賴組裝（`GetDashboardDataUseCase`、`SearchResumesUseCase` 等）直接寫在 `web_dashboard.py:main()` 中，而 `src/interfaces/web/fastapi_server.py` 僅提供需要外部傳入 Use Case 的 `create_app(use_case, search_use_case)`。

這導致熟悉 FastAPI / Docker / ASGI 部署的開發者無法直接使用標準 `uvicorn` 指令（例如 `uvicorn src.interfaces.web.fastapi_server:app --reload`、`uvicorn src.interfaces.web.fastapi_server:create_default_app --factory --reload` 或 `uvicorn web_dashboard:app --reload`）啟動服務。

本需求目標是在**不破壞既有 `python web_dashboard.py` CLI 向下相容性與雙引擎自動降級機制**的前提下，將 Web 服務依賴注入組裝邏輯（Dependency Injection Bootstrap）收斂至表現層，並在 `fastapi_server.py` 與 `web_dashboard.py` 提供預設 ASGI Factory（`create_default_app`）與延遲載入頂層 `app` 實例，全面支援標準 `uvicorn` 直接啟動。

### 2. 範疇界定（Scope）

* **In-Scope**：
  1. **Web 依賴注入組裝器收斂（`build_web_use_cases`）**：
     - 將原本散落於 `web_dashboard.py` 的 `GetDashboardDataUseCase` 與 `SearchResumesUseCase` 依賴注入組裝邏輯收斂為可重用之工廠函式 `build_web_use_cases(config: Optional[AppConfig] = None)`（放置於 `src/interfaces/web/server.py` 並由 `fastapi_server.py` 匯出），同時保留無 FastAPI 環境時的零外部相依相容性。
  2. **支援標準 ASGI Factory 模式（`create_default_app`）**：
     - 在 `src/interfaces/web/fastapi_server.py` 新增 `create_default_app(config: Optional[AppConfig] = None) -> FastAPI`，自動載入 `AppConfig.load()`（若未傳入 `config`）並組裝 Use Cases，支援 `uvicorn src.interfaces.web.fastapi_server:create_default_app --factory --reload`。
  3. **支援標準 Uvicorn 頂層 `app` 屬性（PEP 562 延遲載入）**：
     - 在 `src/interfaces/web/fastapi_server.py` 與 `web_dashboard.py` 實作模組層級 `__getattr__("app")`（PEP 562），當執行 `uvicorn src.interfaces.web.fastapi_server:app --reload` 或 `uvicorn web_dashboard:app --reload` 時，自動延遲初始化並回傳完整組裝之 `FastAPI` 實例；同時確保單元測試僅 `import` 模組時不觸發多餘初始化。
  4. **100% 向下相容 `python web_dashboard.py`**：
     - 保留 `web_dashboard.py` 所有 CLI 參數（`--host`, `--port`, `--audit-file`, `--log-file`, `--engine`, `--open`）與雙引擎（`auto` / `fastapi` / `builtin`）啟動行為。

* **Out-of-Scope**：
  - 不變更既有 REST API 路徑、參數格式或前端 HTML/JS 畫面。
  - 不變更 Domain 層或 Application 層業務邏輯。

### 3. 驗收標準（Acceptance Criteria, AC）
* **AC-1（ASGI App Factory 啟動）**：呼叫 `create_default_app()`（含預設載入 `AppConfig` 或傳入自訂 `AppConfig`）能成功建立並回傳綁定好路由與 Use Case 的 `FastAPI` 實例，支援 `uvicorn src.interfaces.web.fastapi_server:create_default_app --factory`。
* **AC-2（Uvicorn 頂層 `app` 直接啟動與延遲載入）**：透過 `src.interfaces.web.fastapi_server:app` 或 `web_dashboard:app` 存取頂層 `app` 屬性時，能透過 PEP 562 `__getattr__` 自動回傳有效的 `FastAPI` 實例，並正常回應 `/api/stats`、`/api/audit`、`/api/logs`、`/docs` 等端點。
* **AC-3（依賴組裝收斂與容錯降級）**：`build_web_use_cases(config)` 能正確組裝 `GetDashboardDataUseCase` 與 `SearchResumesUseCase`；當向量檢索服務初始化拋出例外時，能優雅降級（`search_use_case=None`）並記錄警告，不阻斷儀表板啟動。
* **AC-4（CLI 100% 向下相容）**：`python web_dashboard.py` 支援原有全部旗標，並改為調用共用的 `build_web_use_cases(config)`，消除重複組裝代碼。

---

## 二、8 大架構維度前審（Gate 1 審查）

| 審查維度 | 評估結論 |
| :--- | :--- |
| **1. 個資隱私 (PII)** | 零新增個資處理；僅重構表現層與組合根的 DI 組裝入口。 |
| **2. 容量與極限 (Capacity)** | 採用 PEP 562 `__getattr__` 延遲初始化 `app`，避免模組匯入時產生不必要之物件配置。 |
| **3. 非同步與演進 (Async / Evolution)** | 原生對齊 ASGI 標準（`uvicorn ...:app` 與 `--factory`），有利於容器化與多 Worker 部署。 |
| **4. 成本與熔斷 (Cost)** | 初始化階段 `GeminiEmbeddingService` 與 `RedisVectorStore` 皆為 Lazy Client，0 Token 消耗。 |
| **5. 可抽換性 (Portability)** | `GetDashboardDataUseCase` 與 `SearchResumesUseCase` 完全不變，遵循 DIP 依賴反轉。 |
| **6. 惡意輸入與配額 (Security)** | 沿用既有路由參數校驗與路徑遍歷防禦，無安全退化。 |
| **7. 索引演進 (Index Evolution)** | 不影響 Redis 索引結構。 |
| **8. 併發與可觀測性 (Observability)** | 支援 Uvicorn 標準啟動與 Reload 開發模式，保留完整日誌與錯誤追蹤。 |

**Gate 1 審查結論：PASS**（無架構債，符合 DDD 表現層與組合根設計規範）。

---

## 三、DDD 技術實作規格與 QA 測試案例矩陣

### 1. 變更模組清單
| 層級 / 檔案 | 變更內容 |
| :--- | :--- |
| [server.py](../../src/interfaces/web/server.py) | 新增 `build_web_use_cases(config: Optional[AppConfig] = None)` 共用依賴注入組裝工廠，回傳 `(use_case, search_use_case, search_init_err)`，確保無 FastAPI 時亦可獨立運作。 |
| [fastapi_server.py](../../src/interfaces/web/fastapi_server.py) | 新增 `create_default_app(config: Optional[AppConfig] = None) -> FastAPI` 及 PEP 562 `__getattr__(name: str)` 延遲載入頂層 `app` 實例。 |
| [web_dashboard.py](../../web_dashboard.py) | 改為調用 `build_web_use_cases(config)` 消除重複組裝邏輯，並支援 PEP 562 `__getattr__("app")` 轉發至 `fastapi_server.create_default_app()`。 |
| [test_web_dashboard.py](../../tests/unit/test_web_dashboard.py) | 新增單元測試驗證 `build_web_use_cases`、`create_default_app`、延遲載入 `app` 及檢索服務初始化異常時的優雅降級。 |
| [test_web_dashboard_e2e.py](../../tests/e2e/test_web_dashboard_e2e.py) | 新增 E2E 測試驗證 `uvicorn` 目標字串（`src.interfaces.web.fastapi_server:app`、`create_default_app` Factory 與 `web_dashboard:app`）端到端請求回應。 |

### 2. QA 驗收測試案例矩陣
| 測試案例 ID | 對應 AC | 測試類型 | 驗證內容 |
| :--- | :---: | :---: | :--- |
| **TC-18-01** | AC-1, AC-3 | Unit | 驗證 `build_web_use_cases(config)` 正確建立 `GetDashboardDataUseCase` 與 `SearchResumesUseCase`，且當檢索依賴拋出例外時優雅降級回傳 `search_use_case=None`。 |
| **TC-18-02** | AC-1 | Unit | 驗證 `create_default_app(config)` 能以自訂暫存 CSV/Log 路徑之 `AppConfig` 建立 `FastAPI` 實例並正確回應 `/api/stats`。 |
| **TC-18-03** | AC-2 | Unit | 驗證 `fastapi_server.app` 與 `web_dashboard.app` 透過 PEP 562 `__getattr__` 延遲載入 `FastAPI` 實例，且屬性名稱不存在時正常拋出 `AttributeError`。 |
| **TC-18-04** | AC-2, AC-4 | E2E | 驗證透過 `uvicorn` 模組匯入方式載入 `src.interfaces.web.fastapi_server:app` 與 `create_default_app` 工廠，對 `/`, `/docs`, `/api/stats`, `/api/audit`, `/api/logs` 發送端到端請求皆回傳 200 OK。 |
