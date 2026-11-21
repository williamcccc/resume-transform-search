# QA 實測驗收報告：專案概況檔、閉環自我測試隨核心移植、AGENTS.md 紅線分區（Spec-0037）

> **規格**：[Spec-0037](../specs/0037-project-profile-tests-and-red-lines-spec.md)｜**決策**：[ADR-0037](../adr/0037-agents-red-lines-generic-and-project-groups.md)｜**所走流程**：[governance.md](../../.agents/workflows/governance.md)（大改）｜**分支**：`docs/spec-0037-profile-tests-red-lines`（G1 提案 commit `71a1afe`）

## 1. 測試環境與前置條件
* **測試日期**：2026-11-21
* **作業系統與 Python 版本**：Windows 11 / Python 3.13
* **外部相依服務**：不需要
* **測試資料集**：只讀取版控中的規範文件；移植演練於暫存目錄建立合成假專案（`demo_proj`），不讀取 `data/`、`resume/`

---

## 2. 測試計畫摘要
* **測試範圍**：專案概況檔與核心引用、閉環自我測試搬移與 CI、AGENTS.md 紅線分區與 ADR、移植演練。
* **不測範圍**：

  | 不測項目 | 理由 | 風險與替代保障 |
  | :--- | :--- | :--- |
  | CI 實際執行新增之 Step 4 | 需推送後由 GitHub Actions 執行 | 本機以相同指令執行 `.agents/tests` 全數通過；PR CI 結果於合併前確認 |
  | 紅線語意審查之外的 AGENTS.md 其他章節 | 本案只改第 1 節編排、第 2 節一行標記、第 4 節一行 | 比對腳本驗證紅線原文 |

* **進入條件**：G2 使用者核准（2026-11-21，待決事項全數採建議）。
* **退出條件**：見第 8 節。

---

## 3. 需求驗收追溯矩陣 (RTM)

| AC | 條款說明 | 測試案例 | 測試類型 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **AC-1** | 概況檔涵蓋專案事實；引用之核心檔不再含這些事實與專屬標記 | TC-01、TC-02 | 單元 + 搜尋 | **PASS** |
| **AC-2** | 專屬標記只剩 AGENTS.md 本專案紅線整節標記；PORTING 第 5 步改寫 | TC-03 | 搜尋 | **PASS** |
| **AC-3** | 紅線原文保留（只改編排）；分層樹無本專案元件；ADR-0037 登錄 | TC-04、TC-05 | 比對腳本 + 搜尋 | **PASS**（附註見第 7 節） |
| **AC-4** | 搬移後測試總數不減且全數通過；CI 執行 `.agents/tests/` | TC-06、TC-07 | 回歸 | **PASS** |
| **AC-5** | 移植演練：替換實例檔與設定後，假專案內 `.agents/tests/` 與閘門腳本通過 | TC-08 | E2E | **PASS** |
| **AC-6** | `verify_doc_sync.py`、`audit_guardrails.py` 通過；斷鏈測試無回歸 | TC-09 | 回歸 | **PASS** |

> **RTM 統計**：PASS 6 / FAIL 0 / DEFERRED 0 / NOT COVERED 0（共 6 條 AC）

---

## 4. 測試案例執行矩陣

| TC | 內容 | 預期 | 實際 | 狀態 |
| :---: | :--- | :--- | :--- | :---: |
| TC-01 | `test_profile_covers_project_facts` | 5 節標題與 `convert_to_md.py`、轉檔、檢索、`idx:resumes`、求職者姓名、DB 15 皆在 | 符合 | PASS |
| TC-02 | 搜尋 bug-triage、hotfix、bug.md、缺陷報告範本、feature-design、doc-sync、developer、gatekeeper、unit-testing、quality-evaluation、tech_spec_template | 無 `轉檔、檢索`、`Redis 索引結構`、`convert_to_md.py`、`--index-to-redis`、DB 15 等事實 | 符合；改為引用專案概況 | PASS |
| TC-03 | 全倉搜尋 `<!-- 專案專屬`（AGENTS.md + `.agents/`） | 只剩 AGENTS.md 本專案紅線整節標記 | 1 處標記；另 2 處為 PORTING 說明文字 | PASS |
| TC-04 | 比對腳本：舊 AGENTS.md 紅線章節 12 段文字（去除標記與標題前綴），於新檔逐字搜尋 | 全數存在 | 12/12 存在 | PASS |
| TC-05 | 分層樹狀圖、ADR 索引 | 無 `google-genai`、RediSearch、PyMuPDF、「轉檔邏輯」；ADR-0037 已登錄 | 符合 | PASS |
| TC-06 | 測試總數 | 搬移前 `tests/unit` 703 項 | 搬移後 `tests/unit` 573 + `.agents/tests` 131 = 704（新增 1 項概況檔測試）；E2E `.agents/tests/e2e` 8 項 | PASS |
| TC-07 | CI 設定 | `.github/workflows/ci.yml` 有執行 `.agents/tests` 之步驟 | Step 4 已新增 | PASS |
| TC-08 | `test_a3_core_self_tests_pass_in_ported_project` | 假專案內 `python -m unittest discover -s .agents/tests` 結束碼 0 | 首次執行失敗 3 項（見第 7 節），修正後通過；移植演練 16 項全數通過 | PASS |
| TC-09 | `verify_doc_sync.py`、`audit_guardrails.py`、斷鏈測試 | 結束碼 0；無斷鏈 | 符合 | PASS |

