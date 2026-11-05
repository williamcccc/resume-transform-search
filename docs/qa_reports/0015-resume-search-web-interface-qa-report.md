# QA 實測驗收報告：0015 履歷智能搜尋 Web 介面與年資過濾

> **驗收狀態**：通過 (PASS)  
> **測試執行日期**：2026-11-05  
> **測試執行環境**：Windows 11 / Python 3.13 / FastAPI 0.162.0 / Uvicorn 0.54.0 / Redis 7.4.2  
> **關聯規格書**：[0015-resume-search-web-interface-spec.md](../specs/0015-resume-search-web-interface-spec.md)  
> **關聯 ADR**：[0015-resume-search-web-interface.md](../adr/0015-resume-search-web-interface.md)  

---

## 1. 驗收測試概覽 (Executive Summary)

本報告針對「智能履歷搜尋 Web 介面（含自然語言語意檢索、年資/標籤複合過濾、候選人分組與全文預覽）」進行全維度黑箱/灰箱 QA 驗證。
測試涵蓋了 API 端點契約檢核、自然語言 KNN 語意搜尋、正則年資解析正確性、候選人切片歸併排序、路徑遍歷（Path Traversal）安全防禦、以及內建 ThreadingHTTPServer 降級引擎相容性。

### 驗收成果總表

| 測試類別 | 規劃測試案例數 | 實測通過數 | 阻斷型瑕疵 (P0) | 測試結果 |
| :--- | :---: | :---: | :---: | :---: |
| **年資解析單元測試** | 6 | 6 | 0 | **PASS (100%)** |
| **領域與使用案例測試** | 5 | 5 | 0 | **PASS (100%)** |
| **FastAPI 端點整合測試** | 6 | 6 | 0 | **PASS (100%)** |
| **安全性注入測試 (Path Traversal)** | 5 | 5 | 0 | **PASS (100%)** |
| **儀表板向下相容測試** | 10 | 10 | 0 | **PASS (100%)** |
| **總計** | **32** | **32** | **0** | **ALL PASS** |

---

## 2. 需求追溯性矩陣 (Requirements Traceability Matrix, RTM)

| 規格條款 ID | 驗收條件 (Acceptance Criteria) | 對應測試案例 | 實測結果 | 判定 |
| :--- | :--- | :--- | :--- | :---: |
| **AC-01** | 提供自然語言輸入列，將自然語言轉為 768 維 Embedding 進行 Redis KNN 搜尋 | `test_e2e_search_grouped_with_min_years_filter` | 成功檢索出相似度高之候選人與切片 | **PASS** |
| **AC-02** | 支援最低工作年資 (`min_years`) 篩選，未達門檻之候選人被排除 | `test_execute_web_search_grouped_with_min_years` | 篩選 3 年以上，1~2 年之候選人被精確剔除 | **PASS** |
| **AC-03** | 支援按求職者整合呈現 (`group_by_candidate`)，計算最高相似度與所有切片 | `test_execute_web_search_grouped_with_min_years` | 正確歸併 2 筆切片並保留技能與年資 | **PASS** |
| **AC-04** | 提供一鍵彈窗安全讀取候選人 Markdown 履歷全文 | `test_e2e_get_resume_success` | 成功取得並完整展示履歷全文內容 | **PASS** |
| **AC-05** | 防範路徑遍歷攻擊（`../`、`\` 等），非法請求直接阻斷 | `test_e2e_get_resume_path_traversal_defense` | 包含 `../secret.txt` 等攻擊回傳 400 Bad Request | **PASS** |
| **AC-06** | 空字串或缺少 query 參數時優雅處理 | `test_e2e_search_missing_query_bad_request` | 空白或空參數精確回傳 400 Bad Request | **PASS** |
| **AC-07** | 雙引擎架構（FastAPI 首選，內建 ThreadingHTTPServer 降級）端點皆可正常提供服務 | `test_web_dashboard.py` + `test_resume_web_search_e2e.py` | 雙引擎皆完整具備 `/api/search` 與 `/api/resume` | **PASS** |

---

## 3. 安全性測試評估 (Security Audit & Path Traversal)

針對履歷全文讀取端點 `GET /api/resume?candidate_id=...` 進行惡意路徑探測：

| 探測輸入字串 | 攻擊意圖 | 預期防護行為 | 實測 HTTP 狀態碼 | 防護結論 |
| :--- | :--- | :--- | :---: | :---: |
| `../secret.txt` | 目錄向上越權讀取 | 阻斷拋出 400 | `400 Bad Request` | **PASS** (防禦有效) |
| `..\..\etc\passwd` | Windows/Linux 混合路徑遍歷 | 阻斷拋出 400 | `400 Bad Request` | **PASS** (防禦有效) |
| `dir/../../../etc/shadow` | 子目錄逃逸 | 阻斷拋出 400 | `400 Bad Request` | **PASS** (防禦有效) |
| `c:/windows/system32/cmd.exe` | 絕對路徑直接存取 | 阻斷拋出 400 | `400 Bad Request` | **PASS** (防禦有效) |
| `ghost_user_404` | 不存在之候選人 | 安全回傳 404 | `404 Not Found` | **PASS** (正常防呆) |

---

## 4. 效能與使用者體驗驗證 (Performance Benchmarks)

1. **單元與 E2E 測試整體執行耗時**：32 個測試案例於 4.37 秒內全數執行完畢，毫秒級白箱回饋。
2. **Web 介面響應延遲**：
   - 語意搜尋計算耗時前端即時顯示（預估 50~200 ms）。
   - 前端提供骨架屏載入提示 (`AI 語意向量計算與 Redis 檢索中`)，消除使用者等待焦慮。
   - 履歷彈窗支援一鍵複製 Markdown 文本至系統剪貼簿。

---

## 5. 結論與放行判定

經過 32 項白箱單元測試與黑箱 E2E 整合驗證，本需求實作零功能瑕疵、零未處理異常、安全防護完整，完全符合 PRD 與 Tech Spec 之驗收規範，**Gate 1 驗收全數通過 (PASS)，核准進入 Gate 2 代碼審查階段**。
