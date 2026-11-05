# 8 大架構維度前審檢核清單 (Architecture Review Checklist - Gate 1)

> **使用說明**：在完成 PRD 與 Tech Spec 草案後，進入 Gate 1 審查時，必須逐項檢核以下 8 大架構維度。重大架構異動需於 `docs/adr/` 產出 ADR 草案。

---

## 一、8 大維度審查表

| 維度編號 | 審查維度 | 核心檢核重點 | 通過標準 (PASS Criteria) |
| :---: | :--- | :--- | :--- |
| **1** | **個資隱私 (PII)** | 敏感資料傳輸與儲存合規 | 1. 履歷上雲或呼叫外部 LLM 前具備脫敏機制<br>2. Redis 向量庫與 Hash 嚴禁明文存放身分證號<br>3. 日誌輸出杜絕明文個資與 API 密鑰 |
| **2** | **容量與極限 (Capacity)** | 系統承載力與記憶體上限 | 1. Redis HNSW 記憶體足跡（RAM Footprint）在安全預算內<br>2. 萬筆至百萬筆切片具備擴展能力<br>3. 避免大物件長時間留滯記憶體引發 OOM |
| **3** | **非同步與演進 (Async / Evolution)** | 系統解耦與分散式準備 | 1. Use Case 保持無狀態設計（Stateless）<br>2. 易於無痛封裝至 Celery / Redis Queue 或 FastAPI 背景任務 |
| **4** | **Token 能效與成本熔斷 (Token Economics & Cost)** | API 呼叫預算、Token 能效與配額保護 | 1. **模態決策合理性 (Text-First)**：非必要不渲染傳送圖片 (Vision)，原生文字層健康者強制優先走純文字轉檔<br>2. **增量指紋快取 (Zero-Token Idempotency)**：重複輸入時具備 Hash 指紋比對，未變更資料達成 0 次 API 呼叫與 0 Token 消耗<br>3. **切片語意密度門檻**：切片具備最小長度門檻與智慧合併機制，杜絕破碎微切片浪費<br>4. **上下文與生成成本控制**：多輪對話避免歷史無效膨脹，審核修復優先採局部修補而非全文重寫<br>5. **平滑熔斷**：具備 429 配額用罄熔斷防禦，不盲目密集重試 |
| **5** | **可抽換性 (Portability & Decoupling)** | DDD 依賴反轉純潔性 | 1. 核心業務 100% 依賴 `src/domain/interfaces.py` 的 Protocol 抽象<br>2. 更換外部向量庫或模型時，Domain 與 Use Case 零程式碼改動 |
| **6** | **惡意輸入與配額硬上限 (Input Security)** | 防範 Zip Bomb 與提示詞注入 | 1. 輸入檔案強制設定體積上限（25MB）、PDF 頁數上限（30 頁）與 DOCX 膨脹比（10x）<br>2. LLM Prompt 必須使用 `<resume_content>` 標籤進行圍欄隔離，System Prompt 明確禁止執行履歷內指令 |
| **7** | **向量索引演進遷移 (Index Evolution)** | 向量版本管理與平滑切換 | 1. 索引名稱與鍵前綴具備版本識別（如 `idx:resumes:v1`）<br>2. 更換 Embedding 模型或維度時，支援藍綠雙索引重建與 Alias 切換，達成零停機遷移 |
| **8** | **分散式併發與可觀測性 (Concurrency & Traceability)** | 競爭狀態防範與除錯追蹤 | 1. 轉檔與資料庫切片寫入具備候選人級別之冪等操作，防範多 Worker 競態<br>2. 跨模組調度具備唯一 `Trace ID` / `correlation_id` 貫穿結構化日誌 |

---

## 二、輕重分流判定原則 (Routing Decision)

* **輕量級變更 (Fast Track)**：
  * 適用：單純 Bug 修復、單一既有參數微調、文字提取小重構。
  * 流程：執行上述 8 維度的快速心智自檢，確認不破壞 DDD 邊界與資源管理，免寫 ADR，直接產出簡版 Tech Spec。
* **重大架構變更 (Deep Track)**：
  * 適用：新增外部 API / SDK 整合、資料庫 Schema 異動、新增 Use Case、引入任務隊列、改動向量索引。
  * 流程：強制撰寫完整 PRD、填寫 8 大維度評估表，並於 [`docs/adr/`](../../../../docs/adr/) 建立 ADR 草案，待 Gate 1 審查合格後始得動工。
