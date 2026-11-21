# 提案與規格書：守護字詞移入專案實例、核心規範去除寫死的 src/

> **狀態**：G1 提案（待 G2 使用者核准）｜**類型**：規範變更（大改：修改驗證用程式庫與設定 schema）｜**流程**：[governance.md](../../.agents/workflows/governance.md)｜**影響範圍**：`.agents/lib/project_config.py`、`.agents/project.toml`、`.agents/tests/`、核心規範與範本文字、PORTING，不涉及 `src/`

## 一、動機

以「通用核心＋專案實例檔」重掃後，剩三類不符：

| # | 問題 | 位置 | 後果 |
| :---: | :--- | :--- | :--- |
| 1 | 核心自我測試寫死本專案識別字 | [test_neutral_examples.py](../../.agents/tests/test_neutral_examples.py) `PROJECT_IDENTIFIERS`、[test_review_checklist_portable.py](../../.agents/tests/test_review_checklist_portable.py) `PROJECT_TERMS` 與第 55 行；`test_quality_ac_gate`、`test_security_ac_gate` 測試資料含「履歷」 | 測試隨核心移植，移植後仍守本專案字詞，新專案的業務名詞無人守護，守護形同失效 |
| 2 | 核心規範寫死 `src/` | AGENTS.md 分流表「且不改 `src/`」、[governance.md](../../.agents/workflows/governance.md) 第 3–4 行、缺陷報告與 QA 報告範本之 `src/...py` 佔位（含 `docs/templates/` 鏡像） | 原始碼根目錄不是 `src/` 的專案，規則文字與實際不符 |
| 3 | 技能殘留本專案外部服務 | [bug-triage SKILL.md](../../.agents/skills/bug-triage/SKILL.md) 第 48 行「真實 CLI 或 Redis」 | 通用技能寫入本專案技術元件 |

## 二、修改內容

### 2.1 守護字詞移入 `project.toml`（問題 1）

`[project]` 新增兩鍵（正規式字串清單，TOML 單引號字面字串）：

```toml
[project]
# 本專案業務與元件識別字：全部核心 Markdown 不得出現（test_neutral_examples）
identifiers = ['履歷', '候選人', '求職', '招募', 'resume', 'Resume', 'convert_to_md', ...]
# 本專案技術元件名：須技術中立之核心檢核清單不得出現（test_review_checklist_portable）；其他核心文件可作通用舉例
stack_terms = ['Redis', 'Gemini', 'PDF', 'Docx', 'DOCX']
```

* `identifiers` 內容為現行 `PROJECT_IDENTIFIERS` 去除「本專案為」後之各項，另加 `\bsrc/`（見待決 4）。
* 「本專案為」附註屬通用規則（任何專案皆不得在核心寫附註），留在測試程式內。
* `test_neutral_examples` 改讀 `identifiers`；`test_review_checklist_portable` 改讀 `identifiers` ∪ `stack_terms`。
* `project_config.py` schema 新增兩鍵（`str_list`），並驗證每項皆為合法正規式（不合法時結束碼 2 並指出鍵名與該項）。
* `test_quality_ac_gate`、`test_security_ac_gate` 測試資料之「履歷」改為中性內容（如「文件可被檢索」）。
* PORTING 第 2 步（改寫 `project.toml`）補述兩鍵之填寫方式；`test_project_config.py` 範例設定補兩鍵。

### 2.2 核心規範去除寫死的 `src/`（問題 2）

* AGENTS.md 分流表：「且不改 `src/`」→「且不改原始碼（`layers.src`）」。
* governance.md 第 3–4 行同樣改寫。
* 缺陷報告範本、QA 報告範本（`.agents/` 正本與 `docs/templates/` 鏡像）：`src/...py`、`src/xxx.py` → `<layers.src>/...py`、`<layers.src>/xxx.py`。

### 2.3 技能殘留（問題 3）

* bug-triage 第 48 行：「真實 CLI 或 Redis」→「真實 CLI 或外部服務」。

### 2.4 不改的項目（評估後保留）

* Windows 檔案鎖說明：以 `with` 釋放控制代碼為跨平台通則，Windows 為最常見情境。
* `redis.hget`、`google-genai` 等通用技術舉例：守護規則允許。
* `prompts/`、`tests/eval/`、`REQUIREMENTS.md`、`ARCHITECTURE.md`：閉環文件約定，PORTING 第 7 步建立骨架。
* `.github/workflows/ci.yml`：專案檔，PORTING 已建議加入自我測試步驟。

## 三、衝突與重複檢查

| 檢查 | 結果 |
| :--- | :--- |
| 與既有規則矛盾 | 無。守護範圍與嚴格度不變，只把「守哪些字」改由實例宣告 |
| 同一規則寫在兩處 | 消除既有重複：兩支測試各自寫死的字詞清單合併為 `project.toml` 一處 |
| 紅線 | 不修改第 1 節；AGENTS.md 只改第 2 節分流表一格，行數不變 |
| 專屬標記數 | 不變 |

## 四、規模

**大改**：修改驗證用程式庫（`project_config.py` schema）。產出本規格與 QA 報告；不涉及紅線，不寫 ADR。

## 五、待決事項

| # | 問題 | 建議 | 替代方案 |
| :---: | :--- | :--- | :--- |
| 1 | 字詞格式 | **正規式清單**：可表達 `\b768\b`、`(?<!功能)切片` 等現有規則 | 純字串清單（較易填寫，但現有 2 條規則無法表達，須放寬） |
| 2 | 清單數量 | **兩份**：`identifiers`（全核心禁用）＋ `stack_terms`（只限技術中立檢核清單）；保留「如 Redis」等通用舉例 | 一份：技術元件名也全核心禁用，須改寫 unit-testing 等技能中的通用舉例 |
| 3 | 鍵是否必填 | **必填**（可為空清單），移植時缺鍵即結束碼 2，強迫逐鍵確認；與 `business_skills` 一致 | 選填，缺鍵視為空清單（移植時容易遺漏） |
| 4 | `identifiers` 是否加入 `\bsrc/` | **加入**，問題 2 修正後由守護測試防止再寫回 | 不加入，只修文字 |

## 六、驗收條件

品質評測範圍：否

安全評估範圍：否

* **AC-1**：兩支守護測試不含寫死的本專案字詞，改讀 `project.toml`；以「實例清單加入新字詞、核心文件出現該字詞」之情境驗證測試失敗。
* **AC-2**：`project.toml` 缺 `identifiers` 或 `stack_terms`、或任一項非合法正規式時，`load_project_config` 結束碼 2 並指出鍵名。
* **AC-3**：核心 Markdown（含範本鏡像）不含寫死的 `src/`；bug-triage 不含 Redis；`.agents/tests` 測試資料不含 `identifiers` 字詞。
* **AC-4**：`verify_doc_sync.py`、`audit_guardrails.py`、`security_scan.py` 通過；`tests/unit`、`.agents/tests`、移植演練全數通過（移植演練之假專案設定補兩鍵）。
