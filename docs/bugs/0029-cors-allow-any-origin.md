# 缺陷報告：Web 儀表板 CORS 對任意來源放行，外站網頁可跨站讀取履歷與對話

> **編號**：0029｜**嚴重度**：S1｜**狀態**：處理中（PR 審核中）

## 1. 受理資訊
* **現象**：Web 儀表板（FastAPI 引擎）對任何 `Origin` 皆原樣回寫 `Access-Control-Allow-Origin` 並附 `Access-Control-Allow-Credentials: true`，預檢請求亦放行所有方法；內建引擎則對所有 JSON 回應寫死 `Access-Control-Allow-Origin: *`。
* **環境**：Windows 11 / Python 3.13；FastAPI 引擎與內建 `ThreadingHTTPServer` 引擎；Redis（Docker `localhost:6379`）。
* **觸發條件**：使用者在本機啟動儀表板期間，以瀏覽器開啟任一外站網頁；該網頁腳本以 `fetch("http://127.0.0.1:8080/api/...")` 呼叫儀表板 API。
* **回報來源**：既有 Backlog 項目 G2-09（[Spec-0019 第五部 §2](../specs/0019-recruitment-assistant-chat-spec.md)、[QA-0019 §9](../qa_reports/0019-recruitment-assistant-chat-qa.md)），使用者要求修正；Step 1B 重現時確認風險高於原評估的 P2。
* **嚴重度判定理由**：外站可讀回 `/api/resume`（履歷全文）、`/api/search`（候選人清單）與 `/api/chat`（名單、證據），屬「個資外洩、安全漏洞」，判定 S1，走 [hotfix.md](../../.agents/workflows/hotfix.md)。

## 2. 重現步驟
1. 啟動儀表板：
   ```bash
   python web_dashboard.py --port 8080
   ```
2. 以虛構外站來源發出請求：
   ```bash
   curl -s -D - -o /dev/null -H "Origin: https://evil.example" http://127.0.0.1:8080/api/stats
   curl -s -D - -o /dev/null -X OPTIONS -H "Origin: https://evil.example" -H "Access-Control-Request-Method: POST" -H "Access-Control-Request-Headers: content-type" http://127.0.0.1:8080/api/chat
   ```
3. **預期結果**：回應不含任何 `access-control-allow-*` 標頭，瀏覽器拒絕將回應交給外站腳本。
4. **實際結果**：回應含 `access-control-allow-origin: https://evil.example` 與 `access-control-allow-credentials: true`；預檢回 `access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT, QUERY`。

**紅燈回歸測試**：[tests/unit/test_web_cors_same_origin.py](../../tests/unit/test_web_cors_same_origin.py)（6 項，其中 5 項重現缺陷、1 項守護同源行為）

```text
[修正前（test: commit 44a1c7d）執行結果摘要]
FAILED (failures=5)
AssertionError: 'access-control-allow-origin' unexpectedly found in Headers({... 'access-control-allow-origin': 'https://evil.example', 'access-control-allow-credentials': 'true', ...})
AssertionError: 'access-control-allow-origin' unexpectedly found in ['content-type', 'content-length', 'access-control-allow-origin', 'cache-control']
```

## 3. 根因分析
* **真因**：Web 儀表板初版即以「開發便利」為由全開 CORS，而前端 [dashboard.html](../../src/interfaces/web/static/dashboard.html) 一律以相對路徑同源呼叫 API，從未需要跨來源許可。`allow_origins=["*"]` 加 `allow_credentials=True` 在 Starlette 的實作是**回寫請求來源**，等同對所有網站授權讀取。後續新增 `/api/resume`、`/api/chat` 等含個資端點時，風險隨之放大。
* **所屬 DDD 層**：interfaces
* **位置**：
  * [fastapi_server.py](../../src/interfaces/web/fastapi_server.py) `create_app()` 內 `app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, ...)`
  * [server.py](../../src/interfaces/web/server.py) `DashboardHandler.send_json_response()` 內 `send_header("Access-Control-Allow-Origin", "*")`
* **逃逸分析**：
  * **規格缺口**：Spec-0014、0015、0018 皆未定義跨來源政策；Spec-0019 已識別（R7、G2-09）但列為不在本期範圍。
  * **測試缺口**：既有單元與 E2E 測試只以同源方式呼叫 API，沒有任何測試帶入 `Origin` 標頭。
  * **防線缺口**：`audit_guardrails.py` 與 Gate 2 Checklist 沒有 Web 端跨來源設定的檢核項，靜態掃描無法抓到 `allow_origins=["*"]`。
