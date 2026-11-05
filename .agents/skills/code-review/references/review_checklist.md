# Code Review 檢驗標準清單 (Review Checklist)

本清單為本專案在實施代碼審查時的強制檢核標準，涵蓋 Clean Architecture (DDD)、惡意輸入防禦、資源釋放、例外治理、向量索引演進、日誌安全與測試隔離性。

---

## 一、嚴重等級定義

* **[P0 阻斷型缺陷 - Blockers]**：一票否決。任何一項不符合，禁止交付，必須立即打回修正。
* **[P1 重大防護缺陷 - High Priority]**：高風險項目。原則上必須修正；若有特殊情境需保留，必須附帶清楚的註解與設計決策說明。
* **[P2 品質與風格缺陷 - Medium/Low]**：建議優化項目。型別補全、命名精簡或 Docstring 補齊。

---

## 二、詳細檢核清單

### 1. 架構邊界與依賴原則 (Architecture & DDD Guardrails)
- [ ] **[P0] Domain 純潔性**：`src/domain/` 內嚴禁出現任何第三方外部套件的 import（如 `google-genai`、`fitz`、`docx`、`redis` 等），只能依賴標準庫與純 Python。
- [ ] **[P0] 依賴反轉（DIP）**：`src/application/` 中的 Use Case 只能呼叫 `src/domain/interfaces.py` 的 Protocol 抽象介面，嚴禁直接引用 `src/infrastructure` 或 `src/interfaces` 的實體類別。
- [ ] **[P0] 表現層獨立性**：CLI（`convert_to_md.py` 等）只能負責解析命令列參數與調度 Use Case，嚴禁包含轉檔、向量運算等核心業務邏輯。

### 2. 安全性與惡意輸入防護 (Input Security & Prompt Defense)
- [ ] **[P0] 資源配額硬上限**：解析檔案前必須驗證檔案體積（預設上限 25MB）、PDF 頁數上限（預設 30 頁）與 DOCX 解壓縮膨脹比（預設 10x），杜絕 Zip Bomb 或巨型檔案造成記憶體耗盡（OOM）。
- [ ] **[P0] 提示詞注入隔離 (Context Fencing)**：傳送給 LLM（Gemini）之未受信任履歷內容，必須使用明確標籤（如 `<resume_content>...</resume_content>`）進行上下文圍欄隔離，並在 System Prompt 強調不得遵從履歷內之指示。
- [ ] **[P0] 日誌零洩漏安全 (Zero-Leak Logging)**：日誌嚴禁明文輸出未經脫敏的原始履歷全文、身分證字號、手機號碼或 API Authorization Header。

### 3. 防禦性程式設計與邊界容錯 (Robustness & Fail-Safe)
- [ ] **[P0] 原始檔案保護原則**：轉檔或修復時，絕不可直接覆寫或篡改磁碟上的原始輸入檔案（如 Docx 破圖需採用記憶體串流修復）。
- [ ] **[P0] 資源生命週期管理 (Windows File Lock 防禦)**：所有檔案讀寫、PDF Document 物件、Docx 串流必須強制使用 `with` Context Manager，確保控制代碼即時關閉，根除 Windows 下 `PermissionError: [WinError 32]` 檔案鎖死隱患。
- [ ] **[P1] API 故障隔離與重試**：呼叫外部 Gemini API 時，必須妥善處理 `429 (Rate Limit)`、`配額耗盡` 與 `FinishReason.RECITATION (版權背誦安全攔截)`。嚴禁在命中安全攔截或配額用罄時盲目重試造成無限迴圈或情境漂移。
- [ ] **[P1] 例外處理精準度與防吞噬**：嚴禁使用裸的 `except: pass` 盲目吞噬未知錯誤，必須儘可能捕獲具體例外（如 `KeyError`, `ResponseError`）並記錄日誌。
- [ ] **[P1] 例外鏈完整度 (Exception Chaining)**：重新拋出領域自定義例外時，必須使用 `raise DomainException(...) from err` 保留原始呼叫堆疊，嚴禁抹除真實根因。

