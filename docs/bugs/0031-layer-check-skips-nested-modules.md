# 缺陷報告：DDD 分層檢查只掃 Domain／Application 第一層檔案，子資料夾模組漏檢

> **編號**：0031｜**嚴重度**：S3｜**狀態**：已登錄，待處理（尚未進入 Step 1B 第 3 階段）

## 1. 受理資訊
* **現象**：[audit_guardrails.py](../../.agents/skills/code-review/scripts/audit_guardrails.py) 的 `check_domain_purity()` 與 `check_application_dip()` 以 `glob("*.py")` 列舉檔案，只檢查 `layers.domain`、`layers.application` 目錄的第一層。放在子資料夾的模組（例如 `src/application/<子套件>/<模組>.py`）即使 import 第三方套件或外層模組，也不會產生 P0。
* **環境**：Windows 11 / Python 3.13；不需 Redis。
* **觸發條件**：Domain 或 Application 層出現子套件，且其中模組違反分層規則。
* **回報來源**：2026-11-20 說明 `project.toml` 的 `[layers]` 參數時，閱讀腳本發現。
* **嚴重度判定理由**：屬 Gate 2 防線盲點，非執行期功能錯誤。目前 `src/domain/`、`src/application/` 皆無子資料夾，現有程式未受影響；Gate 2 仍有人工 Checklist 覆核（[review_checklist.md](../../.agents/skills/code-review/references/review_checklist.md) DIP 項）作為替代防線。判定 S3，走 [bug.md](../../.agents/workflows/bug.md) 的編排（修正軌別見第 4 節）。

## 2. 重現步驟
1. 動態載入 `audit_guardrails.py`，將 `DOMAIN_DIR`（或 `APPLICATION_DIR`）指向暫存目錄。
2. 在暫存目錄建立兩個內容相同的違規檔：
   * `top.py`：`import redis`
   * `sub/nested.py`：`import redis`
3. 呼叫 `check_domain_purity()`（或 `check_application_dip()`）。
4. **預期結果**：兩個檔案都回報 P0（共 2 筆）。
5. **實際結果**：只回報 `top.py`（1 筆），`sub/nested.py` 漏檢。

```text
[2026-11-20 手動重現結果]
domain violations: 1 ['top.py']
application violations: 1 ['top.py']
```

**紅燈回歸測試**：待修正時於 Step 1B 第 3 階段撰寫（建議位置：`tests/unit/test_project_config.py` 的 `TestGuardrailHelpers`，或新增 `tests/unit/test_layer_checks_nested.py`）。測試須在暫存目錄動態建構違規檔，不得讀取本機 `data/`、`resume/`。

## 3. 根因分析（初判，修正時於 Step 1B 第 4 階段確認）
* **真因**：兩個分層檢查函式使用 `Path.glob("*.py")`（不遞迴）；同檔其他檢查（硬編碼、資源釋放、例外處理、提示詞）對 `SRC_DIR` 使用 `rglob("*.py")`，做法不一致。
* **所屬層**：不屬於 `src/` 四層；位於閉環守門腳本（`.agents/skills/code-review/scripts/`）。
* **位置**：`audit_guardrails.py` 的 `check_domain_purity()`、`check_application_dip()`（`for py_file in DOMAIN_DIR.glob("*.py")`、`for py_file in APPLICATION_DIR.glob("*.py")`）。
* **連帶瑕疵**：違規訊息只印 `py_file.name`，改為遞迴後同名檔案（不同子資料夾）將無法區分，訊息應改印專案相對路徑。
* **逃逸分析**：測試缺口 —— 既有單元測試與 [test_portable_closed_loop_e2e.py](../../tests/e2e/test_portable_closed_loop_e2e.py) 的違規樣本都放在層目錄第一層，未涵蓋巢狀子套件。
* **教訓歸屬**：通用 —— 失效層：工具規則。任何採用本閉環、分層目錄有子套件的專案都會受影響。

## 4. 修正範圍與升級判斷

| 預計修改檔案 | 修改性質 |
| :--- | :--- |
| `.agents/skills/code-review/scripts/audit_guardrails.py` | 兩處 `glob` 改 `rglob`；違規訊息改印相對路徑 |
| `tests/unit/`（新增或擴充一個測試檔） | 紅燈回歸測試：巢狀模組違規須被抓到 |

**修正軌別注意**：修正只改 `.agents/**` 與測試、不改 `src/`，依 [AGENTS.md](../../AGENTS.md) 第 2 節分流表屬**規範變更**；[governance.md](../../.agents/workflows/governance.md) 將「修改驗證腳本」列為大改，需 G1 提案、使用者 G2 核准、spec 與 QA 報告。修正時應先由使用者決定：沿用本報告作為缺陷紀錄、以 governance 流程執行修正（建議），並於本報告第 6 節記錄對應編號。同類守門腳本缺陷 [Bug-0032](./0032-env-sync-check-narrow-detection.md)、[Bug-0033](./0033-env-sync-check-skips-missing-files.md) 可併入同一份規範變更提案。

**升級條件檢查**：

| # | 條件 | 是否觸發 |
| :---: | :--- | :---: |
| 1 | 修改 Domain 契約檔（`project.toml` 的 `layers.domain_interfaces`）的 Protocol 或 DTO 欄位 | 否 |
| 2 | 修改資料模型或 Redis 索引結構 | 否 |
| 3 | 新增 `AppConfig` 環境變數或 CLI 參數 | 否 |
| 4 | 「正確行為」在現有規格中未定義或定義矛盾 | 否（AGENTS.md 紅線 1 與 review_checklist 均要求整層遵守，無子資料夾例外） |
| 5 | 修正範圍跨越 3 個以上 DDD 層 | 否 |

**簡化 Gate 1 簽核**（architect）：待修正時簽核
- [ ] 修正只恢復既有規格行為，不新增行為
- [ ] 影響面已列出：遞迴後若既有子資料夾含違規模組，會新增 P0（目前無子資料夾，預期零新增）
- [ ] 無介面破壞，`audit_guardrails.py` 指令與結束碼不變

## 5. 缺陷驗收條件 (BC)
* **BC-1**：紅燈回歸測試在 `test:` commit 失敗，在 `fix:` commit 通過。
* **BC-2**：Domain 與 Application 層任意深度之子資料夾模組，違反分層規則時皆回報 P0；違規訊息含專案相對路徑。
* **BC-3**：本專案執行 `audit_guardrails.py` 結果與修正前相同（零新增 P0）；全套單元測試無回歸。

品質評測範圍：否

## 6. 結案
* **修正流程與編號**：
* **`test:` commit**：
* **`fix:` commit**：
* **PR**：
* **QA 報告**：
* **結案日期**：
* **升級紀錄**（若有）：
