# 履歷向量化與 Redis 索引架構指南 (Resume Vector Indexing Guide)

本手冊為 `resume-vector-indexing` 技能的參考文檔，詳細說明向量化入庫的架構規範、指令語法、常見故障排除與後續檢索驗證。

---

## 1. 向量儲存與切片架構規範

系統採用 **RediSearch** 模組與 **HNSW** 向量索引演算法：

* **索引識別碼 (Index Name)**：`idx:resumes:v1`（具備藍綠遷移版本號）
* **鍵前綴 (Key Prefix)**：`resume:v1:chunk:<candidate_id>:<chunk_idx>`
* **資料結構 (Storage Type)**：Redis HASH
* **向量維度 (Vector Dimensions)**：768 維 (FLOAT32)
* **距離度量演算法 (Distance Metric)**：Cosine (餘弦相似度)
* **嵌入模型 (Embedding Model)**：預設 `gemini-embedding-001`（支援批次 20 筆向量化）
* **資料庫操作冪等性 (Idempotency)**：入庫前自動調用 `delete_by_candidate` 清除該候選人的既有切片，重複執行不會造成切片堆疊。

---

## 2. 核心 CLI 指令速查 (`index_to_redis.py`)

根目錄的 [`index_to_redis.py`](../../../../index_to_redis.py) 為主要入庫進入點：

```bash
# 1. 索引目錄下所有 Markdown 檔案 (遞迴遍歷子目錄)
python index_to_redis.py data/markdown_out/

# 2. 強制重建 RediSearch 向量索引 (清除舊索引定義重新建立)
python index_to_redis.py data/markdown_out/ --recreate

# 3. 指定遠端或自訂 Redis 位址
python index_to_redis.py data/markdown_out/ --redis-url redis://localhost:6379/0

# 4. 指定 API Key 與 Embedding 模型
python index_to_redis.py data/markdown_out/ --api-key AIzaSy... --model gemini-embedding-001

# 5. 限制處理檔案數量上限 (例如前 10 份)
python index_to_redis.py data/markdown_out/ --limit 10

# 6. 索引單一 Markdown 履歷檔案
python index_to_redis.py data/markdown_out/BE/sample_resume.md

```

---

## 3. 前置條件與相依服務檢核

在執行向量入庫前，必須滿足以下條件：

1. **Redis 伺服器已啟動**：
   - 預設連線為 `redis://localhost:6379/0`。
   - 伺服器必須載入 **RediSearch** 模組（Redis Stack 或包含 `search` 引擎）。
2. **Gemini API 金鑰配置**：
   - 專案根目錄 `.env` 檔案內必須包含 `GEMINI_API_KEY=AIzaSy...`。
   - 或於 CLI 命令列帶入 `--api-key` 參數。
3. **Markdown 檔案存在**：
   - 確認目標目錄（`resume/markdown_out` 或 `data/markdown_out`）內有轉換完成的 `.md` 檔案。

---

## 4. 故障排除與常見錯誤處理 (Troubleshooting)

### 問題 1: `ConnectionError: Error connecting to localhost:6379`
* **根因**：本地 Redis 服務未啟動或連線埠不符。
* **對策**：
  - Windows 環境確認 Docker Desktop 容器是否啟動：`docker run -d -p 6379:6379 redis/redis-stack:latest`
  - 或透過 `--redis-url` 指定正確的 Redis 節點位址。

### 問題 2: `429 RESOURCE_EXHAUSTED (Quota Exceeded)`
* **根因**：Google Gemini Embedding API 每日免費額度已達上限。
* **對策**：
  - 更換具備充足配額的 API Key。
  - 或更換 Google AI Studio Pay-as-you-go 計費專案。

### 問題 3: `Unknown index name` 或重建索引衝突
* **根因**：索引定義與舊版本不相容。
* **對策**：
  - 加入 `--recreate` 引數，系統會自動呼叫 `ft.dropindex(delete_documents=False)` 並重新建立乾淨的 HNSW 索引。

---

## 5. 入庫後之語意檢索驗證 (`search_resumes.py`)

向量化入庫完成後，可使用 [`search_resumes.py`](../../../../search_resumes.py) 驗證檢索效果：

```bash
# 1. 自然語言查詢測試
python search_resumes.py "三年以上 Go 與分散式高併發後端"

# 2. 結合技術標籤與區段過濾
python search_resumes.py "設計過金流微服務" --type experience --skills golang,redis

# 3. 依候選人歸併整合呈現
python search_resumes.py "熟悉 Kubernetes 容器編排架構" --group --top 5
```
