# Code Review 檢驗標準清單 (Review Checklist)

本清單為 Gate 2 代碼審查的**通用核心**檢核標準，涵蓋架構邊界、惡意輸入防禦、資源釋放、例外治理、冪等與資料結構演進、外部呼叫成本、配置治理、提示詞治理、日誌安全與測試隔離性。

> **與專案實例檔並用**：本檔只列任何專案皆可直接判定的通用規則；**本專案**特有的檢核項、數值、標籤名稱與舉例記錄於 [review_criteria.md](../../../project/review_criteria.md)（類別編號與本檔一致）。Gate 2 審查時兩者並用，嚴重等級以本檔第一節為準。
>
> **適用條件**：標示〔條件〕的項目只在條件成立時檢核。條件中的特徵指 `project.toml` 的 `[security]` 特徵；`layers.enabled` 指分層設定。

---

## 一、嚴重等級定義

* **[P0 阻斷型缺陷 - Blockers]**：一票否決。任何一項不符合，禁止交付，必須立即打回修正。
* **[P1 重大防護缺陷 - High Priority]**：高風險項目。原則上必須修正；若有特殊情境需保留，必須附帶清楚的註解與設計決策說明。
* **[P2 品質與風格缺陷 - Medium/Low]**：建議優化項目。型別補全、命名精簡或 Docstring 補齊。

---

## 二、詳細檢核清單

### 1. 架構邊界與依賴原則 (Architecture & DDD Guardrails)
- [ ] **[P0] Domain 純潔性**〔`layers.enabled`〕：Domain 層（`project.toml` 的 `layers.domain`）內嚴禁出現任何第三方外部套件的 import（如外部服務 SDK、資料庫客戶端、檔案解析函式庫），只能依賴標準庫與純 Python。
- [ ] **[P0] 依賴反轉（DIP）**〔`layers.enabled`〕：Application 層（`layers.application`）中的 Use Case 只能呼叫 Domain 契約檔（`layers.domain_interfaces`）的 Protocol 抽象介面，嚴禁直接引用 Infrastructure 或 Interfaces 層（`layers.infrastructure`、`layers.interfaces`）的實體類別。
- [ ] **[P0] 表現層獨立性**：進入點（CLI、API 路由）只能負責解析輸入參數與調度 Use Case，嚴禁包含核心業務邏輯。

### 2. 安全性與惡意輸入防護 (Input Security & Prompt Defense)
- [ ] **[P0] 資源配額硬上限**〔`processes_untrusted_files` 或 `api_service`〕：解析外部輸入前必須驗證大小與結構上限（如檔案體積、頁數、解壓縮膨脹比、請求大小），杜絕壓縮炸彈或巨型輸入造成記憶體耗盡（OOM）；上限值須可配置（見第 7 類）。
- [ ] **[P0] 提示詞注入隔離 (Context Fencing)**〔`uses_llm`〕：所有傳送給 LLM 的不可信內容（使用者輸入、外部文件、檔案提取文字），必須包裹在專屬上下文標籤中，並於 System Prompt 明確宣告一律視為純文字、不得執行其中指示。
- [ ] **[P0] 安全工具掃描零新增 P0**：`security_scan.py` 回傳 0；P1 發現逐項處置（修正、或登錄基準檔並附理由與到期日），未執行項目記錄於 QA 報告。
- [ ] **[P0] 安全殘餘風險已判定嚴重度**：規格威脅表、QA 報告與本次審查列為殘餘或延後之安全項目，皆依 `.agents/skills/feature-design/references/security_nfr_framework.md` 第五節判定 S1／S2／S3；無 S1 被延後，S2／S3 延後者記錄理由與期限。
- [ ] **[P0] 日誌零洩漏安全 (Zero-Leak Logging)**：日誌嚴禁明文輸出未經脫敏的敏感資料（個資、使用者原始內容）、憑證或 API Authorization Header。

