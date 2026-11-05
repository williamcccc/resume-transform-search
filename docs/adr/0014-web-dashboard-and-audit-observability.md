# ADR-0014: 輕量化轉檔稽核日誌與統計摘要 Web 儀表板架構

## 1. 狀態
已採納 (Accepted)

## 2. 背景與問題陳述 (Context & Problem Statement)
目前系統在轉檔與入庫過程中，品管紀錄（`audit_report.csv`）與系統技術日誌（`app.log`）分散在檔案系統中，使用者需要手動開啟終端或試算表軟體方能檢視轉檔成敗、品管分數與錯誤原因。為了提供更友善的可觀測性與即時排錯能力，需要建立一個 Web 查詢介面。
然而，專案核心約束要求：
- 零多餘肥大第三方相依（目前環境未安裝 FastAPI / Flask / Uvicorn）。
- 嚴格遵守 DDD 與整潔架構，Web 表現層絕不侵入領域層與核心 Use Case。
- 零硬編碼，所有 Web 監聽 Port、Host 與檔案路徑皆可透過 Twelve-Factor 配置注入。

## 3. 評估選項 (Options Evaluated)
* **選項 A：僅採用 Python 內建 `ThreadingHTTPServer`**
  - 優點：零外部相依，開箱即用。
  - 缺點：缺乏業界主流的 Swagger UI (`/docs`) 與 OpenAPI 自動文件。
* **選項 B：僅採用 FastAPI + Uvicorn**
  - 優點：業界標準、Swagger UI 互動文件、Pydantic 自動資料校驗、ASGI 高吞吐量。
  - 缺點：若未安裝套件環境無法執行。
* **選項 C (最終選型)：雙模態自適應架構 (Dual-Engine: FastAPI-First with Builtin Fallback)**
  - 優先載入 **FastAPI + Uvicorn**，提供 Swagger UI 與業界標準 API 開發體驗。
  - 若環境缺少依賴，**自動平滑降級至內建 `ThreadingHTTPServer`**，兼具業界主流先進性與極致強健開箱即用能力。
  - 核心 Use Case（`GetDashboardDataUseCase`）零修改，完美印證 DDD 整潔架構的抽換彈性。

## 4. 架構決策 (Decision Outcome)
**採納選項 C**。
- 在 `src/interfaces/web/fastapi_server.py` 實作 FastAPI ASGI 路由與 OpenAPI 文件支援。
- 在 `src/interfaces/web/server.py` 保留內建 `ThreadingHTTPServer` 作為強健回退。
- `web_dashboard.py` 提供 `--engine [auto|fastapi|builtin]`，預設 `auto`（優先啟動 FastAPI）。

## 5. 8 大架構審查維度評估 (Architecture Review Analysis)
1. **個資隱私 (PII)**：Web 端僅展示檔名與技術警示，絕不印出未脫敏之履歷全文。
2. **容量與極限 (Capacity)**：Log 與 Audit 讀取限制筆數（預設 500~1000 行），防止記憶體暴衝。
3. **非同步與演進 (Async / Evolution)**：Use Case 與 HTTP 伺服器徹底解耦，未來若引入 FastAPI，只需新增路由轉接器，Use Case 零修改。
4. **成本與熔斷 (Cost)**：全本地查詢，0 Token 消耗。
5. **可抽換性 (Portability)**：完全遵循依賴反轉 (DIP)，資料讀取 100% 抽象於 Protocol。
6. **惡意輸入與安全性 (Security)**：防止路徑遍歷，限制靜態檔案只回傳內建 Dashboard；API 參數型別保護。
7. **配置解耦 (Twelve-Factor)**：支援 `WEB_PORT`、`WEB_HOST` 與 `.env` 注入。
8. **可觀測性 (Observability)**：提供視覺化 KPI 卡片、成功率進度條、即時日誌檢索，提升維運能見度。
