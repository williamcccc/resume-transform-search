# 移植指南：把閉環帶到其他專案

本閉環的專案專屬內容分三處存放：

* **值**：集中在 [project.toml](project.toml)，閘門腳本只讀這份設定。
* **紅線**：本專案紅線與執行環境集中於 AGENTS.md 第 1 節「本專案紅線」小節（每次對話自動載入，以 `<!-- 專案專屬` 整節標記）。
* **事實與答案**：專案概況與通用檢核清單的本專案具體標準，集中在 [project/](project/) 下的專案實例檔，移植時整份替換。

**適用範圍**：閘門腳本與測試規範綁定 **Python 專案**——`audit_guardrails.py` 以 Python AST 掃描、`security_scan.py` 使用 Semgrep `p/python` 規則與 pip-audit、單元測試規範以 `unittest` 為準。其他語言的專案可沿用流程、角色、技能與檢核清單，但兩支閘門腳本與測試指令須自行替換。
閉環核心（通用紅線 1、角色與技能）**以 DDD 四層與依賴反轉為前提**；非 DDD 專案可沿用流程與雙門禁，但須自行改寫紅線 1 與各技能之分層描述。

## 步驟

1. **複製檔案**：`AGENTS.md`、`CLAUDE.md`、`GEMINI.md`（工具薄層檔，未使用該工具時保留亦無害；核心文件有連結指向它們）、`.agents/`（含閉環自我測試 `.agents/tests/`）、`.claude/`。略過所有 `__pycache__/`。
2. **刪除業務技能**：刪除 `project.toml` 的 `project.business_skills` 所列技能（`.agents/skills/` 與 `.claude/skills/` 下同名資料夾），再將清單改為新專案的業務技能（無則清空）。
3. **改寫 `project.toml`**，逐鍵確認：
   * `[layers]`：填入新專案的分層路徑；`enabled = false` 只關閉自動分層檢查（如逐步導入 DDD 之專案），紅線 1 與技能之分層規範仍適用；`src` 仍須指向原始碼根目錄。
   * `[config]`：設定模組（集中讀取環境變數）與環境變數範本檔；原始碼以字串常值讀取的環境變數都須列於範本檔。
   * `[guardrails]`：連線 scheme（`url_schemes` 為空即停用寫死連線 URL 檢查，僅於確無外部連線時清空）、金鑰格式、提示詞片語、評測專用套件、`.gitignore` 必備項目、掃描略過目錄；`url_exceptions` 清空或改填新專案的例外（每筆附 `reason`）。清空時刪除 `[[guardrails.url_exceptions]]` 表格，並於 `[guardrails]` 區段內（下一個區段標題之前）寫 `url_exceptions = []`。
   * `[privacy]`：**`forbidden_hash_prefixes` 必須清空**（那是原專案受保護身分的指紋）；`sensitive_dirs`、`sensitive_extensions`（敏感目錄下的檔案副檔名）、`personal_filename_keywords`、`safe_filename_stems` 依新專案的敏感資料改寫；`locale_patterns` 依地區選用。
   * `[project]`：`identifiers` 改為新專案的業務名詞、檔名、類別名與原始碼路徑（如 `'\bapp/'`），`stack_terms` 改為新專案的技術元件名；兩者皆為正規式清單（單引號字面字串），供閉環自我測試守護核心文件中性化。無則清空。
   * `[docs]`：`quality_ac_enforced_from` 與 `security_ac_enforced_from` 皆改為 `1`（新專案從第一份規格起強制）。
   * `[security]`：**逐項回答專案特徵**（網路暴露範圍、Web 介面、API、LLM、個資、不受信任檔案、多使用者）與 `asvs_level`；適用標準由 [security_nfr_framework.md](skills/feature-design/references/security_nfr_framework.md) 第四節自動對照，不必重寫檢核項目。`not_applicable` 清空後依新專案填寫，每筆附 `reason`（無項目時同 `url_exceptions`，於 `[security]` 區段內寫 `not_applicable = []`）；第四節適用條件為「技術」的章節（如 V9、V10、V17），新專案有使用者列於 `tech_chapters_in_use`，未使用者於 `not_applicable` 逐章登錄。
   * `[security.tools]`：`scan_paths` 改為新專案的原始碼與入口檔，`dependency_files` 改為新專案的需求檔；`baseline` 指向 `project/` 下的基準檔（見第 4 步）。`diff_base` 改為新專案的主分支名稱；`full_scan_max_age_days` 依需要調整（預設 7 天）。
