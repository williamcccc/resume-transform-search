# QA 實測驗收報告：核心自我測試去除實例值斷言、移植演練多組參數化（Spec-0046）

> **規格**：[Spec-0046](../specs/0046-core-tests-instance-assumptions-spec.md)｜**所走流程**：[governance.md](../../.agents/workflows/governance.md)（大改：修改核心自我測試與移植演練）｜**分支**：`docs/spec-0046-core-tests-instance-assumptions`（G1 提案 commit `d753b85`）

## 1. 測試環境與前置條件
* **測試日期**：2026-11-21
* **作業系統與 Python 版本**：Windows 11 / Python 3.13
* **外部相依服務**：Semgrep、pip-audit（五組實測沿用本機 `.venv-tools`）
* **測試資料集**：暫存目錄之合成假專案（參數化演練 3 變體、五組實測各 1 專案），不讀取本機敏感目錄

---

## 2. 測試計畫摘要
* **測試範圍**：3 支核心測試去除實例值斷言、實例值斷言移至專案側、假專案強制啟用分層、參數化演練、以新核心重跑五組實測、全套回歸。
* **不測範圍**：參數化演練不含安全掃描（由既有移植演練與五組實測涵蓋）。
* **進入條件**：G2 使用者核准（2026-11-21，2 項待決事項全數採建議）。
* **退出條件**：見第 8 節。

---

## 3. 需求驗收追溯矩陣 (RTM)

| AC | 條款說明 | 測試案例 | 測試類型 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **AC-1** | 核心測試無本專案實例值斷言；本專案實例值由專案側守護 | TC-02、TC-03 | 單元 | **PASS** |
| **AC-2** | 實例 `enabled = false` 時 `test_guardrail_gaps` 通過且分層違規仍檢出 | TC-04 | 整合（CLI） | **PASS** |
| **AC-3** | 參數化演練 3 變體通過；修正前至少一變體失敗 | TC-01、TC-05 | E2E（先紅後綠） | **PASS** |
| **AC-4** | 新核心重跑五組實測：自我測試全數通過，閘門腳本與探測結果不變 | TC-06 | 實測 | **PASS** |
| **AC-5** | 本專案閘門腳本與全套測試通過 | TC-07 | 回歸 | **PASS** |

> **RTM 統計**：PASS 5 / FAIL 0 / DEFERRED 0 / NOT COVERED 0（共 5 條 AC）

---

## 4. 測試案例執行矩陣

| TC | 內容 | 預期 | 實際 | 狀態 |
| :---: | :--- | :--- | :--- | :---: |
| TC-01 | 修正前執行 `test_portable_variants_e2e` | 變體失敗 | 3 變體之核心自我測試皆失敗（逐步導入 7 項、清單全空 1 項、非預設佈局 1 項）；`verify_doc_sync`、`audit_guardrails` 三變體皆通過 | PASS（紅燈） |
| TC-02 | `test_agents_md_has_project_section_and_no_annotations_outside` | 只驗小節存在與其外無附註 | 符合 | PASS |
| TC-03 | 專案側 `test_project_red_lines_map_red_lines_1_and_6`、`test_layers_enabled_for_this_project` | 本專案紅線小節列出 `src/domain/interfaces.py`、`src/infrastructure/config.py`、`AppConfig`；`enabled` 為真 | 符合 | PASS |
| TC-04 | `TestInstanceLayersDisabled`：實例 `enabled = false` 建立假專案 | 基準零 P0；植入 `app/domain/leak.py` 引入第三方即 P0 | 符合 | PASS |
| TC-05 | 修正後執行 `test_portable_variants_e2e` | 3 變體三項驗證全數通過；TOML 改寫器處理多行陣列與表格陣列 | OK | PASS |
| TC-06 | 以新核心重跑五組實測（乾淨 clone） | 自我測試全過；探測 21/21；T5 基準流程不變 | 五組自我測試 183 項 OK；探測 4/4、4/4、4/4、6/6、3/3；T5 刻意植入之 Semgrep 發現：首掃 P0 → 登錄基準後通過（基準內=1）→ 基準過期恢復 P0 | PASS |
| TC-07 | 閘門腳本、`tests/unit`、`.agents/tests`、`.agents/tests/e2e`、移植演練 | 全數通過 | 見第 5 節 | PASS |

---

## 5. 實測執行日誌摘要

```text
[五組實測，修正前]  自我測試：T1 7 項失敗、T2–T5 各 1 項失敗；閘門腳本與探測全數正確
[五組實測，修正後]  自我測試：五組皆 183 項 OK；探測 21/21
audit_guardrails.py         → 100% PASSED（exit 0）
verify_doc_sync.py          → [SUCCESS]（exit 0）
security_scan.py            → P0=0 P1=0（exit 0）
unittest tests/unit         → Ran 575 tests ... OK（新增 2 項，含斷鏈）
unittest .agents/tests      → Ran 183 tests ... OK（新增 1 項）
unittest .agents/tests/e2e  → OK
unittest e2e porting        → OK
unittest e2e variants       → OK（新增）
```

---

## 6. 品質評測結果

不適用（品質評測範圍：否）。

---

## 7. 失敗分析與後續事項

* **逃逸分析**：3 支核心測試斷言本專案實例值，屬測試設計缺口——「核心測試只驗通用規則、實例值由專案側驗」之原則未落實到測試層；既有移植演練只測一組參數且沿用原專案之紅線小節與分層開關，無法揭露。已以參數化演練補上，教訓歸屬通用，已回寫核心。
* **索引未登錄致 `verify_doc_sync.py` 失敗（已修正）**：登錄後通過，屬執行順序。

---

## 8. QA 驗收結論

**通過**。5 條 AC 全數 PASS。

---

## 9. 規範變更檢查紀錄（G4、G5）與 Gate 2

**G4 一致性檢查**

| # | 項目 | 結果 |
| :---: | :--- | :--- |
| 1 | `verify_doc_sync.py` | 通過 |
| 2 | 改名殘留 | `test_agents_md_project_section_keeps_red_line_values` 改名為 `test_agents_md_has_project_section_and_no_annotations_outside`，全倉無殘留 |
| 3 | 新名稱撞名 | `TestInstanceLayersDisabled`、`test_portable_variants_e2e`、`VARIANTS` 無撞名 |
| 4 | AGENTS.md 行數 | 未修改，175 行 |
| 5 | Markdown 斷鏈測試 | 通過 |
| 6 | 程式變更 | 僅測試程式；走 Gate 2（下表） |

**Gate 2 程式檢查**

| 輪次 | 日期 | 範圍 | `audit_guardrails.py` | `security_scan.py` | P0 | P1 | P2 | 判定 |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 2026-11-21 | `d753b85..HEAD` | Exit 0 | Exit 0 | 0 | 0 | 0 | **PASS** |

* 程式覆核：參數化演練只寫入暫存目錄；TOML 改寫器以引號感知之括號深度判定多行陣列結尾，並有單元測試涵蓋含 `]` 之字串值；子程序設逾時。

**G5 審查**（gatekeeper 視角）：零矛盾、零重複。本專案實例值斷言只存在於專案側測試；核心測試只驗通用規則，與「通用核心＋專案實例檔」分工一致。
