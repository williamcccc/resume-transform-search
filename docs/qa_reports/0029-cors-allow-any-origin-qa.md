# QA 實測驗收報告: Bug-0029 Web 儀表板 CORS 只允許同源

> 缺陷報告：[docs/bugs/0029-cors-allow-any-origin.md](../bugs/0029-cors-allow-any-origin.md)｜軌別：[hotfix.md](../../.agents/workflows/hotfix.md)（S1）

## 1. 測試環境與前置條件 (Test Environment)
* **測試日期與時間**：`2026-11-20`
* **作業系統與 Python 版本**：Windows 11 / Python 3.13
* **外部相依服務狀態**：
  * Redis（Docker）：`localhost:6379` 連線正常，索引 `idx:resumes:v1` 就緒
  * Gemini API：正常連線（僅同源 `/api/search` 冒煙使用）
* **測試資料集**：單元測試全為記憶體 Mock；實測使用虛構來源 `https://evil.example` 與本機不同連接埠作為跨來源頁面

---

## 2. 測試計畫摘要 (Test Plan Summary)
* **測試範圍 (In Scope)**：FastAPI 與內建兩種引擎的跨來源回應標頭；同源 API 與儀表板頁面行為；真實瀏覽器跨來源讀取是否被擋下；CSRF 簡單請求能否觸發 `/api/chat`。
* **不測範圍 (Out of Scope)**：

  | 不測項目 | 理由 | 風險與替代保障 |
  | :--- | :--- | :--- |
  | 招募助手完整多輪對話 | 本修正不觸及對話邏輯，且每輪約 20 次 LLM 呼叫 | 同源 `DELETE /api/chat` 實測 204 確認路由可用；既有 `test_recruitment_chat_api.py` 全數通過 |
  | 跨來源白名單設定 | 本次未新增此功能 | 需求出現時另開功能規格 |

* **進入條件 (Entry Criteria)**：Step 3 全套單元測試通過（639 項 OK）；Redis 就緒。
* **退出條件 (Exit Criteria)**：見第 8 節。
* **風險與優先順序**：(1) 修正後跨來源仍可讀取（漏修某一引擎）；(2) 同源功能被誤傷；(3) 實測「被擋下」其實源於瀏覽器其他限制而非修正生效，故加做對照組。

---

## 3. 需求驗收追溯矩陣 (RTM)

| 驗收條款 | 條款說明 | 覆蓋測試案例 | 測試類型 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **BC-1** | 回歸測試先紅後綠 | `TC-01` | Unit | **PASS** |
| **BC-2** | FastAPI 跨來源 GET／帶 Cookie／預檢不放行 | `TC-02`、`TC-03`、`TC-04`、`TC-08` | Unit + Live + Browser | **PASS** |
| **BC-3** | 內建引擎不回傳 ACAO | `TC-05`、`TC-06`、`TC-08` | Unit + Live + Browser | **PASS** |
| **BC-4** | 同源行為不變 | `TC-07`、`TC-09` | Unit + Live + Browser | **PASS** |
| **BC-5** | 全套單元測試無回歸 | `TC-10` | Unit | **PASS** |
| Spec-0019 G2-09 | 外站不得跨站呼叫 `/api/chat` 讀回名單或消耗 Token | `TC-04`、`TC-08`、`TC-11` | Live + Browser | **PASS** |

---

## 4. 測試案例執行矩陣 (Test Case Execution Matrix)

| 案例編號 | 測試案例名稱 | 分類 | 輸入條件 / 指令 | 預期結果 | 實際結果 | 判定 |
| :---: | :--- | :---: | :--- | :--- | :--- | :---: |
| **TC-01** | 先紅後綠 | Regression | 於 `44a1c7d` 與 `0b195a1` 分別執行 `test_web_cors_same_origin` | 前者失敗、後者通過 | `FAILED (failures=5)` → `OK` | **PASS** |
| **TC-02** | FastAPI 跨來源 GET | Security | `Origin: https://evil.example` GET `/api/stats` | 無 `access-control-*` 標頭 | 僅 `HTTP/1.1 200 OK`，無 CORS 標頭 | **PASS** |
| **TC-03** | FastAPI 跨來源 GET 帶 Cookie | Security | 同上加 `Cookie: a=b` | 不回寫來源、無 credentials | 無 CORS 標頭 | **PASS** |
| **TC-04** | FastAPI `/api/chat` 預檢 | Security | OPTIONS + `Access-Control-Request-Method: POST` | 不放行 | `405 Method Not Allowed`，無 CORS 標頭 | **PASS** |
| **TC-05** | 內建引擎跨來源 GET（含 Cookie） | Security | `--engine builtin`，同 TC-02、TC-03 | 無 ACAO | `HTTP/1.0 200 OK`，無 CORS 標頭 | **PASS** |
| **TC-06** | 內建引擎預檢 | Security | 同 TC-04 | 不放行 | `501 Unsupported method ('OPTIONS')` | **PASS** |
| **TC-07** | 同源 API 冒煙（兩引擎） | Happy | GET `/api/stats`、`/api/audit`、`/api/logs`、`/api/search` | 皆 200 | 兩引擎 4 支皆 200 | **PASS** |
| **TC-08** | 真實瀏覽器跨來源讀取 | Browser | 於 `localhost:8081` 頁面 `fetch` `127.0.0.1:8080` 的 GET 與 DELETE；反向於 `127.0.0.1:8080` 頁面 `fetch` `localhost:8081` | 皆被瀏覽器擋下 | 三者皆 `TypeError: Failed to fetch` | **PASS** |
| **TC-09** | 真實瀏覽器同源 | Browser | `127.0.0.1:8080` 頁面同源 GET `/api/stats`、DELETE `/api/chat/{id}`；儀表板畫面載入 | 200／204，畫面正常 | 200／204，畫面正常渲染 | **PASS** |
| **TC-10** | 全套單元測試 | Regression | `python -m unittest discover -s tests/unit -p "test_*.py"` | 全數通過 | `Ran 639 tests ... OK` | **PASS** |
| **TC-11** | CSRF 簡單請求觸發對話 | Adversarial | 外站以 `text/plain`、`application/x-www-form-urlencoded` POST `/api/chat`（不觸發預檢） | 不得進入對話流程 | 兩者皆 `422`，未呼叫 LLM | **PASS** |
| **TC-12** | 對照組：瀏覽器在伺服器允許時可讀 | Control | 臨時伺服器回 `Access-Control-Allow-Origin: *`，於同一頁面跨來源 `fetch` | 可讀取 | 讀回 `{"control":true}` | **PASS** |

