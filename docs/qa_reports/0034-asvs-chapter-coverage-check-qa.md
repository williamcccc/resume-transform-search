# QA 實測驗收報告：閉環結構自動檢查（Spec-0034）

> **規格**：[Spec-0034](../specs/0034-asvs-chapter-coverage-check-spec.md)｜**所走流程**：[governance.md](../../.agents/workflows/governance.md)（大改，含程式變更）｜**分支**：`docs/spec-0034-structure-checks`（G1 修訂 commit `0b47c3c`）

## 1. 測試環境與前置條件
* **測試日期**：2026-11-21
* **作業系統與 Python 版本**：Windows 11 / Python 3.13
* **外部相依服務**：不需要（安全掃描為差異模式）
* **測試資料集**：框架表、設定與標記樣本於記憶體或暫存目錄建構；移植演練於暫存目錄建立合成假專案（`demo_proj`），不讀取 `data/`、`resume/`

---

## 2. 測試計畫摘要
* **測試範圍**：C1–C8 檢查邏輯、新設定鍵 `tech_chapters_in_use`、AGENTS.md 安全規則第 2 條用詞、移植後專案的結構檢查。
* **不測範圍**：

  | 不測項目 | 理由 | 風險與替代保障 |
  | :--- | :--- | :--- |
  | Bug-0031～0033 | 決議第 5 項：分開處理 | 本案不觸及 `audit_guardrails.py` |
  | ASVS 新版（V18 以後） | 尚未發布 | 章節總數集中於 `ASVS_CHAPTER_COUNT` 常數，新版時以規範變更更新 |

* **進入條件**：G2 使用者核准（2026-11-21，7 項待決事項全數採建議）。
* **退出條件**：見第 8 節。

---

## 3. 需求驗收追溯矩陣 (RTM)

| AC | 條款說明 | 測試案例 | 測試類型 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **AC-1** | 對照表缺章、重複、適用條件不屬三類時 FAIL 並指出章節 | TC-01、TC-02 | 單元 | **PASS** |
| **AC-2** | 技術章節未宣告 FAIL；`not_applicable` 範圍外編號 FAIL | TC-03、TC-04 | 單元 | **PASS** |
| **AC-3** | 刪除必備實例檔或核心檢核清單時 FAIL 並指出檔案 | TC-05、TC-09 | 單元 + E2E | **PASS** |
| **AC-4** | 核心新增專屬標記時 FAIL 並指出檔案與行號；反引號說明文字不觸發 | TC-06 | 單元 | **PASS** |
| **AC-5** | `business_skills` 列出不存在之技能時 FAIL；空清單通過 | TC-07、TC-09 | 單元 + E2E | **PASS** |
| **AC-6** | 本專案與移植後專案為 PASS；全套測試無回歸 | TC-08、TC-10 | 回歸 + E2E | **PASS** |

> **RTM 統計**：PASS 6 / FAIL 0 / DEFERRED 0 / NOT COVERED 0（共 6 條 AC）

---

## 4. 測試案例執行矩陣

| TC | 內容 | 預期 | 實際 | 狀態 |
| :---: | :--- | :--- | :--- | :---: |
| TC-01 | `test_missing_and_duplicated_chapters_fail`、`test_chapter_beyond_range_fails`、`test_missing_section_fails` | 指出缺 [5]、重複 [2]、超出 [18]；無第四節 FAIL | 符合 | PASS |
| TC-02 | `test_unclassified_condition_fails` | 「同 V6」未歸屬時 FAIL | 符合 | PASS |
| TC-03 | `test_undeclared_tech_chapter_fails`、`test_tech_chapter_in_use_counts_as_declared`、`test_tech_chapter_in_both_lists_fails` | 漏宣告 FAIL；列於 `tech_chapters_in_use` 視為宣告；兩處皆列 FAIL | 符合 | PASS |
| TC-04 | `test_not_applicable_out_of_range_and_invalid_in_use_fail`；`test_missing_tech_chapters_in_use_raises` | V18、`X1` FAIL；新鍵缺鍵或型別錯誤結束碼 2 | 符合 | PASS |
| TC-05 | `test_required_instance_files` | 刪除 `profile.md` 時 FAIL 並指出路徑 | 符合 | PASS |
| TC-06 | `TestProjectMarkers` 4 項 | 行內程式碼與程式碼區塊不算；`project/` 排除；核心標記指出 `檔案:行號`；允許標記 0 處或多 1 處皆 FAIL | 符合 | PASS |
| TC-07 | `test_business_skills_must_exist_in_both_trees` | 空清單通過；缺 `.claude/skills/` 同名資料夾 FAIL | 符合 | PASS |
| TC-08 | 本專案執行 `verify_doc_sync.py` | 4 項新檢查 PASS、結束碼 0 | 符合（見第 7 節首次執行發現） | PASS |
| TC-09 | `test_a5_structure_checks_guard_ported_project` | 移植後 PASS；刪除 `profile.md` 並寫回業務技能後結束碼 1 且指出兩項 | 符合 | PASS |
| TC-10 | `tests/unit`、`.agents/tests`、`.agents/tests/e2e`、移植演練 | 全數通過 | 573、151、8、18 項通過 | PASS |