4. **替換專案實例檔**：[project/](project/) 下的檔案是原專案的具體標準，整份替換為新專案內容；新專案尚無程式碼時可先留空表或只留類別標題，隨首份規格與首次審查補齊。核心檢核清單不必改寫。
   * [security_baseline.json](project/security_baseline.json)：原專案的安全掃描既有發現，**內容清空為 `{"findings": []}`**（保留檔案，核心文件有連結指向它），於第 6 步首次掃描後依需要登錄。
   * [profile.md](project/profile.md)：專案概況（入口與介面、主要流程、持久化結構、敏感資料類型、測試環境），核心檔寫「見專案概況」之處即指本檔。
   * [arch_review_criteria.md](project/arch_review_criteria.md)：Gate 1 架構前審 8 大維度的通過標準（核心為 `arch_review_checklist.md`）。
   * [review_criteria.md](project/review_criteria.md)：Gate 2 代碼審查的本專案檢核項與數值（核心為 `review_checklist.md`）。
5. **改寫本專案紅線**：AGENTS.md 第 1 節「本專案紅線」小節整節改寫為新專案的紅線與執行環境（新增紅線編號自 8 起接續，不重用 1–7）；通用紅線 1、6、7 原樣保留。之後全倉搜尋 `<!-- 專案專屬`，確認無其他殘留。**未帶專屬標記的通用核心檔不得刪除**，包括 `security_nfr_framework.md`、`security_scan.py` 與 AGENTS.md「安全與非功能需求規則」一節；`verify_doc_sync.py` 檢查核心檔存在。無檢索或 LLM 功能的專案**不必刪除** AGENTS.md 第 2 節「品質評測規則」與 `quality-evaluation` 技能：規格一律宣告 `品質評測範圍：否`，技能不會被觸發（`verify_doc_sync.py` 仍要求每份規格宣告範圍，且多處核心文件連結該技能）。
6. **安裝安全掃描工具並建立基準**：工具裝在獨立虛擬環境，避免與執行期相依衝突：

   ```bash
   python -m venv .venv-tools
   .venv-tools/Scripts/python -m pip install -r requirements-dev.txt
   python .agents/skills/code-review/scripts/security_scan.py --full
   ```

   POSIX 系統改用 `.venv-tools/bin/python`。複製 `requirements-dev.txt`，並將 `.venv-tools/` 加入 `.gitignore`。首次掃描的既有發現逐項評估：該修的修，誤報或延後者以 `--write-baseline --reason "…" --expires YYYY-MM-DD` 登錄後，再逐筆改寫具體理由。
7. **建立文件骨架**：`docs/specs/`、`docs/qa_reports/`、`docs/adr/`（含 `README.md` 索引）、`docs/bugs/`、`docs/README.md`（中樞索引）、`REQUIREMENTS.md`、`ARCHITECTURE.md`；並將 5 份範本自 `.agents/` 正本複製到 `docs/templates/`（清單見 `verify_doc_sync.py` 的 `TEMPLATE_MIRRORS`）。`docs/specs/`、`docs/qa_reports/`、`docs/bugs/` 在首份文件建立前為空目錄、不進版控，乾淨 checkout 下不存在屬正常（`verify_doc_sync.py` 回報 WARN）。
8. **驗證**：

   ```bash
   python .agents/skills/doc-sync/scripts/verify_doc_sync.py
   python .agents/skills/code-review/scripts/audit_guardrails.py
   python .agents/skills/code-review/scripts/security_scan.py
   python -m unittest discover -s .agents/tests -p "test_*.py"
   ```

   最後一行是閉環核心的自我測試（隨 `.agents/` 一併複製，驗證閘門腳本、規範結構與核心文件內部連結）；新專案的 CI 建議加入同一步。

   結束碼 2 表示 `project.toml` 缺鍵或格式錯誤，訊息會指出缺少的鍵。`verify_doc_sync.py` 另會檢查閉環結構：ASVS 技術章節皆已宣告、第 4 步的必備實例檔存在、核心只保留 AGENTS.md「本專案紅線」一處專屬標記、`business_skills` 與實際技能資料夾一致；FAIL 訊息會指出章節、檔案或行號。