---

## 5. 實測執行日誌摘要 (Execution Logs Summary)
* 單元測試：`Ran 639 tests in 55.8s OK`；回歸測試單檔 `Ran 6 tests OK`。
* TC-12 對照組證明 TC-08 的「擋下」確實源自伺服器不再回傳 CORS 標頭，而非瀏覽器其他限制。

---

## 6. 品質評測結果 (Quality Evaluation)
不適用（品質評測範圍：否）。

---

## 7. 失敗分析與根因定位 (Failure Analysis & RCA)
無失敗項目。

**對抗實測發現之殘餘風險（不同根因，另案處理）**：
* **未驗證 `Host` 標頭**：以 `Host: attacker.example:8080` 請求 `/api/stats` 回 200。攻擊者可藉 DNS rebinding 讓外站網域解析到 `127.0.0.1`，以「同源」身分讀取 API，繞過本次修正。建議以 `TrustedHostMiddleware`（及內建引擎對應檢查）限制為綁定之主機名稱。
* **`no-cors` 盲打 GET `/api/search`**：外站無法讀回結果，但每次請求會觸發一次 Embedding 呼叫（Token 成本極低）。

---

## 8. QA 驗收結論 (QA Sign-Off)
* **驗收判定**：**【通過 (PASSED)】**
* **放行標準**：
  1. RTM 零 `FAIL`、零 `NOT COVERED` ✅
  2. 邊界與異常對抗實測全數通過（含 CSRF 簡單請求、對照組） ✅
  3. Windows 資源生命週期：本修正不涉及檔案 I/O ✅
  4. 品質評測：不適用
* **放行說明**：**准予放行進入 Gate 2 代碼審查。**

---

## 9. Gate 2 代碼審查紀錄 (Code Review Record)

### 9.1 審查輪次

| 輪次 | 日期 | 審查範圍 (commit / diff) | `audit_guardrails.py` | P0 | P1 | P2 | 判定 |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| 1 | 2026-11-20 | `da0cce6..0b195a1` | Exit 0（100% PASSED） | 0 | 0 | 0 | **PASS** |

### 9.2 發現項目

無。審查中發現之 `Host` 標頭未驗證屬不同根因，記於第 7 節殘餘風險並另案處理，不列為本次發現項目。

### 9.3 需求—斷言追溯抽查

| 驗收條款 | 對應測試與斷言 | 預期值來源 | 判定 |
| :--- | :--- | :--- | :---: |
| BC-2 | `TestFastApiCorsSameOrigin::test_cross_origin_preflight_for_chat_should_not_be_allowed` 斷言 `access-control-allow-origin`、`access-control-allow-methods` 不在回應標頭，且 `chat.execute` 未被呼叫 | 缺陷報告第 2 節預期結果；Spec-0019 G2-09「預設只允許同源」 | **OK** |
| BC-3 | `TestBuiltinEngineCorsSameOrigin::test_json_response_should_not_send_acao_header` 斷言送出標頭不含 ACAO、仍含 `content-type`，且本文為 `{"ok": true}` | 缺陷報告第 2 節預期結果 | **OK** |
| BC-4 | `TestFastApiCorsSameOrigin::test_same_origin_request_should_still_work` 斷言狀態碼 200 且 `total_files == 1` | 測試夾具固定樣本 | **OK** |

### 9.4 雙門禁審查結論

### 🛡️ Code Review 雙門禁審查結果
* **架構靜態掃描**： 通過 (`audit_guardrails.py` 零 P0 違規)
* **DDD 依賴邊界**： 通過 (僅修改 interfaces 層，未新增跨層依賴)
* **安全與配額硬上限**： 通過 (移除跨來源許可；CSRF 簡單請求實測 422)
* **資源釋放與鎖定防禦**： 不適用 (未涉及檔案 I/O)
* **Twelve-Factor 配置治理**： 通過 (未新增設定；零寫死金鑰/URL/絕對路徑)
* **邊界例外與例外鏈**： 不適用 (未變更例外處理)
* **日誌安全合規**： 通過 (未新增日誌輸出)
* **資料操作與冪等性**： 不適用
* **測試隔離與負面覆蓋**： 通過 (6 項單元測試以 TestClient 與 Mock 離線執行，含 5 項跨來源負面情境)
* **需求—斷言追溯**： 通過 (5/5 條 BC 具備直接驗證預期結果之斷言；抽查 BC-2、BC-3、BC-4 預期值來源獨立)
* **先紅後綠與逃逸分析**： 通過 (`test:` commit `44a1c7d` 紅燈 5 項失敗、`fix:` commit `0b195a1` 綠燈；逃逸分析已記錄於缺陷報告第 3 節)
* **Git 版控衛生與零個資防線**： 通過 (測試使用虛構來源 `evil.example`，零真實個資與絕對路徑)
