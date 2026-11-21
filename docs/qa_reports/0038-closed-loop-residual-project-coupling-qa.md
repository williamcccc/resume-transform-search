# QA 實測驗收報告：閉環殘留專案相依清理（Spec-0038）

> **規格**：[Spec-0038](../specs/0038-closed-loop-residual-project-coupling-spec.md)｜**所走流程**：[governance.md](../../.agents/workflows/governance.md)（大改，含程式變更）｜**分支**：`docs/spec-0038-residual-coupling`（G1 提案 commit `55824b7`）

## 1. 測試環境與前置條件
* **測試日期**：2026-11-21
* **作業系統與 Python 版本**：Windows 11 / Python 3.13
* **外部相依服務**：安全掃描需連網（Semgrep 規則、pip-audit 漏洞資料庫）；其餘不需要
* **測試資料集**：設定檔與樣本字串於暫存目錄或記憶體建構；移植演練於暫存目錄建立合成假專案（`demo_proj`），不讀取 `data/`、`resume/`

---

## 2. 測試計畫摘要
* **測試範圍**：敏感副檔名設定化、命中類別與常數改名、兩個新設定鍵之綱要驗證、基準檔搬移、業務技能清單、移植演練。
* **不測範圍**：

  | 不測項目 | 理由 | 風險與替代保障 |
  | :--- | :--- | :--- |
  | `quality-evaluation` 技能 | 決議第 3 項：不修改 | 無 |
  | Bug-0031～0033、Spec-0034 之腳本修正 | 決議第 4 項：分開處理 | 本案不觸及其函式 |

* **進入條件**：G2 使用者核准（2026-11-21，待決事項全數採建議）。
* **退出條件**：見第 8 節。

---

## 3. 需求驗收追溯矩陣 (RTM)

| AC | 條款說明 | 測試案例 | 測試類型 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **AC-1** | 副檔名清單決定偵測；空清單不啟用；缺鍵或型別錯誤結束碼 2 | TC-01、TC-02 | 單元 | **PASS** |
| **AC-2** | 本專案執行結果與修改前一致 | TC-03、TC-04 | 回歸比對 | **PASS** |
| **AC-3** | 腳本與 `.agents/`（不含 `project/`）無 `resume` 字樣之常數或類別 | TC-05 | 單元 + 搜尋 | **PASS** |
| **AC-4** | 基準檔位於 `.agents/project/`，讀取正常、基準內項目數不變 | TC-06 | 完整掃描 | **PASS** |
| **AC-5** | `business_skills` 綱要驗證；移植演練依清單刪除後閘門與自我測試通過 | TC-02、TC-07 | 單元 + E2E | **PASS** |
| **AC-6** | `verify_doc_sync.py` 通過；全套測試無回歸 | TC-08 | 回歸 | **PASS** |

> **RTM 統計**：PASS 6 / FAIL 0 / DEFERRED 0 / NOT COVERED 0（共 6 條 AC）

---

## 4. 測試案例執行矩陣

| TC | 內容 | 預期 | 實際 | 狀態 |
| :---: | :--- | :--- | :--- | :---: |
| TC-01 | `test_sensitive_directory_pattern_follows_configured_extensions` | `["csv"]` 時 `records/<人名>.csv` 命中、`.pdf` 不命中；目錄或副檔名任一為空時不命中 | 符合 | PASS |
| TC-02 | `test_wrong_types_raise`（新增兩例）、`test_missing_spec0038_keys_raise` | 型別錯誤與缺鍵皆以 `ProjectConfigError` 指出 `[privacy].sensitive_extensions`、`[project].business_skills` | 符合 | PASS |
| TC-03 | 於 `main` 工作樹與本分支各執行 `audit_guardrails.py`，比對輸出 | 除工作區根目錄一行外完全相同 | 完全相同 | PASS |
| TC-04 | 上庫衛生測試（全倉隱私掃描、命中類別改為 `personal_filename`） | 8 項通過、零違規 | 符合 | PASS |
| TC-05 | `test_privacy_marker_category_is_neutral`；搜尋腳本 | 模組內無含 `RESUME` 之名稱；腳本無 `resume` 字樣 | 符合 | PASS |
| TC-06 | `security_scan.py --full` | 基準內 = 基準檔筆數 11 | `基準內=11`，P0=0 | PASS |
| TC-07 | `test_a4_business_skills_removed_by_config_list`；移植演練全套 | 依清單刪除兩技能、清單清空、基準檔已刪；閘門與 `.agents/tests` 通過 | 符合；17 項通過 | PASS |
| TC-08 | `verify_doc_sync.py`、`tests/unit`、`.agents/tests`、`.agents/tests/e2e` | 全數通過 | 結束碼 0；573、134、8 項通過 | PASS |

