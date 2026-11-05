# PRD 與 DDD 技術實作規格書（Spec 0017）

> **關聯 ADR**：[ADR-0017](../adr/0017-publish-privacy-scanner-hardening.md)
> **QA 報告**：[QA Report 0017](../qa_reports/0017-github-publish-privacy-hardening-qa-report.md)

## 一、產品需求文件（PRD）

### 背景與目標

上庫前審核發現，既有隱私掃描只比對完整文字雜湊，漏掉部分遮蔽的識別線索與個人化履歷檔名；0016 規格與 QA 報告因此留下過度肯定的零個資結論。另有數個文件連結指向範例佔位路徑或被 Git 忽略的本機輸出。

目標是移除文件中的來源識別線索、擴大本機靜態防線，並讓版控文件只連結已存在的專案檔案。

### 範疇

**In Scope**

1. 清理 0016 規格中可識別履歷來源的片段，將舊規格與需求文件中的個人化履歷路徑改為通用範例，並為 0016 QA 報告標註其原始 PASS 結論已被後續審核取代。
2. 擴充單元測試與 `audit_guardrails.py`，檢查部分遮蔽的 CJK 識別字串、個人化履歷檔名、既有受保護文字指紋與 Markdown 內部斷鏈。
3. 保留 `sample_resume.md` 等明確通用範例；不得把本機 `data/` 輸出加入版控。
4. 將佔位規格路徑和本機生成履歷路徑改為行內程式碼範例，避免產生失效連結。
5. 新增本規格、ADR、QA 報告，並更新文件索引。

**Out of Scope**

- 不讀取或修改 `.env`、`data/`、`logs/` 中的本機內容。
- 不更動轉檔、搜尋、索引、CLI、API 或 Redis 行為。
- 不執行 Git add、commit、remote 設定或 push。

### 驗收標準

- **AC-1 隱私清理：**本次已識別的遮蔽姓名、個人化履歷檔名與來源組織線索已泛化；現有掃描規則對候選檔案零命中，舊報告明確記錄原掃描限制與更正。
- **AC-2 掃描器覆蓋：**純函式測試能攔截遮蔽 CJK 識別字串與個人化履歷檔名，並接受通用樣本檔名；錯誤訊息只列檔案與類別，不回顯疑似敏感文字。
- **AC-3 連結完整：**所有 Markdown 內部檔案連結均解析到存在的專案檔案；範例佔位路徑以行內程式碼呈現。
- **AC-4 原防線保留：**`.gitignore`、`.env.example`、金鑰與本機絕對路徑檢查持續通過，且掃描器仍排除既有忽略目錄。
- **AC-5 品質驗證：**相關單元測試、E2E 實測及架構靜態掃描通過；文件索引與同步檢查於 Gate 2 後完成。

## 二、架構前審（Gate 1）

這是文件與開發期守門工具的修正，不變更執行時架構或外部服務。掃描只在本機執行，不上傳文件內容；錯誤輸出僅包含相對路徑和違規類型。檔案讀取沿用 UTF-8 與 `Path`，不新增第三方依賴。

| 維度 | 評估 |
| :--- | :--- |
| 個資隱私 | 擴大遮蔽字串與檔名檢查；不保留原始識別值或本機履歷內容。 |
| 容量與極限 | 沿用現有遞迴文字掃描，輸入規模不變。 |
| 非同步與演進 | 不涉及執行時請求或非同步流程。 |
| 成本與熔斷 | 不呼叫外部 API，不產生 Token 成本。 |
| 可抽換性 | 不涉及 Domain、Use Case 或 Protocol。 |
| 惡意輸入 | 只處理本機 UTF-8 文字；二進位副檔名與忽略目錄維持排除。 |
| 索引演進 | 不涉及 Redis 或向量索引。 |
| 併發與可觀測性 | 不改變應用程式日誌或併發模型。 |

**Gate 1：PASS。** 變更範圍明確，無執行時架構債；依下列測試矩陣實作。

## 三、DDD 技術實作規格與 QA 矩陣

| 檔案 | 職責 |
| :--- | :--- |
| `tests/unit/test_github_pre_publish_hygiene.py` | 驗證新掃描器案例、候選檔案隱私衛生及本機 Markdown 連結。 |
| `.agents/skills/code-review/scripts/audit_guardrails.py` | 加入遮蔽識別字串、個人化履歷檔名檢查；不輸出命中原文。 |
| `docs/adr/0017-publish-privacy-scanner-hardening.md` | 記錄本機掃描與安全錯誤輸出的決策。 |
| `docs/specs/0016-github-pre-publish-sanitization-spec.md` | 泛化原始風險敘述，刪除來源識別線索。 |
| `docs/specs/0015-resume-search-web-interface-spec.md`, `REQUIREMENTS.md` | 將個人化履歷檔案路徑改為通用樣本路徑。 |
| `docs/qa_reports/0016-github-pre-publish-sanitization-qa-report.md` | 加入後續更正，明確撤回原始零個資保證。 |
| `AGENTS.md`, `GEMINI.md`, `.agents/skills/resume-vector-search/SKILL.md` | 修正指向佔位規格或忽略輸出的 Markdown 連結。 |
| `tests/unit/test_resume_indexing_skill.py` | 使用暫存目錄與記憶體建構的 Markdown 樣本，避免掃描本機履歷資料。 |

| 案例 | 驗收方式 |
| :--- | :--- |
| TC-17-01 | 記憶體構造遮蔽 CJK 字串，掃描器回報類別但不回顯字串。 |
| TC-17-02 | 記憶體構造個人化履歷檔名並確認攔截；通用樣本檔名不攔截。 |
| TC-17-03 | 掃描所有版控候選文字檔，確認無隱私違規。 |
| TC-17-04 | 解析 Markdown 相對連結，確認目標存在；忽略程式碼區塊與外部連結。 |
| TC-17-05 | 執行相關單元測試、E2E 實測及 `audit_guardrails.py`；Gate 2 後執行 `verify_doc_sync.py`。 |
