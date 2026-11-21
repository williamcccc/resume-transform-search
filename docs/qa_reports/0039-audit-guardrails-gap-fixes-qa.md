# QA 實測驗收報告：audit_guardrails.py 守門缺口修正（Spec-0039：Bug-0031、Bug-0032、Bug-0033）

> **規格**：[Spec-0039](../specs/0039-audit-guardrails-gap-fixes-spec.md)｜**缺陷**：[Bug-0031](../bugs/0031-layer-check-skips-nested-modules.md)、[Bug-0032](../bugs/0032-env-sync-check-narrow-detection.md)、[Bug-0033](../bugs/0033-env-sync-check-skips-missing-files.md)｜**所走流程**：[governance.md](../../.agents/workflows/governance.md)（大改），缺陷部分依 [bug.md](../../.agents/workflows/bug.md) 先紅後綠｜**分支**：`fix/spec-0039-guardrail-gaps`（G1 提案 commit `6b2ecfa`）

## 1. 測試環境與前置條件
* **測試日期**：2026-11-21
* **作業系統與 Python 版本**：Windows 11 / Python 3.13
* **外部相依服務**：不需要（安全掃描為差異模式）
* **測試資料集**：每個案例於暫存目錄建立最小假專案（複製閘門腳本與 lib、`app/` 分層、合成設定模組與 `.env.example`），不讀取 `data/`、`resume/`

---

## 2. 測試計畫摘要
* **測試範圍**：三項缺陷之 BC、本專案零新增違規、移植演練與全套測試回歸。
* **不測範圍**：

  | 不測項目 | 理由 | 風險與替代保障 |
  | :--- | :--- | :--- |
  | 動態取名之環境變數讀取 | 決議 2：無法靜態判定，不列入 | 說明文字註明限制；`langsmith_tracing.py` 之變數已列於 `.env.example` |
  | 重構 `src/` 使環境變數只由設定模組讀取 | 決議 1：不判違規 | 紅線 6 原意（連線字串由設定模組注入）不受影響 |

* **進入條件**：G2 使用者核准（2026-11-21，5 項待決事項全數採建議）。
* **退出條件**：見第 8 節。

---

## 3. 需求驗收追溯矩陣 (RTM)

| AC／BC | 條款說明 | 測試案例 | 測試類型 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **AC-1**／Bug-0031 BC-2 | 任意深度子資料夾之違規模組回報 P0，訊息含相對路徑 | TC-01 | 整合（CLI） | **PASS** |
| **AC-2**／Bug-0032 BC-2～4 | `os.environ.get`、`os.getenv`、`os.environ[...]`、`from os import getenv`，任一檔案讀取而未列者 P0；共用偵測函式 | TC-02、TC-03 | 整合 + 單元 | **PASS** |
| **AC-3**／Bug-0033 BC-2 | 設定路徑不存在回報 P0，指出鍵名與路徑；分層停用時不檢查分層目錄 | TC-04 | 整合（CLI） | **PASS** |
| **AC-4**／各 BC-1 | 回歸測試於 `test:` commit 失敗、`fix:` commit 通過 | TC-05 | 先紅後綠 | **PASS** |
| **AC-5**／各 BC-3 | 本專案零新增違規；全套測試與移植演練無回歸 | TC-06、TC-07 | 回歸 + E2E | **PASS** |

> **RTM 統計**：PASS 5 / FAIL 0 / DEFERRED 0 / NOT COVERED 0（共 5 條 AC）

---

## 4. 測試案例執行矩陣

| TC | 內容 | 預期 | 實際 | 狀態 |
| :---: | :--- | :--- | :--- | :---: |
| TC-01 | `TestBug0031NestedLayerModules`：`app/domain/sub/nested.py` import 第三方、`app/application/flows/runner.py` import 外層 | 結束碼 1，訊息含相對路徑 | 符合 | PASS |
| TC-02 | `TestBug0032EnvVarDetection` 4 項紅燈情境 + 1 項對照（已列變數、動態取名不觸發） | 4 項 P0 指出變數名；對照結束碼 0 | 符合 | PASS |
| TC-03 | 上庫衛生測試改呼叫 `collect_env_var_reads`；本專案偵測數比對 | 偵測 100 個變數，與修正前設定模組範圍一致，皆已列於 `.env.example` | 符合 | PASS |
| TC-04 | `TestBug0033MissingConfiguredPaths` 4 項紅燈情境 + 1 項分層停用對照 | `config.module`、`config.env_example`、`layers.src`、`layers.domain`／`layers.application` 不存在時 P0；停用時結束碼 0 | 符合 | PASS |
| TC-05 | 以 `git worktree` 切至各 commit 重跑對應測試類別 | `test:` 失敗、`fix:` 通過 | `6952d12` 2 失敗 → `fc8571f` 通過；`a4f39a9` 4 失敗 → `f542682` 通過；`09ebf55` 4 失敗 → `0a528ab` 通過 | PASS |
| TC-06 | 本專案 `audit_guardrails.py` | 零 P0、新增「設定路徑驗證」PASS | 100% PASSED | PASS |
| TC-07 | `tests/unit`、`.agents/tests`、`.agents/tests/e2e`、移植演練 | 全數通過 | 573、164、8、18 項通過 | PASS |

