# ADR-0007: Twelve-Factor 全盤環境變數提取與配置治理

## 1. 狀態
已採納 (Accepted)

## 2. 背景與問題陳述 (Context & Problem Statement)
在系統演進至多模態文件轉檔與履歷向量檢索雙軌架構後，組件間散落了多項硬編碼常數，包含：
1. **轉檔安全與配額**：25MB 檔案上限、30 頁 PDF 配額、10.0x DOCX 解壓膨脹比、150 DPI。
2. **外部網路彈性**：外部 API 固定的 3 次重試、2.0 秒退避延遲。
3. **向量資料庫與檢索**：Redis 實例位址、測試庫隔離、1500 字元切片上限、768 向量維度、Top-5 搜尋等。

若將這些參數硬編碼在代碼中，將違反 The Twelve-Factor App（第 III 條：在環境中儲存配置）原則，且無法靈活因應容器化、測試環境隔離（如 DB 15）及生產多節點切換。

## 3. 評估選項 (Options Evaluated)
* **選項 A：保留代碼預設值，僅提取核心連線字串至 `.env`**
  - 優點：改動小。
  - 缺點：無法在不同環境（如 CI/CD、高並發環境）靈活微調配額與重試策略，仍有環境污染與維護死角。
* **選項 B：全盤提取至 Twelve-Factor `.env`，透過 `AppConfig` 統一載入，組件採用依賴注入 (DIP)**
  - 優點：
    1. 100% 遵循整潔架構，外層技術細節與數值完全不污染 Domain / UseCase 抽象。
    2. 具備 `_safe_int` / `_safe_float` 容錯解析機制，在環境變數缺失或格式異常時平穩退回預設值。
    3. 測試環境與生產環境徹底隔離（例如 QA 實測使用獨立 `REDIS_TEST_URL` DB 15，防範生產庫 DB 0 污染）。
  - 缺點：需要對 Readers、UseCase 建構子及 CLI 工廠函式進行系統性重構。

## 4. 架構決策 (Decision Outcome)
採納 **選項 B**。
1. 在 `src/infrastructure/config.py` 中定義 `AppConfig` 資料模型與安全解析器。
2. 在 `ConvertDocumentUseCase`、`PdfRenderer`、`PdfTextReader`、`DocxReader`、`retry_call`、`MarkdownChunker`、`RedisVectorStore` 等組件中實施構造注入。
3. 更新 `.env` 與 `.env.example`，將 17 項參數以清晰分區結構規範呈現。

## 5. 8 大架構審查維度評估 (Architecture Review Analysis)
1. **個資隱私 (PII)**：環境變數嚴禁明文記錄履歷內容，敏感金鑰（`GEMINI_API_KEY`）自原始碼徹底解耦。
2. **容量與極限 (Capacity)**：可透過 `MAX_FILE_SIZE_MB` 與 `MAX_PDF_PAGES` 在不同硬體節點動態調控記憶體防線。
3. **非同步與演進 (Async / Evolution)**：`AppConfig` 為無狀態物件，利於未來 Web API (FastAPI) 多實例共用。
4. **能耗與 Token (Token Economics)**：透過 `PDF_RENDER_DPI` 與 `MAX_CHUNK_SIZE` 精確調控視覺與文字 Token 消耗。
5. **可觀測性 (Observability)**：CLI 啟動時完整揭露當前連線節點、維度與切片門檻，便於稽核排錯。
6. **成本與計費 (Cost & Billing)**：支援調降重試次數（`API_MAX_RETRIES`）以避免惡意網路震盪下的無效 API 扣款。
7. **彈性與容錯 (Resilience)**：提供指數退避與多重 fallback，環境變數型別錯誤時系統零崩潰。
8. **安全性與防護 (Security)**：DOCX Zip Bomb 與 PDF 頁數硬上限可動態依資安等級微調收緊。
