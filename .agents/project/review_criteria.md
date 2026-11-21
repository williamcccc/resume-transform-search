# Gate 2 代碼審查：本專案檢核項 (Project Review Criteria)

> **定位**：**專案實例檔**。Gate 2 的通用規則與嚴重等級定義，以核心檔 [review_checklist.md](../skills/code-review/references/review_checklist.md) 為準；本檔只記錄**本專案**特有的檢核項、數值、標籤名稱與舉例，類別編號與核心檔一致。Gate 2 審查時兩者並用。
> **移植**：搬到其他專案時整份替換為新專案內容（可先只留類別標題，隨首次審查補齊），見 [PORTING.md](../PORTING.md)。
> **來源**：[Spec-0036](../../docs/specs/0036-portable-review-checklist-spec.md)（原核心檔之本專案內容移入）。

---

### 1. 架構邊界與依賴原則
- [ ] **[P0] Domain 純潔性（本專案外部套件）**：Domain 層嚴禁 import `google-genai`、`fitz`、`docx`、`redis` 等外部套件。
- [ ] **[P0] 表現層獨立性（本專案進入點）**：CLI（`convert_to_md.py` 等）只能負責解析命令列參數與調度 Use Case，嚴禁包含轉檔、向量運算等核心業務邏輯。

### 2. 安全性與惡意輸入防護
- [ ] **[P0] 資源配額硬上限（數值正本）**：解析檔案前必須驗證檔案體積（預設上限 25MB）、PDF 頁數上限（預設 30 頁）與 DOCX 解壓縮膨脹比（預設 10x），杜絕 Zip Bomb 或巨型檔案造成記憶體耗盡（OOM）。*（本處為上限數值的文件正本；括號內為預設值，實際值以 `.env.example` 與 `AppConfig` 為準。）*
- [ ] **[P0] 提示詞注入隔離（本專案圍欄標籤）**：傳送給 LLM（Gemini）之未受信任履歷內容（含履歷原文、PDF 提取文字），必須使用 `<resume_content>...</resume_content>` 標籤進行上下文圍欄隔離，並在 System Prompt 強調不得遵從履歷內之指示。同名標籤亦列於 `project.toml` 的 `guardrails.prompt_indicators`。
- [ ] **[P0] 日誌零洩漏（本專案敏感資料）**：日誌嚴禁明文輸出未經脫敏的敏感資料（類型見 [profile.md](./profile.md) 第 4 節）或 API Authorization Header。

### 3. 防禦性程式設計與邊界容錯
- [ ] **[P0] 原始檔案保護原則**：轉檔或修復時，絕不可直接覆寫或篡改磁碟上的原始輸入檔案（如 Docx 破圖需採用記憶體串流修復）。對應 AGENTS.md 紅線 3。
- [ ] **[P0] 資源生命週期（本專案物件）**：PDF Document 物件、Docx 串流必須使用 `with` Context Manager，根除 Windows 下 `PermissionError: [WinError 32]` 檔案鎖死隱患。
- [ ] **[P1] API 故障隔離（Gemini）**：呼叫外部 Gemini API 時，必須妥善處理 `429 (Rate Limit)`、`配額耗盡` 與 `FinishReason.RECITATION (版權背誦安全攔截)`。嚴禁在命中安全攔截或配額用罄時盲目重試造成無限迴圈或情境漂移。
- 例外捕獲舉例：`KeyError`、`ResponseError`。

### 4. 冪等性、索引演進與併發
- [ ] **[P0] 資料庫操作冪等性（Redis）**：Redis 向量索引入庫前，必須先清除該候選人的舊切片資料（以候選人名稱為鍵模式清除舊 Hash），避免重跑時資料堆疊污染。
- [ ] **[P1] 轉檔產出冪等性**：產出 Markdown 與隔離檔案（Quarantine）應有一致的覆寫或版本管理邏輯，轉檔失敗需自動清理或移入隔離區。
- [ ] **[P1] 向量索引平滑遷移相容 (Index Evolution)**：Redis 向量索引定義與鍵前綴應具備版本識別（如 `idx:resumes:v1`），便於未來進行藍綠雙索引切換。
- 追蹤識別碼舉例：文件處理過程之 `trace_id` / `doc_id` 貫穿日誌與品質檢驗報告。

### 5. 代碼品質與測試防護
- [ ] **[P0] 測試獨立性（本專案外部服務）**：單元測試必須 100% 透過 Mock 隔離真實 Gemini API 與真實 Redis。
- 故障注入舉例：網路超時、檔案毀損、API 429 配額用罄。

### 6. 外部呼叫成本（本專案 LLM 與向量化）
- [ ] **[P0] 重複執行零 Token 增量防線**：批次向量化或轉檔必須具備內容 Hash 指紋比對，未變更資料重複執行時嚴禁重新呼叫 LLM/Embedding API。
- [ ] **[P0] 模態決策合理性 (Text-First 優先)**：健康且可提取純文字層的文件，嚴禁無條件渲染為高解析度圖片走多模態 Vision API，避免 2~4 倍 Token 浪費與 OCR 錯字風險。對應 AGENTS.md 紅線 5。
- [ ] **[P1] 切片語意密度門檻**：切片器必須包含過短微小切片智慧合併機制，嚴禁產生大量低於門檻（如 80 字元）的空泛零碎切片。
- [ ] **[P1] 對話上下文膨脹防護**：多輪對話嚴禁無謂累積重複圖片或整篇歷史長文；自我審核修復優先採用局部修補 (Patch-only) 而非全文強制重新輸出。

### 7. 配置管理與零硬編碼
- 連線 URL 舉例：`redis://`、`postgres://`、`http://`；設定模組為 `AppConfig`。
- 須可由環境變數覆寫之本專案閥值：檔案大小、頁數、膨脹比、DPI、重試退避、切片上下限、保留率、HNSW 參數。

### 8. 提示詞資產化與治理
- [ ] **[P0] 提示詞資產位置**：所有 LLM Prompt（包括 System Prompt、文件轉檔、Self-Review、LLM Judge 等）必須 100% 抽離至專案根目錄 `prompts/*.md`，透過 `load_prompt()` 快取載入與依賴注入管理。
- [ ] **[P1] Prompt 檔案完整度單元測試**：新增或微調的提示詞檔案，必須有單元測試（如 `test_prompt_loader.py`）驗證該檔案存在、語法有效且快取正常。
- 提示詞範例禁用：源自真實履歷案例之特定企業名稱（錯字校正與結構範例一律使用通用軟體工程術語，防止誘導模型產生特定公司幻覺）。

### 9. Git 版控衛生與零個資
- [ ] **[P0] 零真實個資與真實履歷檔名殘留**：全面檢視原始碼、FastAPI Query/Body `description`、CLI `--help` (`epilog`)、單元測試、E2E 測試與 `docs/` 文檔，確認零真實求職者姓名、真實聯絡方式或真實履歷檔名（一律使用如 `王小明`、`sample_resume.md` 等虛構通用範例）。
- [ ] **[P0] 單元測試零外部樣本檔依賴（本專案）**：`tests/unit/` 嚴禁 glob 或讀取本機 `data/`、`resume/` 下之真實檔案，所有測試夾具（如 Word 破圖 `.rels`、PDF 混淆字型）必須 100% 於記憶體動態建構（`BytesIO` / `Mock`）。
