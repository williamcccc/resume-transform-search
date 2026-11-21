# 缺陷報告：環境變數同步檢查只認設定模組內的 os.environ.get()，其他檔案與其他寫法漏檢

> **編號**：0032｜**嚴重度**：S3｜**狀態**：已結案

## 1. 受理資訊
* **現象**：[audit_guardrails.py](../../.agents/skills/code-review/scripts/audit_guardrails.py) 的 `check_git_hygiene_and_pii_guardrails()` 檢查「環境變數須列於 `.env.example`」時，只以一條比對 `os.environ.get("大寫變數名")` 的正規式掃描 `config.module`（本專案為 `src/infrastructure/config.py`）一個檔案。以下情況新增的環境變數未列於 `.env.example` 時，不產生 P0：
  1. 設定模組以 `os.getenv("X")` 或 `os.environ["X"]` 讀取。
  2. 設定模組以外的檔案讀取環境變數。
* **規範落差**：[AGENTS.md](../../AGENTS.md) 紅線 6 要求連線字串統一由設定模組注入，[PORTING.md](../../.agents/PORTING.md) 與 `project.toml` 註解稱設定模組為「唯一可讀環境變數的模組」，但沒有任何自動檢查阻止其他模組讀取環境變數。
* **現況**：`src/` 中除設定模組外另有 3 個檔案讀取環境變數（`src/infrastructure/embeddings/gemini_embedding.py`、`src/infrastructure/transformers/utils.py`、`src/infrastructure/observability/langsmith_tracing.py`）；其讀取之變數目前皆已列於 `.env.example`，無實際漏記。
* **環境**：Windows 11 / Python 3.13；不需 Redis。
* **觸發條件**：新增環境變數時採上述任一寫法或位置，且忘記更新 `.env.example`。
* **回報來源**：2026-11-20 說明 `project.toml` 的 `[config]` 參數時，閱讀腳本發現。
* **嚴重度判定理由**：屬 Gate 2 防線盲點，非執行期功能錯誤；現有變數皆已記載，無實際影響；Gate 2 人工 Checklist 仍可覆核。判定 S3，走 [bug.md](../../.agents/workflows/bug.md) 的編排（修正軌別見第 4 節）。

## 2. 重現步驟
1. 動態載入 `audit_guardrails.py`，將 `ROOT_DIR` 指向暫存目錄；建立含 `required_gitignore` 全部項目的 `.gitignore`，以及只含 `KNOWN=1` 的 `.env.example`。
2. 分別建立以下內容後呼叫 `check_git_hygiene_and_pii_guardrails()`，只看與環境變數相關的違規：

   | 情境 | 內容 | 預期 | 實際 |
   | :--- | :--- | :--- | :--- |
   | A（對照） | 設定模組：`os.environ.get("NEW_A")` | P0 | P0 ✅ |
   | B | 設定模組：`os.getenv("NEW_B")` | P0 | 無 ❌ |
   | C | 設定模組：`os.environ["NEW_C"]` | P0 | 無 ❌ |
   | D | 設定模組不讀取；`src/infrastructure/other.py`：`os.environ.get("NEW_D")` | P0（或「非設定模組讀取環境變數」違規） | 無 ❌ |

```text
[2026-11-20 手動重現結果]
A control  get(): ["[P0 違規 - .env.example 未同步環境變數] AppConfig 中的變數未列於 .env.example: ['NEW_A']"]
B getenv       : []
C environ[]    : []
D other module : []
```

**紅燈回歸測試**：[test_guardrail_gaps.py](../../.agents/tests/test_guardrail_gaps.py) `TestBug0032EnvVarDetection`（於暫存目錄建立最小假專案，以真實 CLI 執行 `audit_guardrails.py`）。`test:` commit `a4f39a9` 失敗 4 項、`fix:` commit `f542682` 通過。

## 3. 根因分析（初判，修正時於 Step 1B 第 4 階段確認）
* **真因**：環境變數偵測以單一正規式比對單一檔案的文字，未以 AST 辨識 `os.environ.get`、`os.getenv`、`os.environ[...]` 等讀取方式，也未掃描設定模組以外的 `src/` 檔案。
* **所屬層**：不屬於 `src/` 四層；位於閉環守門腳本。
* **位置**：
  * `audit_guardrails.py` 的 `check_git_hygiene_and_pii_guardrails()`（`cfg_keys = set(re.findall(r'os\.environ\.get\(...', cfg_text))`）。
  * [test_github_pre_publish_hygiene.py](../../tests/unit/test_github_pre_publish_hygiene.py) 的 `test_env_example_covers_all_app_config_variables_and_has_no_real_secrets` 重複同一正規式，有相同盲點。
