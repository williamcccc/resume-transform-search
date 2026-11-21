# 提案與規格書：核心文件去除本專案歷史連結、範本與核心 Python 殘留清理

> **狀態**：G1 提案（待 G2 使用者核准）｜**類型**：規範變更（大改：修改驗證腳本 `audit_guardrails.py` 之說明文字）｜**流程**：[governance.md](../../.agents/workflows/governance.md)｜**影響範圍**：`.agents/PORTING.md`、`security_nfr_framework.md`、技術規格範本（含鏡像）、`.agents/tests/` 說明文字與守護測試、`audit_guardrails.py` 說明文字、`project.toml`，不涉及 `src/`

## 一、動機

以「通用核心＋專案實例檔」第三次掃描，剩三項不符：

| # | 問題 | 位置 | 後果 |
| :---: | :--- | :--- | :--- |
| 1 | 核心文件連結本專案規格歷史 | [PORTING.md](../../.agents/PORTING.md) 第 3、7 行連至 `docs/specs/0028`、`0035`、`0036`、`0037`，第 51 行「Spec-0034」；[security_nfr_framework.md](../../.agents/skills/feature-design/references/security_nfr_framework.md) 第 5 行連至 `docs/specs/0030`，第 125 行「Spec-0034」 | 移植只複製 `.agents/`，新專案無這些規格檔，連結斷裂；編號指向原專案歷史，對新專案無意義 |
| 2 | 技術規格範本殘留本專案流程 | [tech_spec_template.md](../../.agents/skills/feature-design/references/tech_spec_template.md) 第 104 行「CLI 轉換指定樣本｜產出完整 Markdown，品管通過」（含 `docs/templates/` 鏡像） | 範本寫入本專案轉檔與品管閥流程 |
| 3 | 核心 Python 說明文字殘留，守護測試未涵蓋 | 7 支核心測試之模組 docstring「不讀取本機 data/ 或 resume/」（`test_guardrail_gaps` 另含 `app/`）；`audit_guardrails.py` 第 61 行舉例 `'src/domain'` | 守護測試只掃 Markdown，核心 `.py` 之本專案字詞無人守護 |

## 二、修改內容

### 2.1 去除核心文件之歷史連結與編號（問題 1）

* PORTING 第 3、7 行：刪除「（[Spec-0028](…)）」等括號連結，句意不變。第 51 行「（Spec-0034）」刪除。
* security_nfr_framework 第 5 行「**來源**」整行刪除；第 125 行「（Spec-0034）」刪除。
* [test_neutral_examples.py](../../.agents/tests/test_neutral_examples.py) 新增守護：核心 Markdown 不得連結 `docs/(specs|qa_reports|adr|bugs)/` 下之編號檔，亦不得出現 `Spec-`、`ADR-`、`QA-`、`Bug-` 加四位數編號（見待決 1）。此為通用規則，固定於測試程式。

### 2.2 範本殘留（問題 2）

* 技術規格範本第 104 行（正本與鏡像）：「CLI 轉換指定樣本｜產出完整 Markdown，品管通過」→「處理指定樣本｜產出符合規格之結果」（比照 QA 報告範本 TC-01 寫法）。

### 2.3 核心 Python 殘留與守護範圍（問題 3）

* 7 支核心測試 docstring：「不讀取本機 data/ 或 resume/」→「不讀取本機敏感目錄（`privacy.sensitive_dirs`）」；`test_guardrail_gaps` 之 `app/` 改為「假專案原始碼目錄」。
* `audit_guardrails.py` 第 61 行：舉例改為 `'pkg/domain' → 'pkg.domain'`。
* 守護測試擴大至核心 Python（見待決 2）：
  * `.agents/lib/`、`.agents/skills/*/scripts/`（業務技能除外）：全文比對 `identifiers`。
  * `.agents/tests/`：只比對模組 docstring（測試夾具需操作路徑字串，如假專案 `app/` 目錄與設定改寫，不納入）。
* `project.toml` `identifiers` 新增 `'(?<![\w/.])data/'`（見待決 3；`tests/eval/data/` 不受影響）。

### 2.4 不改的項目

* 核心 `.py` 註解中的「Spec-00xx」來源註記：非連結、不斷鏈，逐一移除成本高。
* 對外介面預設 CLI 之寫法：本次不處理（使用者選定 1–3 項）。

## 三、衝突與重複檢查

| 檢查 | 結果 |
| :--- | :--- |
| 與既有規則矛盾 | 無。PORTING 與安全框架之規則內容不變，只去除來源連結 |
| 同一規則寫在兩處 | 無新增；歷史來源仍記錄於各規格與 `docs/README.md` 索引 |
| 紅線 | 不修改 AGENTS.md |
| 另發現（不在本案範圍） | `privacy.sensitive_dirs` 未含 `data`，但紅線 7 本專案補充與專案概況第 5 節皆將 `data/` 列為禁止單元測試讀取之目錄；`.gitignore` 已排除 `data/`。是否補入 `sensitive_dirs` 會影響 `audit_guardrails.py` 隱私掃描結果，建議另案評估 |

## 四、規模

**大改**：修改驗證腳本 `audit_guardrails.py`（僅說明文字）。產出本規格與 QA 報告；不涉及紅線，不寫 ADR。

## 五、待決事項

| # | 問題 | 建議 | 替代方案 |
| :---: | :--- | :--- | :--- |
| 1 | 核心文件中的規格編號 | **連結與編號一併移除**，並由守護測試禁止 | 只移除連結、保留「Spec-0028」純文字（不斷鏈，但移植後指向不存在的歷史） |
| 2 | 守護核心 Python 的範圍 | **腳本與程式庫全文＋測試只看模組 docstring** | 測試也全文比對：須把假專案夾具的 `app/` 等路徑改為由設定推導，改動面大；或維持只掃 Markdown |
| 3 | `identifiers` 是否加入 `data/` | **加入**，與紅線 7 本專案補充一致 | 不加入，只修 docstring 文字 |

## 六、驗收條件

品質評測範圍：否

安全評估範圍：否

* **AC-1**：核心 Markdown 無 `docs/(specs|qa_reports|adr|bugs)/` 編號檔連結與 `Spec-`／`ADR-`／`QA-`／`Bug-` 編號；寫回時守護測試失敗。
* **AC-2**：技術規格範本（正本與鏡像）不含「Markdown」「品管」。
* **AC-3**：核心腳本、程式庫與測試 docstring 不含 `identifiers` 字詞；寫回時守護測試失敗；移植演練於新專案字詞下通過。
* **AC-4**：`verify_doc_sync.py`、`audit_guardrails.py`、`security_scan.py` 通過；`tests/unit`（含斷鏈）、`.agents/tests`、移植演練全數通過。