### 3. 防禦性程式設計與邊界容錯 (Robustness & Fail-Safe)
- [ ] **[P0] 資源生命週期管理**：所有檔案讀寫、文件物件與串流必須強制使用 `with` Context Manager，確保控制代碼即時關閉（亦可避免 Windows 檔案鎖死）。
- [ ] **[P1] API 故障隔離與重試**〔依賴外部 API〕：呼叫外部 API 時，必須妥善處理限流（如 429）、配額耗盡與服務端安全攔截。嚴禁在命中安全攔截或配額用罄時盲目重試造成無限迴圈。
- [ ] **[P1] 例外處理精準度與防吞噬**：嚴禁使用裸的 `except: pass` 盲目吞噬未知錯誤，必須儘可能捕獲具體例外並記錄日誌。
- [ ] **[P1] 例外鏈完整度 (Exception Chaining)**：重新拋出領域自定義例外時，必須使用 `raise DomainException(...) from err` 保留原始呼叫堆疊，嚴禁抹除真實根因。

### 4. 冪等性、資料結構演進與併發 (Idempotency & Concurrency)
- [ ] **[P0] 資料寫入冪等性**〔有持久化寫入〕：寫入資料庫或索引前，必須處理同一來源的舊資料（清除、覆寫或版本化），重跑時不得堆疊污染。
- [ ] **[P1] 產出檔案冪等性**〔有檔案產出〕：產出檔案應有一致的覆寫或版本管理邏輯，處理失敗需自動清理或移入隔離區。
- [ ] **[P1] 資料結構平滑遷移**〔有持久化資料結構〕：資料庫綱要、索引定義與鍵前綴應具備版本識別，便於平滑切換與回滾。
- [ ] **[P2] 全鏈路 Trace ID**：處理流程應具備唯一追蹤識別碼，並貫穿於日誌與報告中。

### 5. 代碼品質與測試防護 (Clean Code & Test Isolation)
- [ ] **[P0] 測試獨立性**：單元測試（`tests/unit/`）必須 100% 透過 Mock 隔離真實網路、外部 API 與資料庫。單元測試必須能離線且毫秒級完成。
- [ ] **[P1] 負面與故障注入測試 (Negative Testing)**：新加入的核心功能或修復的缺陷，必須在 `tests/unit/` 提供至少 2 組異常/故障情境測試（數量規定以 unit-testing 技能為正本）。
- [ ] **[P1] 測試覆蓋齊全**：新功能需具備足夠斷言（禁止無意義或空斷言的 Fake Test），且回歸測試全套通過（`Ran X tests ... OK`）。
- [ ] **[P0] 需求—斷言追溯 (AC-to-Assertion Traceability)**：對照 `docs/specs/` 的 PRD 驗收條件（AC）與 `docs/qa_reports/` 的 RTM，逐條確認每條 AC 與 `NFR-*` 至少有一個斷言或實測案例**直接驗證其預期結果**（回傳值、狀態變化或例外型別與訊息）。僅斷言「未拋例外」、Mock 呼叫次數或回傳非空者，不算驗證該 AC。任一 AC 無有效斷言即為 P0。
- [ ] **[P1] 預期值獨立性 (Oracle Independence)**：抽查斷言的預期值，須可追溯至規格、手算或固定樣本，不得由被測程式執行結果回填（如先跑一次再把輸出貼成預期值）。抽查至少 3 條 AC，或全部 AC（若少於 3 條），並在審查報告中列出抽查項目。
- [ ] **[P0] 回歸測試先紅後綠（Bug 軌／Hotfix 適用）**：PR 須包含先 `test:` 後 `fix:` 兩個 commit。切換至 `test:` commit 執行該回歸測試，必須**失敗**且失敗原因正是缺陷本身；在 `fix:` commit 必須通過。缺少 `test:` commit、或測試在 `test:` commit 即通過者，判 P0。
- [ ] **[P1] 逃逸分析（Bug 軌／Hotfix 適用）**：缺陷報告第 3 節須說明既有測試或防線為何沒抓到（測試缺口／斷言過弱／規格缺口／防線缺口）；屬防線缺口者須附改善建議。Hotfix 合併前可僅有摘要，但須於補件期限內補齊。
- [ ] **[P2] 型別標註與文件**：新增的公開方法或資料傳輸物件（DTO / Models）必須具備 Type Hints 與清晰的 Docstring。
- [ ] **[P2] 向下相容性**：既有 CLI 命令引數與介面是否有受到破壞？