---

## 5. 實測執行日誌摘要

```text
audit_guardrails.py         → ✅ [Pass] 設定路徑驗證 … 🎉 100% PASSED（exit 0）
security_scan.py            → P0=0 P1=0
verify_doc_sync.py          → [SUCCESS]（exit 0）
unittest tests/unit         → Ran 573 tests ... OK
unittest .agents/tests      → Ran 164 tests ... OK（新增 13 項）
unittest .agents/tests/e2e  → Ran 8 tests ... OK
unittest e2e porting        → Ran 18 tests ... OK
先紅後綠（worktree 重跑）    → 三組皆 test: FAILED → fix: OK
```

---

## 6. 品質評測結果

不適用（品質評測範圍：否）。

---

## 7. 失敗分析與後續事項

* **Bug-0033 修正後移植演練首次失敗（已修正）**：假專案只建立 `app/domain`、`app/infrastructure`，缺 `app/application`。啟用分層時新檢查正確回報 P0；此為演練設定不完整，已補建目錄。修正前此缺漏被靜默跳過，正是 Bug-0033 所描述的情形。
* **移植後專案執行守門缺口測試出錯（已修正）**：測試之設定改寫會再插入 `url_exceptions = []`，移植後專案設定已有此鍵造成 TOML 重複鍵。改為鍵存在時不插入。
* **逃逸分析回顧**：三項缺陷皆屬測試缺口（既有測試只涵蓋第一層、單一寫法、檔案齊備之情境）；本案之回歸測試以真實 CLI 在假專案執行，涵蓋上述情境。教訓歸屬通用，回寫至核心自我測試 `.agents/tests/test_guardrail_gaps.py`。

---

## 8. QA 驗收結論

**通過**。5 條 AC 與三份缺陷報告之 BC 全數 PASS；三份缺陷報告已結案。

---

## 9. 規範變更檢查紀錄（G4、G5）與 Gate 2

**G4 一致性檢查**

| # | 項目 | 結果 |
| :---: | :--- | :--- |
| 1 | `verify_doc_sync.py` | 通過；缺陷索引三列改為「已結案」 |
| 2 | 改名與搬移之引用殘留 | 「唯一可讀環境變數的模組」於 `project.toml`、PORTING 已改；舊正規式只剩歷史文件 |
| 3 | 新名稱撞名 | `collect_env_var_reads`、`check_configured_paths` 無撞名 |
| 4 | AGENTS.md 行數 | 未修改，174 行 |
| 5 | Markdown 斷鏈測試 | 通過 |
| 6 | 程式變更 | `audit_guardrails.py`；新增測試 13 項；走 Gate 2（下表） |

**Gate 2 程式檢查**

| 輪次 | 日期 | 範圍 | `audit_guardrails.py` | `security_scan.py` | P0 | P1 | P2 | 判定 |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 2026-11-21 | `6b2ecfa..HEAD` | Exit 0 | Exit 0 | 0 | 0 | 0 | **PASS** |

* **先紅後綠**：見 TC-05，三組皆符合；`test:` commit 失敗原因為腳本結束碼 0（漏檢），即缺陷本身。
* **逃逸分析**：三份缺陷報告第 3 節已記錄（測試缺口）。
* 程式覆核：AST 解析失敗之檔案略過（與其他檢查一致）；新檢查只讀檔、不寫檔；訊息只含鍵名、路徑與變數名，不輸出檔案內容；`Path.is_relative_to` 為 Python 3.9+，符合專案環境。

**G5 審查**（gatekeeper 視角）：零矛盾、零重複。紅線 6、`project.toml` 註解、PORTING 第 3 步對設定模組的描述一致；環境變數規則改由腳本與上庫衛生測試共用同一函式，消除重複。