* **防線改善建議**（另案處理）：
  1. Gate 2 Checklist「輸入安全」節新增 P0 項：Web 端點不得以萬用字元或回寫方式開放跨來源存取。
  2. `audit_guardrails.py` 新增 AST 檢查：偵測 `CORSMiddleware` 的 `allow_origins` 含 `"*"`，以及字面值 `Access-Control-Allow-Origin` 搭配 `"*"`。

## 4. 修正範圍與升級判斷

| 預計修改檔案 | 修改性質 |
| :--- | :--- |
| `src/interfaces/web/fastapi_server.py` | 移除 `CORSMiddleware` 掛載與 import，更新 docstring |
| `src/interfaces/web/server.py` | 移除 `Access-Control-Allow-Origin: *` 標頭 |
| `tests/unit/test_web_cors_same_origin.py` | 新增回歸測試 |

**修正策略說明**：Backlog 原建議新增 `WEB_CORS_ORIGINS` 白名單設定，但新增 `AppConfig` 環境變數會觸發升級條件 3。由於現行前端完全同源、沒有跨來源使用者，止血採「不開放任何跨來源許可」，與 Backlog 建議之預設值（只允許同源）一致。若日後出現跨來源需求，再開功能規格新增白名單設定。

**升級條件檢查**：

| # | 條件 | 是否觸發 |
| :---: | :--- | :---: |
| 1 | 修改 Domain 契約檔（`project.toml` 的 `layers.domain_interfaces`）的 Protocol 或 DTO 欄位 | 否 |
| 2 | 修改資料模型或 Redis 索引結構 | 否 |
| 3 | 新增 `AppConfig` 環境變數或 CLI 參數 | 否 |
| 4 | 「正確行為」在現有規格中未定義或定義矛盾 | 否（Spec-0019 G2-09 明訂建議之預設為只允許同源） |
| 5 | 修正範圍跨越 3 個以上 DDD 層 | 否（僅 interfaces） |

**簡化 Gate 1 簽核**（architect，2026-11-20）：
- [x] 修正只恢復既有規格行為，不新增行為：移除未被任何規格要求的跨來源許可，同源 API 行為不變。
- [x] 影響面已列出：呼叫端為 [dashboard.html](../../src/interfaces/web/static/dashboard.html)（全部相對路徑，不受影響）、Swagger `/docs`（同源，不受影響）；兩種伺服器引擎；既有測試無 CORS 斷言。唯一受影響者為從其他來源（含其他連接埠）以瀏覽器呼叫 API 的使用方式，現行專案內不存在。
- [x] 無介面破壞，既有 CLI 與 API 相容：路由、參數、回應格式皆未變更。

## 5. 缺陷驗收條件 (BC)
* **BC-1**：紅燈回歸測試 [test_web_cors_same_origin.py](../../tests/unit/test_web_cors_same_origin.py) 在 `test:` commit 失敗，在 `fix:` commit 通過。
* **BC-2**：FastAPI 引擎對跨來源的 GET（含帶 Cookie）與 `POST /api/chat` 預檢請求，皆不回傳 `access-control-allow-origin`、`access-control-allow-credentials`、`access-control-allow-methods`。
* **BC-3**：內建引擎之 JSON 與錯誤回應不回傳 `access-control-allow-origin`。
* **BC-4**：同源呼叫（儀表板頁面、`/api/stats`、`/api/audit`、`/api/logs`、`/api/search`、`/api/chat`）行為不變。
* **BC-5**：全套單元測試無回歸。

品質評測範圍：否

## 6. 結案
* **`test:` commit**：`44a1c7d`
* **`fix:` commit**：`0b195a1`
* **PR**：[#23](https://github.com/williamcccc/resume-transform-search/pull/23)
* **QA 報告**：[QA-0029](../qa_reports/0029-cors-allow-any-origin-qa.md)
* **結案日期**：（PR 合併後填寫）
* **另案追蹤**：審查時發現伺服器未驗證 `Host` 標頭（DNS rebinding 可繞過同源限制），根因不同，依 [bug.md](../../.agents/workflows/bug.md)「一個 bug 一個 PR」另案處理。
