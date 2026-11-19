# QA 實測驗收報告：規範體系一致性清理（Spec-0027）

> **規格**：[Spec-0027](../specs/0027-governance-consistency-cleanup-spec.md)｜**所走流程**：[governance.md](../../.agents/workflows/governance.md)（大改）｜**分支**：`docs/spec-0027-governance-consistency`（基準 `1d138c2`）

## 1. 測試環境與前置條件
* **測試日期**：2026-11-19
* **作業系統與 Python 版本**：Windows 11 / Python 3.13.14 on PowerShell
* **外部相依服務**：不需要
* **測試資料集**：記憶體內虛構規格文字；E2E 將專案規範文件複製到暫存目錄後執行

---

## 2. 測試計畫摘要
* **測試範圍**：Spec-0027 第二章 24 項發現的處理結果；M7 腳本修正；既有測試與驗證腳本無回歸。
* **不測範圍**：

  | 不測項目 | 理由 | 風險與替代保障 |
  | :--- | :--- | :--- |
  | 修正後的規範能否讓 AI 實際走對流程 | 屬 AI 行為，無法自動化驗證 | 以全倉搜尋確認矛盾字句已移除（G4-2）；下一次功能或缺陷任務即為實戰驗證 |
  | `docs/images/closed_loop_workflow.svg` | 不在 Spec-0027 檔案清單內 | 列為後續事項（第 7 節） |

* **進入條件**：G2 使用者核准（2026-11-19，待決事項第 4 項依使用者回饋修訂）。
* **退出條件**：見第 8 節。

---

## 3. 需求驗收追溯矩陣 (RTM)

| AC | 條款說明 | 測試案例 | 測試類型 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **AC-1** | 24 項發現逐項處理 | TC-01 | 人工覆核 | **PASS** |
| **AC-2** | 8 大維度只有一份定義 | TC-02 | 全倉搜尋 | **PASS** |
| **AC-3** | 指定過時字句無殘留 | TC-03 | 全倉搜尋 | **PASS** |
| **AC-4** | `governance.md` 具角色欄；CLAUDE.md 分級表涵蓋規範變更 | TC-01 | 人工覆核 | **PASS** |
| **AC-5** | G4 六項檢查、全套測試、兩支腳本通過 | TC-04、TC-05 | 回歸 + 單元 | **PASS** |

> **RTM 統計**：PASS 5 / FAIL 0 / DEFERRED 0 / NOT COVERED 0（共 5 條 AC）

---

## 4. 測試案例執行矩陣

| 案例 | 名稱 | 分類 | 輸入 / 操作 | 預期 | 實際 | 判定 |
| :---: | :--- | :---: | :--- | :--- | :--- | :---: |
| **TC-01** | 24 項逐項覆核 | Review | 對照附錄 A 處理結果表 | 每項皆有處理或理由 | 24 項皆已處理 | **PASS** |
| **TC-02** | 8 大維度單一正本 | Search | 全倉搜尋 ADR 舊版維度名稱（可稽核性、無損與容錯性） | `.agents/` 內零命中 | 零命中；feature-design、ADR 範本、doc-sync 皆改為引用 arch_review_checklist | **PASS** |
| **TC-03** | 過時字句 | Search | 搜尋「單純 Bug 修復」「或缺陷修復」「8 大技能」「四大修復底線」「Google Antigravity 團隊設計」「CLI 入口點」「tests/integration」（排除 `docs/specs`、`docs/qa_reports` 歷史紀錄與 `tests/`） | 零不當殘留 | 命中 7 處：5 處為正當用法（如「功能交付或缺陷修復後」、CLI 入口點的架構描述）；REQUIREMENTS.md 的 `tests/integration/` 已修正；`closed_loop_workflow.svg` 列為後續事項 | **PASS** |
| **TC-04** | M7 先紅後綠 | Unit | 新增 3 項測試，先以修正前的腳本執行，再以修正後執行 | 修正前 2 項失敗（引用字樣誤判），修正後全數通過；第 3 項（後備搜尋）兩者皆通過 | 修正前 `FAILED (failures=2)`；修正後 `Ran 18 tests ... OK` | **PASS** |
| **TC-05** | 全套回歸 | Regression | 全套單元測試、E2E、兩支驗證腳本 | 全數通過 | 見第 5 節 | **PASS** |

