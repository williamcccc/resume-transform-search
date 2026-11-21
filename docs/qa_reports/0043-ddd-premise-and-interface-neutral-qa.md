# QA 實測驗收報告：閉環核心之 DDD 前提明文化、對外介面去 CLI 預設、掃描說明去規格編號（Spec-0043）

> **規格**：[Spec-0043](../specs/0043-ddd-premise-and-interface-neutral-spec.md)｜**所走流程**：[governance.md](../../.agents/workflows/governance.md)（大改：修改驗證腳本說明字串）｜**分支**：`docs/spec-0043-ddd-premise`（G1 提案 commit `05f0578`）

## 1. 測試環境與前置條件
* **測試日期**：2026-11-21
* **作業系統與 Python 版本**：Windows 11 / Python 3.13
* **外部相依服務**：不需要（安全掃描為差異模式）
* **測試資料集**：不需要；以文字搜尋與既有測試驗證，不讀取本機敏感目錄

---

## 2. 測試計畫摘要
* **測試範圍**：DDD 前提明文化、7 處對外介面表述、`security_scan.py --help`、範本鏡像一致、全套回歸與移植演練。
* **不測範圍**：腳本與程式庫註解中之「Spec-00xx」來源註記（Spec-0043 第 2.3 節，保留）。
* **進入條件**：G2 使用者核准（2026-11-21，3 項待決事項全數採建議）。
* **退出條件**：見第 8 節。

---

## 3. 需求驗收追溯矩陣 (RTM)

| AC | 條款說明 | 測試案例 | 測試類型 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **AC-1** | PORTING 明文 DDD 前提；PORTING 與 `project.toml` 不再寫「非 DDD 專案設 false」 | TC-01 | 搜尋 | **PASS** |
| **AC-2** | 7 處不再只以 CLI 表述對外介面；範本正本與鏡像一致 | TC-02、TC-03 | 搜尋 + 鏡像同步檢查 | **PASS** |
| **AC-3** | `security_scan.py --help` 不含規格編號 | TC-04 | CLI | **PASS** |
| **AC-4** | 閘門腳本、全套測試、移植演練通過 | TC-05 | 回歸 + E2E | **PASS** |

> **RTM 統計**：PASS 4 / FAIL 0 / DEFERRED 0 / NOT COVERED 0（共 4 條 AC）

---

## 4. 測試案例執行矩陣

| TC | 內容 | 預期 | 實際 | 狀態 |
| :---: | :--- | :--- | :--- | :---: |
| TC-01 | 搜尋「非 DDD 專案設」；檢視 PORTING 適用範圍 | 零命中；適用範圍含「以 DDD 四層與依賴反轉為前提」 | 符合 | PASS |
| TC-02 | 搜尋「CLI 參數對齊」「CLI 入口命令同步」「CLI 指令設計」「CLI 旗標設計」「CLI 原有參數」「CLI 指令與引數」 | `.agents/`、`docs/templates/` 零命中 | 符合 | PASS |
| TC-03 | `verify_doc_sync.py` 範本鏡像比對 | 技術規格範本正本與鏡像一致 | 符合 | PASS |
| TC-04 | `security_scan.py --help` 輸出搜尋「Spec-」 | 0 處 | 0 處 | PASS |
| TC-05 | 閘門腳本、`tests/unit`、`.agents/tests`、`.agents/tests/e2e`、移植演練 | 全數通過 | 見第 5 節 | PASS |

---

## 5. 實測執行日誌摘要

```text
audit_guardrails.py         → 100% PASSED（exit 0）
verify_doc_sync.py          → [SUCCESS]（exit 0）
security_scan.py            → P0=0 P1=0（exit 0）
unittest tests/unit         → Ran 573 tests ... OK（含斷鏈）
unittest .agents/tests      → Ran 173 tests ... OK
unittest .agents/tests/e2e  → OK
unittest e2e porting        → OK
```

---

## 6. 品質評測結果

不適用（品質評測範圍：否）。

---

## 7. 失敗分析與後續事項

* 首次執行 `verify_doc_sync.py` 因本規格未登錄索引而 FAIL；登錄後通過，屬執行順序。
* 本案為文字表述調整，未新增守護測試：「只講 CLI」之寫法難以用字詞清單判定（「CLI 與 API」並列屬合理），由 Gate 1／G5 審查把關。

---

## 8. QA 驗收結論

**通過**。4 條 AC 全數 PASS。

---

## 9. 規範變更檢查紀錄（G4、G5）與 Gate 2

**G4 一致性檢查**

| # | 項目 | 結果 |
| :---: | :--- | :--- |
| 1 | `verify_doc_sync.py` | 通過；技術規格範本鏡像一致 |
| 2 | 改名殘留 | 第 2.2 節舊表述全倉（`.agents/`、`docs/templates/`）零命中 |
| 3 | 新名稱撞名 | 「對外介面同步」「對外介面參數對齊」無撞名 |
| 4 | AGENTS.md 行數 | 未修改，175 行 |
| 5 | Markdown 斷鏈測試 | 通過 |
| 6 | 程式變更 | `security_scan.py` 一處 `argparse` 說明字串；走 Gate 2（下表） |

**Gate 2 程式檢查**

| 輪次 | 日期 | 範圍 | `audit_guardrails.py` | `security_scan.py` | P0 | P1 | P2 | 判定 |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 2026-11-21 | `05f0578..HEAD` | Exit 0 | Exit 0 | 0 | 0 | 0 | **PASS** |

* 程式覆核：只改說明字串，掃描行為與參數不變。

**G5 審查**（gatekeeper 視角）：零矛盾、零重複。PORTING 適用範圍、第 3 步與 `project.toml` 註解對 `enabled = false` 之語意一致（只關自動檢查，DDD 前提不變），與 AGENTS.md 紅線 1 不再矛盾；feature-design 不再重述本專案紅線 2，CLI 向下相容僅由本專案紅線小節約束。