---

## 5. 實測執行日誌摘要

```text
verify_doc_sync.py              → [SUCCESS] 100% In Sync（exit 0）
audit_guardrails.py             → exit 0；與 main 輸出比對相同
security_scan.py（差異）         → P0=0 P1=0
security_scan.py --full         → P0=0 P1=1 基準內=11 未執行=0 錯誤=0
unittest tests/unit             → Ran 573 tests ... OK
unittest .agents/tests          → Ran 134 tests ... OK（新增 3 項）
unittest .agents/tests/e2e      → Ran 8 tests ... OK
unittest e2e porting            → Ran 17 tests ... OK（新增 1 項）
```

---

## 6. 品質評測結果

不適用（品質評測範圍：否）。

---

## 7. 失敗分析與後續事項

* **完整掃描 P1（非本案引入）**：`pip-audit` 回報 `wcmatch 8.5.2`（`requirements-dev.txt`，semgrep 之相依套件，只裝於 `.venv-tools`）有新公布漏洞 CVE-2026-132276，修正版本 11.2。`requirements-dev.txt` 自 Spec-0030 起未變更，屬既有相依之事後公布漏洞，與本案無關。使用者於 2026-11-21 決定**登錄基準檔**（比照既有 `mcp` 項目），理由：掃描工具相依、隔離於 `.venv-tools`；到期日 2027-02-20。登錄後完整掃描 `P0=0 P1=0 基準內=12`。
* 無其他失敗案例。

---

## 8. QA 驗收結論

**通過**。6 條 AC 全數 PASS。完整掃描之既有相依 P1 已依使用者決定登錄基準檔。

---

## 9. 規範變更檢查紀錄（G4、G5）與 Gate 2

**G4 一致性檢查**

| # | 項目 | 結果 |
| :---: | :--- | :--- |
| 1 | `verify_doc_sync.py` | 通過；載入區段加入 `project`，缺鍵時結束碼 2 |
| 2 | 改名與搬移之引用殘留 | 舊命中類別名稱只剩歷史文件；舊基準檔路徑於規範、腳本、CI 零殘留 |
| 3 | 新名稱撞名 | `sensitive_extensions`、`[project]`、`business_skills` 無撞名 |
| 4 | AGENTS.md 行數 | 未修改，174 行 |
| 5 | Markdown 斷鏈測試 | 通過 |
| 6 | 程式變更 | `audit_guardrails.py`、`project_config.py`、`verify_doc_sync.py`；新增單元測試 3 項、E2E 1 項；走 Gate 2 程式檢查（下表） |

**Gate 2 程式檢查**

| 輪次 | 日期 | 範圍 | `audit_guardrails.py` | `security_scan.py` | P0 | P1 | P2 | 判定 |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 2026-11-21 | `55824b7..HEAD` | Exit 0 | Exit 0（差異 P1=0；完整 P1=1，非本案，已登錄基準檔） | 0 | 1 | 0 | **PASS** |

| ID | 等級 | 檢核項 | 位置 | 描述 | 處置 |
| :--- | :---: | :--- | :--- | :--- | :--- |
| R1-01 | P1 | 安全工具掃描 | `requirements-dev.txt:wcmatch==8.5.2` | 既有掃描工具相依之新公布漏洞 | 已登錄基準檔（使用者決定，到期 2027-02-20）；完整掃描 P1=0、基準內=12 |

* 程式覆核：`sensitive_directory_filename_pattern` 與修改前樣式等價（副檔名改由 `_alternation` 組成，已 `re.escape`）；空清單回傳 `_NeverMatch`，與其他清單一致；例外與資源處理無變更。

**G5 審查**（gatekeeper 視角）：零矛盾、零重複。基準檔集中於 `project/` 後，PORTING 第 3 步不再重複「不要複製」提醒，改由第 4 步實例檔清單統一說明。
