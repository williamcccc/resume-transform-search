# 架構決策紀錄 (Architecture Decision Records, ADR)

本目錄存放本專案所有關鍵架構設計與技術選型的決策紀錄（ADR）。
每個 ADR 均記錄了決策時的**時空背景、評估的替代方案、最終選型與 8 大維度架構衝擊分析**。

---

## 一、ADR 檢索清單 (ADR Index)

| 編號 | 標題 | 狀態 | 決策日期 | 核心技術標籤 |
| :---: | :--- | :--- :---: | :---: | :--- |
| **[ADR-0001](./0001-clean-architecture-and-ddd.md)** | 採用 Clean Architecture 與 DDD 四層依賴反轉架構 | 已採納 (Accepted) | 2026-11 | `DDD`, `Clean Architecture`, `DIP` |
| **[ADR-0002](./0002-dual-routing-and-self-refinement.md)** | 文件轉檔智慧自動判別管線與兩階段自我審核修復 | 已採納 (Accepted) | 2026-11 | `Gemini Vision`, `Auto-Routing`, `Fail-Safe` |
| **[ADR-0003](./0003-redis-hnsw-vector-store.md)** | 採用 Redis HNSW 向量庫與 768 維語意切片檢索 | 已採納 (Accepted) | 2026-11 | `Redis`, `HNSW`, `Embedding`, `KNN` |
| **[ADR-0004](./0004-four-tier-quality-guardrails.md)** | 建立確定性品管閥與獨立評審員四層品管防線 | 已採納 (Accepted) | 2026-11 | `Quality Gate`, `LLM-as-a-Judge`, `Quarantine` |
| **[ADR-0005](./0005-security-observability-and-code-governance.md)** | 全面安全性防禦、可觀測性演進與代碼治理規範升級 | 已採納 (Accepted) | 2026-11 | `Security`, `Observability`, `Index Migration`, `Exception Chaining` |
| **[ADR-0006](./0006-token-optimization-and-incremental-indexing.md)** | Token 消耗最佳化、增量指紋入庫與切片語意合併 | 已採納 (Accepted) | 2026-11 | `Token Optimization`, `Incremental Indexing`, `Chunk Merging`, `Text-First` |
| **[ADR-0007](./0007-twelve-factor-configuration-and-env-extraction.md)** | Twelve-Factor 全盤環境變數提取與配置治理 | 已採納 (Accepted) | 2026-11 | `Twelve-Factor`, `AppConfig`, `DIP`, `Environment Isolation` |
| **[ADR-0008](./0008-prompt-engineering-externalization-and-runtime-config.md)** | Prompt Engineering 獨立檔案化與運行時演算法配置治理 | 已採納 (Accepted) | 2026-11 | `Prompt Engineering`, `Git Versioning`, `HNSW Tuning`, `Retention Ratio` |
| **[ADR-0009](./0009-comprehensive-hardcode-extraction-and-config-penetration.md)** | 全面硬編碼提取、配置貫通與文字轉檔提示詞資產解耦 | 已採納 (Accepted) | 2026-11 | `Twelve-Factor`, `Config Penetration`, `Prompt Decoupling`, `Threshold Tuning` |
| **[ADR-0010](./0010-comprehensive-prompt-externalization-and-template-governance.md)** | 全面提示詞外部化與評判模板資產化治理 | 已採納 (Accepted) | 2026-11 | `Prompt Externalization`, `LLM-as-a-Judge`, `Template Decoupling`, `AST Guardrails` |
| **[ADR-0011](./0011-agent-memory-management-and-streaming-token-governance.md)** | 多 Agent 狀態記憶治理、延遲串流索引與視覺審核 Token 節流 | 已採納 (Accepted) | 2026-11 | `Memory Management`, `Lazy Streaming`, `Token Governance`, `Context Handoff` |
| **[ADR-0012](./0012-centralized-system-logging-and-api-latency-tracking.md)** | 集中式系統技術日誌與外部 API 請求耗時可觀測性治理 | 已採納 (Accepted) | 2026-11 | `Logging`, `Observability`, `Latency Tracking`, `Twelve-Factor` |
| **[ADR-0013](./0013-full-lifecycle-doc-archiving-and-governance.md)** | 專案全生命週期文檔持久化體系與雙重歸檔架構 | 已採納 (Accepted) | 2026-11 | `Documentation`, `Traceability`, `Dual-Persistence` |
| **[ADR-0014](./0014-web-dashboard-and-audit-observability.md)** | 輕量化轉檔稽核日誌與統計摘要 Web 儀表板架構 | 已採納 (Accepted) | 2026-11 | `Web Dashboard`, `Observability`, `Zero-Dependency`, `ThreadingHTTPServer` |
| **[ADR-0015](./0015-resume-search-web-interface.md)** | 智能履歷搜尋 Web 介面與工作年資/技術標籤複合檢索 | 已採納 (Accepted) | 2026-11 | `Resume Search`, `FastAPI`, `Experience Parser`, `DIP` |
| **[ADR-0016](./0016-github-pre-publish-security-and-pii-governance.md)** | GitHub 上庫前全方位安全脫敏、個資 (PII) 清零與跨平台路徑治理 | 已採納 (Accepted) | 2026-11 | `PII Sanitization`, `Git Hygiene`, `Cross-Platform`, `SHA-256 Guardrail` |
| **[ADR-0017](./0017-publish-privacy-scanner-hardening.md)** | 上庫前個資掃描與文件連結防線補強 | 已採納 (Accepted) | 2026-11 | `Privacy`, `Static Scanning`, `Git Hygiene`, `Documentation` |
| **[ADR-0018](./0018-uvicorn-standard-asgi-entrypoint-and-di-bootstrap.md)** | 支援 Uvicorn 標準 ASGI 啟動、App Factory 與 Web 依賴注入組裝收斂 | 已採納 (Accepted) | 2026-11 | `FastAPI`, `Uvicorn`, `ASGI`, `Dependency Injection` |
| **[ADR-0019](./0019-recruitment-assistant-langgraph-chat.md)** | HR 多輪對話招募助手：LangGraph 意圖路由固定節點圖與查詢期延遲結構化抽取 | 已採納 (Accepted) | 2026-11 | `LangGraph`, `Gemini`, `Lazy Extraction`, `Deterministic Ranking` |
| **[ADR-0020](./0020-recruitment-chat-langsmith-masked-tracing.md)** | 招募助手 LangSmith 遮蔽式效能追蹤 | 已採納 (Accepted) | 2026-11 | `Observability`, `LangSmith`, `Tracing`, `Zero-PII` |

