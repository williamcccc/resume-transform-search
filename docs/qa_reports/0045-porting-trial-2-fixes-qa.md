# QA 實測驗收報告：第二次移植實測卡點修正（Spec-0045）

> **規格**：[Spec-0045](../specs/0045-porting-trial-2-fixes-spec.md)｜**所走流程**：[governance.md](../../.agents/workflows/governance.md)（大改：修改驗證腳本與核心自我測試）｜**分支**：`docs/spec-0045-porting-trial-2-fixes`（G1 提案 commit `d4cb02d`）

## 1. 測試環境與前置條件
* **測試日期**：2026-11-21
* **作業系統與 Python 版本**：Windows 11 / Python 3.13
* **外部相依服務**：Semgrep、pip-audit（沿用本機 `.venv-tools`）
* **測試資料集**：暫存目錄之兩個示範專案——第二次實測專案（對外 API、`master`、`service/` 非預設層名、根目錄 `settings.py`、`.env.sample`、守護與隱私清單幾乎全空、業務技能 1 個、安全範圍規格 1 份）與第一次實測專案（回歸用）；不讀取本機敏感目錄

---

## 2. 測試計畫摘要
* **測試範圍**：卡點 A–E 之修正、PORTING 補述、以乾淨 clone 重做第二次實測、第一次實測專案回歸、全套回歸。
* **不測範圍**：重新安裝掃描工具（沿用本機 `.venv-tools`，已知偏差）。
* **進入條件**：G2 使用者核准（2026-11-21，2 項待決事項全數採建議）。
* **退出條件**：見第 8 節。

---

## 3. 需求驗收追溯矩陣 (RTM)

| AC | 條款說明 | 測試案例 | 測試類型 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **AC-1** | 非預設層名與範本檔名下 `test_guardrail_gaps` 全數通過；回歸測試先紅後綠 | TC-01、TC-06 | 單元 + 實測 | **PASS** |
| **AC-2** | 守護清單皆空時 `test_review_checklist_portable` 通過；組樣式函式空清單永不命中 | TC-02、TC-06 | 單元 + 實測 | **PASS** |
| **AC-3** | 尚無文件之目錄不存在時 WARN、結束碼 0；存在而未登錄仍 FAIL | TC-03、TC-06 | 單元 + 實測 | **PASS** |
| **AC-4** | 訊息顯示設定之範本檔名；分層停用時結語含停用附註 | TC-04 | 整合（CLI，先紅後綠） | **PASS** |
| **AC-5** | 同參數、乾淨 clone 重做第二次實測全數通過 | TC-06 | 實測 | **PASS** |
| **AC-6** | 本專案閘門腳本、全套測試、移植演練通過；第一次實測專案無回歸 | TC-05、TC-07 | 回歸 | **PASS** |

> **RTM 統計**：PASS 6 / FAIL 0 / DEFERRED 0 / NOT COVERED 0（共 6 條 AC）

---

## 4. 測試案例執行矩陣

| TC | 內容 | 預期 | 實際 | 狀態 |
| :---: | :--- | :--- | :--- | :---: |
| TC-01 | `TestNonDefaultInstanceLayout`：實例設定改為 `service/usecases`、`settings.py`、`.env.sample` 後建立假專案 | 修正前 FAIL（4 項 P0：路徑不存在）、修正後零 P0 | 符合 | PASS |
| TC-02 | `test_terms_pattern_never_matches_when_lists_empty` | 修正前 ERROR（函式不存在）；修正後空清單零命中、`DemoDB`、`\bv9\b` 正確命中 | 符合 | PASS |
| TC-03 | `TestMissingEmptyDocsDirectory`：不存在之目錄 | 修正前 FAIL；修正後回傳通過、印 WARN、無 FAIL | 符合 | PASS |
| TC-04 | `TestMessagesFollowConfig`：範本改為 `.env.sample` 並讀取未列變數；`enabled = false` | 訊息含「未列於 .env.sample」；結語含「DDD 分層檢查已停用」且不含「架構分層、邊界防護」；以舊版腳本重跑 2 項皆失敗 | 符合 | PASS |
| TC-05 | `docs/` 目錄存在時之既有檢查（本專案全倉） | 未登錄索引之規格仍 FAIL | 本規格登錄前 `verify_doc_sync.py` 確實 FAIL「未登載於索引表」 | PASS |
| TC-06 | 第二次實測專案套用新核心、commit、乾淨 clone 後執行驗證 | 三支腳本通過；自我測試全數通過 | `verify_doc_sync` SUCCESS（2 則「尚無…」WARN）、`audit` 100% PASSED、`scan --full` SUCCESS；自我測試 182 項 OK（skipped=1：`url_schemes` 為空，依 Spec-0044 設計） | PASS |
| TC-07 | 第一次實測專案套用新核心後執行自我測試 | 全數通過 | OK | PASS |

