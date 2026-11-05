# ADR-0015: 履歷自然語言與制式條件智能 Web 檢索介面架構

## 1. 狀態
已採納 (Accepted)

## 2. 背景與問題陳述 (Context & Problem Statement)
原先系統的履歷搜尋僅支援命令列終端機 `search_resumes.py`，無法滿足招募人員（HR / 用人主管）對於圖形化介面、自然語言輸入、工作年資硬性過濾、以及一鍵查看履歷全文的需求。需要將搜尋能力產品化並整合進 Web 介面。

## 3. 評估選項 (Options Evaluated)
* **選項 A：另起獨立的前端專案與新 Web 服務**
  - 缺點：增加了多個服務維運與連接埠管理的複雜度。
* **選項 B：在現行整合 Web 儀表板架構中，擴充智能檢索模組與 REST API**
  - 優點：
    1. 統一於單一服務入口（`web_dashboard.py`），單一連接埠（8080）。
    2. 結合 SPA 單頁 Tab 切換，使用者能在同一個面板上進行轉檔品管監控、技術排錯與求職者履歷檢索。
    3. 同步支援自然語言（768 維 HNSW 向量檢索）與結構化條件（工作年資、技術標籤、區塊類型）複合過濾。
    4. 支援履歷全文安全預覽（Path Traversal 防禦）。

## 4. 架構決策 (Decision Outcome)
採納選項 B。
- 在 `src/domain/models.py` 擴充 `SearchQuery.min_years` 與 `CandidateSummary`。
- 在 `src/infrastructure/parsers/experience_parser.py` 實作堅固的工作年資正則解析器。
- 在 `src/application/search_resumes_use_case.py` 支援候選人年資篩選與安全讀取履歷全文。
- 在表現層（`fastapi_server.py` 與 `server.py`）提供 `/api/search` 與 `/api/resume` 端點。
- 在 `static/dashboard.html` 擴充搜尋 Tab、快捷條件 Pills、候選人卡片與全文 Modal。

## 5. 8 大架構審查維度評估 (Architecture Review Analysis)
1. **個資隱私 (PII)**：履歷資料僅供本地與內網查詢，日誌零敏感個資。
2. **容量與極限 (Capacity)**：分頁截斷 `top_k`（上限 100），防止記憶體暴衝。
3. **可抽換性 (Portability)**：Use Case 保持純粹依賴 Domain Protocol。
4. **成本與熔斷 (Cost)**：僅自然語言生成向量調用 1 次 Gemini Embedding，其餘制式篩選全本地運行。
5. **安全性 (Security)**：`candidate_id` 檔案讀取進行白名單驗證，阻斷 `..` 路徑遍歷。
