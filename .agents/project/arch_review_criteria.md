# 架構前審：本專案通過標準 (Project Architecture Review Criteria)

> **定位**：**專案實例檔**。8 大架構維度的定義、適用條件與要問的問題，以核心檔 [arch_review_checklist.md](../skills/feature-design/references/arch_review_checklist.md) 為準；本檔只記錄**本專案**對各維度的具體通過標準。Gate 1 審查時兩者並用。
> **移植**：搬到其他專案時整份替換為新專案內容（可先留空表，隨首份規格補齊），見 [PORTING.md](../PORTING.md)。
> **來源**：[Spec-0035](../../docs/specs/0035-portable-arch-review-checklist-spec.md)（原核心檔「通過標準」欄原文移入）。表中數值上限為預設值，實際值以 `.env.example` 與 `AppConfig` 為準。

| # | 維度 | 本專案通過標準 |
| :---: | :--- | :--- |
| **1** | 個資與敏感資料 | 1. 履歷上雲或呼叫外部 LLM 前具備脫敏機制<br>2. Redis 向量庫與 Hash 嚴禁明文存放身分證號<br>3. 日誌輸出杜絕明文個資與 API 密鑰 |
| **2** | 容量與資源上限 | 1. Redis HNSW 記憶體足跡（RAM Footprint）在安全預算內<br>2. 萬筆至百萬筆切片具備擴展能力<br>3. 避免大物件長時間留滯記憶體引發 OOM |
| **3** | 解耦與非同步演進 | 1. Use Case 保持無狀態設計（Stateless）<br>2. 易於無痛封裝至 Celery / Redis Queue 或 FastAPI 背景任務 |
| **4** | 外部呼叫成本與配額 | 1. **模態決策合理性 (Text-First)**：非必要不渲染傳送圖片 (Vision)，原生文字層健康者強制優先走純文字轉檔<br>2. **增量指紋快取 (Zero-Token Idempotency)**：重複輸入時具備 Hash 指紋比對，未變更資料達成 0 次 API 呼叫與 0 Token 消耗<br>3. **切片語意密度門檻**：切片具備最小長度門檻與智慧合併機制，杜絕破碎微切片浪費<br>4. **上下文與生成成本控制**：多輪對話避免歷史無效膨脹，審核修復優先採局部修補而非全文重寫<br>5. **平滑熔斷**：具備 429 配額用罄熔斷防禦，不盲目密集重試 |
| **5** | 可抽換性 | 1. 核心業務 100% 依賴 Domain 契約檔（`project.toml` 的 `layers.domain_interfaces`）的 Protocol 抽象<br>2. 更換外部向量庫或模型時，Domain 與 Use Case 零程式碼改動 |
| **6** | 惡意輸入與資源上限 | 1. 輸入檔案強制設定體積、PDF 頁數與 DOCX 膨脹比上限（預設值見 [review_checklist.md](../skills/code-review/references/review_checklist.md) 第 2 類）<br>2. LLM Prompt 必須使用 `<resume_content>` 標籤進行圍欄隔離，System Prompt 明確禁止執行履歷內指令 |
| **7** | 資料結構演進 | 1. 索引名稱與鍵前綴具備版本識別（如 `idx:resumes:v1`）<br>2. 更換 Embedding 模型或維度時，支援藍綠雙索引重建與 Alias 切換，達成零停機遷移 |
| **8** | 併發與可觀測性 | 1. 轉檔與資料庫切片寫入具備候選人級別之冪等操作，防範多 Worker 競態<br>2. 跨模組調度具備唯一 `Trace ID` / `correlation_id` 貫穿結構化日誌 |

**本專案之 Deep Track 舉例**（補充核心檔第二節）：改動 Redis 向量索引定義、更換 Embedding 模型或維度。