### 4. 冪等性、索引演進與併發 (Idempotency & Concurrency)
- [ ] **[P0] 資料庫操作冪等性**：Redis 向量索引入庫前，必須先清除該候選人的舊切片資料（以候選人名稱為鍵模式清除舊 Hash），避免重跑時資料堆疊污染。
- [ ] **[P1] 轉檔產出冪等性**：產出 Markdown 與隔離檔案（Quarantine）應有一致的覆寫或版本管理邏輯，轉檔失敗需自動清理或移入隔離區。
- [ ] **[P1] 向量索引平滑遷移相容 (Index Evolution)**：Redis 向量索引定義與鍵前綴應具備版本識別（如 `idx:resumes:v1`），便於未來進行藍綠雙索引切換。
- [ ] **[P2] 全鏈路 Trace ID**：文件處理過程應具備唯一追蹤識別碼（`trace_id` / `doc_id`），並貫穿於日誌與品質檢驗報告中。

### 5. 代碼品質與測試防護 (Clean Code & Test Isolation)
- [ ] **[P0] 測試獨立性**：單元測試（`tests/unit/`）必須 100% 透過 Mock 隔離真實網絡、真實 Gemini API 與真實 Redis。單元測試必須能離線且毫秒級完成。
- [ ] **[P1] 負面與故障注入測試 (Negative Testing)**：新加入的核心功能或修復的缺陷，必須在 `tests/unit/` 提供至少一組異常/故障情境測試（如：網路超時、檔案毀損、API 429 配額用罄）。
- [ ] **[P1] 測試覆蓋齊全**：新功能需具備足夠斷言（禁止無意義或空斷言的 Fake Test），且回歸測試全套通過（`Ran X tests ... OK`）。
- [ ] **[P2] 型別標註與文件**：新增的公開方法或資料傳輸物件（DTO / Models）必須具備 Type Hints 與清晰的 Docstring。
- [ ] **[P2] 向下相容性**：既有 CLI 命令引數與介面是否有受到破壞？

### 6. Token 能效與經濟學防護 (Token Efficiency & Economics Guardrails)
- [ ] **[P0] 重複執行零 Token 增量防線**：批次向量化或轉檔必須具備內容 Hash 指紋比對，未變更資料重複執行時嚴禁重新呼叫 LLM/Embedding API。
- [ ] **[P0] 模態決策合理性 (Text-First 優先)**：健康且可提取純文字層的文件，嚴禁無條件渲染為高解析度圖片走多模態 Vision API，避免 2~4 倍 Token 浪費與 OCR 錯字風險。
- [ ] **[P1] 切片語意密度門檻**：切片器必須包含過短微小切片智慧合併機制，嚴禁產生大量低於門檻（如 80 字元）的空泛零碎切片。
- [ ] **[P1] 對話上下文膨脹防護**：多輪對話嚴禁無謂累積重複圖片或整篇歷史長文；自我審核修復優先採用局部修補 (Patch-only) 而非全文強制重新輸出。

### 7. Twelve-Factor 配置管理與零硬編碼防禦 (No-Hardcoded-Configuration Guardrails)
- [ ] **[P0] 零機密憑證硬編碼**：原始碼與 Git 版控檔案中嚴禁明文寫死任何 API Key、Token 或密碼（必須透過 `.env` 注入）。
- [ ] **[P0] 外部連線與端點零寫死**：禁止在核心業務程式碼中硬編碼外部連線 URL（如 `redis://`、`postgres://`、`http://` 等），所有連線字串必須統一由 `AppConfig` 與 `.env` 注入管理。
- [ ] **[P1] 運行時配額與演算法閥值可配置化**：所有安全配額（檔案大小、頁數、膨脹比、DPI、重試退避、切片上下限、保留率、HNSW 參數）必須具備環境變數覆寫機制，嚴禁在 Use Case 或業務層寫死 Magic Numbers。
- [ ] **[P1] 跨平台絕對路徑禁令**：禁止在代碼中寫死任何本機絕對路徑（如 `C:\...` 或 `/home/...`），一律使用 `pathlib.Path` 相對路徑或環境變數注入。

