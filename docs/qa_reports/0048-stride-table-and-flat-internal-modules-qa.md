# QA 實測驗收報告：STRIDE 威脅表以欄名判定、扁平根目錄內部模組判定（Spec-0048）

> **規格**：[Spec-0048](../specs/0048-stride-table-and-flat-internal-modules-spec.md)｜**所走流程**：[governance.md](../../.agents/workflows/governance.md)（大改：修改驗證腳本）｜**分支**：`docs/spec-0048-stride-table-and-flat-internal-modules`（G1 提案 commit `004128a`）

## 1. 測試環境與前置條件
* **測試日期**：2026-11-21
* **作業系統與 Python 版本**：Windows 11 / Python 3.13
* **外部相依服務**：Semgrep、pip-audit（沿用本機 `.venv-tools`）
* **測試資料集**：記憶體內虛構規格文字與暫存目錄假專案；不讀取本機敏感目錄

---

## 2. 測試計畫摘要
* **測試範圍**：威脅表判定（問題 1）、扁平根目錄內部模組判定（問題 2）、PORTING 補述、全套回歸。
* **不測範圍**：重新執行 Spec-0047 之六個實測專案（本次變更只影響 `package = ""` 與宣告安全範圍之規格，已由整合測試與移植演練涵蓋）。
* **進入條件**：G2 使用者核准（2026-11-21，2 項待決事項全數採建議）。
* **退出條件**：見第 8 節。

---

## 3. 需求驗收追溯矩陣 (RTM)

| AC | 條款說明 | 測試案例 | 測試類型 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **AC-1** | 無 STRIDE 欄之表格首欄為 D／E 時 FAIL；先紅後綠 | TC-01 | 單元 | **PASS** |
| **AC-2** | STRIDE 欄任一位置、「STRIDE 類別」、加粗皆通過；無威脅列 FAIL | TC-02、TC-03 | 單元 | **PASS** |
| **AC-3** | `package = ""` 時根目錄非分層套件屬內部；略過目錄與 `.agents/` 不計；先紅後綠 | TC-04、TC-05 | 單元 + 整合 | **PASS** |
| **AC-4** | `package` 非空時結果不變 | TC-06 | 單元 + 回歸 | **PASS** |
| **AC-5** | 本專案閘門腳本與全套測試、移植演練通過 | TC-07 | 回歸 | **PASS** |

> **RTM 統計**：PASS 5 / FAIL 0 / DEFERRED 0 / NOT COVERED 0（共 5 條 AC）

---

## 4. 測試案例執行矩陣

| TC | 內容 | 預期 | 實際 | 狀態 |
| :---: | :--- | :--- | :--- | :---: |
| TC-01 | `test_single_letter_in_non_stride_table_is_not_a_threat_table`：卡點表首欄 `D`、`**E**`，另有 `NFR-1` | FAIL「缺少 STRIDE 威脅表」 | 修正前通過（偽陰性重現）；修正後 FAIL | PASS |
| TC-02 | `test_stride_column_variants_pass`、既有 `test_stride_letter_in_first_column_counts` 與範本格式案例 | 通過 | 符合 | PASS |
| TC-03 | `test_stride_column_without_threat_rows_fails`（空範本列、`S、T` 多字母）；`test_markdown_tables_parsing`（跳脫 `\|`、無分隔列之區塊不算表格） | FAIL；解析結果正確 | 符合（解析函式修正前不存在） | PASS |
| TC-04 | `TestFlatRootPackage`：Application 引用根目錄 `shared/` 零 P0；Domain 引用為「逆向依賴外層模組」；略過目錄名被引用仍為「第三方套件」 | 如左 | 修正前前兩項失敗；修正後全過 | PASS |
| TC-05 | `test_internal_roots_flat_layout_lists_top_level_entries`：頂層目錄、`.py` 模組、略過目錄、隱藏目錄、非識別字目錄、非 `.py` 檔 | 只計 `domain`、`application`、`shared`、`main` | 符合 | PASS |
| TC-06 | 同測試之 `package = "kit"` 案例；`TestSrcLayoutPackage`；本專案稽核 | 只回傳 `{"kit"}`；結果不變 | 符合 | PASS |
| TC-07 | 本專案全套回歸 | 全數通過 | 見第 5 節 | PASS |

