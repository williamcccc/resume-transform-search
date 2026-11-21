# 提案與規格書：移植實測卡點修正（自我測試寫死 scheme、選用檔案斷鏈、表格陣列清空說明）

> **狀態**：G1 提案（待 G2 使用者核准）｜**類型**：規範變更（大改：修改驗證用程式庫 `project_config.py` 錯誤訊息與核心自我測試）｜**流程**：[governance.md](../../.agents/workflows/governance.md)｜**影響範圍**：`.agents/PORTING.md`、`.agents/lib/project_config.py`、`.agents/tests/`、`tests/e2e/test_portable_closed_loop_e2e.py`，不涉及 `src/`、不修改紅線

## 一、動機

2026-11-21 依 PORTING 第 1–8 步將閉環移植至全新示範專案（`app/` 四層、PostgreSQL、CLI、無 Web／API／LLM），三支閘門腳本通過，核心自我測試 173 項中 1 項失敗，另記錄 5 項卡點：

| # | 卡點 | 實測現象 | 根因 |
| :---: | :--- | :--- | :--- |
| 1 | 自我測試寫死 `redis://` | `TestHardcodedUrlMessageIsNeutral` 失敗：新專案 `url_schemes` 不含 `redis`，寫死 URL 未被偵測 | 測試假設實例設定值；移植演練未改 `url_schemes`，故未測出 |
| 2 | 刪除 `quality-evaluation` 留下斷鏈 | architect、gatekeeper、feature.md（2 處）、feature-design、qa-testing 共 6 處連結失效 | PORTING 允許刪除，未列出相依引用 |
| 3 | 未複製 `GEMINI.md` 留下斷鏈 | AGENTS.md、`.agents/README.md` 連結失效 | PORTING 將其列為選用 |
| 4 | 刪除基準檔留下斷鏈 | PORTING、`.agents/README.md` 連結失效；首次掃描零發現時不重建 | 第 4 步要求「直接刪除」 |
| 5 | `url_exceptions` 無法照字面清空 | 刪除 `[[guardrails.url_exceptions]]` 表格後報「缺少必要鍵」 | 表格陣列之空值須寫成 `url_exceptions = []` 且置於區段內；PORTING 與錯誤訊息皆未說明 |
| 6 | PORTING 第 3 行文字錯誤 | 「分兩處存放」下列三項 | 歷次修訂未同步 |

卡點 2–4 未被發現，因 `verify_doc_sync.py` 不檢查連結，斷鏈測試位於專案側 `tests/unit/`，不隨核心移植。

## 二、修改內容

### 2.1 自我測試改讀實例設定（卡點 1）

* `TestHardcodedUrlMessageIsNeutral` 改用假專案設定之 `url_schemes` 第一項組成樣本 URL；清單為空時 `skipTest`（附理由）。
* 移植演練 `_rewrite_project_toml` 將 `url_schemes` 改為與原專案不同之值（如 `["postgres", "https"]`），使此類假設日後可被測出。

### 2.2 選用檔案不再造成斷鏈（卡點 2–4）

* **品質評測（卡點 2）**：PORTING 第 5 步改為「無檢索或 LLM 功能的專案**不必刪除**品質評測規則與 `quality-evaluation` 技能；規格一律宣告 `品質評測範圍：否`，技能不會被觸發」（見待決 1）。
* **GEMINI.md（卡點 3）**：PORTING 第 1 步改為一律複製 `GEMINI.md`（薄層檔，不使用 Antigravity 時亦無害）（見待決 2）。
* **基準檔（卡點 4）**：PORTING 第 4 步「直接刪除」改為「內容清空為 `{"findings": []}`」，保留檔案，連結不斷。
* **防再犯**：新增核心自我測試 `test_core_links.py`：核心 Markdown（AGENTS.md、CLAUDE.md、GEMINI.md、`.agents/**`、`.claude/**`，業務技能除外）之相對連結必須存在；連往核心以外（`docs/`、專案根目錄文件）者不檢查（見待決 3）。

### 2.3 表格陣列清空說明（卡點 5）

* PORTING 第 3 步 `[guardrails]` 補述：清空 `url_exceptions` 時，刪除 `[[guardrails.url_exceptions]]` 表格並於 `[guardrails]` 區段內寫 `url_exceptions = []`；`[security]` 之 `not_applicable` 同理。
* `project_config.py`：`exception_list`／`item_reason_list` 缺鍵時，錯誤訊息附提示「無項目時於該區段內寫 `<key> = []`」。

### 2.4 文字錯誤（卡點 6）

* PORTING 第 3 行「分兩處存放」→「分三處存放」。

## 三、衝突與重複檢查

| 檢查 | 結果 |
| :--- | :--- |
| 與既有規則矛盾 | 無。品質評測規則不刪除時，「每份規格宣告品質評測範圍」之既有強制（`verify_doc_sync.py`）反而與 AGENTS.md 保持一致；原「可刪除」與該強制本有落差 |
| 同一規則寫在兩處 | 新連結測試只管核心內部連結；專案側斷鏈測試（`tests/unit/`）照舊管全倉，兩者範圍不重疊於規則來源 |
| 紅線 | 不修改 AGENTS.md |

## 四、規模

**大改**：修改驗證用程式庫（`project_config.py` 錯誤訊息）與核心自我測試。產出本規格與 QA 報告；不涉及紅線，不寫 ADR。

## 五、待決事項

| # | 問題 | 建議 | 替代方案 |
| :---: | :--- | :--- | :--- |
| 1 | 無 LLM 專案之品質評測內容 | **不刪除**，規格宣告「否」即可 | 保留「可刪除」，PORTING 列出 6 處相依連結供一併修改（易漏，且 `verify_doc_sync.py` 仍強制宣告） |
| 2 | GEMINI.md | **一律複製** | 維持選用，AGENTS.md 與 README 改為不加連結之純文字 |
| 3 | 核心連結檢查放哪裡 | **核心自我測試**（`.agents/tests/test_core_links.py`，隨核心移植） | 加入 `verify_doc_sync.py`（屬驗證腳本，CI 第 2 步即執行；改動面較大） |

## 六、驗收條件

品質評測範圍：否

安全評估範圍：否

* **AC-1**：`url_schemes` 不含 `redis` 之假專案中，`TestHardcodedUrlMessageIsNeutral` 通過；移植演練改寫 `url_schemes` 後全數通過。
* **AC-2**：核心連結測試於本專案通過；刻意加入一條指向不存在核心檔之連結時失敗；連往 `docs/` 者不檢查。
* **AC-3**：PORTING 第 1、3、4、5 步與第 3 行依第二節修改；`project_config.py` 表格陣列缺鍵訊息含 `= []` 提示（單元測試驗證）。
* **AC-4**：以修改後之核心重做移植實測（同一示範專案設定），自我測試全數通過、核心零斷鏈。
* **AC-5**：`verify_doc_sync.py`、`audit_guardrails.py`、`security_scan.py` 通過；`tests/unit`（含斷鏈）、`.agents/tests`、移植演練全數通過。