---

## 5. 實測執行日誌摘要

```text
verify_doc_sync.py      → [PASS] ASVS 章節歸屬完整（17 章；技術條件章節 3 章皆已宣告）
                          [PASS] 專案實例檔齊備 (3 個)
                          [PASS] 專屬標記只位於 AGENTS.md「本專案紅線」小節（1 處）
                          [PASS] 業務技能清單與技能資料夾一致 (2 個)
                          [SUCCESS]（exit 0；既有 WARN：ADR 編號不連續 2 則）
audit_guardrails.py     → exit 0
security_scan.py        → P0=0 P1=0
unittest tests/unit     → Ran 573 tests ... OK
unittest .agents/tests  → Ran 151 tests ... OK（新增 17 項）
unittest .agents/e2e    → Ran 8 tests ... OK
unittest e2e porting    → Ran 18 tests ... OK（新增 1 項）
```

---

## 6. 品質評測結果

不適用（品質評測範圍：否）。

---

## 7. 失敗分析與後續事項

* **TC-08 首次執行即抓到既有問題（已修正）**：安全框架第四節 V7、V8 之適用條件寫「同 V6」，未明確歸屬三類之一，C2 回報 FAIL。已改為「特徵：同 V6」。此即本案要攔截的情形：規則寫在文件、但表格本身未完全遵守。
* 無其他失敗案例。

---

## 8. QA 驗收結論

**通過**。6 條 AC 全數 PASS，無遺留缺陷。

---

## 9. 規範變更檢查紀錄（G4、G5）與 Gate 2

**G4 一致性檢查**

| # | 項目 | 結果 |
| :---: | :--- | :--- |
| 1 | `verify_doc_sync.py` | 通過；新增 4 項結構檢查皆 PASS |
| 2 | 改名與搬移之引用殘留 | 無改名或搬移；Spec-0034 標題更新已同步至 `docs/README.md` |
| 3 | 新名稱撞名 | `tech_chapters_in_use`、`REQUIRED_INSTANCE_FILES` 無撞名 |
| 4 | AGENTS.md 行數 | 174 行不變（安全規則第 2 條改寫為同一行） |
| 5 | Markdown 斷鏈測試 | 通過 |
| 6 | 程式變更 | `verify_doc_sync.py`、`project_config.py`；新增單元測試 17 項、E2E 1 項；走 Gate 2 程式檢查（下表） |

**Gate 2 程式檢查**

| 輪次 | 日期 | 範圍 | `audit_guardrails.py` | `security_scan.py` | P0 | P1 | P2 | 判定 |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 2026-11-21 | `0b47c3c..HEAD` | Exit 0 | Exit 0 | 0 | 0 | 0 | **PASS** |

* 程式覆核：新函式皆為純讀取檢查，不寫檔；路徑以 `ROOT_DIR` 與 `Path` 組合；讀檔指定 UTF-8；失敗訊息只含章節、檔案路徑與行號，不輸出檔案內容。
* 單元測試與 C7 之重疊（決議：保留）：`test_arch_review_portable` 等測試守護個別核心檔結構，C7 為全核心交付閘門，兩者用途不同，暫不精簡。

**G5 審查**（gatekeeper 視角）：零矛盾、零重複。AGENTS.md 安全規則第 2 條、安全框架第四節、PORTING 第 3、8 步對 `tech_chapters_in_use` 的描述一致。
