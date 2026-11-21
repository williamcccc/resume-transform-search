# 移植指南：把閉環帶到其他專案

本閉環的專案專屬內容分兩處存放（[Spec-0028](../docs/specs/0028-portable-closed-loop-spec.md)）：

* **值**：集中在 [project.toml](project.toml)，閘門腳本只讀這份設定。
* **紅線**：本專案紅線與執行環境集中於 AGENTS.md 第 1 節「本專案紅線」小節（每次對話自動載入，以 `<!-- 專案專屬` 整節標記）。
* **事實與答案**：專案概況與通用檢核清單的本專案具體標準，集中在 [project/](project/) 下的專案實例檔，移植時整份替換（[Spec-0035](../docs/specs/0035-portable-arch-review-checklist-spec.md)、[Spec-0036](../docs/specs/0036-portable-review-checklist-spec.md)、[Spec-0037](../docs/specs/0037-project-profile-tests-and-red-lines-spec.md)）。

**適用範圍**：閘門腳本與測試規範綁定 **Python 專案**——`audit_guardrails.py` 以 Python AST 掃描、`security_scan.py` 使用 Semgrep `p/python` 規則與 pip-audit、單元測試規範以 `unittest` 為準。其他語言的專案可沿用流程、角色、技能與檢核清單，但兩支閘門腳本與測試指令須自行替換。

## 步驟

1. **複製檔案**：`AGENTS.md`、`CLAUDE.md`（使用 Antigravity 時另加 `GEMINI.md`）、`.agents/`（含閉環自我測試 `.agents/tests/`）、`.claude/`。略過所有 `__pycache__/`。
2. **刪除業務技能**：`.agents/skills/resume-vector-indexing/`、`.agents/skills/resume-vector-search/`，以及 `.claude/skills/` 下同名資料夾。
3. **改寫 `project.toml`**，逐鍵確認：
   * `[layers]`：填入新專案的分層路徑；非 DDD 專案設 `enabled = false`，但 `src` 仍須指向原始碼根目錄。
   * `[config]`：唯一可讀環境變數的模組與環境變數範本檔。
   * `[guardrails]`：連線 scheme、金鑰格式、提示詞片語、評測專用套件、`.gitignore` 必備項目、掃描略過目錄；`url_exceptions` 清空或改填新專案的例外（每筆附 `reason`）。
   * `[privacy]`：**`forbidden_hash_prefixes` 必須清空**（那是原專案受保護身分的指紋）；`sensitive_dirs`、`personal_filename_keywords`、`safe_filename_stems` 依新專案的敏感資料改寫；`locale_patterns` 依地區選用。
   * `[docs]`：`quality_ac_enforced_from` 與 `security_ac_enforced_from` 皆改為 `1`（新專案從第一份規格起強制）。
   * `[security]`：**逐項回答專案特徵**（網路暴露範圍、Web 介面、API、LLM、個資、不受信任檔案、多使用者）與 `asvs_level`；適用標準由 [security_nfr_framework.md](skills/feature-design/references/security_nfr_framework.md) 第四節自動對照，不必重寫檢核項目。`not_applicable` 清空後依新專案填寫，每筆附 `reason`；第四節適用條件為「技術」的章節（如 V9、V10、V17），新專案未使用該技術者須逐章登錄。
   * `[security.tools]`：`scan_paths` 改為新專案的原始碼與入口檔，`dependency_files` 改為新專案的需求檔；`baseline` 指向的基準檔**不要複製**（那是原專案的發現）。`diff_base` 改為新專案的主分支名稱；`full_scan_max_age_days` 依需要調整（預設 7 天）。
4. **替換專案實例檔**：[project/](project/) 下的檔案是原專案的具體標準，整份替換為新專案內容；新專案尚無程式碼時可先留空表或只留類別標題，隨首份規格與首次審查補齊。核心檢核清單不必改寫。
   * [profile.md](project/profile.md)：專案概況（入口與介面、主要流程、持久化結構、敏感資料類型、測試環境），核心檔寫「見專案概況」之處即指本檔。
   * [arch_review_criteria.md](project/arch_review_criteria.md)：Gate 1 架構前審 8 大維度的通過標準（核心為 `arch_review_checklist.md`）。
   * [review_criteria.md](project/review_criteria.md)：Gate 2 代碼審查的本專案檢核項與數值（核心為 `review_checklist.md`）。
5. **改寫本專案紅線**：AGENTS.md 第 1 節「本專案紅線」小節整節改寫為新專案的紅線與執行環境（新增紅線編號自 8 起接續，不重用 1–7）；通用紅線 1、6、7 原樣保留。之後全倉搜尋 `<!-- 專案專屬`，確認無其他殘留。**未帶專屬標記的通用核心檔不得刪除**，包括 `security_nfr_framework.md`、`security_scan.py` 與 AGENTS.md「安全與非功能需求規則」一節；`verify_doc_sync.py` 檢查核心檔存在。無檢索或 LLM 功能的專案，可刪除 AGENTS.md 第 2 節「品質評測規則」整節與 `quality-evaluation` 技能。
6. **安裝安全掃描工具並建立基準**：工具裝在獨立虛擬環境，避免與執行期相依衝突：

   ```bash
   python -m venv .venv-tools
   .venv-tools/Scripts/python -m pip install -r requirements-dev.txt
   python .agents/skills/code-review/scripts/security_scan.py --full
   ```

   POSIX 系統改用 `.venv-tools/bin/python`。複製 `requirements-dev.txt`，並將 `.venv-tools/` 加入 `.gitignore`。首次掃描的既有發現逐項評估：該修的修，誤報或延後者以 `--write-baseline --reason "…" --expires YYYY-MM-DD` 登錄後，再逐筆改寫具體理由。
7. **建立文件骨架**：`docs/specs/`、`docs/qa_reports/`、`docs/adr/`（含 `README.md` 索引）、`docs/bugs/`、`docs/README.md`（中樞索引）、`REQUIREMENTS.md`、`ARCHITECTURE.md`；並將 5 份範本自 `.agents/` 正本複製到 `docs/templates/`（清單見 `verify_doc_sync.py` 的 `TEMPLATE_MIRRORS`）。
8. **驗證**：

   ```bash
   python .agents/skills/doc-sync/scripts/verify_doc_sync.py
   python .agents/skills/code-review/scripts/audit_guardrails.py
   python .agents/skills/code-review/scripts/security_scan.py
   python -m unittest discover -s .agents/tests -p "test_*.py"
   ```

   最後一行是閉環核心的自我測試（隨 `.agents/` 一併複製，驗證閘門腳本與規範結構）；新專案的 CI 建議加入同一步。

   結束碼 2 表示 `project.toml` 缺鍵或格式錯誤，訊息會指出缺少的鍵。
