# 提案與規格書：第三輪移植實測卡點修正（套件根名推導、原始碼掃描範圍、設定檔 BOM、pyproject 依賴掃描）

> **狀態**：已實作（G2：使用者於 2026-11-21 核准，4 項待決事項全數採建議；QA 見 [QA-0047](../qa_reports/0047-porting-trial-3-fixes-qa.md)）｜**類型**：規範變更（大改：修改驗證腳本 `audit_guardrails.py`、`security_scan.py` 與設定載入器）｜**流程**：[governance.md](../../.agents/workflows/governance.md)｜**影響範圍**：`.agents/lib/project_config.py`、`.agents/skills/code-review/scripts/audit_guardrails.py`、`.agents/skills/code-review/scripts/security_scan.py`、`.agents/skills/doc-sync/scripts/verify_doc_sync.py`、`.agents/project.toml`、`.agents/tests/`、`tests/e2e/test_portable_variants_e2e.py`、`.agents/PORTING.md`，不涉及 `src/`、不修改紅線

## 一、動機

2026-11-21 以五組新參數（避開 Spec-0044～0046 用過之佈局）各建真實 git 空專案移植，commit 後乾淨 clone 驗證並逐項植入違規：

| 組 | 主題 | verify_doc_sync | audit_guardrails | security_scan | 核心自我測試 |
| :---: | :--- | :---: | :---: | :---: | :---: |
| V1 | 扁平根目錄：`layers.src = "."`，四層位於倉庫根 | 通過 | **833 項 P0** | 通過 | 通過 |
| V2 | `project.toml` 存為 UTF-8 BOM + CRLF | **結束碼 2** | **結束碼 2** | **結束碼 2** | **全數 ERROR** |
| V2b | 對照：只有 CRLF、無 BOM | 通過 | 通過 | 通過 | 通過 |
| V3 | src-layout：`src/widgetkit/`，import 根名 `widgetkit`；依賴只寫於 `pyproject.toml` | 通過 | **2 項 P0** | **pip-audit 錯誤** | 通過 |
| V4 | 內網多使用者 Web、ASVS L2、JWT；首份規格（安全範圍：是）、QA、ADR、缺陷報告 | 通過 | 通過 | 通過 | 通過 |
| V5 | 業務技能 1 個、缺一層目錄、自訂守護清單、主分支 `release` | 通過 | 通過 | 通過 | 通過 |

違規探測（Domain 引第三方、Application 引外層、環境變數未列範本、測試含手機號碼、Semgrep `shell=True`，V5 另加 4 項自訂守護）於可判定之組別全數抓到；卡點如下：

| # | 卡點 | 實測現象 | 根因 |
| :---: | :--- | :--- | :--- |
| A | 套件根名由路徑推導 | V1：`from domain.entity import …` 判為「Domain 引入外部第三方套件」；V3：合法之 `from widgetkit.domain…` 同樣誤判，且 Application 引用外層被歸類為「第三方套件」而非「違反依賴反轉」 | `audit_guardrails.py` 以 `layers.src` 第一段為套件名（`.` → 空字串、`src/widgetkit` → `src`），各層模組名亦由路徑直譯；設定無法宣告實際 import 根名 |
| B | 原始碼掃描不排除工具與虛擬環境 | V1：資源、例外、提示詞、環境變數同步等檢查掃進 `.venv-tools/`（800 餘項）與 `.agents/tests/` | 以 `SRC_DIR.rglob` 掃描之檢查未套用 `ignore_scan_dirs`；`src` 為倉庫根時涵蓋閉環核心 |
| C | 設定檔 BOM 致全面中止 | 訊息「語法錯誤: Invalid statement (at line 1, column 1)」，未提示 BOM | 設定載入器以位元組交給 `tomllib`，不接受 BOM；Windows PowerShell 5.1 `Out-File` 等預設寫入 BOM |
| D | 依賴掃描不支援 `pyproject.toml` | `pip-audit -r pyproject.toml` 失敗：「Invalid requirement … line 1」 | `security_scan.py` 一律以 `-r` 視為 requirements 格式；PORTING 未說明格式限制。實測 `pip-audit <專案目錄>` 可正確解析 `pyproject.toml` |
| E | STRIDE 字母在第一欄不被認得 | 威脅表 STRIDE 欄置於第一欄時 FAIL「缺少 STRIDE 威脅表」；依範本置第 2 欄則通過 | `STRIDE_ROW_PATTERN` 要求字母前至少兩個 `\|` |
| F | `infrastructure`／`interfaces` 層目錄不存在時不報 | V5 刪除 `core/interfaces/` 仍「設定路徑驗證 Pass」 | `check_configured_paths` 只驗 `src`、`domain`、`application`；屬逐步建層之合理容許，但 PORTING 未說明 |

既有移植演練與 Spec-0046 參數化變體皆以「`src` 第一段即 import 根名」之佈局（`app/`、`lib/`、`service/`）建立，故 A、B 未被測出。

## 二、修改內容

### 2.1 宣告 import 根名（卡點 A）

* `[layers]` 新增**選填**鍵 `package`：`layers.src` 目錄對應之 Python 模組路徑。未設定時沿用現行推導（`src` 路徑轉模組名），既有專案不需改設定。
  * src-layout：`src = "src/widgetkit"`、`package = "widgetkit"`。
  * 扁平根目錄：`src = "."`、`package = ""`（各層目錄即頂層套件）。
* `audit_guardrails.py`：各層模組名改為「`package` + 該層相對 `src` 之路徑」；專案內部根模組改為 `package` 第一段，`package` 為空時為各層目錄之頂層名稱集合。
* `project_config.py`：SCHEMA 支援選填鍵（缺鍵不報錯、有值時驗型別）；`package` 為本專案唯一之選填鍵。
* 本專案 `project.toml` 於 `[layers]` 加註解說明（不設值，行為不變）。