---

## 二、ADR 生命週期狀態
* **提案中 (Proposed)**：提出新架構想法，正在進行 8 大維度評估與原型驗證。
* **已採納 (Accepted)**：通過架構審查（Gate 1），已正式落地實施。
* **已廢止 (Deprecated)**：因業務演進或技術迭代而退役。
* **被取代 (Superseded by ADR-xxxx)**：由更新的架構決策替換。

---

## 三、ADR 撰寫範本 (Template)

```markdown
# ADR-XXXX: [決策標題]

## 1. 狀態
[提案中 (Proposed) | 已採納 (Accepted) | 已廢止 (Deprecated)]

## 2. 背景與問題陳述 (Context & Problem Statement)
[為什麼需要做這個架構決策？面臨了什麼挑戰或業務瓶頸？]

## 3. 評估選項 (Options Evaluated)
* **選項 A**：優點 / 缺點
* **選項 B**：優點 / 缺點

## 4. 架構決策 (Decision Outcome)
[選擇哪個方案，其核心理由為何？]

## 5. 8 大架構審查維度評估 (Architecture Review Analysis)
1. **個資隱私 (PII)**：履歷資料傳輸與儲存脫敏規劃。
2. **容量與極限 (Capacity)**：Redis 記憶體足跡、向量切片上限與儲存擴展性。
3. **非同步與演進 (Async / Evolution)**：無狀態 Use Case，與任務隊列/API 解耦能力。
4. **成本與熔斷 (Cost & Circuit Breaker)**：外部 API 預算控制、429 配額用罄熔斷防禦。
5. **可抽換性 (Portability & Decoupling)**：Domain 介面純潔度，替換外部底層技術零衝擊。
6. **惡意輸入與配額硬上限 (Input Security & Bomb Defense)**：Zip Bomb、巨型 PDF、Prompt Injection 防禦。
7. **向量索引演進與藍綠遷移 (Index Evolution & Migration)**：Embedding 升級與平滑無痛遷移。
8. **分散式併發與全鏈路可觀測性 (Concurrency & Observability)**：多 worker 冪等競爭防禦與 Trace ID 結構化追蹤。
```