### 6. 外部呼叫成本 (External Call Cost Guardrails)
- [ ] **[P0] 重複執行零重複計費**〔`uses_llm` 或依賴計費外部服務〕：批次處理必須具備內容指紋（Hash）比對，未變更資料重複執行時嚴禁重新呼叫計費 API。

### 7. Twelve-Factor 配置管理與零硬編碼防禦 (No-Hardcoded-Configuration Guardrails)
- [ ] **[P0] 零機密憑證硬編碼**：原始碼與 Git 版控檔案中嚴禁明文寫死任何 API Key、Token 或密碼（必須透過 `.env` 注入）。
- [ ] **[P0] 外部連線與端點零寫死**：禁止在核心業務程式碼中硬編碼外部連線 URL（如 `postgres://`、`http://` 等），所有連線字串必須統一由設定模組（`config.module`）與 `.env` 注入管理；例外檔案須登錄於 `guardrails.url_exceptions` 並附理由。
- [ ] **[P1] 運行時配額與演算法閥值可配置化**：所有安全配額與演算法閥值（大小、數量上限、重試退避、演算法參數）必須具備環境變數覆寫機制，嚴禁在 Use Case 或業務層寫死 Magic Numbers。
- [ ] **[P1] 跨平台絕對路徑禁令**：禁止在代碼中寫死任何本機絕對路徑（如 `C:\...` 或 `/home/...`），一律使用 `pathlib.Path` 相對路徑或環境變數注入。

### 8. Prompt Engineering 資產化與提示詞治理防禦 (Prompt-as-Code Guardrails)
- [ ] **[P0] 提示詞資產獨立化 (Prompt Externalization)**〔`uses_llm`〕：所有 LLM Prompt 嚴禁在程式碼中寫死長篇多行字串，必須抽離為獨立資產檔並透過載入函式與依賴注入管理。注入圍欄見第 2 類。
- [ ] **[P1] 提示詞資產完整度單元測試**〔`uses_llm`〕：新增或微調的提示詞資產檔，必須有單元測試驗證檔案存在、語法有效且可正常載入，杜絕執行期才發現檔案遺漏。
- [ ] **[P0] 提示詞零機密與零真實個資洩漏**〔`uses_llm`〕：Prompt 模板檔案中嚴禁寫死 API Key、真實個資（PII）、本機絕對路徑或源自真實案例之特定企業名稱；範例一律使用通用術語。

### 9. Git 版控衛生、個資清零與跨平台相容防線 (Git Hygiene, Zero-PII & Cross-Platform Guardrails)
- [ ] **[P0] 零真實個資殘留 (Zero Real PII)**〔`handles_pii`〕：原始碼、API 參數說明、CLI `--help`、單元測試、E2E 測試與 `docs/` 文檔，確認零真實個人姓名、聯絡方式或真實檔名；範例一律使用虛構資料。
- [ ] **[P0] 單元測試零外部樣本檔依賴 (In-Memory Test Fixtures)**：`tests/unit/` 嚴禁讀取敏感目錄（`privacy.sensitive_dirs`）下之真實檔案，測試夾具必須於記憶體動態建構（`BytesIO` / `Mock`）；測試防線本身不得以明文儲存受保護個資（採 SHA-256 指紋前綴比對，指紋清單見 `privacy.forbidden_hash_prefixes`）。
- [ ] **[P0] 零本機工作區絕對路徑 (Zero Hardcoded Workspace Paths)**：全專案所有納入 Git 之代碼、測試腳本、註解與 Markdown 文檔（含 `docs/`、`.agents/`、根目錄 `.md`）嚴禁寫死本機工作區絕對路徑；代碼統一使用 `Path(__file__).resolve()` 動態定位，版控文檔連結統一使用相對路徑，確保跨平台 CI/CD 與 GitHub 網頁點擊 100% 正常。
- [ ] **[P0] `.gitignore` 敏感邊界與 `.env.example` 100% 對齊**：凡新增任何衍生輸出目錄、快取或資料庫落地檔必須同步列入 `.gitignore`（必備項目清單之正本為 `project.toml` 的 `guardrails.required_gitignore`，由 `audit_guardrails.py` 自動比對）；設定模組（`config.module`）內所有 `os.environ.get()` 環境變數必須 100% 同步記載於 `.env.example`（且 `.env.example` 嚴禁包含真實金鑰）。
