# ADR-0006: Token 消耗最佳化、增量指紋入庫與切片語意合併

## 1. 狀態
已採納 (Accepted) - 2026-11

---

## 2. 背景與問題陳述 (Context & Problem Statement)
在履歷批次轉換為 Markdown 並存入 Redis 向量資料庫的流程中，原系統在執行時存在顯著的無效 Token 浪費：
1. **全量無條件向量化**：每次執行 `index_to_redis.py`，全量履歷（181 份共 2,600 個切片）均無條件重新調用 Gemini Embedding API，缺乏增量快取機制。
2. **切片破碎與上下文貧瘠**：切片器產生大量極短區塊（例如 <60 字元的聯絡資訊或單一畢業年份），造成切片數量虛高，並引入向量檢索雜訊。
3. **健康 PDF 圖片渲染濫用**：在 `AUTO` 模式下，文字層健全的 PDF 仍預設渲染為 150 DPI 高解析度圖片走多模態 Vision 輸入，消耗 2~4 倍 Token 且有 OCR 錯字風險。

---

## 3. 評估選項 (Options Evaluated)
* **選項 A：維持現狀，依賴外部調度器控制呼叫頻率**
  - 優點：代碼零變更。
  - 缺點：無法解決重複執行時 99% 的無謂費用浪費與 API 配額耗盡 (429) 風險。
* **選項 B：建立 Content-Hash 增量指紋、智慧切片合併與 Text-First 轉換管線 (採納)**
  - 優點：未變更檔案零 API 調用（耗時自數十秒降至數百毫秒）；切片量精簡 >23% 且檢索語意密度顯著提升；健康文字 PDF 節省 60%~80% 轉檔輸入 Token。
  - 缺點：需在 Redis 儲存候選人與切片 Hash 指紋，需增加 `--force` 強制更新引數。

---

## 4. 架構決策 (Decision Outcome)
決定採納 **選項 B**，嚴格遵循 Clean Architecture 與 DDD 規範：
1. 在 `IVectorStore` 抽象新增候選人指紋查詢與設定契約；
2. 在 `IndexResumesUseCase` 實作 SHA-256 增量快取比對；
3. 在 `MarkdownChunker` 實作過短切片智慧合併，同時嚴格保持相異領域大綱類別（如 SKILLS vs EDUCATION）的結構隔離；
4. 在 `ConvertDocumentUseCase` 中對健康文字 PDF 落實 Text-First 策略，並保留 Vision 異常降級安全防線；
5. 在多 Agent 協調閉環建立 5 大能效防禦牆：Step 6 三振熔斷機制（最多嘗試 3 輪）、Subagent 階梯式模型指派（機械任務強制 Flash）、最小上下文隔離、Artifact-First 共享黑板與通訊去客套化。

---

## 5. 8 大架構審查維度評估 (Architecture Review Analysis)
1. **個資隱私 (PII)**：Hash 僅採用單向 SHA-256 摘要，無明文個資外洩風險。
2. **容量與極限 (Capacity)**：Redis 僅需儲存輕量 SHA-256 指紋字串（<200KB），合併後總切片數減少 23% 反而釋放記憶體。
3. **非同步與演進 (Async / Evolution)**：增量比對由 Use Case 無狀態調度，原生相容未來分散式 Worker。
4. **成本與熔斷 (Cost & Circuit Breaker)**：重複入庫 API 調用降為 0，徹底杜絕 429 配額用罄風險。
5. **可抽換性 (Portability & Decoupling)**：Domain 抽象保持純潔，對上層完全透明。
6. **惡意輸入與配額硬上限 (Input Security & Bomb Defense)**：保留 25MB 硬上限與安全圍欄。
7. **向量索引演進與藍綠遷移 (Index Evolution & Migration)**：Hash 欄位向後相容既有 `idx:resumes:v1` Schema。
8. **分散式併發與全鏈路可觀測性 (Concurrency & Observability)**：入庫回傳結果明確區分 `indexed_files` 與 `skipped_files`。
