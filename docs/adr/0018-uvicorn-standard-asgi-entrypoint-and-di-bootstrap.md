# ADR-0018: 支援 Uvicorn 標準 ASGI 啟動、App Factory 與 Web 依賴注入組裝收斂

## 1. 決策狀態

* **狀態**：已採納 (Accepted)
* **日期**：2026-11-05
* **決策負責人**：Development Team
* **標籤**：`FastAPI`, `Uvicorn`, `ASGI`, `Dependency Injection`, `Clean Architecture`
* **規格與驗收**：[Spec 0018](../specs/0018-uvicorn-asgi-factory-and-web-entrypoint-spec.md)、[QA Report 0018](../qa_reports/0018-uvicorn-asgi-factory-and-web-entrypoint-qa-report.md)

## 2. 背景與問題陳述

在 ADR-0014 與 ADR-0015 中，本專案建立了支援 `FastAPI` 與內建 `ThreadingHTTPServer` 的雙引擎 Web 儀表板及智能履歷搜尋服務，並以根目錄 `web_dashboard.py` 作為 CLI 啟動入口。

然而，原先的依賴注入組裝邏輯（實例化 `CsvAuditLogReader`、`FileAppLogReader`、`GetDashboardDataUseCase`、`GeminiEmbeddingService`、`RedisVectorStore` 與 `SearchResumesUseCase`）直接寫在 `web_dashboard.py:main()` 中；而 `src/interfaces/web/fastapi_server.py` 僅暴露了需要傳入參數的 `create_app(use_case, search_use_case)`。

這導致在容器化（Docker）、正式環境部署或開發熱重載（Hot Reload）情境下，開發者無法使用業界標準的 `uvicorn src.interfaces.web.fastapi_server:app --reload` 或 `--factory` 指令直接啟動 ASGI 伺服器。

## 3. 評估之架構選項

### 選項 A：在 `fastapi_server.py` 模組匯入時直接實例化全域 `app = create_default_app()`

* **優點**：實作最簡單，支援 `uvicorn src.interfaces.web.fastapi_server:app`。
* **缺點**：任何單元測試只要執行 `from src.interfaces.web.fastapi_server import create_app`，就會在模組匯入階段強制觸發 `AppConfig.load()` 與預設依賴建構，污染單元測試隔離性並增加匯入開銷。

### 選項 B：僅提供 `create_default_app()`，強制使用者加上 `--factory` 參數

* **優點**：不會在匯入時產生副作用。
* **缺點**：若開發者習慣直覺輸入 `uvicorn src.interfaces.web.fastapi_server:app --reload`（未加 `--factory`），會因找不到 `app` 屬性而報錯。

### 選項 C：共用依賴組裝器 `build_web_use_cases` + `create_default_app` 工廠 + PEP 562 模組延遲 `__getattr__("app")`（選定）

* **優點**：
  1. 同時支援 `uvicorn src.interfaces.web.fastapi_server:app --reload`、`uvicorn src.interfaces.web.fastapi_server:create_default_app --factory --reload`、`uvicorn web_dashboard:app --reload` 與 `python web_dashboard.py` 四種啟動方式。
  2. 利用 Python PEP 562 模組級 `__getattr__`，在一般 `from src.interfaces.web.fastapi_server import create_app` 時完全不觸發預設實例化，100% 保持單元測試純淨與零額外開銷。
  3. 將組裝邏輯統一收斂於 `build_web_use_cases(config)`，消除 `web_dashboard.py` 與 `fastapi_server.py` 的重複程式碼。
* **缺點**：需理解 PEP 562 模組屬性延遲載入機制。

## 4. 最終決策結果

採納 **選項 C**：
1. 在 `src/interfaces/web/server.py` 建立零外部框架相依的 `build_web_use_cases(config: Optional[AppConfig] = None)`，統一負責組裝 `GetDashboardDataUseCase` 與 `SearchResumesUseCase`。
2. 在 `src/interfaces/web/fastapi_server.py` 新增 `create_default_app(config: Optional[AppConfig] = None) -> FastAPI`，並透過 `__getattr__("app")` 提供延遲初始化之頂層 `app` 實例。
3. 重構 `web_dashboard.py` 呼叫 `build_web_use_cases(config)`，並同樣提供 `__getattr__("app")` 轉發，兼顧 CLI 易用性與標準 ASGI 部署體驗。

## 5. 8 大架構審查維度評估

1. **個資隱私 (PII)**：不涉及個資邏輯變更。
2. **容量與極限 (Capacity)**：PEP 562 延遲載入確保非 ASGI 頂層存取時零記憶體額外負擔。
3. **非同步與演進 (Async / Evolution)**：完全符合 ASGI 規範，可無縫對接 Gunicorn (`UvicornWorker`) 或 Uvicorn 多進程與 `--reload` 模式。
4. **成本與熔斷 (Cost & Circuit Breaker)**：依賴初始化採 Lazy Connection，啟動時 0 Token 消耗。
5. **可抽換性 (Portability & Decoupling)**：核心 Use Case 與 Domain 契約零修改，展現 Clean Architecture 表現層的高可塑性。
6. **惡意輸入與配額硬上限 (Input Security)**：所有 API 端點驗證與防護維持不變。
7. **向量索引演進 (Index Evolution)**：無影響。
8. **分散式併發與全鏈路可觀測性 (Concurrency & Observability)**：保留完整日誌與錯誤降級告警。
