# QA 實測驗收報告：移植實測卡點修正（Spec-0044）

> **規格**：[Spec-0044](../specs/0044-porting-trial-fixes-spec.md)｜**所走流程**：[governance.md](../../.agents/workflows/governance.md)（大改：修改驗證用程式庫錯誤訊息與核心自我測試）｜**分支**：`docs/spec-0044-porting-trial-fixes`（G1 提案 commit `371db29`）

## 1. 測試環境與前置條件
* **測試日期**：2026-11-21
* **作業系統與 Python 版本**：Windows 11 / Python 3.13
* **外部相依服務**：Semgrep、pip-audit（沿用本機 `.venv-tools`）
* **測試資料集**：暫存目錄之示範專案（`app/` 四層、PostgreSQL、CLI、無 Web／API／LLM；敏感資料為供應商聯絡人），不讀取本機敏感目錄

---

## 2. 測試計畫摘要
* **測試範圍**：6 項卡點之修正、核心連結守護、依新版 PORTING 重做移植實測、全套回歸。
* **不測範圍**：重新安裝掃描工具（實測沿用本機 `.venv-tools`，以 `tools_venv` 指向；屬已知偏差，不影響其餘步驟）。
* **進入條件**：G2 使用者核准（2026-11-21，3 項待決事項全數採建議）。
* **退出條件**：見第 8 節。

---

## 3. 需求驗收追溯矩陣 (RTM)

| AC | 條款說明 | 測試案例 | 測試類型 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **AC-1** | `url_schemes` 不含 `redis` 時自我測試通過；移植演練改寫 `url_schemes` | TC-01 | E2E（先紅後綠） | **PASS** |
| **AC-2** | 核心連結測試：本專案通過、缺檔時失敗、`docs/` 不檢查 | TC-02、TC-03 | 單元 + E2E | **PASS** |
| **AC-3** | PORTING 依規格修改；表格陣列缺鍵訊息含 `= []` 提示 | TC-04、TC-05 | 單元 + 實測 | **PASS** |
| **AC-4** | 依新版 PORTING 重做移植實測：自我測試全數通過、核心零斷鏈 | TC-06 | 實測 | **PASS** |
| **AC-5** | 閘門腳本、全套測試、移植演練通過 | TC-07 | 回歸 | **PASS** |

> **RTM 統計**：PASS 5 / FAIL 0 / DEFERRED 0 / NOT COVERED 0（共 5 條 AC）

---

## 4. 測試案例執行矩陣

| TC | 內容 | 預期 | 實際 | 狀態 |
| :---: | :--- | :--- | :--- | :---: |
| TC-01 | 移植演練（`url_schemes = ["postgres", "https"]`）之 `test_a3`：以 `git stash` 還原舊版 `test_guardrail_gaps.py` 重跑，再套用修正重跑 | 舊版失敗、新版通過 | `FAILED (failures=1)` → `OK` | PASS |
| TC-02 | `test_detects_missing_core_target_and_ignores_project_side` | 抓到缺檔核心連結與未複製之 `GEMINI.md`；`docs/`、網址、錨點、行內碼不報 | 符合 | PASS |
| TC-03 | 移植演練更新前執行（未複製 `GEMINI.md`、刪除基準檔） | 連結測試失敗並指出 `GEMINI.md`、基準檔連結 | 符合（即實測卡點 3、4 之重現）；演練改依新版 PORTING 後通過 | PASS |
| TC-04 | `test_missing_table_array_key_hints_empty_array` | 表格陣列缺鍵訊息含 `url_exceptions = []`；一般鍵不附提示 | 符合 | PASS |
| TC-05 | 實測中只刪 `[[guardrails.url_exceptions]]` 表格後執行 `audit_guardrails.py` | 訊息指出補寫位置與寫法 | 「無項目時於 [guardrails] 區段內（下一個區段標題之前）寫 url_exceptions = []」 | PASS |
| TC-06 | 依新版 PORTING 重做示範專案移植（複製 `GEMINI.md`、基準檔清空、保留 `quality-evaluation`） | 三支腳本通過；自我測試全過 | `verify_doc_sync.py` SUCCESS、`audit_guardrails.py` 100% PASSED、`security_scan.py --full` SUCCESS；自我測試 177 項 OK | PASS |
| TC-07 | 閘門腳本、`tests/unit`、`.agents/tests`、`.agents/tests/e2e`、移植演練 | 全數通過 | 見第 5 節 | PASS |

