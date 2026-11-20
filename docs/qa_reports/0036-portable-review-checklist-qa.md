# QA 實測驗收報告：Gate 2 檢核清單通用化與 .agents 專案相依清理（Spec-0036）

> **規格**：[Spec-0036](../specs/0036-portable-review-checklist-spec.md)｜**所走流程**：[governance.md](../../.agents/workflows/governance.md)（大改）｜**分支**：`docs/spec-0036-portable-review-checklist`（G1 提案 commit `2547b95`）

## 1. 測試環境與前置條件
* **測試日期**：2026-11-21
* **作業系統與 Python 版本**：Windows 11 / Python 3.13
* **外部相依服務**：不需要
* **測試資料集**：只讀取版控中的規範文件；移植演練於暫存目錄建立合成假專案（`demo_proj`），不讀取 `data/`、`resume/`

---

## 2. 測試計畫摘要
* **測試範圍**：Gate 2 核心清單改寫、實例檔內容完整性與嚴重等級保留、零散修正、移植指南、移植演練。
* **不測範圍**：

  | 不測項目 | 理由 | 風險與替代保障 |
  | :--- | :--- | :--- |
  | PORTING 第 6 步補列之 5 個檔案中性化 | 決議第 5 項：只補列、維持選擇性 | 清單完整，移植者可依需要處理 |
  | 以腳本檢查核心檔無標記、實例檔存在 | 決議第 6 項：併入 Spec-0034 | 單元測試 `test_review_checklist_portable.py` 守護同一性質 |
  | 閘門腳本跨語言化 | 決議第 4 項：只宣告適用範圍 | PORTING.md「適用範圍」明載 |

* **進入條件**：G2 使用者核准（2026-11-21，待決事項全數採建議）。
* **退出條件**：見第 8 節。

---

## 3. 需求驗收追溯矩陣 (RTM)

| AC | 條款說明 | 測試案例 | 測試類型 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **AC-1** | 核心清單無專屬標記、無本專案元件名稱 | TC-01、TC-02 | 單元 | **PASS** |
| **AC-2** | 原清單本專案內容逐項可在實例檔找到，零遺失 | TC-03、TC-04、TC-05 | 比對腳本 + 單元 | **PASS** |
| **AC-3** | 升級條件 3 四檔一致；doc_sync_checklist、qa-testing 無本專案元件名稱 | TC-06、TC-07 | 單元 | **PASS** |
| **AC-4** | PORTING 宣告 Python 範圍、列全實例檔與補列檔案；移植演練通過且無殘留 | TC-08、TC-09 | 單元 + E2E | **PASS** |
| **AC-5** | 兩支閘門腳本通過；斷鏈測試與全套單元測試無回歸 | TC-10 | 回歸 | **PASS** |

> **RTM 統計**：PASS 5 / FAIL 0 / DEFERRED 0 / NOT COVERED 0（共 5 條 AC）

---

## 4. 測試案例執行矩陣

| TC | 內容 | 預期 | 實際 | 狀態 |
| :---: | :--- | :--- | :--- | :---: |
| TC-01 | `test_core_checklist_free_of_markers_and_project_terms` | 無標記、無 Redis／Gemini／履歷／PDF／切片／`resume_content` 等 | 符合 | PASS |
| TC-02 | `test_core_keeps_nine_categories_and_severity_definitions` | 9 類、P0／P1／P2 定義保留 | 符合 | PASS |
| TC-03 | 比對腳本：自 G1 commit 舊清單擷取含本專案內容之 20 行，抽出元件名稱、數值與反引號標記，於實例檔或核心檔搜尋 | 零遺失 | 零遺失 | PASS |
| TC-04 | `test_criteria_categories_align_with_core_and_hold_quota_values` | 實例檔 9 類對齊，持有 25MB／30 頁／10x 正本、圍欄標籤、Text-First、80 字元 | 符合 | PASS |
| TC-05 | 嚴重等級數量核對 | 減少項目皆可對應至移入實例檔或合併 | P0 25→22（原始檔保護、Text-First 移入實例檔；圍欄兩項合併）；P1 14→12（切片、對話膨脹移入實例檔）；其餘等級不變 | PASS |
| TC-06 | `test_upgrade_rule_uses_config_module_everywhere` | 4 檔皆為 `config.module` | 符合 | PASS |
| TC-07 | `test_doc_sync_and_qa_testing_free_of_project_terms` | 無 `IVectorStore` 等名稱 | 符合 | PASS |
| TC-08 | `test_porting_declares_python_scope_and_lists_instance_files` | 適用範圍、兩份實例檔、補列檔案皆在 | 符合 | PASS |
| TC-09 | `test_a2_review_checklist_core_kept_and_project_criteria_replaced` | 核心原樣、實例檔無原專案內容、兩支腳本結束碼 0 | 符合 | PASS |
| TC-10 | `verify_doc_sync.py`、`audit_guardrails.py`、全套單元測試、移植 E2E | 全數通過 | 結束碼皆 0；單元 702 項、E2E 15 項通過 | PASS |

---

## 5. 實測執行日誌摘要

```text
verify_doc_sync.py   → [SUCCESS] 100% In Sync（exit 0；範本鏡像 5 個一致）
audit_guardrails.py  → exit 0
unittest tests/unit  → Ran 702 tests ... OK
unittest e2e porting → Ran 15 tests ... OK
零遺失比對           → project lines 20，missing fragments []
專屬標記（AGENTS.md + .agents/） → 40 → 26
```

---

## 6. 品質評測結果

不適用（品質評測範圍：否）。

---

## 7. 失敗分析與後續事項

* G5 自審發現合併時兩處嚴重等級被調高（產出檔案冪等 P1→P0、提示詞載入測試 P1→P0），已於 G3 修正為獨立 P1 項，見 TC-05。
* **後續**：Spec-0034（腳本檢查，含本案決議 6）；PORTING 第 6 步所列檔案之選擇性中性化。

---

## 8. QA 驗收結論

**通過**。5 條 AC 全數 PASS，無遺留缺陷。

---

## 9. 規範變更檢查紀錄（G4、G5）

**G4 一致性檢查**

| # | 項目 | 結果 |
| :---: | :--- | :--- |
| 1 | `verify_doc_sync.py` | 通過（轉接層、鏡像、索引） |
| 2 | 改名與搬移之引用殘留 | 「上限數值的文件正本」只在實例檔；Gate 1 實例檔維度 6 連結已改指 Gate 2 實例檔；code-review 技能類別摘要已改為新類別名稱 |
| 3 | 新名稱撞名 | `review_criteria.md` 與 `review_checklist.md`、`arch_review_criteria.md` 無撞名 |
| 4 | AGENTS.md 行數 | 未修改，167 行 |
| 5 | Markdown 斷鏈測試 | 通過 |
| 6 | 程式變更 | 無腳本變更；新增單元測試 6 項、E2E 1 項 |

**G5 審查**（gatekeeper 視角）：零矛盾、零重複。備註：

* 嚴重等級保留：見 TC-05；修正後核心與實例檔對同一事項的等級一致。
* 核心清單第 2、8 類的提示詞圍欄已合併為第 2 類一項（決議 3），第 8 類以「注入圍欄見第 2 類」指向。
* 〔依賴外部 API〕〔有持久化寫入〕〔有檔案產出〕等條件無對應設定鍵，由 gatekeeper 依變更內容判斷，與 Spec-0035 維度 4 的處理一致。
* `code-review/SKILL.md` 報告範例（「Redis 清除舊切片」）屬 PORTING 第 6 步選擇性中性化範圍，本案不改。
