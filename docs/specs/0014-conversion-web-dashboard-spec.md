# PRD 與 DDD 技術實作規格書 (ADR-0014 / 規格 0014)

## 一、產品需求文件 (PRD)

### 1. 商業背景與使用者目標 (Problem Statement & Goals)
目前文件轉檔（`convert_to_md.py`）與向量入庫（`index_to_redis.py`）在批次處理或生產環境運行時，產生的轉檔品管紀錄（`logs/audit_report.csv`）與系統技術日誌（`logs/app.log`）僅能透過終端文字或手動開啟 CSV 檢視。維運人員與一般使用者缺乏直觀的介面進行**轉檔成功率統計、品質分數分佈、評判卡結果檢視、極速即時日誌搜尋與錯誤排查**。
本功能旨在提供一個**零外部重型依賴、開箱即用、自帶輕量 Web 伺服器**的視覺化儀表板（Web Dashboard），供使用者在瀏覽器中即時查詢轉檔統計與詳細日誌。

### 2. 範疇界定 (Scope)
* **In-Scope**:
  1. **【統計摘要 KPI 儀表板】**：
     - 總處理檔數、轉換成功數、品質不合格/隔離數、系統錯誤數。
     - 平均品質分數（Rule Score）與評判員平均分（Judge Score）。
     - 成功率百分比與模型使用分佈（如 `gemini-3.8-flash`、`fast_text` 等）。
  2. **【轉檔品管稽核紀錄 (Audit Logs) 查詢】**：
     - 表格呈現：時間戳、檔名、狀態（SUCCESS / QUARANTINE / ERROR）、品管分數、評判分數、模型、是否 Review、警示/例外訊息。
     - 支援前端即時過濾：依狀態（All, SUCCESS, QUARANTINE, ERROR）、關鍵字（檔名或訊息）篩選與分頁。
  3. **【系統技術日誌 (System Logs) 串流查詢】**：
     - 提供近端 `app.log` 檢索介面，支援等級（INFO / WARN / ERROR）過濾與文字搜尋。
  4. **【輕量內建 HTTP 服務與 FastAPI 雙模態引擎 (Dual-Engine Web Server)】**：
     - **優先業界標準引擎 (FastAPI + Uvicorn)**：
       - 自動提供 OpenAPI 規範與 Swagger 互動式線上文檔（`GET /docs` 與 `GET /redoc`）。
       - 支援高效非同步 ASGI 處理。
     - **零依賴回退防線 (Builtin ThreadingHTTPServer)**：
       - 若環境未安裝第三方框架時，自動平滑降級至 Python 3.13 內建標準庫 `http.server.ThreadingHTTPServer`，環境相容性 100%。
     - 提供 REST API 端點：
       - `GET /api/stats`：回傳統計摘要 JSON。
       - `GET /api/audit`：回傳品管紀錄清單 JSON（支援 query 參數）。
       - `GET /api/logs`：回傳系統日誌行 JSON。
       - `GET /`：回傳單頁 (SPA) 響應式 Web 儀表板 HTML/CSS/JS。
       - `GET /docs`：(FastAPI 模式) Swagger UI 互動式測試端點。
  5. **【入口點與 Twelve-Factor 配置】**：
     - 根目錄提供 CLI 入口 `web_dashboard.py`（支援 `--port`, `--host`, `--audit-file`, `--log-file`, `--engine`）。
     - 連動 `AppConfig`，支援從 `.env`（`WEB_PORT`, `WEB_HOST`, `WEB_ENGINE`）注入配置。
* **Out-of-Scope**:
  - 不引入肥大的 Node.js 構建流程或肥大前端框架，採用現代原生 Vanilla JS + CSS Grid + Glassmorphism 設計，單檔直接載入。
  - 本階段不提供帳號密碼登入或多租戶權限控制（設定於本機或內部網路存取）。

### 3. 輸入與輸出合約 (Input & Output Contract)
* **API: `GET /api/stats`**
  ```json
  {
    "total_files": 120,
    "success_count": 110,
    "quarantined_count": 8,
    "error_count": 2,
    "success_rate": 91.67,
    "avg_score": 88.5,
    "avg_judge_score": 82.0,
    "model_distribution": {"gemini-3.8-flash": 100, "fast_text": 20}
  }
  ```
* **API: `GET /api/audit?status=QUARANTINE&search=candidate&limit=50`**
  ```json
  {
    "total": 8,
    "items": [
      {
        "timestamp": "2026-11-05 14:33:16",
        "filename": "candidate.pdf",
        "status": "QUARANTINE",
        "score": 40,
        "judge_score": "N/A",
        "model": "gemini-3.8-flash",
        "reviewed": true,
        "warnings": "缺少 H1; 字數嚴重不足"
      }
    ]
  }
  ```
