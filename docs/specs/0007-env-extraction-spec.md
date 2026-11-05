# PRD 與 Tech Spec：全盤硬編碼參數提取至 .env 與 Twelve-Factor App 治理

## 1. 業務背景與目標 (PRD)

### 1.1 背景
系統先前已成功將 Redis URL、Gemini 模型、向量索引、品質閥值與測試隔離庫提取至 `.env`。然而經深度代碼探測，在文件轉檔管道、安全配額防護、API 重試機制、向量切片與語意搜尋中，仍存在若干硬編碼常數（如 25MB 上限、30 頁 PDF 配額、10.0x DOCX 膨脹比、150 DPI、3 次重試、1500 字元上限、768 維度、Top-5 搜尋等）。

### 1.2 目標
1. **Twelve-Factor App 100% 遵循**：所有控制閥、安全門檻、網路策略與維度參數皆可由環境變數配置。
2. **向下相容與安全兜底**：若環境變數未提供或內容格式錯誤，系統維持原預設值平穩運作，絕不因缺失或型別異常崩潰。
3. **依賴注入 (DIP) 落地**：各層組件（Use Case、Readers、Stores、Chunker）透過構造式參數注入配置，禁止直接向底層 hardcode。

---

## 2. 參數提取與重構規格清單 (Tech Spec)

| 參數名稱 | 預設值 | 適用組件 | 責任歸屬 | 預期功能 |
| :--- | :--- | :--- | :--- | :--- |
| `MAX_FILE_SIZE_MB` | `25` | `ConvertDocumentUseCase` | 資源配額 | 防止超大檔案耗盡伺服器記憶體 |
| `MAX_PDF_PAGES` | `30` | `PdfRenderer`, `PdfTextReader` | DoS 防護 | 防範超長 PDF 導致視覺渲染與 Token 爆炸 |
| `MAX_DOCX_EXPANSION_RATIO` | `10.0` | `DocxReader` | Zip Bomb 防禦 | 防範高壓縮比 Word 炸彈攻擊 |
| `PDF_RENDER_DPI` | `150` | `ConvertDocumentUseCase`, `PdfRenderer` | 能效與品質 | 控制多模態影像渲染解析度與 Token 消耗 |
| `API_MAX_RETRIES` | `3` | `retry_call` (utils.py) | 網路韌性 | 呼叫外部 API 失敗時最大自動重試次數 |
| `API_RETRY_DELAY` | `2.0` | `retry_call` (utils.py) | 網路韌性 | 外部 API 重試退避基礎秒數 |
| `MAX_CHUNK_SIZE` | `1500` | `MarkdownChunker`, `index_to_redis.py` | 切片粒度 | Markdown 語意切片的最大字元長度 |
| `EMBEDDING_DIM` | `768` | `GeminiEmbeddingService`, `RedisVectorStore`, `search_resumes.py` | 向量幾何 | 向量維度一致性管理 |
| `SEARCH_DEFAULT_TOP_K` | `5` | `search_resumes.py` | 搜尋體驗 | 向量檢索預設回傳之切片數量 |

---

## 3. 架構實施設計 (Implementation Plan)

### 3.1 基礎設施層 (Infrastructure)
1. `src/infrastructure/config.py`：
   - 已完成 `AppConfig` 結構體擴充與 `_safe_int`, `_safe_float` 容錯解析函式。
2. `src/infrastructure/readers/`：
   - `pdf_renderer.py`：`PdfRenderer.__init__(max_pages: int = 30)`，並在 `render_pages_to_png` 使用 `self.max_pages`。
   - `pdf_text_reader.py`：`PdfTextReader.__init__(max_pages: int = 30)`，並在 `extract_text` 使用 `self.max_pages`。
   - `docx_reader.py`：`DocxReader.__init__(max_expansion_ratio: float = 10.0)`，並傳遞至 `_validate_docx_zip_safety`。
3. `src/infrastructure/transformers/utils.py`：
   - 已完成動態環境變數讀取。

### 3.2 應用層 (Application)
1. `src/application/convert_document_use_case.py`：
   - `ConvertDocumentUseCase.__init__` 新增 `max_file_size_mb: int = 25`, `pdf_render_dpi: int = 150`。
   - 將全域常數 `MAX_FILE_SIZE` 替換為可配置實例屬性 `self.max_file_size_bytes`。
   - 渲染 PDF 頁面時改用 `self.pdf_render_dpi`。
2. `src/application/index_resumes_use_case.py`：
   - 支援將 `dim` 傳遞至 `ensure_index`。

### 3.3 表現層與 CLI 入口 (Interfaces)
1. `src/interfaces/cli/runner.py`：
   - 在 `build_use_case` 工廠中將 `config.max_pdf_pages`, `config.max_docx_expansion_ratio`, `config.max_file_size_mb`, `config.pdf_render_dpi` 注入 Readers 與 UseCase。
2. `search_resumes.py`：
   - 預設 `--top` 讀取 `config.search_default_top_k`。
   - Embedding 初始化傳入 `config.embedding_dim`。
3. `index_to_redis.py`：
   - `MarkdownChunker` 傳入 `config.max_chunk_size`。
   - `GeminiEmbeddingService` 與 `ensure_index` 傳入 `config.embedding_dim`。

### 3.4 配置範本同步
- 更新 `.env` 與 `.env.example`，將新參數納入標準分區註解。

---

## 4. QA 驗收測試矩陣 (QA Acceptance Criteria)

| 編號 | 測試案例 | 驗證項目 | 預期結果 |
| :--- | :--- | :--- | :--- |
| **TC-ENV-01** | `test_app_config.py` | 驗證新參數之純預設值與環境變數覆寫 | 預設值 100% 吻合；覆寫值精準載入 |
| **TC-ENV-02** | `test_convert_document_use_case.py` | 注入自訂 `max_file_size_mb=1`，傳入 2MB 檔案 | 觸發 `FileQuotaExceededError` |
| **TC-ENV-03** | `test_pdf_renderer.py` | 注入自訂 `max_pages=2`，渲染 3 頁 PDF | 觸發 `FileQuotaExceededError` |
| **TC-ENV-04** | `test_docx_reader.py` | 注入自訂 `max_expansion_ratio=2.0` | 正確防禦超標檔案 |
| **TC-ENV-05** | AST 靜態稽核 | 掃描核心代碼有無殘留硬編碼常數 | `audit_guardrails.py` 通過 |
| **TC-ENV-06** | E2E 整合驗證 | 透過 CLI 執行檢索與索引流程 | 正常運作且不拋出未預期異常 |
