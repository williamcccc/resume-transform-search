# 提案與規格書：閉環殘留專案相依清理（敏感副檔名設定化、基準檔歸位、業務技能清單）

> **狀態**：已實作（G2：使用者於 2026-11-21 核准，待決事項全數採建議；QA 見 [QA-0038](../qa_reports/0038-closed-loop-residual-project-coupling-qa.md)）｜**類型**：規範變更（大改：修改驗證腳本與設定綱要）｜**流程**：[governance.md](../../.agents/workflows/governance.md)｜**影響範圍**：`audit_guardrails.py`、`project_config.py`、`project.toml`、`.agents/project/`、[PORTING.md](../../.agents/PORTING.md) 與相關測試，不涉及 `src/`

## 一、動機

2026-11-21 以「通用核心 + 專案實例檔」概念重掃閉環時列出 4 個小問題（[Spec-0037](./0037-project-profile-tests-and-red-lines-spec.md) 處理了其餘三項）：

1. **`audit_guardrails.py` 寫死履歷相關假設**：
   * 敏感目錄下的檔名偵測寫死副檔名 `pdf|docx|doc|md`（`RESUME_DIRECTORY_FILENAME_PATTERN`），這是「履歷檔」的假設；其他專案的敏感檔可能是 `csv`、`xlsx`、`json`。
   * 命中類別名稱 `personal_resume_filename`、常數名稱 `PERSONAL_RESUME_FILENAME_PATTERN`、`RESUME_DIRECTORY_FILENAME_PATTERN` 帶有履歷字樣，會出現在其他專案的審查報告中。
2. **`security_baseline.json` 位置不一致**：基準檔是本專案的發現紀錄（專案實例），卻放在 `.agents/` 根目錄；[PORTING.md](../../.agents/PORTING.md) 須另外提醒「不要複製」。其他專案實例檔已集中於 `.agents/project/`。
3. **業務技能沒有可查詢的清單**：`resume-vector-indexing`、`resume-vector-search` 兩個業務技能與核心技能同放 `skills/`，只靠 PORTING 第 2 步與移植演練 E2E 各自寫死名稱來刪除。
4. **`quality-evaluation` 技能**：只有含檢索、抽取或 LLM 生成的專案需要；AGENTS.md 第 2 節與 PORTING 已說明可整節刪除。

## 二、提案內容

### 2.1 敏感副檔名設定化與命名中性化

* `project.toml` 的 `[privacy]` 新增 `sensitive_extensions`（字串清單，不含點），本專案值 `["pdf", "docx", "doc", "md"]`；`project_config.py` 綱要同步（缺鍵或型別錯誤以結束碼 2 中止）。空清單表示此項偵測不啟用（與其他清單一致）。
* `audit_guardrails.py`：敏感目錄檔名樣式改由 `sensitive_extensions` 組成；常數改名為 `PERSONAL_FILENAME_PATTERN`、`SENSITIVE_DIRECTORY_FILENAME_PATTERN`；命中類別 `personal_resume_filename` 改為 `personal_filename`。
* 偵測行為不變：本專案以相同設定值執行，結果與修改前一致。
* `binary_exts`（全倉掃描時略過的二進位格式清單）屬通用格式清單，不變。

### 2.2 基準檔歸位

* `security_baseline.json` 以 `git mv` 移至 `.agents/project/security_baseline.json`；`project.toml` 的 `[security.tools].baseline` 同步改值。
* PORTING：第 3 步 `baseline` 說明改為指向 `project/`；第 4 步實例檔清單加入基準檔（移植時刪除或清空，首次掃描後重建）。
* 移植演練 E2E 刪除基準檔的路徑同步。

### 2.3 業務技能清單

* `project.toml` 新增 `[project]` 區段，鍵 `business_skills`（字串清單），本專案值 `["resume-vector-indexing", "resume-vector-search"]`；`project_config.py` 綱要同步。
* PORTING 第 2 步改為「刪除 `project.business_skills` 列出的技能（`.agents/skills/` 與 `.claude/skills/` 下同名資料夾），並將清單清空」。
* 移植演練 E2E 改為讀取此鍵，不再寫死名稱。

### 2.4 quality-evaluation 技能

