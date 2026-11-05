# PRD 與 DDD 技術實作規格書 (ADR-0016 / 規格 0016)

> **隱私更正（Spec 0017）**：本規格原稿曾包含部分遮蔽的來源識別文字，現已泛化；原始零個資判定由 [Spec 0017](./0017-github-publish-privacy-and-link-hardening-spec.md) 與 [QA Report 0017](../qa_reports/0017-github-publish-privacy-hardening-qa-report.md) 重新檢視。

## 一、產品需求文件 (PRD)

### 1. 商業背景與使用者目標 (Problem Statement & Goals)
專案即將正式推送至 GitHub 進行版本控制與展示。在首次 `git commit` 之前，經過全專案深度安全與隱私審計，發現以下 4 大潛在風險：
1. **可識別履歷來源線索**：開發與實測期間曾有姓名片段或個人化檔名殘留於候選版控文件；即使遮蔽部分字元，仍可能形成重新識別線索。
2. **源自履歷的組織資訊**：Prompt 範例或工程文件若保留特定組織線索，可能暴露案例來源並誘導模型生成特定組織資訊。
3. **本機絕對路徑硬編碼**：單元測試 [`test_hardcode_extractions.py`](../../tests/unit/test_hardcode_extractions.py) 與多處 Markdown 文檔/註解寫死本機工作區絕對路徑，導致跨平台 CI/CD 或他人 Clone 至不同目錄時測試失敗、GitHub 網頁連結失效。
4. **`.gitignore` 與 `.env.example` 邊界缺漏**：[`.gitignore`](../../.gitignore) 漏列 `resume/`、`markdown_out/`、`markdown_output/`、`dump.rdb` 等高風險目錄；[`.env.example`](../../.env.example) 漏列 `WEB_ENGINE` 配置項。

本規格旨在於不改變任何核心業務行為與 CLI 向下相容性的前提下，達成 **「100% 個資清零、100% 提示詞通用化、100% 跨平台相對路徑解耦、100% 版控防護閉環」**。

### 2. 範疇界定 (Scope)
* **In-Scope**:
  1. **【PII 個資與真實履歷檔名清零】**：
     - 清理 `src/interfaces/web/fastapi_server.py`、`index_to_redis.py`、`tests/unit/test_docx_reader.py`、`tests/unit/test_pdf_probe.py`、`REQUIREMENTS.md`、`ARCHITECTURE.md`、`docs/specs/0015-*.md` 與 `.agents/skills/` 中的所有真實姓名與真實履歷檔名。
     - 將 `test_docx_reader.py` 與 `test_pdf_probe.py` 中依賴本機 `resume/` 實體檔案的測試重構為 **100% 記憶體模擬 (In-Memory BytesIO / Mock) 單元測試**。
  2. **【Prompt 真實企業案例泛化】**：
     - 將 `prompts/self_review.md`、`prompts/vision_convert.md`、`REQUIREMENTS.md`、`ARCHITECTURE.md` 中的特定企業名稱替換為通用軟體工程詞彙（「微服務 / 微服霧」）。
  3. **【本機絕對路徑清零與相對路徑化】**：
     - 修正 `tests/unit/test_hardcode_extractions.py`、`src/infrastructure/prompts/__init__.py`、`.agents/skills/code-review/scripts/audit_guardrails.py` 中的本機工作區絕對路徑寫死問題。
     - 將全專案文檔（`AGENTS.md`、`GEMINI.md`、`CLAUDE.md`、`ARCHITECTURE.md`、`docs/`、`.agents/`）中的本機磁碟連結轉換為標準專案相對路徑連結。
     - 擴充 `audit_guardrails.py`，使 AST 靜態掃描亦涵蓋 `tests/` 內的本機工作區路徑硬編碼檢查。
  4. **【`.gitignore` 與 `.env.example` 補強】**：
     - 於 `.gitignore` 補入 `resume/`, `resumes/`, `markdown_out/`, `markdown_output/`, `dump.rdb`, `appendonlydir/`。
     - 於 `.env.example` 第 9 區補入 `WEB_ENGINE=auto`。
* **Out-of-Scope**:
  - 不更動 `data/` 目錄下的本機真實檔案（該目錄受 `.gitignore` 保護，不上傳 Git）。
  - 不修改任何業務邏輯演算法與 API 契約介面。

