# 缺陷報告：設定模組或 .env.example 不存在時，環境變數同步檢查靜默跳過

> **編號**：0033｜**嚴重度**：S3｜**狀態**：已結案

## 1. 受理資訊
* **現象**：[audit_guardrails.py](../../.agents/skills/code-review/scripts/audit_guardrails.py) 的 `check_git_hygiene_and_pii_guardrails()` 以 `if config_path.exists() and env_example_path.exists():` 包住環境變數同步檢查。`project.toml` 的 `config.module` 或 `config.env_example` 指向不存在的檔案時，整項檢查被跳過，不產生 P0、P1 或任何提示，Gate 2 視為通過。
* **設計不一致**：`project.toml` 缺鍵或型別錯誤時腳本以結束碼 2 中止（Spec-0028），但鍵存在、路徑錯誤時卻靜默放行。
* **現況**：本專案兩個檔案皆存在，無實際影響。另 [test_github_pre_publish_hygiene.py](../../tests/unit/test_github_pre_publish_hygiene.py) 會 `assertTrue(... .exists())`，在本專案可抓到檔案遺失；但移植到其他專案時此測試不一定隨行，Gate 2 腳本是唯一防線。
* **環境**：Windows 11 / Python 3.13；不需 Redis。
* **觸發條件**：移植時 `config.module` 路徑填錯、設定模組改名或搬移、`.env.example` 被刪除或改名。
* **回報來源**：2026-11-20 說明 `project.toml` 的 `[config]` 參數時，閱讀腳本發現。
* **嚴重度判定理由**：屬 Gate 2 防線失效即放行（fail-open），非執行期功能錯誤；本專案現有單元測試可替代偵測，無實際影響。判定 S3，走 [bug.md](../../.agents/workflows/bug.md) 的編排（修正軌別見第 4 節）。

## 2. 重現步驟
1. 動態載入 `audit_guardrails.py`，將 `ROOT_DIR` 指向暫存目錄；建立含 `required_gitignore` 全部項目的 `.gitignore`。
2. 分別建立以下內容後呼叫 `check_git_hygiene_and_pii_guardrails()`，只看與環境變數相關的違規：

   | 情境 | 內容 | 預期 | 實際 |
   | :--- | :--- | :--- | :--- |
   | E | 只有 `.env.example`，設定模組不存在 | 回報設定模組找不到 | 無 ❌ |
   | F | 設定模組含 `os.environ.get("NEW_F")`，`.env.example` 不存在 | 回報範本檔找不到 | 無 ❌ |

```text
[2026-11-20 手動重現結果]
E missing cfg  : []
F missing ex   : []
```

**紅燈回歸測試**：[test_guardrail_gaps.py](../../.agents/tests/test_guardrail_gaps.py) `TestBug0033MissingConfiguredPaths`（於暫存目錄建立最小假專案，以真實 CLI 執行 `audit_guardrails.py`）。`test:` commit `09ebf55` 失敗 4 項、`fix:` commit `0a528ab` 通過。

## 3. 根因分析（初判，修正時於 Step 1B 第 4 階段確認）
* **真因**：以 `exists()` 條件包住檢查，檔案不存在時走「略過」分支而非「報錯」分支；防線失效時沒有輸出。
* **所屬層**：不屬於 `src/` 四層；位於閉環守門腳本。
* **位置**：`audit_guardrails.py` 的 `check_git_hygiene_and_pii_guardrails()`，「2. 檢查 .env.example 與 AppConfig 100% 同步」段落。
* **同類疑點**（修正時一併檢查）：同檔其他以 `if not X.exists(): return` 開頭的檢查（如 `layers.src`、`layers.domain`、`layers.application` 不存在時）也是靜默略過；`layers.enabled = true` 而目錄不存在，是否應報錯，修正時一併判斷。
* **逃逸分析**：測試缺口 —— 既有測試只驗證檔案存在時的同步結果，未驗證檔案缺失時腳本的行為。
* **教訓歸屬**：通用 —— 失效層：工具規則。

## 4. 修正範圍與升級判斷

| 預計修改檔案 | 修改性質 |
| :--- | :--- |
| `.agents/skills/code-review/scripts/audit_guardrails.py` | 設定模組或範本檔不存在時回報違規（等級待定：P0，或比照設定錯誤以結束碼 2 中止） |
| `tests/unit/`（新增或擴充） | 紅燈回歸測試：情境 E、F |

**修正軌別注意**：修正只改 `.agents/**` 與測試、不改 `src/`，依 [AGENTS.md](../../AGENTS.md) 第 2 節分流表屬**規範變更**；[governance.md](../../.agents/workflows/governance.md) 將「修改驗證腳本」列為大改，需 G1 提案、使用者 G2 核准、spec 與 QA 報告。可與 [Bug-0031](./0031-layer-check-skips-nested-modules.md)、[Bug-0032](./0032-env-sync-check-narrow-detection.md) 併入同一份規範變更提案，各自保留 `test:` → `fix:` commit。

**升級條件檢查**：

| # | 條件 | 是否觸發 |
| :---: | :--- | :---: |
| 1 | 修改 Domain 契約檔（`project.toml` 的 `layers.domain_interfaces`）的 Protocol 或 DTO 欄位 | 否 |
| 2 | 修改資料模型或 Redis 索引結構 | 否 |
| 3 | 新增 `AppConfig` 環境變數或 CLI 參數 | 否 |
| 4 | 「正確行為」在現有規格中未定義或定義矛盾 | 否（Spec-0028 已定義設定錯誤須以結束碼 2 中止，本缺陷屬未貫徹） |
| 5 | 修正範圍跨越 3 個以上 DDD 層 | 否 |

**簡化 Gate 1 簽核**（architect）：待修正時簽核
- [x] 修正只恢復既有規格行為，不新增行為
- [x] 影響面已列出：本專案兩檔皆存在，預期零新增違規；移植專案路徑錯誤時將由「通過」變為「失敗」
- [x] 無介面破壞，`audit_guardrails.py` 指令不變

## 5. 缺陷驗收條件 (BC)
* **BC-1**：紅燈回歸測試在 `test:` commit 失敗，在 `fix:` commit 通過。
* **BC-2**：`config.module` 或 `config.env_example` 指向不存在的檔案時，腳本回報違規或以結束碼 2 中止，訊息指出是哪一個鍵、哪一個路徑。
* **BC-3**：本專案執行結果與修正前相同；全套單元測試無回歸。

品質評測範圍：否

## 6. 結案
* **修正流程與編號**：[Spec-0039](../specs/0039-audit-guardrails-gap-fixes-spec.md)（規範變更大改，governance.md）
* **`test:` commit**：`09ebf55`
* **`fix:` commit**：`0a528ab`
* **PR**：
* **QA 報告**：[QA-0039](../qa_reports/0039-audit-guardrails-gap-fixes-qa.md)
* **結案日期**：2026-11-21
* **升級紀錄**（若有）：
