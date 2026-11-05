# ADR-0001: 採用 Clean Architecture 與 DDD 四層依賴反轉架構

## 1. 狀態
已採納 (Accepted)

## 2. 背景與問題陳述 (Context & Problem Statement)
本專案為企業級履歷解析與檢索系統，需要整合諸多異質技術：
* 外部 AI 雲端模型（Google Gemini API）。
* 底層底層檔案解析器（PyMuPDF, python-docx, Windows win32com）。
* 資料儲存與檢索引擎（Redis HNSW 向量庫）。
* 多元輸入進入點（CLI、未來的 Web API / 任務隊列）。

若採用傳統腳本式或 MVC 框架，外部 SDK 容易與業務邏輯高度耦合，導致未來替換模型、更換向量庫或撰寫單元測試極為困難（例如無法離線跑測試，或者測試需啟動真實 Redis）。

## 3. 評估選項 (Options Evaluated)
* **選項 A：單一平鋪腳本 (Flat Script)**：開發極速，但代碼膨脹後無法維護，完全無法 Mock 測試。
* **選項 B：經典 MVC 架構**：分層模糊，業務邏輯容易流入 Controller 或 Model，難以切換底層 AI SDK。
* **選項 C：Clean Architecture + DDD 四層架構（推薦）**：
  * `domain/`：純領域模型與介面契約，零外部依賴。
  * `application/`：Use Cases 流程編排，依賴抽象介面（DIP）。
  * `infrastructure/`：外部套件與資料庫實作。
  * `interfaces/`：表現層對外輸入。

## 4. 架構決策 (Decision Outcome)
**採納選項 C**。
* 核心業務規則必須置於 `src/domain/`，並透過 Protocol 定義契約介面。
* 所有實體基礎設施類別（如 GeminiTransformer, RedisVectorStore）必須透過依賴注入（Dependency Injection）組裝傳入 Use Case。
* 單元測試 100% 透過 Mock 介面達成毫秒級離線運行。

## 5. 5 大架構審查維度評估 (Architecture Review Analysis)
1. **個資隱私 (PII)**：Domain 模型統一管理履歷實體，有助於在邊界統一進行個資脫敏過濾。
2. **容量與極限 (Capacity)**：分層架構確保資料處理流（Stream）與記憶體釋放邏輯能集中於 Infrastructure，不污染核心。
3. **非同步與演進 (Async / Evolution)**：Use Case 不綁死 CLI 呼叫，隨時可被 FastAPI、Celery 或雲端 Lambda 無縫調用。
4. **成本與熔斷 (Cost & Circuit Breaker)**：外部 API 呼叫點集中於 Infrastructure 轉接器，便於集中配置配額限制與重試策略。
5. **可抽換性 (Portability & Decoupling)**：外部第三方套件（如 Redis, Gemini, PyMuPDF）與核心邏輯完全解耦，切換代價最低。
