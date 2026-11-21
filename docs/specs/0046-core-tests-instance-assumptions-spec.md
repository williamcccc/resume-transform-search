# 提案與規格書：核心自我測試去除實例值斷言、移植演練多組參數化

> **狀態**：G1 提案（待 G2 使用者核准）｜**類型**：規範變更（大改：修改核心自我測試與移植演練）｜**流程**：[governance.md](../../.agents/workflows/governance.md)｜**影響範圍**：`.agents/tests/`、`tests/unit/test_project_instance_files.py`、`tests/e2e/`，不涉及 `src/`、不修改紅線與驗證腳本

## 一、動機

2026-11-21 以實測工具對五組參數各做一次移植（commit 後乾淨 clone 驗證，並逐項植入違規）：

| 組 | 主題 | 閘門腳本 | 違規探測 | 核心自我測試 |
| :--- | :--- | :---: | :---: | :---: |
| T1 | 逐步導入 DDD（`layers.enabled = false`、層目錄不存在） | 通過 | 4/4 | 7 項失敗 |
| T2 | 深層路徑（`src/acme/core`、子目錄範本檔、特殊字元識別字、`develop`） | 通過 | 4/4 | 1 項失敗 |
| T3 | 中文、空白、括號之專案路徑；地區樣式與敏感目錄 | 通過 | 4/4 | 1 項失敗 |
| T4 | LLM 應用（提示詞、金鑰、評測套件、URL 例外、完整文件） | 通過 | 6/6 | 1 項失敗 |
| T5 | 與原專案同名 `src/`、兩個業務技能、基準檔完整生命週期、`trunk` | 通過（刻意植入之 Semgrep 發現經基準登錄後通過；過期後恢復 P0） | 3/3 | 1 項失敗 |

閘門腳本與違規偵測於五組皆正確；失敗全數來自 3 支核心自我測試斷言**本專案之實例值**：

| # | 測試 | 斷言內容 | 失敗組 |
| :---: | :--- | :--- | :--- |
| 1 | `test_neutral_examples.test_agents_md_project_section_keeps_red_line_values` | 「本專案紅線」小節必含「紅線 1、6 本專案對應」條目（Spec-0040 新增） | 五組皆失敗：新專案改寫該節時不一定保留此條 |
| 2 | `test_guardrail_gaps` 假專案 | 沿用實例之 `layers.enabled`；實例為 `false` 時假專案之分層檢查亦停用 | T1：5 項 |
| 3 | `test_project_config.test_repository_config_is_valid` | `layers.enabled` 必須為 `true` | T1：1 項 |

內建移植演練只測一組參數，且沿用原專案之 AGENTS.md 本專案紅線小節與 `enabled = true`，故未能揭露。

## 二、修改內容

### 2.1 核心自我測試只驗通用規則（問題 1、3）

* `test_neutral_examples`：刪除「本專案紅線小節必含特定條目」之斷言；保留通用部分（本專案紅線小節存在、其外無「本專案為」附註）。
* `test_project_config.test_repository_config_is_valid`：刪除 `layers.enabled` 為真之斷言；保留設定可載入與例外理由非空之檢查。
* 上述兩項本專案實例值斷言移至專案側 [test_project_instance_files.py](../../tests/unit/test_project_instance_files.py)（不隨核心移植）：AGENTS.md 本專案紅線小節含「紅線 1、6 本專案對應」且列出本專案契約檔與設定模組；`layers.enabled` 為真。

### 2.2 假專案強制啟用分層（問題 2）

* `test_guardrail_gaps` 之假專案設定除逐鍵覆寫路徑外，另將 `[layers].enabled` 設為 `true`；需要停用情境之測試自行改寫。
* 回歸測試：實例設定 `enabled = false` 時，假專案基準案例零 P0 且分層違規仍被檢出。

### 2.3 移植演練多組參數化（防再犯）

新增專案側 E2E `tests/e2e/test_portable_variants_e2e.py`：將核心移植至暫存假專案，於下列變體各執行一次核心自我測試，須全數通過：

| 變體 | 內容 |
| :--- | :--- |
| 逐步導入 | `layers.enabled = false`、層目錄不存在；本專案紅線小節改寫為不含「紅線 1、6 本專案對應」之內容 |
| 清單全空 | `url_schemes`、`identifiers`、`stack_terms`、隱私清單、`url_exceptions`、`not_applicable`（技術章節全列 `tech_chapters_in_use`）皆空 |
| 非預設佈局 | 原始碼根目錄與層名非預設、設定模組位於原始碼根目錄之外、範本檔名非 `.env.example` |

既有移植演練（`test_portable_closed_loop_e2e.py`）不變。

## 三、衝突與重複檢查

| 檢查 | 結果 |
| :--- | :--- |
| 與既有規則矛盾 | 無。核心測試之通用規則守護強度不變；本專案實例值改由專案側測試守護，強度亦不變 |
| 同一規則寫在兩處 | 無：實例值斷言移出核心後只存在於專案側 |
| 紅線與驗證腳本 | 不修改 |

## 四、規模

**大改**：修改核心自我測試與移植演練。產出本規格與 QA 報告；不涉及紅線，不寫 ADR。

## 五、待決事項

| # | 問題 | 建議 | 替代方案 |
| :---: | :--- | :--- | :--- |
| 1 | 本專案實例值斷言之去處 | **移至 `tests/unit/test_project_instance_files.py`**（專案側，不隨核心移植） | 直接刪除（本專案失去這兩項守護） |
| 2 | 參數化演練之範圍 | **新增 3 個變體之 E2E**（約 20 秒，納入 `tests/e2e`） | 五組實測工具全量納入（較完整但需 Semgrep，執行時間長）；或不新增，只修 3 支測試 |

## 六、驗收條件

品質評測範圍：否

安全評估範圍：否

* **AC-1**：核心自我測試不含本專案實例值斷言；本專案之兩項實例值改由專案側測試守護且通過。
* **AC-2**：實例設定 `enabled = false` 時 `test_guardrail_gaps` 全數通過，且分層違規仍被檢出。
* **AC-3**：參數化演練 3 個變體之核心自我測試全數通過；修正前（以舊版核心測試執行）至少一個變體失敗。
* **AC-4**：以修正後核心重跑五組實測：核心自我測試全數通過，閘門腳本與違規探測結果不變。
* **AC-5**：本專案 `verify_doc_sync.py`、`audit_guardrails.py`、`security_scan.py` 通過；`tests/unit`（含斷鏈）、`.agents/tests`、`.agents/tests/e2e`、`tests/e2e` 之移植演練全數通過。
