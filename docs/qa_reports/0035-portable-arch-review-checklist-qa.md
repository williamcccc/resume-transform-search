# QA 實測驗收報告：架構前審 8 大維度通用化（Spec-0035）

> **規格**：[Spec-0035](../specs/0035-portable-arch-review-checklist-spec.md)｜**所走流程**：[governance.md](../../.agents/workflows/governance.md)（大改）｜**分支**：`docs/spec-0035-portable-arch-review`（G1 提案 commit `79b4530`）

## 1. 測試環境與前置條件
* **測試日期**：2026-11-20
* **作業系統與 Python 版本**：Windows 11 / Python 3.13
* **外部相依服務**：不需要
* **測試資料集**：只讀取版控中的規範文件；移植演練於暫存目錄建立合成假專案（`demo_proj`），不讀取 `data/`、`resume/`

---

## 2. 測試計畫摘要
* **測試範圍**：核心清單改寫、專案實例檔內容完整性、ADR 範本與引用處同步、移植演練。
* **不測範圍**：

  | 不測項目 | 理由 | 風險與替代保障 |
  | :--- | :--- | :--- |
  | 以腳本檢查實例檔存在與核心檔無標記 | 決議第 4 項：本次不改腳本，併入 Spec-0034 評估 | 單元測試 `test_arch_review_portable.py` 守護同一性質 |
  | Gate 2 `review_checklist.md` 通用化 | 決議第 5 項：另開提案 | 無；維持現狀 |
  | 回改 19 份歷史 ADR 的維度名稱 | 維度編號 1–8 不變，可對照 | 無 |

* **進入條件**：G2 使用者核准（2026-11-20，待決事項全數採建議）。
* **退出條件**：見第 8 節。

---

## 3. 需求驗收追溯矩陣 (RTM)

| AC | 條款說明 | 測試案例 | 測試類型 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **AC-1** | 核心清單無專屬標記；8 維度皆有適用條件、問題、對應標準 | TC-01、TC-02 | 單元 | **PASS** |
| **AC-2** | 原通過標準逐項可在實例檔找到，零遺失 | TC-03、TC-04 | 比對腳本 + 單元 | **PASS** |
| **AC-3** | ADR 範本維度名稱與核心一致；引用處正確、無斷鏈 | TC-05、TC-06 | 單元 + 搜尋 | **PASS** |
| **AC-4** | 移植演練：替換實例檔後核心原樣保留、原專案答案不殘留、`verify_doc_sync.py` 通過 | TC-07 | E2E | **PASS** |
| **AC-5** | `verify_doc_sync.py` 通過；全套單元測試無回歸 | TC-08 | 回歸 | **PASS** |

> **RTM 統計**：PASS 5 / FAIL 0 / DEFERRED 0 / NOT COVERED 0（共 5 條 AC）

---

## 4. 測試案例執行矩陣

| TC | 內容 | 預期 | 實際 | 狀態 |
| :---: | :--- | :--- | :--- | :---: |
| TC-01 | `test_core_checklist_has_no_project_markers` | 核心清單無 `<!-- 專案專屬` | 無 | PASS |
| TC-02 | `test_core_dimensions_complete_with_condition_question_standard` | 維度 1–8 各 4 欄非空 | 符合 | PASS |
| TC-03 | 比對腳本：自 G1 commit 的舊核心清單擷取 21 項通過標準，逐項於實例檔搜尋 | 21 項皆在 | 20 項原文相符；第 6 維度第 1 項的路徑改為可點擊連結，文字其餘相同 | PASS |
| TC-04 | `test_project_criteria_cover_all_dimensions` | 實例檔維度 1–8 皆有標準，名稱與核心一致 | 符合 | PASS |
| TC-05 | `test_adr_template_dimension_names_match_core` | ADR 範本第 5 節名稱一致、無標記 | 符合 | PASS |
| TC-06 | 全倉搜尋舊維度名稱（如「向量索引演進遷移」「Token 能效與成本熔斷」） | 規範與範本中零殘留（歷史規格與 ADR 除外） | 零殘留 | PASS |
| TC-07 | `test_a1_arch_review_core_kept_and_project_criteria_replaced` | 核心原樣、實例檔無 Redis／`resume_content`／Celery、腳本結束碼 0 | 符合 | PASS |
| TC-08 | `verify_doc_sync.py`、`audit_guardrails.py`、全套單元測試、移植 E2E | 全數通過 | 結束碼皆 0；單元 696 項、E2E 14 項通過 | PASS |

---

## 5. 實測執行日誌摘要

```text
verify_doc_sync.py   → [SUCCESS] 100% In Sync（exit 0；既有 WARN：ADR 編號 0022→0028 不連續）
audit_guardrails.py  → exit 0
unittest tests/unit  → Ran 696 tests ... OK
unittest e2e porting → Ran 14 tests ... OK
零遺失比對           → total 21，唯一差異為第 6 維度路徑轉連結
```

---

## 6. 品質評測結果

不適用（品質評測範圍：否）。

---

## 7. 失敗分析與後續事項

* 無失敗案例。
* **後續**：Gate 2 檢核清單通用化（決議第 5 項）、腳本檢查實例檔與核心標記（決議第 4 項，併入 Spec-0034）。
* 規範內專屬標記由 47 處減為 40 處（移除核心清單 6 處、ADR 範本 1 處；不含 `docs/` 歷史文件）。

---

## 8. QA 驗收結論

**通過**。5 條 AC 全數 PASS，無遺留缺陷。

---

## 9. 規範變更檢查紀錄（G4、G5）

**G4 一致性檢查**

| # | 項目 | 結果 |
| :---: | :--- | :--- |
| 1 | `verify_doc_sync.py` | 通過（轉接層、鏡像、索引） |
| 2 | 改名與搬移之引用殘留 | 舊維度名稱零殘留；PORTING.md 步驟重新編號（新增第 4 步），倉內無以步驟編號引用第 4 步以後者 |
| 3 | 新名稱撞名 | `.agents/project/`、`arch_review_criteria.md` 無撞名 |
| 4 | AGENTS.md 行數 | 未修改，167 行 |
| 5 | Markdown 斷鏈測試 | 通過 |
| 6 | 程式變更 | 無腳本變更；新增單元測試 4 項、E2E 1 項 |

**G5 審查**（gatekeeper 視角）：零矛盾、零重複。備註：

* 核心清單第二節 Fast Track 舉例「文字提取小重構」改為「小範圍重構」，屬去專案化的措辭調整，未改變規則。
* 維度 4「依賴計費外部服務」無對應特徵鍵，由 architect 依專案情況判斷；若日後需要自動化，可於 Spec-0034 一併評估。
* `.agents/project/` 未列入 `verify_doc_sync.py` 的核心檔存在檢查（決議第 4 項），移植時若誤刪實例檔，只會在 Gate 1 審查時發現。
