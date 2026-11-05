# ADR-0003: 採用 Redis HNSW 向量庫與 768 維語意切片檢索

## 1. 狀態
已採納 (Accepted)

## 2. 背景與問題陳述 (Context & Problem Statement)
履歷轉換為 Markdown 後，HR 需要透過自然語言（如「高併發金流系統、Golang 與 Redis 經驗」）精準檢索合適的候選人。
需要一套高效能向量索引，且必須同時具備以下能力：
1. 向量近鄰語意比對（KNN Vector Search）。
2. 元資料標籤過濾（Tag Filtering，如 skills、job_type、experience）。
3. 毫秒級即時查詢回應。
4. 容易與既有系統整合，避免過度複雜的維運負擔。

## 3. 評估選項 (Options Evaluated)
* **選項 A：ChromaDB / SQLite-vss**：單機輕量，但在多程序並發寫入時容易遭遇 SQLite 資料庫鎖，缺乏生產級叢集運維工具。
* **選項 B：Milvus / Qdrant**：功能極其強大，但架構龐大（需要 etcd、minio 等多個依賴容器），小型與中型規模運維成本過高。
* **選項 C：Redis (RediSearch HNSW 向量擴充，推薦)**：
  * 原生支援 HNSW 與 FLAT 向量索引。
  * 支援向量與標籤的混合查詢（Hybrid Query：`(@skills:{...})=>[KNN k @vec $v]`）。
  * 記憶體快取速度極快（毫秒級）。

## 4. 架構決策 (Decision Outcome)
**採納選項 C**。
* 模型選型：採用 Google `gemini-embedding-001`，維度指定為 **768 維**（兼顧表達力與記憶體用量）。
* 索引參數：`idx:resumes`，`M=16`, `efConstruction=200`, `efSearch=10`，距離度量為 `COSINE`。
* 冪等性防護：入庫前必須先清除同候選人的舊切片資料，避免重跑累積垃圾資料。

## 5. 5 大架構審查維度評估 (Architecture Review Analysis)
1. **個資隱私 (PII)**：向量庫僅儲存經歷、技能、專案切片摘要與候選人 ID，不存放原始身份證號與住址明文。
2. **容量與極限 (Capacity)**：
   * 768 維 Float32 向量 = 3,072 bytes $\approx$ 3 KB。
   * 包含中繼資料與 HNSW 圖結構，單筆切片約 8 KB。
   * 1 萬筆切片（約 1,500 份履歷）消耗約 80 MB RAM，現行單機 Redis 足以輕鬆承載數萬份履歷。若擴展至百萬級，可橫向分片（Redis Cluster）。
3. **非同步與演進 (Async / Evolution)**：切片與入庫解耦為 `IndexResumesUseCase`，未來可接入背景 Queue 非同步消化。
4. **成本與熔斷 (Cost & Circuit Breaker)**：Gemini 768 維 Embedding 成本極低（百萬 tokens 僅數美分），具備批次重試防護。
5. **可抽換性 (Portability & Decoupling)**：透過 `IVectorStore` 與 `IEmbeddingService` 介面隔離，若未來需遷移至 Qdrant 或 Milvus，Domain 與 Use Case 零改動。
