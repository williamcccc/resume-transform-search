# 提案與規格書：閉環核心之 DDD 前提明文化、對外介面去 CLI 預設、掃描說明去規格編號

> **狀態**：已實作（G2：使用者於 2026-11-21 核准，3 項待決事項全數採建議；QA 見 [QA-0043](../qa_reports/0043-ddd-premise-and-interface-neutral-qa.md)）｜**類型**：規範變更（大改：修改驗證腳本 `security_scan.py` 說明文字；其餘為小改內容）｜**流程**：[governance.md](../../.agents/workflows/governance.md)｜**影響範圍**：`.agents/PORTING.md`、`.agents/project.toml` 註解、角色檔與技能、技術規格範本（含 `docs/templates/` 鏡像）、`security_scan.py`，不涉及 `src/`、不修改紅線

## 一、動機

第五次以「通用核心＋專案實例檔」掃描，殘留文字已清除，剩三項核心前提與設定不一致：

| # | 問題 | 位置 | 後果 |
| :---: | :--- | :--- | :--- |
| 1 | 核心以 DDD 四層為前提，設定卻暗示非 DDD 專案可用 | `project.toml` `[layers]` 註解「非 DDD 專案設為 false」、PORTING 第 3 步同；但 AGENTS.md 第 1 節、通用紅線 1、角色檔與 feature-design、code-review、bug-triage、doc-sync、auto-fix 技能皆以 DDD 四層為前提 | 非 DDD 專案設 `enabled = false` 後，腳本不檢查分層，紅線 1 與技能卻仍要求 DDD，規則自相矛盾 |
| 2 | 對外介面預設為 CLI | architect 角色「REQUIREMENTS.md (CLI 指令與引數)」；doc-sync「CLI 參數對齊」與流程圖「命令清單」；doc_sync_checklist「CLI 入口命令同步」「CLI 使用範例更新」；技術規格範本「CLI 指令設計」；feature-design「表現層：CLI 旗標設計，保證 100% 向下相容」；auto-fix「不得變更 CLI 原有參數名稱」 | 無 CLI 之專案（純 Web、函式庫）套用不順；feature-design 一句等同將本專案紅線 2 寫入核心 |
| 3 | 使用者可見之說明含規格編號 | `security_scan.py` `--help` 顯示「Spec-0030」 | 移植後指向不存在的規格 |

## 二、修改內容

### 2.1 DDD 前提明文化（問題 1）

* PORTING「適用範圍」補一句：閉環核心（紅線 1、角色與技能）**以 DDD 四層與依賴反轉為前提**；非 DDD 專案可沿用流程與門禁，但須自行改寫紅線 1 與各技能之分層描述。
* PORTING 第 3 步與 `project.toml` 註解：「非 DDD 專案設 `enabled = false`」改為「`enabled = false` 只關閉自動分層檢查（如逐步導入 DDD 之專案）；紅線 1 與技能之分層規範仍適用」。

### 2.2 對外介面去 CLI 預設（問題 2）

以「對外介面（CLI 參數、API 端點等；本專案入口見專案概況）」取代只講 CLI 之處；已寫「CLI 與 API」並列者不動：

| 檔案 | 現行 | 改為 |
| :--- | :--- | :--- |
| architect/AGENT.md | REQUIREMENTS.md (CLI 指令與引數) | REQUIREMENTS.md (對外介面：CLI 指令、API 端點與參數) |
| doc-sync/SKILL.md 流程圖 | 核對 REQUIREMENTS.md 命令清單與參數說明 | 核對 REQUIREMENTS.md 對外介面與參數說明 |
| doc-sync/SKILL.md 階段 1 | **CLI 參數對齊**：若本次異動新增或修改了命令列參數 | **對外介面參數對齊**：若本次異動新增或修改了對外介面參數（CLI 參數、API 端點等） |
| doc_sync_checklist.md | **CLI 入口命令同步**、**CLI 使用範例更新** | **對外介面同步**、**使用範例更新**（命令列或 API 呼叫範例） |
| tech_spec_template.md（含鏡像） | **CLI 指令設計** ＋ `python <cli_entry>.py` 範例 | **對外介面設計**（CLI 指令、API 端點等擇一或並列），保留 CLI 範例並註明「以 CLI 為例」 |
| feature-design/SKILL.md | **【表現層】**：CLI 旗標設計，保證 100% 向下相容。 | **【表現層】**：對外介面（CLI 參數、API 端點等）設計與向下相容策略。 |
| auto-fix/SKILL.md | 不得因為修復 bug 而變更 CLI 原有參數名稱 | 不得因為修復 bug 而變更對外介面（CLI 參數、API 端點等）既有名稱 |

技術規格範本第 18 行之 Interfaces 列（`<layers.interfaces>/cli/`）為舉例列，保留。

### 2.3 掃描說明去規格編號（問題 3）

* `security_scan.py` `argparse` 說明：「Gate 2 通用安全掃描（Semgrep + pip-audit，Spec-0030）」→「Gate 2 通用安全掃描（Semgrep + pip-audit）」。
* 腳本與程式庫之註解、docstring 中的「Spec-00xx」來源註記不改（不對使用者顯示、不斷鏈）。

## 三、衝突與重複檢查

| 檢查 | 結果 |
| :--- | :--- |
| 與既有規則矛盾 | 消除既有矛盾（問題 1）；本專案紅線 2（CLI 向下相容）不受影響，仍由本專案紅線小節約束 |
| 同一規則寫在兩處 | 消除重複：feature-design 不再重述本專案紅線 2 |
| 紅線 | 不修改 AGENTS.md |
| 守護測試 | 不新增；既有中性化與歷史引用守護持續適用 |

## 四、規模

**大改**：修改驗證腳本 `security_scan.py`（僅說明字串）。產出本規格與 QA 報告；不涉及紅線，不寫 ADR。若待決 3 選擇不改 `security_scan.py`，本案降為小改（G1 記於 PR 描述，不另寫 QA 報告）。

## 五、待決事項

| # | 問題 | 建議 | 替代方案 |
| :---: | :--- | :--- | :--- |
| 1 | DDD 前提之處理方式 | **明文化前提**：核心以 DDD 為前提，`enabled = false` 只關自動檢查 | 核心 DDD 文字全面改為條件式（涉及紅線 1，須 ADR，改動面大） |
| 2 | 技術規格範本 CLI 範例 | **保留範例並註明「以 CLI 為例」** | 刪除範例，只留通用描述 |
| 3 | `security_scan.py` 說明是否一併修改 | **一併修改**（走大改） | 不改，本案降為小改 |

## 六、驗收條件

品質評測範圍：否

安全評估範圍：否

* **AC-1**：PORTING 適用範圍明文核心以 DDD 為前提；PORTING 與 `project.toml` 不再寫「非 DDD 專案設 false」。
* **AC-2**：第 2.2 節所列 7 處不再只以 CLI 表述對外介面；技術規格範本正本與鏡像一致。
* **AC-3**：`security_scan.py --help` 不含規格編號。
* **AC-4**：`verify_doc_sync.py`、`audit_guardrails.py`、`security_scan.py` 通過；`tests/unit`（含斷鏈）、`.agents/tests`、移植演練全數通過。
