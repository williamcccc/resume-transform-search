# QA 實測驗收報告 (QA Report 0016)

> **功能名稱**：GitHub 上庫前全方位安全脫敏、個資 (PII) 清零、跨平台路徑解耦與版控衛生治理
> **關聯規格書**：[0016-github-pre-publish-sanitization-spec.md](../specs/0016-github-pre-publish-sanitization-spec.md)
> **關聯 ADR**：[0016-github-pre-publish-security-and-pii-governance.md](../adr/0016-github-pre-publish-security-and-pii-governance.md)
> **測試日期**：2026-11-05
> **簽核狀態**：⚠️ **已撤回；零個資簽核由 QA 0017 重新驗收**
> **後續更正**：後續審核發現原掃描未覆蓋部分遮蔽識別字串與個人化履歷檔名。原 AC-1 的零命中結果不足以證明個資已清零，原始上庫簽核不得作為公開發布依據；修正與重新驗收結果請參閱 [QA Report 0017](./0017-github-publish-privacy-hardening-qa-report.md)。

---

## 一、需求追溯矩陣 (Requirements Traceability Matrix, RTM)

| AC 編號 | 驗收條件描述 | 對應測試案例 | 實測結果 |
| :---: | :--- | :--- | :---: |
| **AC-1** | 全專案待入庫檔案與 `data/` 真實求職者姓名交叉比對 **0 命中** | `test_prompts_and_code_free_of_real_candidate_names_and_company_examples` + 全量掃描 | ⚠️ **原判定已撤回：掃描範圍不足** |
| **AC-2** | `prompts/*.md` 零真實企業名稱，僅保留通用軟體工程術語範例 | `test_prompts_and_code_free_of_real_candidate_names_and_company_examples` | ✅ **PASS** |
| **AC-3** | 全專案待入庫檔案掃描本機絕對路徑硬編碼 **0 命中** | `test_no_hardcoded_workspace_paths_or_secrets_in_repo_files` | ✅ **PASS** (`0` 命中) |
| **AC-4** | `.gitignore` 涵蓋 `resume/`、`markdown_out/`、`dump.rdb`；`.env.example` 100% 對齊 `AppConfig` | `test_gitignore_covers_sensitive_and_runtime_paths` & `test_env_example_covers_all_app_config_variables_and_has_no_real_secrets` | ✅ **PASS** |
| **AC-5** | 全套單元測試 (128 項)、E2E 實測、`audit_guardrails.py` 與 `verify_doc_sync.py` 100% 通過 | `tests/unit/` + `tests/e2e/` + 靜態防線腳本 | ✅ **PASS** |

---

## 二、對抗式與邊界情境實測成果 (Adversarial & Edge-Case Verification)

1. **測試程式碼自身零個資明文防禦 (SHA-256 Hash Prefix Matching)**：
   - 為避免在回歸測試代碼 `test_github_pre_publish_hygiene.py` 中寫入欲攔截之真實人名明文（否則測試代碼上 Git 反成洩漏源），實作採用 **SHA-256 前 16 碼雜湊指紋比對** 掃描全專案所有 3~4 字中文詞組，達成測試防線自身 0 個資明文。
2. **Word 破圖自癒 100% 記憶體模擬 (In-Memory Corrupt `.rels` Injection)**：
   - 重構 `tests/unit/test_docx_reader.py`，不再讀取本機 `resume/` 實體檔案，改由 `zipfile` 於記憶體動態向 `word/_rels/document.xml.rels` 注入指向不存在圖檔 `media/missing_image.jpeg` 之殘留關聯，實測驗證 `_heal_docx_stream` 100% 自動補樁並成功萃取段落與表格。
3. **PDF 刪除線混淆探測離線化**：
   - 重構 `tests/unit/test_pdf_probe.py`，移除真實人名檔名硬編碼，新增刪除線標記 (`~~`) 超標判定為 `DocumentHealth.OBFUSCATED` 之離線單元測試。
4. **跨平台相對路徑連結轉換**：
   - 全專案 19 份 Markdown 文檔（含 `AGENTS.md`、`GEMINI.md`、`CLAUDE.md`、`ARCHITECTURE.md`、`docs/`、`.agents/`）中之 `file:///...` 本機絕對路徑已全數轉為標準相對路徑，在本地 IDE 與 GitHub 網頁版皆可直接點擊跳轉。

---

## 三、QA 驗收簽核結論
本報告記錄的是原始驗收結果。後續發現 AC-1 掃描未涵蓋遮蔽識別字串與個人化檔名，因此原始「零個資」結論及公開發布簽核已撤回。應以 [Spec 0017](../specs/0017-github-publish-privacy-and-link-hardening-spec.md) 與 [QA Report 0017](./0017-github-publish-privacy-hardening-qa-report.md) 的修正和驗收結果為準。