* **逃逸分析**：規格缺口加測試缺口 —— 「唯一可讀環境變數的模組」只寫在文件，未轉成可執行檢查；既有測試只涵蓋 `os.environ.get` 寫在設定模組內的情境。
* **教訓歸屬**：通用 —— 失效層：工具規則。

## 4. 修正範圍與升級判斷

| 預計修改檔案 | 修改性質 |
| :--- | :--- |
| `.agents/skills/code-review/scripts/audit_guardrails.py` | 改以 AST 收集環境變數讀取（`os.environ.get`、`os.getenv`、`os.environ[...]`、`environ.get` 等）；決定設定模組以外的讀取如何處理（見下） |
| `tests/unit/test_github_pre_publish_hygiene.py` | 改為呼叫腳本的同一套偵測函式，不再重複正規式 |
| `tests/unit/`（新增或擴充） | 紅燈回歸測試：情境 B、C、D |

**修正前須決定的行為**（可能觸發升級條件第 4 條）：設定模組以外讀取環境變數，應判 P0（強制「唯一模組」），還是只要求變數列於 `.env.example`？前者會讓現有 3 個檔案違規，需一併重構或登錄例外。若規範本身未定義，屬「正確行為需重新定義」，應經使用者確認後改走功能開發或規範變更。

**決議**（2026-11-21，Spec-0039 G2）：設定模組以外讀取環境變數**不判違規**；原始碼以字串常值讀取的變數都須列於 `.env.example`。紅線 6 只要求連線字串由設定模組注入，`project.toml` 註解與 PORTING 的「唯一可讀」用詞已修正。

**修正軌別注意**：修正只改 `.agents/**` 與測試、不改 `src/` 時，依 [AGENTS.md](../../AGENTS.md) 第 2 節分流表屬**規範變更**（[governance.md](../../.agents/workflows/governance.md) 將「修改驗證腳本」列為大改）；若決定強制「唯一模組」而需重構上述 3 個 `src/` 檔案，依 governance.md 開頭說明，`src/` 部分依性質走 bug 或 feature 軌。

**升級條件檢查**：

| # | 條件 | 是否觸發 |
| :---: | :--- | :---: |
| 1 | 修改 Domain 契約檔（`project.toml` 的 `layers.domain_interfaces`）的 Protocol 或 DTO 欄位 | 否 |
| 2 | 修改資料模型或 Redis 索引結構 | 否 |
| 3 | 新增 `AppConfig` 環境變數或 CLI 參數 | 否 |
| 4 | 「正確行為」在現有規格中未定義或定義矛盾 | 否（2026-11-21 Spec-0039 G2 決議 1 定義：不判違規，只要求列於 `.env.example`） |
| 5 | 修正範圍跨越 3 個以上 DDD 層 | 否 |

**簡化 Gate 1 簽核**（architect）：待修正時簽核
- [x] 修正只恢復既有規格行為，不新增行為
- [x] 影響面已列出：
- [x] 無介面破壞，`audit_guardrails.py` 指令與結束碼不變

## 5. 缺陷驗收條件 (BC)
* **BC-1**：紅燈回歸測試在 `test:` commit 失敗，在 `fix:` commit 通過。
* **BC-2**：情境 B、C 之變數未列於 `.env.example` 時回報 P0。
* **BC-3**：情境 D 依第 4 節決定之行為回報。
* **BC-4**：腳本與上庫衛生測試共用同一套偵測邏輯；本專案執行結果與修正前一致（或新增項目已處置）；全套單元測試無回歸。

品質評測範圍：否

## 6. 結案
* **修正流程與編號**：[Spec-0039](../specs/0039-audit-guardrails-gap-fixes-spec.md)（規範變更大改，governance.md）
* **`test:` commit**：`a4f39a9`
* **`fix:` commit**：`f542682`
* **PR**：
* **QA 報告**：[QA-0039](../qa_reports/0039-audit-guardrails-gap-fixes-qa.md)
* **結案日期**：2026-11-21
* **升級紀錄**（若有）：
