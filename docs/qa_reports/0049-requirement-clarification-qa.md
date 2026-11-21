# QA 實測驗收報告：feature-design 新增需求澄清階段與假設清單（Spec-0049）

> **規格**：[Spec-0049](../specs/0049-requirement-clarification-spec.md)｜**所走流程**：[governance.md](../../.agents/workflows/governance.md)（大改：修改驗證腳本）｜**分支**：`docs/spec-0049-requirement-clarification`（尚未 commit）

## 1. 測試環境與前置條件
* **測試日期**：2026-11-21
* **作業系統與 Python 版本**：Windows 11 / Python 3.13
* **外部相依服務**：Semgrep、pip-audit（沿用本機 `.venv-tools`）
* **測試資料集**：記憶體內虛構規格文字；不讀取本機敏感目錄

---

## 2. 測試計畫摘要
* **測試範圍**：階段 1.5 與參考檔（AC-1）、PRD 範本與鏡像（AC-2）、假設清單驗證（AC-3）、多代理與工具薄層對應（AC-4）、全套回歸與移植演練（AC-5）。
* **不測範圍**：以真實需求實際走一次階段 1.5 之對話演練（屬流程行為，於下一份功能規格首次使用時觀察，見第 7 節）。
* **進入條件**：G2 使用者核准（2026-11-21，待決事項 1–4 採建議、第 5 項改為一併寫入 GEMINI.md）。
* **退出條件**：見第 8 節。

---

## 3. 需求驗收追溯矩陣 (RTM)

| AC | 條款說明 | 測試案例 | 測試類型 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **AC-1** | SKILL.md 含階段 1.5 並連結參考檔；規則只寫在參考檔 | TC-01、TC-07 | 檢視 + 自我測試 | **PASS** |
| **AC-2** | PRD 範本與鏡像含第 6 節，鏡像檢查通過 | TC-02 | 腳本 | **PASS** |
| **AC-3** | 假設清單缺漏 FAIL、合法通過、舊規格不回溯 | TC-03、TC-04、TC-05 | 單元 | **PASS** |
| **AC-4** | 轉接規則只在正本；CLAUDE.md、GEMINI.md 含提問介面對應 | TC-06 | 檢視 + 腳本 | **PASS** |
| **AC-5** | 閘門腳本、全套測試、移植演練通過 | TC-08 | 回歸 | **PASS** |

> **RTM 統計**：PASS 5 / FAIL 0 / DEFERRED 0 / NOT COVERED 0（共 5 條 AC）

---

## 4. 測試案例執行矩陣

| TC | 內容 | 預期 | 實際 | 狀態 |
| :---: | :--- | :--- | :--- | :---: |
| TC-01 | SKILL.md 流程圖含 Phase15 分支、階段說明連結 `requirement_clarification.md`；7 條觸發判定只出現於參考檔 | 如左 | 符合（全倉搜尋「階段 1.5」僅 SKILL.md、參考檔、角色檔、規格） | PASS |
| TC-02 | `verify_doc_sync.py` 範本鏡像檢查 | 通過 | 通過 | PASS |
| TC-03 | `test_assumption_list_gate`：缺章節、缺宣告、缺來源欄、空表、來源「推測」、來源空白 | 各自 FAIL 並指出原因 | 符合 | PASS |
| TC-04 | 五種合法來源、加粗來源、「略過」宣告；章節外表格之「推測」不計 | 通過 | 符合 | PASS |
| TC-05 | 編號 0048 規格無清單不檢查；程式碼區塊內之標題不算章節 | 通過；FAIL | 符合 | PASS |
| TC-06 | `test_project_config`：新鍵缺漏或非整數指出 `[docs].assumptions_enforced_from`；轉接層一致性 | 如左 | 符合 | PASS |
| TC-07 | 核心中性化自我測試（`test_neutral_examples`） | 通過 | 首次失敗：參考檔引用規格編號「Spec-0049」，移除後通過 | PASS |
| TC-08 | 本專案全套回歸與移植演練（新鍵於演練中改為 1） | 全數通過 | 見第 5 節 | PASS |

---

## 5. 實測執行日誌摘要

```text
[舊版腳本＋新測試]  新函式不存在，test_assumption_list_gate 全數失敗（必然紅燈）
audit_guardrails.py         → 100% PASSED（exit 0）
verify_doc_sync.py          → [SUCCESS]；假設清單檢查受檢規格 1 個（本規格）
security_scan.py            → P0=0 P1=0（exit 0）
unittest tests/unit         → Ran 575 tests ... OK（含斷鏈）
unittest .agents/tests      → Ran 225 tests ... OK（新增 13 項）
unittest .agents/tests/e2e  → Ran 8 tests ... OK
unittest e2e porting + variants → Ran 21 tests ... OK
```

---

## 6. 品質評測結果

不適用（品質評測範圍：否）。

---

## 7. 失敗分析與後續事項

* **TC-07 首次失敗**：新參考檔頭註引用「Spec-0049」，違反核心文件不引用本專案規格歷史之守護；已移除。教訓已由既有測試涵蓋，無需新增規則。
* **殘餘風險（低）**：
  * 腳本只驗證假設清單**格式**與來源值，無法驗證來源是否屬實（例如標「使用者確認」但實際未問）；由 Gate 1 使用者檢視把關。
  * 「來源」欄須表頭恰為「來源」；表頭加粗或改名不被辨識，將判為缺欄（偏嚴，不會漏放）。
  * 階段 1.5 之實際提問效果未經真實需求演練，於下一份功能規格首次使用時觀察。

---

## 8. QA 驗收結論

**通過**。5 條 AC 全數 PASS。

---

## 9. 規範變更檢查紀錄（G4、G5）與 Gate 2

**G4 一致性檢查**

| # | 項目 | 結果 |
| :---: | :--- | :--- |
| 1 | `verify_doc_sync.py` | 通過 |
| 2 | 改名殘留 | 無改名或搬移；CLAUDE.md、GEMINI.md 條目順延編號，全倉無「第 N 項」引用 |
| 3 | 新名稱撞名 | `requirement_clarification.md`、`assumptions_enforced_from`、`check_assumption_specs` 等無撞名 |
| 4 | AGENTS.md 行數 | 未修改，175 行 |
| 5 | Markdown 斷鏈測試 | 通過 |
| 6 | 程式變更 | 驗證腳本與設定載入；單元測試齊備，走 Gate 2（下表） |

**Gate 2 程式檢查**

| 輪次 | 日期 | 範圍 | `audit_guardrails.py` | `security_scan.py` | P0 | P1 | P2 | 判定 |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 2026-11-21 | 工作區對 `main` 之差異 | Exit 0 | Exit 0 | 0 | 0 | 0 | **PASS** |

* 程式覆核：章節擷取沿用品質評測之標題層級與程式碼圍欄處理；表格解析沿用 `markdown_tables()`；新設定鍵為必要鍵，與「不提供隱含預設值」原則一致，移植演練已同步。

**G5 審查**（gatekeeper 視角）：首輪發現 2 項並已修正——(1) 「子 Agent 不得代答」與五種來源值於多檔重複，改為只寫在 `requirement_clarification.md`，其餘檔案只指向；(2) 原提案之 `action: "clarify"` 不在 AGENTS.md 交接 Schema 之 action 列舉內，為避免擴大範圍改 AGENTS.md，改為「子 Agent 結束任務並於回報中列出問題」。修正未改變提案範圍。複查零矛盾、零重複。