---

## 5. 實測執行日誌摘要

```text
[第二次實測，修正前]  自我測試 177 項 FAILED (failures=18, skipped=1)；乾淨 clone 之 verify_doc_sync FAIL
[第二次實測，修正後]  乾淨 clone：verify_doc_sync SUCCESS / audit 100% PASSED / scan SUCCESS / 自我測試 182 項 OK
[第一次實測專案回歸]  自我測試 OK
audit_guardrails.py         → 100% PASSED（exit 0）
verify_doc_sync.py          → [SUCCESS]（exit 0）
security_scan.py            → P0=0 P1=0（exit 0）
unittest tests/unit         → Ran 573 tests ... OK（含斷鏈）
unittest .agents/tests      → Ran 182 tests ... OK（新增 5 項）
unittest .agents/tests/e2e  → OK
unittest e2e porting        → OK
```

---

## 6. 品質評測結果

不適用（品質評測範圍：否）。

---

## 7. 失敗分析與後續事項

* **逃逸分析**：卡點 A、B 屬測試缺口——移植演練固定使用原專案之層名、範本檔名與非空守護清單，無法揭露自我測試對實例設定字面值與空清單之假設；本案以合成設定之回歸測試補上，教訓歸屬通用，已回寫核心。卡點 D 屬規格缺口——未考慮 git 不追蹤空目錄。
* **測試結構調整**：新測試類別原繼承 `TestBug0033MissingConfiguredPaths` 以取用輔助方法，致該類 5 項測試重複執行；已將 `remove`、`set_config` 移至共同基底類別。
* **索引未登錄致 `verify_doc_sync.py` 失敗（已修正）**：登錄後通過，屬執行順序。

---

## 8. QA 驗收結論

**通過**。6 條 AC 全數 PASS。

---

## 9. 規範變更檢查紀錄（G4、G5）與 Gate 2

**G4 一致性檢查**

| # | 項目 | 結果 |
| :---: | :--- | :--- |
| 1 | `verify_doc_sync.py` | 通過 |
| 2 | 改名殘留 | 無改名；`_rewrite_config` 不再含 `"src/"` 字面替換 |
| 3 | 新名稱撞名 | `MINI_LAYOUT`、`terms_pattern`、`TestNonDefaultInstanceLayout`、`TestMissingEmptyDocsDirectory`、`TestMessagesFollowConfig` 無撞名 |
| 4 | AGENTS.md 行數 | 未修改，175 行 |
| 5 | Markdown 斷鏈測試 | 通過 |
| 6 | 程式變更 | `verify_doc_sync.py`（目錄不存在改 WARN）、`audit_guardrails.py`（訊息）；走 Gate 2（下表） |

**Gate 2 程式檢查**

| 輪次 | 日期 | 範圍 | `audit_guardrails.py` | `security_scan.py` | P0 | P1 | P2 | 判定 |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 2026-11-21 | `d4cb02d..HEAD` | Exit 0 | Exit 0 | 0 | 0 | 0 | **PASS** |

* 程式覆核：目錄不存在改 WARN 只影響 `check_directory_docs` 開頭分支，目錄存在時之格式與索引檢查不變；`docs/adr/` 與核心文件存在性檢查不受影響。訊息改用 `ENV_EXAMPLE_PATH.name`，不輸出完整路徑。

**G5 審查**（gatekeeper 視角）：零矛盾、零重複。PORTING 第 7 步對空目錄之說明與腳本 WARN 行為一致；第 3 步對 `url_schemes` 為空之說明與自我測試之 skip 理由一致；兩支守護測試之空清單處理一致。