### 3. 驗收標準 (Acceptance Criteria, AC)
* **AC-1 (Zero PII Leakage)**: 以 `data/` 目錄提取之全部真實求職者姓名特徵詞庫掃描全專案所有 Git 候選檔案，命中數必須為 `0`。
* **AC-2 (Zero Real Company in Prompts)**: `prompts/*.md` 內零真實企業名稱，僅保留通用軟體工程術語範例。
* **AC-3 (Zero Hardcoded Workspace Path)**: 全專案所有 Git 候選檔案（含 `src/`, `tests/`, `prompts/`, `docs/`, `.agents/`, 根目錄 `.md`/`.py`）掃描本機工作區絕對路徑或 `file:///` 本機絕對連結，命中數必須為 `0`。
* **AC-4 (Gitignore & Env Example Completeness)**: `.gitignore` 完整涵蓋 `resume/`、`markdown_out/`、`dump.rdb`；`.env.example` 涵蓋 `AppConfig` 所有環境變數（含 `WEB_ENGINE`）。
* **AC-5 (100% Offline Unit Tests & Guardrails Pass)**: 全套單元測試、E2E 測試、`audit_guardrails.py` 與 `verify_doc_sync.py` 100% 綠燈通過。

---

## 二、8 大架構維度前審 (Gate 1 審查)

1. **個資隱私 (PII)**：徹底消除代碼、測試、規格書與 Prompt 中的真實求職者姓名與真實企業案例，達成公開開源合規。
2. **容量與極限 (Capacity)**：無影響。
3. **非同步與演進 (Async / Evolution)**：無影響。
4. **成本與熔斷 (Cost)**：單元測試 `test_docx_reader.py` 與 `test_pdf_probe.py` 改為 100% 記憶體模擬，0 外部 I/O 消耗。
5. **可抽換性 (Portability)**：消除 本機工作區絕對路徑 硬編碼後，專案可於任意作業系統（Windows / Linux / macOS）與任意目錄名稱下無縫執行。
6. **輸入安全性 (Input Security)**：`.gitignore` 嚴密封鎖 `resume/` 與 `markdown_out/`，防止未來誤觸 `git add .` 造成資料外洩。
7. **版本相容性 (Versioning)**：100% 向下相容既有 CLI 與 Web API。
8. **可觀測性與追溯性 (Observability)**：新增專屬單元測試 `test_github_pre_publish_hygiene.py`，將個資清零、路徑解耦與 `.gitignore`/`.env.example` 完整性納入自動化回歸測試防線。

---

## 三、DDD 技術實作規格書 (Tech Spec)

### 1. 異動模組清單
- **表現層與入口腳本**：
  - `src/interfaces/web/fastapi_server.py`：更新 Query 參數範例說明。
  - `index_to_redis.py`：更新 CLI `--help` epilog 範例路徑。
- **基礎設施層與提示詞資產**：
  - `src/infrastructure/prompts/__init__.py`：移除註解中之本機絕對路徑。
  - `prompts/self_review.md`、`prompts/vision_convert.md`：泛化 OCR 錯字校正範例。
- **配置與版控防線**：
  - `.gitignore`：新增履歷輸入/輸出與 Redis RDB/AOF 忽略規則。
  - `.env.example`：新增 `WEB_ENGINE=auto` 配置說明。
- **測試與守門員腳本**：
  - `tests/unit/test_docx_reader.py`：使用 `zipfile` + `io.BytesIO` 動態建立含殘留圖片關聯之模擬 `.docx` 進行記憶體自癒測試。
  - `tests/unit/test_pdf_probe.py`：移除真實檔案依賴，新增刪除線混淆標記 (`~~`) 之離線單元測試。
  - `tests/unit/test_hardcode_extractions.py`：使用 `Path(__file__).resolve().parents[2]` 動態定位 `audit_guardrails.py`。
  - `tests/unit/test_github_pre_publish_hygiene.py`（新增）：自動化檢驗 `.gitignore`、`.env.example`、零本機絕對路徑與零敏感資訊。
- **工程文檔與 AI 協作規範**：
  - 批量脫敏並將本機磁碟絕對路徑轉為專案相對路徑。

---

## 四、QA 驗收測試案例矩陣 (Test Matrix)

| 測試案例 ID | 對應 AC | 測試情境描述 | 預期結果 |
| :--- | :---: | :--- | :--- |
| **TC-16-01** | AC-1 | 交叉掃描全專案待入庫檔案是否殘留真實候選人姓名 | 0 命中 |
| **TC-16-02** | AC-2 | 檢查 `prompts/*.md` 是否不含特定真實企業名稱 | 0 命中，且通過 Prompt 載入測試 |
| **TC-16-03** | AC-3 | 掃描全專案待入庫檔案是否含本機工作區絕對路徑 | 0 命中 |
| **TC-16-04** | AC-4 | 驗證 `.gitignore` 忽略規則與 `.env.example` 對齊 `AppConfig` | 100% 覆蓋所有環境變數與敏感目錄 |
| **TC-16-05** | AC-5 | 執行全套 Unit Tests、E2E Tests、`audit_guardrails.py`、`verify_doc_sync.py` | 100% 通過 (Exit Code 0) |

---

## 五、Gate 1 審查結論
8 大架構維度檢核通過，**Gate 1 審查通過 (PASS)**，放行進入 Step 2 實作。