---

## 5. 實測執行日誌摘要
```text
[Unit] python -m unittest tests.unit.test_quality_ac_gate        → 修正前 FAILED (failures=2)；修正後 Ran 18 tests ... OK
[Unit] python -m unittest discover -s tests/unit -p "test_*.py" → Ran 615 tests ... OK
[E2E]  python -m unittest tests.e2e.test_workflow_tracks_doc_sync_e2e → Ran 8 tests ... OK
[Doc]  verify_doc_sync.py → SUCCESS；轉接層 Skill 10／角色 3；分流表 4；鏡像 5；AGENTS.md 158 行
[AST]  audit_guardrails.py → 100% PASSED（零 P0）
```

---

## 6. 品質評測結果
不適用（規格宣告品質評測範圍：否）。

---

## 7. 失敗分析與後續事項

| # | 現象 | 根因 | 處置 |
| :---: | :--- | :--- | :--- |
| 1 | 撰寫 Spec-0027 草稿時 `verify_doc_sync.py` FAIL | 發現表引用了品質評測範圍宣告字樣，`quality_scope()` 取全文第一個 | 即 M7，本案已修正 |
| 2 | 全倉斷鏈測試失敗：`docs/README.md` | 索引先登錄 QA-0027 連結，報告尚未建立 | 建立本報告後通過 |
| 3 | `docs/images/closed_loop_workflow.svg`（根目錄 README 引用）仍為單一流程的舊圖 | Spec-0025 起流程已分軌，圖片未更新 | **後續事項**：另以規範變更小改重繪，或改為引用 AGENTS.md 分流表 |

---

## 8. QA 驗收結論
* **驗收判定**：**【通過 (PASSED)】**
* **放行標準**：RTM 零 `FAIL`、零 `NOT COVERED` ✅；M7 先紅後綠 ✅；品質評測不適用
* **放行說明**：准予進入 G5 審查與程式部分的 Gate 2。

---

## 9. 規範變更檢查紀錄（G4、G5）與 Gate 2

### 9.1 G4 一致性檢查

| # | 檢查項 | 結果 |
| :---: | :--- | :--- |
| G4-1 | `verify_doc_sync.py` | **通過** |
| G4-2 | 舊名稱與舊引用殘留 | **通過**（見 TC-03；svg 列後續事項） |
| G4-3 | 新名稱撞名 | **通過**：本案未新增檔名或術語；「G1 提案格式」「QA 驗收案例矩陣」全倉無同名衝突 |
| G4-4 | AGENTS.md 大小 | **通過**：158 → 158 行（+0）、10,279 → 10,312 字元（+33） |
| G4-5 | 全倉斷鏈測試 | **通過**（建立本報告後） |
| G4-6 | 程式部分單元測試與 Gate 2 | **通過**：`quality_scope()` 新增 3 項單元測試，先紅後綠（TC-04）；Gate 2 見 9.3 |

### 9.2 G5 審查（規則矛盾與重複）

| ID | 等級 | 發現 | 處置 |
| :--- | :---: | :--- | :--- |
| G5-01 | P2 | ADR 範本第 5 節仍列出 8 個維度名稱（作為填寫表格的欄位），與 arch_review_checklist 名稱重複 | 保留：只列名稱、不列內容，並明載以 arch_review_checklist 為唯一正本；名稱已逐字比對一致 |
| G5-02 | P2 | 負面測試最低數量改為 2 組後，review_checklist 該項同時涵蓋「修復的缺陷」，Bug 軌修正也須 2 組負面測試，較先前（1 組）嚴格 | 依決議第 3 項執行；Bug 軌的紅燈回歸測試可計入其中一組 |
| G5-03 | — | 檢查 code-review SKILL 階段 B 改為引用後，清單九類是否涵蓋原 12 項 | 已逐項比對：原 12 項皆對應到 review_checklist 第 1–9 類，無遺漏 |
| G5-04 | — | 檢查 governance.md 角色欄與 CLAUDE.md 分級表、architect／gatekeeper 角色檔是否一致 | 一致：G1/G3 architect、G5 gatekeeper、G4 不指定角色 |

