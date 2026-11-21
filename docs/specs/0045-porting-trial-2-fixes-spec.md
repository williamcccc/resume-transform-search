# 提案與規格書：第二次移植實測卡點修正（自我測試路徑假設、空清單誤判、空目錄致 CI 失敗）

> **狀態**：已實作（G2：使用者於 2026-11-21 核准，2 項待決事項全數採建議；QA 見 [QA-0045](../qa_reports/0045-porting-trial-2-fixes-qa.md)）｜**類型**：規範變更（大改：修改驗證腳本 `verify_doc_sync.py`、`audit_guardrails.py` 與核心自我測試）｜**流程**：[governance.md](../../.agents/workflows/governance.md)｜**影響範圍**：`.agents/skills/doc-sync/scripts/verify_doc_sync.py`、`.agents/skills/code-review/scripts/audit_guardrails.py`、`.agents/tests/`、`.agents/PORTING.md`，不涉及 `src/`、不修改紅線

## 一、動機

2026-11-21 以與第一次實測差異最大之參數再做移植實測：對外 API 服務（internet、ASVS L2、多使用者、JWT）、主分支 `master`、原始碼根目錄 `service/` 且層名為 `usecases`／`adapters`／`api`、設定模組為根目錄 `settings.py`、環境變數範本 `.env.sample`、守護與隱私清單幾乎全空、新增一個業務技能、撰寫首份安全範圍規格。三支閘門腳本通過，違規植入探測全數抓到；但：

| # | 卡點 | 實測現象 | 根因 |
| :---: | :--- | :--- | :--- |
| A | `test_guardrail_gaps` 假專案路徑與設定不符 | 自我測試 10 項失敗：設定指向 `service/usecases`、`.env.sample`，假專案建於 `app/` | 假專案讀取實例設定後只把 `"src/"` 換為 `"app/"`，假設原專案之層名與範本檔名 |
| B | 守護清單全空時誤判 | `test_review_checklist_portable` 8 項失敗 | `identifiers`、`stack_terms` 皆空時組出空正規式，任何文字皆命中（`test_neutral_examples` 已防，本檔漏防） |
| D | 空目錄不進版控 | 乾淨 clone 後 `verify_doc_sync.py` FAIL「`docs/qa_reports`、`docs/bugs` 目錄不存在」 | git 不追蹤空目錄；新專案於首份 QA 報告與缺陷報告前 CI 第 2 步必紅 |
| C | 訊息寫死範本檔名 | 範本為 `.env.sample`，訊息仍寫「.env.example」 | `audit_guardrails.py` 字串寫死 |
| E | 停用分層後結語誤導 | 分層檢查已跳過，結語仍稱「架構分層…完全符合規格」 | 結語未區分停用情形 |

移植演練固定使用 `app/`、預設層名、`.env.example` 與非空守護清單，故 A、B 未被測出。

## 二、修改內容

### 2.1 假專案自建分層與設定（卡點 A）

* `test_guardrail_gaps.py` 之設定改寫：逐鍵覆寫 `[layers]` 全部路徑鍵（`src`、`domain`、`application`、`infrastructure`、`interfaces`、`domain_interfaces`）與 `[config]` 之 `module`、`env_example` 為假專案自身之值，不再依賴實例設定之字面內容。
* 新增回歸測試：以層名與範本檔名皆不同於預設之合成設定（`service/usecases`、`.env.sample`）建立假專案，基準案例須零 P0。

### 2.2 空清單永不命中（卡點 B）

* `test_review_checklist_portable.py` 之字詞樣式於清單皆空時改為永不命中（與 `test_neutral_examples` 一致）；抽出組樣式函式並加單元測試（空清單、單一字詞）。

### 2.3 尚無報告之目錄不視為失敗（卡點 D）

* `verify_doc_sync.py`：`docs/specs/`、`docs/qa_reports/`、`docs/bugs/` 不存在時由 FAIL 改為 WARN（「尚無…，目錄不存在」）；目錄存在時之檢查不變。`docs/adr/` 與四份核心文件（含索引）仍為必要（見待決 1）。
* PORTING 第 7 步補述：空目錄不進版控，於首份文件建立前不存在屬正常。

### 2.4 訊息修正（卡點 C、E）

* `audit_guardrails.py`：環境變數同步相關 3 處訊息改用設定之 `config.env_example` 檔名。
* `audit_guardrails.py`：`layers.enabled = false` 時結語附註「（DDD 分層檢查已停用）」，不宣稱分層符合規格。

### 2.5 PORTING 補述（實測觀察）

* 第 3 步 `[guardrails]`：`url_schemes` 為空即停用寫死連線 URL 檢查，僅於確無外部連線時清空。

## 三、衝突與重複檢查

| 檢查 | 結果 |
| :--- | :--- |
| 與既有規則矛盾 | 無。`docs/` 目錄存在時之檢查強度不變；空目錄 WARN 只影響「尚無文件」情形 |
| 同一規則寫在兩處 | 消除重複：兩支守護測試之空清單處理一致 |
| 紅線 | 不修改 AGENTS.md |

## 四、規模

**大改**：修改驗證腳本。產出本規格與 QA 報告；不涉及紅線，不寫 ADR。

## 五、待決事項

| # | 問題 | 建議 | 替代方案 |
| :---: | :--- | :--- | :--- |
| 1 | 空目錄處理 | **腳本改為 WARN**：CI 不因尚無文件而失敗，移植者無須額外動作 | PORTING 要求於空目錄放 `.gitkeep`（只改文字，但依賴移植者記得） |
| 2 | 卡點 A 之回歸測試放哪裡 | **`test_guardrail_gaps.py` 內以合成設定建立假專案**（自包含，執行快） | 移植演練改用 `service/` 與非預設層名（改動面大，演練多處寫死 `app/`） |

## 六、驗收條件

品質評測範圍：否

安全評估範圍：否

* **AC-1**：層名與範本檔名非預設之設定下，`test_guardrail_gaps` 全數通過；回歸測試於修正前失敗、修正後通過。
* **AC-2**：守護清單皆空時，`test_review_checklist_portable` 全數通過；組樣式函式空清單永不命中。
* **AC-3**：`docs/specs`、`docs/qa_reports`、`docs/bugs` 不存在時 `verify_doc_sync.py` 結束碼 0 並印 WARN；目錄存在而文件未登錄索引時仍 FAIL。
* **AC-4**：範本檔名為 `.env.sample` 時訊息顯示 `.env.sample`；分層停用時結語含停用附註。
* **AC-5**：以修正後核心重做第二次實測（同參數、乾淨 clone）：三支腳本通過、自我測試全數通過。
* **AC-6**：本專案 `verify_doc_sync.py`、`audit_guardrails.py`、`security_scan.py` 通過；`tests/unit`（含斷鏈）、`.agents/tests`、`.agents/tests/e2e`、移植演練全數通過。