---

## 5. 實測執行日誌摘要

```text
verify_doc_sync.py              → [SUCCESS] 100% In Sync（exit 0）
audit_guardrails.py             → exit 0
unittest tests/unit             → Ran 573 tests ... OK
unittest .agents/tests          → Ran 131 tests ... OK
unittest .agents/tests/e2e      → Ran 8 tests ... OK
unittest e2e porting            → Ran 16 tests ... OK
紅線原文比對                    → checked 12 fragments; missing []
專屬標記（AGENTS.md + .agents/） → 26 → 1（另 2 處為 PORTING 說明文字）
AGENTS.md 行數                  → 167 → 174
```

---

## 6. 品質評測結果

不適用（品質評測範圍：否）。

---

## 7. 失敗分析與後續事項

* **TC-08 首次失敗（已修正）**：`test_quality_ac_gate` 3 項以本專案門檻（`quality_ac_enforced_from = 23`）撰寫，移植後門檻為 1 即失敗。根因：測試結果依賴專案設定值。修正：測試模組以 `setUpModule` 固定測試用門檻，不受專案設定影響。此即本案「閉環自我測試須在移植後通過」所要攔截的情形。
* **未搬移之候選**（依 3.2 搬移條件逐檔確認）：`test_audit_eval_only_imports`（依賴 `eval_only_modules = ["ragas"]` 專案設定）、`test_hardcode_extractions`（測試 `src/`）、`test_portable_closed_loop_e2e`（本專案移植來源之演練，依賴原專案業務技能與指紋）留在 `tests/`。
* **AC-3 附註**：紅線 7 第一點拆為通用敘述與「紅線 7 本專案補充」；補充保留原文（求職者、履歷、`data/`、`resume/`），通用敘述為新增之一般化文字。約束效力未放寬，詳 ADR-0037。
* **後續**：CI Step 4 於 PR 上實際執行結果待合併前確認。

---

## 8. QA 驗收結論

**通過**。6 條 AC 全數 PASS，無遺留缺陷。

---

## 9. 規範變更檢查紀錄（G4、G5）

**G4 一致性檢查**

| # | 項目 | 結果 |
| :---: | :--- | :--- |
| 1 | `verify_doc_sync.py` | 通過（轉接層、鏡像、索引、ADR） |
| 2 | 搬移與改名之引用殘留 | `docs/README.md` 10 處測試路徑改為 `.agents/tests/`；規範與 CI 中無舊測試路徑；紅線編號保留，22 處歷史引用不需修改 |
| 3 | 新名稱撞名 | `profile.md`、`.agents/tests/` 無撞名 |
| 4 | AGENTS.md 行數 | 167 → 174（+7，低於 20 行門檻），低於 200 行上限 |
| 5 | Markdown 斷鏈測試 | 通過 |
| 6 | 程式變更 | 無閘門腳本變更；CI 新增 1 步；測試搬移 10 檔、新增 `test_project_instance_files.py`、移植演練新增 1 項 |

**G5 審查**（gatekeeper 視角）：零矛盾、零重複。備註：

* 敏感資料類型只定義於專案概況檔第 4 節與 AGENTS.md 紅線 7 本專案補充；後者為紅線原文保留，概況檔為技能引用用之事實清單，Gate 2 實例檔改為引用概況檔，未新增第三處。
* 紅線 7 通用敘述以 `privacy.sensitive_dirs` 表示敏感目錄，與 `audit_guardrails.py` 實際檢查來源一致。
* 本專案紅線小節說明「新增紅線編號自 8 起接續」，與 PORTING 第 5 步一致。
