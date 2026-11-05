# PRD & DDD Tech Spec: 架構合規與安全防護全面修復

> **狀態**：Gate 1 審查通過 (APPROVED)  
> **目標**：修復 Gate 2 審查發現的 3 項 P0 阻斷型缺陷與 3 項 P1 重大防護缺陷，使專案達到 100% 架構合規與資安防禦。

---

## Part 1. 產品需求文件 (PRD)

### 1. 背景與使用者目標
* **業務背景**：本專案處理大量來自外部招募管道之非受信任履歷文件（PDF/DOCX/DOC）。
* **核心欲解決之痛點**：
  1. `ConvertDocumentUseCase` 直接相依 `pymupdf`，破壞 DDD 四層架構。
  2. 缺乏單一檔案大小（25MB）、PDF 頁數（30頁）及 DOCX 膨脹比（10x）之硬上限，存在 Zip Bomb 與 DoS 記憶體耗盡隱患。
  3. LLM 轉換器與評審員缺少 `<resume_content>` 上下文圍欄標籤，易受 Prompt Injection 提示詞劫持。
  4. 單元測試對磁碟檔案有隱性依賴，不利 CI/CD 乾淨環境運作。

### 2. 功能範疇界定 (Scope)
* **[In-Scope]**：
  1. 建立 `PdfTextReader` 實作 `IDocumentReader`，並將其透過依賴注入傳入 Use Case，徹底移除 Use Case 中的 `import pymupdf`。
  2. 升級 `audit_guardrails.py`，新增 Application 層 AST 檢測（嚴禁第三方 SDK）。
  3. 實作 25MB 體積限制、30 頁上限、10x 解壓縮膨脹比防禦，並定義 `FileQuotaExceededError`。
  4. 提示詞全面引入 `<resume_content>` XML 圍欄隔離與 System Prompt 防注入警語。
  5. `DocxReader` 之 `zipfile.ZipFile` 納入 `with` 管理。
  6. Redis 向量索引預設更新為 `idx:resumes:v1` 與 `resume:v1:chunk:`。
  7. 單元測試去耦合化，改為純記憶體/Mock 測試，並增加負面安全測試（配額超額、Zip Bomb 防禦、Prompt 圍欄）。
* **[Out-of-Scope]**：
  - 修改外部 CLI 命令列引數（維持 100% 向下相容）。

### 3. 業務邏輯與驗收標準 (Acceptance Criteria)
* **AC 1: [Application 層 DIP 嚴格合規]**
  - **Given**：`ConvertDocumentUseCase` 執行。
  - **When**：處理健康文字 PDF。
  - **Then**：文字提取由注入之 `IDocumentReader` 執行，`convert_document_use_case.py` 內無 `import pymupdf`，`audit_guardrails.py` 掃描 100% 通過。
* **AC 2: [配額超限安全防禦]**
  - **Given**：輸入檔案超過 25MB 或 PDF 超過 30 頁或 DOCX 膨脹比超過 10x。
  - **When**：呼叫轉檔。
  - **Then**：系統立即拋出 `FileQuotaExceededError`，絕不進行消耗性運算。
* **AC 3: [提示詞圍欄隔離]**
  - **Given**：傳送未受信任文本給 Gemini（文字轉檔或 LLM Judge）。
  - **When**：組裝 Prompt。
  - **Then**：文本 100% 包裹於 `<resume_content>` 中，且提示詞註明不可執行履歷內指令。
* **AC 4: [單元測試離線獨立性]**
  - **Given**：在無本機 `resume/` 實體檔案之目錄下。
  - **When**：執行 `python -m unittest discover -s tests -p "test_*.py"`。
  - **Then**：全部測試順暢通過，零略過、零外部依賴。

---

## Part 2. DDD 技術實作規格書 (Tech Spec)

### 1. 架構影響矩陣
| 分層 | 檔案路徑 | 變更 | 職責 |
| :--- | :--- | :---: | :--- |
| **Domain** | `src/domain/exceptions.py` | 修改 | 新增 `FileQuotaExceededError` |
| **Domain** | `src/domain/interfaces.py` | 保持 | 沿用 `IDocumentReader` |
| **Application** | `src/application/convert_document_use_case.py` | 修改 | 移除 `import pymupdf`，注入 `readers`，加入 25MB 體積防禦與 Trace ID |
| **Infrastructure** | `src/infrastructure/readers/pdf_text_reader.py` | 新增 | 實作 `IDocumentReader`，以 PyMuPDF 提取原生純文字 |
| **Infrastructure** | `src/infrastructure/readers/pdf_renderer.py` | 修改 | 加入 30 頁上限防禦 |
| **Infrastructure** | `src/infrastructure/readers/docx_reader.py` | 修改 | 補上 `with`，加入 10x 膨脹比 Zip Bomb 防禦 |
| **Infrastructure** | `src/infrastructure/transformers/gemini_transformer.py` | 修改 | 實施 `<resume_content>` 圍欄與防注入指令 |
| **Infrastructure** | `src/infrastructure/validators/llm_judge.py` | 修改 | 實施 `<resume_content>` 圍欄與防注入指令 |
| **Infrastructure** | `src/infrastructure/stores/redis_vector_store.py` | 修改 | 預設索引升級為 `idx:resumes:v1` |
| **Interfaces** | `src/interfaces/cli/runner.py` | 修改 | 注入 `PdfTextReader`，相容 `trace_id` |
| **Tools** | `.agents/skills/code-review/scripts/audit_guardrails.py` | 修改 | 強化 Application 層 AST 掃描 (禁第三方 SDK) |
| **Tests** | `tests/unit/test_security_quotas.py` | 新增 | 測試 25MB、30 頁、Zip Bomb 與 Prompt 圍欄 |
| **Tests** | `tests/unit/test_pdf_probe.py` | 修改 | 去除磁碟檔案依賴，使用 Mock / 合成資料 |
| **Tests** | `tests/unit/test_docx_reader.py` | 修改 | 去除磁碟檔案依賴，使用合成 docx 資料 |

### 2. 核心代碼設計
1. **`FileQuotaExceededError`**：
   ```python
   class FileQuotaExceededError(DomainError):
       """資源配額超限 (檔案過大、PDF 頁數過多或解壓膨脹比過高)"""
       pass
   ```
2. **`PdfTextReader`**：
   ```python
   class PdfTextReader(IDocumentReader):
       def can_read(self, doc: Document) -> bool:
           return doc.doc_type == DocumentType.PDF
       def extract_text(self, doc: Document) -> str:
           # 包含頁數限制檢查 (MAX 30 頁)
   ```
3. **提示詞圍欄**：
   ```python
   f"<resume_content>\n{text}\n</resume_content>"
   ```