### 2.2 原始碼掃描排除範圍（卡點 B）

* `audit_guardrails.py` 抽出共用之原始碼檔案列舉函式，所有以 `layers.src` 為範圍之檢查改用之：排除 `__pycache__`、`ignore_scan_dirs` 所列目錄與閉環核心 `.agents/`（見待決 2）。

### 2.3 設定檔 BOM（卡點 C）

* `project_config.py`：以 `utf-8-sig` 解碼後 `tomllib.loads`，接受 BOM（見待決 3）。

### 2.4 pyproject 依賴掃描（卡點 D）

* `security_scan.py`：`dependency_files` 項目檔名為 `pyproject.toml` 時，改以 `pip-audit <該檔所在目錄>` 掃描；其餘維持 `-r`。差異掃描判斷「需求檔有變更」之邏輯不變。
* PORTING 第 3 步 `[security.tools]`：註明可填 requirements 格式檔或 `pyproject.toml`。

### 2.5 STRIDE 表格容許第一欄（卡點 E）

* `verify_doc_sync.py`：`STRIDE_ROW_PATTERN` 改為任一儲存格（含第一欄）只含單一 STRIDE 字母即算。

### 2.6 PORTING 補述（卡點 A、F）

* 第 3 步 `[layers]`：說明 `package` 之用途與兩種佈局寫法；`infrastructure`、`interfaces` 目錄可於首份規格前尚未建立（只驗 `src`、`domain`、`application`）。

### 2.7 防再犯：參數化演練新增變體

* `tests/e2e/test_portable_variants_e2e.py` 新增兩個變體：「扁平根目錄」（`src = "."`、`package = ""`，並於假專案建立 `.venv-tools/` 假套件檔）與「src-layout」（`src/widgetkit`、`package = "widgetkit"`、`pyproject.toml` 依賴檔）；兩者核心自我測試、`verify_doc_sync.py`、`audit_guardrails.py` 須零 P0。

## 三、衝突與重複檢查

| 檢查 | 結果 |
| :--- | :--- |
| 與既有規則矛盾 | 無。`package` 未設定時行為與現行相同；排除 `ignore_scan_dirs` 與該清單「全倉隱私掃描略過」之既有語意一致，`.agents/` 仍受全倉隱私掃描 |
| 同一規則寫在兩處 | 消除重複：原始碼檔案列舉由 5 處 `SRC_DIR.rglob` 收斂為 1 個函式 |
| 紅線 | 不修改 AGENTS.md；紅線 1 之分層檢查強度不變（僅修正套件名判定） |

## 四、規模

**大改**：修改驗證腳本與設定載入器。產出本規格與 QA 報告；不涉及紅線，不寫 ADR。AGENTS.md 不變更。

## 五、待決事項

| # | 問題 | 建議 | 替代方案 |
| :---: | :--- | :--- | :--- |
| 1 | 卡點 A 之處理 | **新增選填鍵 `layers.package`**（兩種常見 Python 佈局皆可用，既有專案零遷移） | 改為必填鍵（所有專案須補設定）；或 PORTING 明文不支援扁平與 src-layout（只改文字） |
| 2 | `src = "."` 時 `tests/` 是否排除於原始碼檢查 | **不排除**：資源、例外、提示詞規則同樣適用測試碼，如需排除由專案自行列入 `ignore_scan_dirs` | 一律排除 `tests/`（與一般佈局「測試不在 src 下」之語意一致，但寫死目錄名） |
| 3 | BOM 處理 | **接受 BOM**（`utf-8-sig`），移植者無須額外動作 | 維持拒絕，但錯誤訊息明示「檔首含 BOM，請另存為無 BOM 之 UTF-8」 |
| 4 | 卡點 E 是否修 | **修**（改一行正規式，避免照直覺排表即 FAIL） | 不修，範本已定第 2 欄 |

## 六、驗收條件

品質評測範圍：否

安全評估範圍：否

* **AC-1**：`src = "src/widgetkit"`、`package = "widgetkit"` 之設定下，合法分層 import 零 P0；Domain 引第三方套件、Application 引外層仍分別以原類別（「第三方套件」「違反依賴反轉」）檢出。`src = "."`、`package = ""` 亦同。回歸測試修正前失敗、修正後通過。
* **AC-2**：未設定 `package` 時，本專案與既有參數化變體之稽核結果與修正前相同。
* **AC-3**：`src = "."` 時，`ignore_scan_dirs` 所列目錄與 `.agents/` 下之 `.py` 不進入原始碼檢查；全倉隱私掃描範圍不變。
* **AC-4**：帶 BOM 之 `project.toml` 可正常載入（或依待決 3 之替代方案，訊息含 BOM 提示）。
* **AC-5**：`dependency_files = ["pyproject.toml"]` 時 `security_scan.py --full` 執行 pip-audit 成功；requirements 檔仍以 `-r` 掃描。
* **AC-6**：STRIDE 字母位於第一欄之威脅表被認得；無 STRIDE 列之表格仍 FAIL。
* **AC-7**：以修正後核心重跑第三輪五組實測（V1、V2、V3 依新設定）：三支腳本與核心自我測試全數通過，違規探測全數以正確類別檢出。
* **AC-8**：本專案 `verify_doc_sync.py`、`audit_guardrails.py`、`security_scan.py` 通過；`tests/unit`（含斷鏈）、`.agents/tests`、`.agents/tests/e2e`、`tests/e2e` 之移植演練全數通過。
