# 文檔雙向同步檢核清單 (Documentation Sync Checklist)

在宣告任務交付（Step 7 結束）前，必須逐項對照本清單進行檢查，確認零文檔債：

---

### 一、REQUIREMENTS.md 同步檢核
- [ ] **CLI 入口命令同步**：所有新增或變更的命令列參數（如 `--review`, `--index-to-redis`, `--output-dir`）是否已登載至 `REQUIREMENTS.md`？
- [ ] **參數預設值與型別標註**：每個參數的型別（String, Flag, Integer）與預設行為是否說明清晰？
- [ ] **業務需求狀態**：PRD 中定義的本次功能是否已納入「已實作功能矩陣」？
- [ ] **CLI 使用範例更新**：文檔中的命令列操作範例是否經測試可實際執行？

---

### 二、ARCHITECTURE.md 同步檢核
- [ ] **DDD 四層邊界維持**：新增之模組是否被精準分類至 Domain / Application / Infrastructure / Interfaces 四層？
- [ ] **Domain 實體與 Value Objects**：新增或擴充的資料欄位（如 ChunkType, QualityReport）是否已反映於架構文檔的類別圖或資料結構章節？
- [ ] **Protocol 協定介面**：新增的 IVectorStore、IQualityValidator 或 IEmbeddingService 介面是否已記錄於依賴反轉說明中？
- [ ] **Mermaid 流程圖/時序圖同步**：系統的 Use Case 流程圖或兩階段處理時序圖是否更新？（確保無語法錯誤且與程式碼一致）

---

### 三、docs/adr/ 架構決策紀錄同步檢核
- [ ] **狀態正規化**：已落地的 ADR 狀態是否已由 `提案中 (Proposed)` 正式變更為 **`已採納 (Accepted)`**？
- [ ] **編號連續性**：ADR 檔名是否依循 `XXXX-kebab-case.md` 連續編號命名？
- [ ] **索引表格同步**：[`docs/adr/README.md`](../../../../docs/adr/README.md) 的索引表格是否已新增該 ADR 條目（包含編號、標題、狀態、日期、技術標籤）？
- [ ] **8 大維度完整度**：ADR 是否完整包含 8 大架構審查維度的分析結論？

---

### 四、自動化驗證執行
- [ ] **執行驗證腳本**：
  ```bash
  python .agents/skills/doc-sync/scripts/verify_doc_sync.py
  ```
  回傳值為 `0` 且無任何報錯。