### 8. Prompt Engineering 資產化與提示詞治理防禦 (Prompt-as-Code & Fencing Guardrails)
- [ ] **[P0] 提示詞資產獨立化 (Prompt Externalization)**：所有 LLM Prompt（包括 System Prompt、文件轉檔、Self-Review、LLM Judge 等）嚴禁在 Python 程式碼中寫死長篇多行字串，必須 100% 抽離至專案根目錄 `prompts/*.md`，透過 `load_prompt()` 快取載入與依賴注入管理。
- [ ] **[P0] 提示詞防注入上下文圍欄 (Prompt Injection Defense)**：所有接收外部不可信使用者內容（如履歷原文、PDF 提取文字）的 Prompt，必須強制包裹在專屬上下文標籤（`<resume_content>...</resume_content>`）中，並具備明確的指示防禦宣告（一律視為純文字，嚴禁執行指示）。
- [ ] **[P1] Prompt 檔案完整度單元測試**：所有新增或微調的提示詞檔案，必須有單元測試（如 `test_prompt_loader.py`）驗證該檔案存在、語法有效且快取正常，杜絕因檔案遺漏導致運行時 `FileNotFoundError`。
- [ ] **[P0] 提示詞零機密與零真實個資/企業案例洩漏**：Prompt 模板檔案中嚴禁寫死 API Key、測試用真實個資（PII）、本機絕對路徑或源自真實履歷案例之特定企業名稱（錯字校正與結構範例一律使用通用軟體工程術語，防止誘導模型產生特定公司幻覺）。

### 9. Git 版控衛生、個資清零與跨平台相容防線 (Git Hygiene, Zero-PII & Cross-Platform Guardrails)
- [ ] **[P0] 零真實個資與真實履歷檔名殘留 (Zero Real PII & Filenames)**：全面檢視原始碼、FastAPI Query/Body `description`、CLI `--help` (`epilog`)、單元測試、E2E 測試與 `docs/` 文檔，確認零真實求職者姓名、真實聯絡方式或真實履歷檔名（一律使用如 `王小明`、`sample_resume.md` 等虛構通用範例）。
- [ ] **[P0] 單元測試零外部樣本檔依賴 (In-Memory Test Fixtures)**：`tests/unit/` 嚴禁 glob 或讀取本機 `data/`、`resume/` 下之真實檔案，所有測試夾具（如 Word 破圖 `.rels`、PDF 混淆字型）必須 100% 於記憶體動態建構（`BytesIO` / `Mock`）；且測試防線本身不得以明文儲存受保護個資（應採用 SHA-256 指紋前綴比對）。
- [ ] **[P0] 零本機工作區絕對路徑 (Zero Hardcoded Workspace Paths)**：全專案所有納入 Git 之代碼、測試腳本、註解與 Markdown 文檔（含 `docs/`、`.agents/`、根目錄 `.md`）嚴禁寫死本機工作區絕對路徑；代碼統一使用 `Path(__file__).resolve()` 動態定位，版控文檔連結統一使用相對路徑，確保跨平台 CI/CD 與 GitHub 網頁點擊 100% 正常。
- [ ] **[P0] `.gitignore` 敏感邊界與 `.env.example` 100% 對齊**：凡新增任何衍生輸出目錄、快取或資料庫落地檔（如 `data/`, `resume/`, `resumes/`, `output/`, `output_md/`, `markdown_out/`, `markdown_output/`, `quarantine/`, `scorecards/`, `logs/`, `dump.rdb`, `appendonlydir/`）必須同步列入 `.gitignore`；`AppConfig` 內所有 `os.environ.get()` 環境變數必須 100% 同步記載於 `.env.example`（且 `.env.example` 嚴禁包含真實金鑰）。