* **API: `GET /api/logs?level=ERROR&limit=100`**
  ```json
  {
    "total": 2,
    "logs": [
      {
        "timestamp": "2026-11-05 14:07:08",
        "level": "ERROR",
        "logger": "cli.runner:352",
        "message": "檔案處理異常 [huge.pdf] - 耗時: 0.000 秒, 狀態: ERROR: 檔案大小 (26.0MB) 超過系統硬上限 (25MB)"
      }
    ]
  }
  ```

### 4. 驗收標準 (Acceptance Criteria, AC)
* **AC-1 (Summary Aggregation)**: 能正確解析 CSV 報告並計算總數、成功/隔離/失敗筆數、成功率與平均評分；若 CSV 檔案不存在時能優雅處理回傳預設 0 筆空統計，無例外崩潰。
* **AC-2 (Audit Log Query & Filter)**: 支援前端/API 依 status、keyword 進行精準過濾。
* **AC-3 (System Log Parsing)**: 能解析標準格式之 `app.log` 行，支援日誌等級過濾。
* **AC-4 (Zero External Web Dependencies)**: 使用 Python 3.13 內建標準庫 `http.server` 實作，不依賴額外 `pip install`，並具備並行請求處理能力（`ThreadingHTTPServer`）。
* **AC-5 (CLI & Configuration)**: 根目錄 `web_dashboard.py` 能接受 `--host`、`--port`、`--audit-file`、`--log-file`，並與 `AppConfig` 整合。

---

## 二、8 大架構維度前審 (Gate 1 審查)

1. **個資隱私 (PII)**：日誌與 CSV 僅包含檔名、分數與技術警告，嚴禁在網頁端揭露未脫敏的候選人全文個資。
2. **容量與極限 (Capacity)**：日誌讀取採用限制行數（預設最多 1000 行），防止記憶體 OOM。
3. **非同步與演進 (Async / Evolution)**：`GetDashboardDataUseCase` 保持純淨且無狀態，未來可隨時抽換底層伺服器至 FastAPI。
4. **成本與熔斷 (Cost)**：Web 查詢皆在本地端進行，零外部 API Token 消耗。
5. **可抽換性 (Portability)**：遵循 DIP，Use Case 透過 `IAuditLogReader` 與 `ISystemLogReader` 契約互動。
6. **輸入安全性 (Input Security)**：防範路徑遍歷（Path Traversal），靜態檔案路由僅允許預設 Dashboard 資源，API 參數具備邊界限制。
7. **版本相容性 (Versioning)**：不影響既有轉檔與入庫 CLI，完全為獨立擴充模組。
8. **可觀測性與追溯性 (Observability)**：提供 Web 即時可觀測性，閉環整合完成。

---

## 三、DDD 技術實作規格書 (Tech Spec)

### 1. 架構分層與模組規劃
```
src/
├── domain/
│   ├── models.py                   # 新增 AuditRecord, DashboardSummary, LogRecord
│   └── interfaces.py               # 新增 IAuditLogReader, ISystemLogReader
│
├── application/
│   ├── dto.py                      # 新增 DashboardQueryDTO, DashboardDataResultDTO
│   └── dashboard_use_case.py       # 新增 GetDashboardDataUseCase
│
├── infrastructure/
│   ├── readers/
│   │   ├── csv_audit_reader.py     # 實作 IAuditLogReader
│   │   └── file_log_reader.py      # 實作 ISystemLogReader
│   └── config.py                   # AppConfig 新增 web_host, web_port, default_audit_report
│
└── interfaces/
    └── web/                        # Web 伺服器表現層
        ├── server.py               # DashboardServer, ThreadingHTTPServer, DashboardHandler
        └── static/
            └── dashboard.html      # 現代化單頁儀表板 (SPA, 內嵌 CSS & JS)
```

### 2. CLI 入口點
- 根目錄 [`web_dashboard.py`](../../web_dashboard.py)：
  ```bash
  python web_dashboard.py --port 8080 --host 127.0.0.1
  ```

### 3. 測試計畫
- 單元測試：`tests/unit/test_web_dashboard.py`（Mock Reader，測試統計聚合、邊界情境、零檔案防禦）。
- E2E 測試：`tests/e2e/test_web_dashboard_e2e.py`（啟動真實 Threading Server，發送 HTTP GET 測試 200 回應與 JSON 結構）。

---

## 四、Gate 1 審查結論
8 大架構維度檢核通過，無外部依賴債務，**Gate 1 審查放行 (PASS)**，進入 Step 2 實作。