不修改。它屬「依功能條件適用」的通用技能（非本專案業務），AGENTS.md 第 2 節已以正文說明適用條件，PORTING 第 5 步已說明可刪除；列入業務技能清單會誤導為專案專屬。

## 三、修改檔案

| 檔案 | 變更 |
| :--- | :--- |
| `.agents/skills/code-review/scripts/audit_guardrails.py` | 2.1 |
| `.agents/lib/project_config.py` | 新增 `privacy.sensitive_extensions`、`project.business_skills` 綱要 |
| `.agents/project.toml` | 新增兩鍵；`baseline` 改值 |
| `.agents/security_baseline.json` → `.agents/project/security_baseline.json` | 搬移 |
| `.agents/PORTING.md`、`.agents/README.md` | 2.2、2.3 說明 |
| `tests/unit/test_github_pre_publish_hygiene.py` | 命中類別名稱改為 `personal_filename` |
| `.agents/tests/test_project_config.py` | 新鍵之缺鍵、型別測試；測試設定加入新鍵 |
| `.agents/tests/`（新增或擴充） | 自訂副檔名清單之偵測測試（如 `csv`）、空清單不啟用 |
| `tests/e2e/test_portable_closed_loop_e2e.py` | 基準檔路徑、業務技能改讀設定 |

## 四、衝突與重複檢查

* **與 Bug-0031～0033、Spec-0034**：皆修改閘門腳本，但涉及不同函式（分層檢查、環境變數同步、`verify_doc_sync.py`）；本案只改隱私檔名偵測與設定綱要，不重疊。見待決事項 4。
* **命中類別名稱**：只出現在 `audit_guardrails.py` 與上庫衛生測試；歷史 QA 報告中的舊名稱屬紀錄，不回改。
* **基準檔路徑**：`security_scan.py` 只讀 `baseline` 設定值，不寫死路徑，搬移後不需改程式。

## 五、規模

**大改**：修改驗證腳本與設定綱要（[governance.md](../../.agents/workflows/governance.md) 規模分級）。產出本規格與 `docs/qa_reports/0038-*.md`；程式部分另走 Gate 2 程式檢查項（G4 第 6 項）。不修改紅線，不另寫 ADR。

## 六、待決事項

| # | 問題 | 建議 | 替代方案 |
| :---: | :--- | :--- | :--- |
| 1 | 命中類別是否改名 | 改為 `personal_filename`，常數一併改名 | 保留 `personal_resume_filename`，只改副檔名設定（報告仍帶履歷字樣） |
| 2 | 業務技能清單放哪個區段 | 新增 `[project]` 區段 | 放入既有 `[docs]` 或 `[guardrails]`（語意不符） |
| 3 | quality-evaluation 技能 | 不修改（2.4） | 列入 `business_skills` 或新增 `optional_skills` 清單 |
| 4 | 是否與 Bug-0031～0033、Spec-0034 合併 | 分開處理，本案先行；四者皆改腳本但函式不重疊 | 合併為一份閘門腳本修正規格 |

## 七、驗收標準

* **AC-1**：`privacy.sensitive_extensions` 設為 `["csv"]` 時，敏感目錄下的 `<人名>.csv` 被判為 `personal_filename`，`<人名>.pdf` 不被判定；設為空清單時此項不啟用；缺鍵或型別錯誤時結束碼 2。
* **AC-2**：本專案執行 `audit_guardrails.py` 與上庫衛生測試，結果與修改前一致（零新增、零遺漏）。
* **AC-3**：`audit_guardrails.py` 與 `.agents/`（不含 `project/`）不含 `resume` 字樣之常數或類別名稱。
* **AC-4**：基準檔位於 `.agents/project/`，`security_scan.py` 讀取正常（基準內項目數與搬移前相同）。
* **AC-5**：`project.business_skills` 缺鍵或型別錯誤時結束碼 2；移植演練依此鍵刪除業務技能後兩支閘門腳本與 `.agents/tests` 通過。
* **AC-6**：`verify_doc_sync.py` 通過；全套單元測試、`.agents/tests` 與移植演練無回歸。

品質評測範圍：否（不涉及檢索、抽取或 LLM 生成）

安全評估範圍：否（隱私偵測行為於本專案不變，只將副檔名改為設定值；無新增對外介面、跨信任邊界資料流、外部相依或敏感資料處理）
