# PRD 與 Tech Spec：類別 A/B 擴充參數提取至 .env 與 Prompt Engineering 獨立版控

## 1. 業務背景與目標 (PRD)

### 1.1 背景
系統已成功提取第一階段 17 項核心設定。經代碼深度稽核，系統仍有 10 項底層策略與演算法參數（包含 Redis 指紋前綴、DOCX 未壓縮上限、OCR DPI、評分卡預設目錄、HNSW 索引拓撲參數、品管保留率範圍、Text-First 門檻）散落在實作中。
同時，`SELF_REVIEW_PROMPT` 與 `JUDGE_SYSTEM_PROMPT` 等關鍵提示詞以長字串形式內嵌於 Python 程式碼，阻礙了提示詞工程（Prompt Engineering）的獨立調優、版本對比與審查。

### 1.2 目標
1. **Prompt 檔案化與 Git 版本控管**：將所有核心提示詞自程式碼抽離，移至 `src/infrastructure/prompts/*.md`，享受純淨的 Markdown 語法高亮、獨立 Git Diff 檢閱與熱插拔覆寫能力。
2. **類別 A (4項) 與 類別 B (6項) 完整提取**：
   - 擴充 `AppConfig` 屬性與容錯解析。
   - 透過依賴注入（DIP）傳遞至 Use Case、Readers、Stores 與 Validators。
3. **向下相容與防禦兜底**：若 Prompt 檔案遺失或環境變數異常，具備內建 fallback 字串與預設值，確保系統絕不中斷。

---

## 2. 參數提取清單 (Tech Spec)

| 參數名稱 | 類型 | 預設值 | 適用組件 | 責任說明 |
| :--- | :---: | :--- | :--- | :--- |
| `REDIS_HASH_PREFIX` | A | `"resume:v1:hash:"` | `RedisVectorStore` | 內容 Hash 指紋快取鍵前綴，保障多租戶隔離 |
| `MAX_DOCX_UNCOMPRESSED_MB` | A | `100` | `DocxReader` | DOCX 解壓縮後的實體記憶體總上限 (MB) |
| `PDF_OCR_DPI` | A | `200` | `ConvertDocumentUseCase` | 降級至 RapidOCR 本機辨識時之影像解析度 |
| `DEFAULT_SCORECARD_DIR` | A | `None` | `runner.py` | 獨立評判員評分卡 JSON 預設儲存目錄 |
| `REDIS_HNSW_M` | B | `16` | `RedisVectorStore` | RediSearch HNSW 向量圖節點連接數 |
| `REDIS_HNSW_EF_CONSTRUCTION`| B | `200` | `RedisVectorStore` | HNSW 索引建置遍歷搜尋深度 |
| `REDIS_DISTANCE_METRIC` | B | `"COSINE"` | `RedisVectorStore` | 向量相似度度量（COSINE / IP / L2） |
| `QUALITY_MIN_RETENTION_RATIO`| B | `0.35` | `MarkdownQualityValidator` | 確定性品管閥之篇幅保留率下限 (35%) |
| `QUALITY_MAX_RETENTION_RATIO`| B | `3.5` | `MarkdownQualityValidator` | 確定性品管閥之篇幅膨脹率上限 (350%) |
| `PDF_TEXT_FIRST_MIN_CHARS` | B | `50` | `ConvertDocumentUseCase` | 健康文字 PDF 走 Text-First 門檻字數 |

---

## 3. Prompt Engineering 獨立檔案化架構

```
src/infrastructure/prompts/
├── __init__.py           # Prompt 載入器 (支援路徑解析與兜底 fallback)
├── vision_convert.md     # 多模態初稿轉換提示詞
├── self_review.md        # 兩階段自我審核與自動修復提示詞
└── judge_system.md       # 獨立評判員 (LLM-as-a-Judge) 評分卡提示詞
```

- 組件 `GeminiTransformer` 與 `GeminiLlmJudge` 透過 `load_prompt(...)` 載入，並支援構造參數自訂提示詞路徑，便於 A/B Testing。

---

## 4. QA 驗收測試矩陣 (Acceptance Criteria)

| 編號 | 測試案例 | 驗證項目 | 預期結果 |
| :--- | :--- | :--- | :--- |
| **TC-ENV2-01** | `test_app_config.py` | 驗證 10 項新參數之預設值與自訂覆寫 | 100% 精準載入，型別正確 |
| **TC-ENV2-02** | `test_prompt_loader.py` | 驗證 Prompt 檔案載入與 fallback 機制 | 正確讀取 `.md` 檔案內容 |
| **TC-ENV2-03** | `test_quality_validator.py` | 自訂 `min_retention_ratio` / `max_retention_ratio` | 依自訂門檻正確判定扣分與通過 |
| **TC-ENV2-04** | `test_redis_vector_store.py`| 自訂 `HNSW_M`, `EF_CONSTRUCTION`, `HASH_PREFIX` | 索引建立 schema 參數完全吻合 |
| **TC-ENV2-05** | AST 代碼稽核 | 執行 `audit_guardrails.py` | 零 P0/P1 違規，架構邊界純潔 |
| **TC-ENV2-06** | E2E 整合驗證 | 執行端到端與 CLI 實測 | 流程順暢無拋出異常 |
