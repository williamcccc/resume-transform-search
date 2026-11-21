# QA 實測驗收報告：紅線 1、6 本專案附註移入本專案紅線小節（Spec-0040）

> **規格**：[Spec-0040](../specs/0040-red-lines-1-6-project-annotations-spec.md)｜**ADR**：[ADR-0040](../adr/0040-red-lines-1-6-project-values-moved.md)｜**所走流程**：[governance.md](../../.agents/workflows/governance.md)（大改：修改架構紅線）｜**分支**：`docs/spec-0040-red-lines-1-6`（G1 提案 commit `9960ae8`）

## 1. 測試環境與前置條件
* **測試日期**：2026-11-21
* **作業系統與 Python 版本**：Windows 11 / Python 3.13
* **外部相依服務**：不需要（安全掃描為差異模式）
* **測試資料集**：守護測試以記憶體字串建構紅線小節；違規訊息測試於暫存目錄建立最小假專案，不讀取 `data/`、`resume/`

---

## 2. 測試計畫摘要
* **測試範圍**：紅線文字逐字保留、守護測試範圍收窄、違規訊息中性化、全套測試與移植演練回歸。
* **不測範圍**：歷史規格與 QA 報告中引用的舊紅線文字（屬歷史紀錄，Spec-0040 第 2.4 節）。
* **進入條件**：G2 使用者核准（2026-11-21，3 項待決事項全數採建議）。
* **退出條件**：見第 8 節。

---

## 3. 需求驗收追溯矩陣 (RTM)

| AC | 條款說明 | 測試案例 | 測試類型 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **AC-1** | 紅線 1、6 不含「本專案為」；本專案紅線小節含對應條目；其餘文字逐字不變 | TC-01、TC-02 | 比對腳本 + 單元 | **PASS** |
| **AC-2** | 守護測試只排除本專案紅線小節；通用紅線寫回附註時測試失敗 | TC-03 | 單元 | **PASS** |
| **AC-3** | 違規訊息不含 `AppConfig`，含「設定模組」 | TC-04、TC-05 | 整合（CLI） + 先紅後綠 | **PASS** |
| **AC-4** | 閘門腳本、全套測試、移植演練、斷鏈測試通過 | TC-06、TC-07 | 回歸 + E2E | **PASS** |

> **RTM 統計**：PASS 4 / FAIL 0 / DEFERRED 0 / NOT COVERED 0（共 4 條 AC）

---

## 4. 測試案例執行矩陣

| TC | 內容 | 預期 | 實際 | 狀態 |
| :---: | :--- | :--- | :--- | :---: |
| TC-01 | 比對腳本：修改前 AGENTS.md 刪去兩處附註，與修改後刪去新條目逐字比較 | 相同 | `verbatim True` | PASS |
| TC-02 | `test_agents_md_project_section_keeps_red_line_values` | 本專案紅線小節含「紅線 1、6 本專案對應」；小節外無「本專案為」 | 符合 | PASS |
| TC-03 | `test_generic_red_lines_are_guarded`：通用紅線含「本專案為」、本專案紅線含「履歷」 | 只抓到通用紅線之「本專案為」；行數不變 | 符合 | PASS |
| TC-04 | `TestHardcodedUrlMessageIsNeutral`：假專案寫死 `redis://` URL | 結束碼 1；訊息含「設定模組（config.module）」，不含 `AppConfig` | 符合 | PASS |
| TC-05 | 以舊版 `audit_guardrails.py` 重跑 TC-04 | 失敗 | `FAILED (failures=1)`，還原後通過 | PASS |
| TC-06 | `audit_guardrails.py`、`verify_doc_sync.py`、`security_scan.py` | 全數結束碼 0 | 100% PASSED；SUCCESS；P0=0 P1=0 | PASS |
| TC-07 | `tests/unit`、`.agents/tests`、`.agents/tests/e2e`、移植演練 | 全數通過 | 見第 5 節 | PASS |

---

## 5. 實測執行日誌摘要

```text
audit_guardrails.py         → 🎉 100% PASSED（exit 0）
verify_doc_sync.py          → [SUCCESS]（exit 0）
security_scan.py            → P0=0 P1=0（exit 0）
unittest tests/unit         → Ran 573 tests ... OK（含斷鏈測試）
unittest .agents/tests      → OK（新增 3 項）
unittest .agents/tests/e2e  → OK
unittest e2e porting        → OK
```

---

## 6. 品質評測結果

不適用（品質評測範圍：否）。

---

## 7. 失敗分析與後續事項

* 首次全套執行時斷鏈測試失敗 1 項：索引與 ADR 已連至本報告，而本報告尚未建立；建立本報告後通過。屬執行順序，非缺陷。
* 無遺留事項。核心文件（含通用紅線）已無「本專案為」附註，由守護測試持續約束。

---

## 8. QA 驗收結論

**通過**。4 條 AC 全數 PASS。

---

## 9. 規範變更檢查紀錄（G4、G5）與 Gate 2

**G4 一致性檢查**

| # | 項目 | 結果 |
| :---: | :--- | :--- |
| 1 | `verify_doc_sync.py` | 通過；專屬標記仍只有「本專案紅線」一處 |
| 2 | 改名與搬移之引用殘留 | `RED_LINE_SECTION` 改名為 `PROJECT_RED_LINE_SECTION`，全倉無殘留；核心文件無「本專案為」 |
| 3 | 新名稱撞名 | `strip_project_red_lines`、`TestHardcodedUrlMessageIsNeutral` 無撞名 |
| 4 | AGENTS.md 行數 | 174 → 175 行（+1）；字元數 18,102 → 18,011 |
| 5 | Markdown 斷鏈測試 | 通過 |
| 6 | 程式變更 | `audit_guardrails.py` 兩處字串（訊息與註解）；新增測試；走 Gate 2（下表） |

**Gate 2 程式檢查**

| 輪次 | 日期 | 範圍 | `audit_guardrails.py` | `security_scan.py` | P0 | P1 | P2 | 判定 |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 2026-11-21 | `9960ae8..HEAD` | Exit 0 | Exit 0 | 0 | 0 | 0 | **PASS** |

* 程式覆核：只改訊息字串與註解，不改檢查邏輯；新訊息不輸出檔案內容以外之資訊。

**G5 審查**（gatekeeper 視角）：零矛盾、零重複。PORTING 第 5 步「通用紅線 1、6、7 原樣保留」與本變更一致（通用紅線已無本專案值）；本專案值於 AGENTS.md（常駐對照）與 `project.toml`（腳本正本）各一處，角色不同，已於 ADR-0040 後果記錄。
