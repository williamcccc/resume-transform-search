# QA 實測驗收報告：守護字詞移入專案實例、核心規範去除寫死的 src/（Spec-0041）

> **規格**：[Spec-0041](../specs/0041-instance-guard-terms-and-src-neutral-spec.md)｜**所走流程**：[governance.md](../../.agents/workflows/governance.md)（大改：修改驗證用程式庫與設定 schema）｜**分支**：`docs/spec-0041-instance-guard-terms`（G1 提案 commit `041c083`）

## 1. 測試環境與前置條件
* **測試日期**：2026-11-21
* **作業系統與 Python 版本**：Windows 11 / Python 3.13
* **外部相依服務**：不需要（安全掃描為差異模式）
* **測試資料集**：設定測試以合成 TOML；移植演練於暫存目錄建立假專案（守護字詞改為 `demo_widget`、`\bapp/`、`DemoDB`），不讀取本機敏感目錄

---

## 2. 測試計畫摘要
* **測試範圍**：設定 schema 新鍵、兩支守護測試改讀實例、移植後守護新專案字詞、核心文字修正、全套回歸。
* **不測範圍**：Spec-0041 第 2.4 節評估後保留之項目（Windows 說明、通用技術舉例、閉環文件約定、CI 檔）。
* **進入條件**：G2 使用者核准（2026-11-21，4 項待決事項全數採建議）。
* **退出條件**：見第 8 節。

---

## 3. 需求驗收追溯矩陣 (RTM)

| AC | 條款說明 | 測試案例 | 測試類型 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **AC-1** | 守護測試不寫死本專案字詞，改讀 `project.toml`；新字詞寫入核心文件時失敗 | TC-01、TC-02 | 單元 + E2E | **PASS** |
| **AC-2** | `identifiers`、`stack_terms` 缺鍵、型別錯誤或非法正規式時結束碼 2 並指出鍵名 | TC-03 | 單元 | **PASS** |
| **AC-3** | 核心 Markdown 無寫死 `src/`；bug-triage 無 Redis；測試資料無本專案字詞 | TC-04、TC-05 | 守護測試 + 搜尋 | **PASS** |
| **AC-4** | 閘門腳本、全套測試、移植演練通過 | TC-06、TC-07 | 回歸 + E2E | **PASS** |

> **RTM 統計**：PASS 4 / FAIL 0 / DEFERRED 0 / NOT COVERED 0（共 4 條 AC）

---

## 4. 測試案例執行矩陣

| TC | 內容 | 預期 | 實際 | 狀態 |
| :---: | :--- | :--- | :--- | :---: |
| TC-01 | `test_pattern_comes_from_instance_terms`：以 `demo_widget`、`\bv9\b` 組樣式 | 命中新字詞、`v95` 不誤判、「本專案為」恆守護、專屬標記行略過、「如 Redis」放行 | 符合 | PASS |
| TC-02 | 移植演練 `test_a6_guard_terms_follow_new_project_instance`：假專案核心文件寫入 `app/demo_widget.py`、`DemoDB` | 兩支守護測試各自失敗 | 符合；`test_a3` 於新字詞下全數通過 | PASS |
| TC-03 | `test_guard_terms_keys_required_and_must_be_valid_regex` | 缺鍵、字串非清單、`(unclosed` 皆結束碼 2，訊息含鍵名（含索引 `[1]`） | 符合 | PASS |
| TC-04 | 文字修正前執行守護測試 | 抓到 AGENTS.md:61、governance.md:3–4、兩範本共 6 處 `src/` 與 bug-triage 之 Redis | 符合（紅燈）；修正後通過 | PASS |
| TC-05 | 搜尋 `.agents/tests` 測試資料 | 「履歷」已改為中性內容 | 餘 `test_guardrail_gaps` 之 `"src/` → `"app/` 為改寫設定之操作字串，非測試資料 | PASS |
| TC-06 | `audit_guardrails.py`、`verify_doc_sync.py`、`security_scan.py` | 全數結束碼 0 | 100% PASSED；SUCCESS；P0=0 P1=0 | PASS |
| TC-07 | `tests/unit`、`.agents/tests`、`.agents/tests/e2e`、移植演練 | 全數通過 | 見第 5 節 | PASS |

---

## 5. 實測執行日誌摘要

```text
audit_guardrails.py         → 100% PASSED（exit 0）
verify_doc_sync.py          → [SUCCESS]（exit 0）
security_scan.py            → P0=0 P1=0（exit 0）
unittest tests/unit         → Ran 573 tests ... OK
unittest .agents/tests      → Ran 170 tests ... OK（新增 2 項，改寫 3 項）
unittest .agents/tests/e2e  → OK
unittest e2e porting        → Ran 19 tests ... OK（新增 a6）
```

---

## 6. 品質評測結果

不適用（品質評測範圍：否）。

---

## 7. 失敗分析與後續事項

* **移植演練首次全數 ERROR（已修正）**：演練以 `re.sub` 改寫 `identifiers`，替換字串中的 `\b` 被解讀為跳脫字元，產生不合法 TOML。改用函式回傳替換字串。
* **`.agents/tests/e2e` 首次 3 項失敗（已修正）**：Spec-0041 尚未登錄於 `docs/README.md` 索引，複製倉庫之 E2E 情境中 `verify_doc_sync.py` 因而失敗；登錄後通過。屬執行順序，非缺陷。
* **逃逸分析回顧**：自我測試寫死本專案字詞，源於「守護」與「守護什麼」未分層；教訓歸屬通用，已回寫核心（守護規則留核心、字詞歸實例）。

---

## 8. QA 驗收結論

**通過**。4 條 AC 全數 PASS。

---

## 9. 規範變更檢查紀錄（G4、G5）與 Gate 2

**G4 一致性檢查**

| # | 項目 | 結果 |
| :---: | :--- | :--- |
| 1 | `verify_doc_sync.py` | 通過；範本鏡像一致 |
| 2 | 改名與搬移之引用殘留 | 兩支測試寫死之字詞清單已移除；核心 Markdown 無 `src/` |
| 3 | 新名稱撞名 | `identifiers`、`stack_terms`、`regex_list`、`build_pattern` 無撞名 |
| 4 | AGENTS.md 行數 | 175 行不變（分流表一格改字） |
| 5 | Markdown 斷鏈測試 | 通過 |
| 6 | 程式變更 | `project_config.py` 新增 `regex_list` 型別與兩鍵；新增與改寫測試；走 Gate 2（下表） |

**Gate 2 程式檢查**

| 輪次 | 日期 | 範圍 | `audit_guardrails.py` | `security_scan.py` | P0 | P1 | P2 | 判定 |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 2026-11-21 | `041c083..HEAD` | Exit 0 | Exit 0 | 0 | 0 | 0 | **PASS** |

* 程式覆核：`regex_list` 驗證於載入時編譯每項，錯誤以 `from err` 保留例外鏈；訊息只含鍵名、索引與該項字串；守護樣式以 `(?:…)` 包覆各項，避免交替運算子跨項誤併。

**G5 審查**（gatekeeper 視角）：零矛盾、零重複。兩支測試原各自寫死之字詞合併為 `project.toml` 一處；PORTING 第 3 步補述 `[project]` 兩鍵，與第 2 步 `business_skills` 同區段說明一致；`stack_terms` 僅約束技術中立檢核清單，與守護測試「通用技術名稱可作舉例」之說明一致。