### 9.3 Gate 2（程式部分：`quality_scope()`）

| 輪次 | 日期 | 審查範圍 | `audit_guardrails.py` | P0 | P1 | P2 | 判定 |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| 1 | 2026-11-19 | `1d138c2..`（`verify_doc_sync.py` `quality_scope()`） | Exit 0 | 0 | 0 | 0 | **PASS** |

**需求—斷言追溯抽查**：

| AC | 對應測試與斷言 | 預期值來源 | 判定 |
| :--- | :--- | :--- | :---: |
| AC-5（M7） | `test_quoted_declaration_before_acceptance_section_is_ignored`：正文引用「是」、驗收段宣告「否」時，斷言 `quality_scope()` 為 `False` 且檢查通過 | Spec-0027 M7：先在驗收段落搜尋 | **OK** |
| AC-5（M7） | `test_declaration_outside_acceptance_section_still_found_as_fallback`：無驗收標題時仍取得宣告 | M7：找不到才退回全文 | **OK** |

**審查結論**：架構靜態掃描通過；向下相容（既有 15 項同檔測試全數通過，含宣告變體與邊界編號）；測試隔離通過（純記憶體字串）；先紅後綠通過；零個資。

---

## 附錄 A：24 項處理結果

| ID | 處理 |
| :--- | :--- |
| U1 | arch_review_checklist Fast Track 改為「功能開發中的小幅變更」，加註缺陷一律走 `bug.md` |
| U2 | feature-design 改為只適用新功能，缺陷修復指向 bug-triage |
| U3 | `.agents/README.md` 改寫為 20 行導覽（見 D4） |
| U4 | 8 大維度以 arch_review_checklist 為唯一正本；feature-design、ADR 範本、doc-sync SKILL 與檢核清單改為引用 |
| U5 | doc-sync 階段 4 改列腳本實際檢查項；註明不檢查 CLI 參數，改由人工清單確認 |
| U6 | auto-fix「四大修復底線」改為「修復底線」 |
| U7 | review_checklist 負面測試改為至少 2 組，以 unit-testing 為正本 |
| U8 | Tech Spec 範本新增第 7 節「QA 驗收案例矩陣」；feature-design 階段 4 同步 |
| U9 | 三個角色檔系統提示詞改為「你是本專案的…」 |
| U10 | qa-testing 註明 QA 缺陷等級沿用 review_checklist；刪除 `tests/integration/`（含 REQUIREMENTS.md 一處） |
| D1 | code-review 階段 B 改為引用 review_checklist，只列九類名稱 |
| D2 | 併入 U4 |
| D3 | 輸入上限數值只在 review_checklist 保留並標為預設值；arch_review_checklist 改為引用；code-review SKILL 隨 D1 移除 |
| D4 | `.agents/README.md` 刪除時序圖與交接表，交接以角色檔為正本 |
| D5 | `feature.md` 與 fix_anti_patterns 的三振規則改為引用 auto-fix 與 AGENTS.md |
| D6 | developer 角色檔 Step 3 改為依 unit-testing 技能執行，只保留離線 Mock 紅線 |
| D7 | test_case_template 改定位為選用的複雜案例補充格式 |
| M1 | `governance.md` 新增角色欄；CLAUDE.md 分級表新增 4 列；architect、gatekeeper 角色檔新增 G1/G3、G5 |
| M2 | `feature.md` Step 1、4 與 architect、gatekeeper 角色檔綁定 quality-evaluation；feature-design、qa-testing 引用之 |
| M3 | doc-sync 新增階段 3.5（索引與鏡像）與「依軌別的同步範圍」表；doc_sync_checklist 新增第四類 |
| M4 | AGENTS.md 第 3 節第 9 條加入流程檔 |
| M5 | `governance.md` 新增「G1 提案格式」五項 |
| M6 | hotfix.md 與 doc_sync_checklist 要求缺陷索引狀態標註補件期限 |
| M7 | `quality_scope()` 先搜尋驗收段落，再退回全文；新增 3 項單元測試 |
