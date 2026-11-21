# QA 實測驗收報告：核心文件去除本專案歷史連結、範本與核心 Python 殘留清理（Spec-0042）

> **規格**：[Spec-0042](../specs/0042-core-history-links-and-py-residue-spec.md)｜**所走流程**：[governance.md](../../.agents/workflows/governance.md)（大改：修改驗證腳本說明文字）｜**分支**：`docs/spec-0042-core-history-links`（G1 提案 commit `90d18e8`）

## 1. 測試環境與前置條件
* **測試日期**：2026-11-21
* **作業系統與 Python 版本**：Windows 11 / Python 3.13
* **外部相依服務**：不需要（安全掃描為差異模式）
* **測試資料集**：守護測試讀取版控中之核心文件與程式；移植演練於暫存目錄建立假專案，不讀取本機敏感目錄

---

## 2. 測試計畫摘要
* **測試範圍**：歷史連結與編號守護、範本殘留、核心 Python 守護範圍擴大、`identifiers` 新增 `data/`、全套回歸與移植演練。
* **不測範圍**：Spec-0042 第 2.4 節（`.py` 註解之來源註記、對外介面預設 CLI 之寫法）；第三節「另發現」之 `sensitive_dirs` 未含 `data`（另案評估）。
* **進入條件**：G2 使用者核准（2026-11-21，3 項待決事項全數採建議）。
* **退出條件**：見第 8 節。

---

## 3. 需求驗收追溯矩陣 (RTM)

| AC | 條款說明 | 測試案例 | 測試類型 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **AC-1** | 核心 Markdown 無規格歷史連結與編號；寫回時失敗 | TC-01、TC-02 | 單元（先紅後綠） | **PASS** |
| **AC-2** | 技術規格範本（正本與鏡像）不含「Markdown」「品管」 | TC-03 | 搜尋 + 鏡像同步檢查 | **PASS** |
| **AC-3** | 核心腳本、程式庫與測試 docstring 無 `identifiers` 字詞；寫回時失敗；移植演練通過 | TC-04、TC-05 | 單元（先紅後綠）+ E2E | **PASS** |
| **AC-4** | 閘門腳本、全套測試、斷鏈測試、移植演練通過 | TC-06 | 回歸 | **PASS** |

> **RTM 統計**：PASS 4 / FAIL 0 / DEFERRED 0 / NOT COVERED 0（共 4 條 AC）

---

## 4. 測試案例執行矩陣

| TC | 內容 | 預期 | 實際 | 狀態 |
| :---: | :--- | :--- | :--- | :---: |
| TC-01 | 修文字前執行 `test_core_markdown_has_no_history_references` | 抓到全部歷史引用 | 6 處：PORTING 第 3、7、20、51 行，安全框架第 5、125 行（第 20 行為 Spec-0041 新增，一併清除） | PASS（紅燈） |
| TC-02 | `test_history_reference_pattern`；修文字後重跑 TC-01 | 命中規格／QA 連結與 `ADR-0037`；`docs/specs/XXXX-*.md` 佔位與 `docs/README.md` 不誤判；TC-01 通過 | 符合 | PASS |
| TC-03 | 搜尋「Markdown，品管」；`verify_doc_sync.py` 鏡像比對 | 零命中；鏡像一致 | 符合 | PASS |
| TC-04 | 修文字前執行 `test_core_python_has_no_project_identifiers` | 抓到 docstring 與腳本殘留 | 8 處：`audit_guardrails.py:61` 之 `src/`、7 支測試 docstring 之 `data/` | PASS（紅燈） |
| TC-05 | 修文字後重跑 TC-04；範圍斷言 | 通過；含 `audit_guardrails.py`、`project_config.py`，不含業務技能腳本 | 符合 | PASS |
| TC-06 | 閘門腳本、`tests/unit`、`.agents/tests`、`.agents/tests/e2e`、移植演練 | 全數通過 | 見第 5 節 | PASS |

---

## 5. 實測執行日誌摘要

```text
audit_guardrails.py         → 100% PASSED（exit 0）
verify_doc_sync.py          → [SUCCESS]（exit 0）
security_scan.py            → P0=0 P1=0（exit 0）
unittest tests/unit         → Ran 573 tests ... OK（含斷鏈）
unittest .agents/tests      → Ran 173 tests ... OK（新增 3 項）
unittest .agents/tests/e2e  → OK
unittest e2e porting        → Ran 19 tests ... OK
```

---

## 6. 品質評測結果

不適用（品質評測範圍：否）。

---

## 7. 失敗分析與後續事項

* **移植演練首次全數 ERROR（已修正）**：`identifiers` 新增之 `(?<![\w/.])data/` 含 `]`，演練以 `[^\]]*` 比對陣列而提前截斷，產生不合法 TOML。改為比對至行首之 `]`。
* **斷鏈測試首次失敗（已修正）**：本規格以 Markdown 連結語法、目標為省略號描述待刪連結，省略號被視為連結目標。改為純文字。
* **索引未登錄致 `verify_doc_sync.py` 失敗（已修正）**：登錄後通過，屬執行順序。
* **後續**：`privacy.sensitive_dirs` 未含 `data`，與紅線 7 本專案補充不一致，建議另案評估（影響隱私掃描結果）。

---

## 8. QA 驗收結論

**通過**。4 條 AC 全數 PASS。

---

## 9. 規範變更檢查紀錄（G4、G5）與 Gate 2

**G4 一致性檢查**

| # | 項目 | 結果 |
| :---: | :--- | :--- |
| 1 | `verify_doc_sync.py` | 通過；技術規格範本鏡像一致 |
| 2 | 刪除之引用殘留 | 核心 Markdown 無規格歷史連結與編號（由守護測試確認） |
| 3 | 新名稱撞名 | `HISTORY_REFERENCE`、`IDENTIFIERS_ONLY`、`core_python_texts` 無撞名 |
| 4 | AGENTS.md 行數 | 未修改，175 行 |
| 5 | Markdown 斷鏈測試 | 通過 |
| 6 | 程式變更 | `audit_guardrails.py` 一處 docstring；守護測試擴充；走 Gate 2（下表） |

**Gate 2 程式檢查**

| 輪次 | 日期 | 範圍 | `audit_guardrails.py` | `security_scan.py` | P0 | P1 | P2 | 判定 |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 2026-11-21 | `90d18e8..HEAD` | Exit 0 | Exit 0 | 0 | 0 | 0 | **PASS** |

* 程式覆核：`audit_guardrails.py` 只改 docstring，行為不變；守護測試以 `ast.get_docstring` 取測試模組說明，不執行受測程式；`identifiers` 為空時以 `(?!)` 永不命中，避免空樣式誤判全部行。

**G5 審查**（gatekeeper 視角）：零矛盾、零重複。PORTING 與安全框架刪除來源連結後規則內容不變；歷史來源仍保存在各規格與 `docs/README.md` 索引（專案側），核心不再重複引用。