---

## 5. 實測執行日誌摘要

```text
[舊版腳本＋新測試]  5 項失敗（AC-1、AC-3 關鍵案例與 2 個新函式）
audit_guardrails.py         → 100% PASSED（exit 0）
verify_doc_sync.py          → [SUCCESS]（exit 0）
security_scan.py            → P0=0 P1=0（exit 0）
unittest tests/unit         → Ran 575 tests ... OK（含斷鏈）
unittest .agents/tests      → Ran 212 tests ... OK（新增 8 項）
unittest .agents/tests/e2e  → OK
unittest e2e porting + variants → OK
```

---

## 6. 品質評測結果

不適用（品質評測範圍：否）。

---

## 7. 失敗分析與後續事項

* **逃逸分析**：兩項皆為 Spec-0047 引入或保留之判定過寬／過窄——放寬 STRIDE 樣式時未同時要求「該表為威脅表」；扁平根目錄之內部根名只取四層名稱，未與一般佈局之語意對照。已登錄於 QA-0047 第 7 節，本規格收斂；教訓（放寬判定時同時列出可能之偽陰性案例並寫成測試）屬通用，已以測試落實。
* **殘餘風險（低）**：
  * 威脅表須為含分隔列之 GFM 表格；無分隔列之管線文字不算表格（與 Markdown 渲染一致）。
  * 扁平根目錄下，根目錄中與第三方套件同名之目錄被視為內部（與 Python 匯入時本地目錄優先之行為一致）。

---

## 8. QA 驗收結論

**通過**。5 條 AC 全數 PASS。

---

## 9. 規範變更檢查紀錄（G4、G5）與 Gate 2

**G4 一致性檢查**

| # | 項目 | 結果 |
| :---: | :--- | :--- |
| 1 | `verify_doc_sync.py` | 通過 |
| 2 | 改名殘留 | `STRIDE_ROW_PATTERN` 改為 `STRIDE_CELL_PATTERN`＋`has_threat_table`，程式碼無殘留（僅歷史規格 Spec-0047 提及舊名，屬紀錄） |
| 3 | 新名稱撞名 | `markdown_tables`、`has_threat_table`、`TABLE_SEPARATOR_PATTERN`、`STRIDE_CELL_PATTERN` 無撞名 |
| 4 | AGENTS.md 行數 | 未修改，175 行 |
| 5 | Markdown 斷鏈測試 | 通過 |
| 6 | 程式變更 | 驗證腳本；單元測試齊備，走 Gate 2（下表） |

**Gate 2 程式檢查**

| 輪次 | 日期 | 範圍 | `audit_guardrails.py` | `security_scan.py` | P0 | P1 | P2 | 判定 |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 2026-11-21 | `004128a..HEAD` | Exit 0 | Exit 0 | 0 | 0 | 0 | **PASS** |

* 程式覆核：`internal_roots` 於 `package` 非空時提早回傳，一般佈局零影響；根目錄列舉只讀目錄項目名稱、不讀檔案內容，略過隱藏目錄（含 `.agents/`、`.git/`）與 `ignore_scan_dirs`；表格解析以 `(?<!\\)\|` 切分保留跳脫管線，分隔列須每格皆為 `:?-{3,}:?`。

**G5 審查**（gatekeeper 視角）：零矛盾、零重複。威脅表格式之正本仍為 `prd_template.md` 與 `security_nfr_framework.md`（表頭皆含「STRIDE」欄），腳本只驗證；PORTING 補述與 `internal_roots` docstring 用語一致。