---

## 5. 實測執行日誌摘要

```text
[首次實測，修正前]  自我測試 173 項 FAILED (failures=1)；核心斷鏈 10 處
[重做實測，修正後]  verify_doc_sync SUCCESS / audit 100% PASSED / scan SUCCESS / 自我測試 177 項 OK
audit_guardrails.py         → 100% PASSED（exit 0）
verify_doc_sync.py          → [SUCCESS]（exit 0）
security_scan.py            → P0=0 P1=0（exit 0）
unittest tests/unit         → Ran 573 tests ... OK（含斷鏈）
unittest .agents/tests      → Ran 177 tests ... OK（新增 4 項）
unittest .agents/tests/e2e  → OK
unittest e2e porting        → OK
```

---

## 6. 品質評測結果

不適用（品質評測範圍：否）。

---

## 7. 失敗分析與後續事項

* **逃逸分析**：卡點 1 屬測試缺口——移植演練沿用原專案 `url_schemes`，無法揭露自我測試對實例設定值之假設；已改寫演練設定。卡點 2–4 屬防線缺口——核心內部連結無隨核心移植之檢查；已新增 `test_core_links.py`。教訓歸屬通用，已回寫核心。
* **移植演練首次失敗（已修正）**：新增連結測試後，演練仍依舊版步驟（未複製 `GEMINI.md`、刪除基準檔），被連結測試正確攔下；演練已依新版 PORTING 更新。
* **索引未登錄致 `verify_doc_sync.py` 與 `.agents/tests/e2e` 失敗（已修正）**：登錄後通過，屬執行順序。

---

## 8. QA 驗收結論

**通過**。5 條 AC 全數 PASS。

---

## 9. 規範變更檢查紀錄（G4、G5）與 Gate 2

**G4 一致性檢查**

| # | 項目 | 結果 |
| :---: | :--- | :--- |
| 1 | `verify_doc_sync.py` | 通過 |
| 2 | 改述之引用殘留 | PORTING 無「直接刪除」基準檔、「可刪除」品質評測、「使用 Antigravity 時另加」字樣 |
| 3 | 新名稱撞名 | `test_core_links.py`、`broken_core_links` 無撞名 |
| 4 | AGENTS.md 行數 | 未修改，175 行 |
| 5 | Markdown 斷鏈測試 | 通過 |
| 6 | 程式變更 | `project_config.py` 缺鍵訊息；自我測試與演練；走 Gate 2（下表） |

**Gate 2 程式檢查**

| 輪次 | 日期 | 範圍 | `audit_guardrails.py` | `security_scan.py` | P0 | P1 | P2 | 判定 |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 2026-11-21 | `371db29..HEAD` | Exit 0 | Exit 0 | 0 | 0 | 0 | **PASS** |

* 程式覆核：缺鍵提示只附於表格陣列型別，其餘訊息不變；連結測試只讀檔、以 `resolve()` 判定核心範圍，連往核心以外者不檢查；`url_schemes` 為空時以 `skipTest` 明示原因，不靜默通過。

**G5 審查**（gatekeeper 視角）：零矛盾、零重複。PORTING 不再允許刪除品質評測內容，與 `verify_doc_sync.py` 強制宣告品質評測範圍一致；核心連結測試管核心內部，專案側斷鏈測試管全倉，範圍分明。
