# 移植指南：把閉環帶到其他專案

本閉環的專案專屬內容分兩處存放（[Spec-0028](../docs/specs/0028-portable-closed-loop-spec.md)）：

* **值**：集中在 [project.toml](project.toml)，閘門腳本只讀這份設定。
* **規則**：留在規範文字中，以 `<!-- 專案專屬` 開頭的 HTML 註解標記（畫面上看不到，搜尋得到）。

## 步驟

1. **複製檔案**：`AGENTS.md`、`CLAUDE.md`（使用 Antigravity 時另加 `GEMINI.md`）、`.agents/`、`.claude/`。略過所有 `__pycache__/`。
2. **刪除業務技能**：`.agents/skills/resume-vector-indexing/`、`.agents/skills/resume-vector-search/`，以及 `.claude/skills/` 下同名資料夾。
3. **改寫 `project.toml`**，逐鍵確認：
   * `[layers]`：填入新專案的分層路徑；非 DDD 專案設 `enabled = false`，但 `src` 仍須指向原始碼根目錄。
   * `[config]`：唯一可讀環境變數的模組與環境變數範本檔。
   * `[guardrails]`：連線 scheme、金鑰格式、提示詞片語、評測專用套件、`.gitignore` 必備項目、掃描略過目錄；`url_exceptions` 清空或改填新專案的例外（每筆附 `reason`）。
   * `[privacy]`：**`forbidden_hash_prefixes` 必須清空**（那是原專案受保護身分的指紋）；`sensitive_dirs`、`personal_filename_keywords`、`safe_filename_stems` 依新專案的敏感資料改寫；`locale_patterns` 依地區選用。
   * `[docs]`：`quality_ac_enforced_from` 改為 `1`（新專案從第一份規格起強制）。
4. **處理專屬標記**：全倉搜尋 `<!-- 專案專屬`，逐處改寫為新專案的規則，或連同規則一併刪除。無檢索或 LLM 功能的專案，可刪除 AGENTS.md 第 2 節「品質評測規則」整節與 `quality-evaluation` 技能。
5. **（選擇性）中性化舉例**：以下檔案的舉例使用了原專案元件（Redis、Gemini、PDF 轉檔等），規則本身通用，不改也能運作：
   `code-review/SKILL.md`、`auto-fix/SKILL.md`、`auto-fix/references/{rca_guide,fix_anti_patterns}.md`、`unit-testing/references/{mocking_patterns,unit_test_checklist}.md`、`feature-design/references/{prd_template,tech_spec_template}.md`、`qa-testing/references/{test_case_template,qa_report_template}.md`、`bug-triage/references/bug_report_template.md`。
6. **建立文件骨架**：`docs/specs/`、`docs/qa_reports/`、`docs/adr/`（含 `README.md` 索引）、`docs/bugs/`、`docs/README.md`（中樞索引）、`REQUIREMENTS.md`、`ARCHITECTURE.md`；並將 5 份範本自 `.agents/` 正本複製到 `docs/templates/`（清單見 `verify_doc_sync.py` 的 `TEMPLATE_MIRRORS`）。
7. **驗證**：

   ```bash
   python .agents/skills/doc-sync/scripts/verify_doc_sync.py
   python .agents/skills/code-review/scripts/audit_guardrails.py
   ```

   結束碼 2 表示 `project.toml` 缺鍵或格式錯誤，訊息會指出缺少的鍵。
