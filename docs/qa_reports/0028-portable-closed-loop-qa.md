# QA 實測驗收報告：閉環可移植化（Spec-0028）

> **規格**：[Spec-0028](../specs/0028-portable-closed-loop-spec.md)｜**決策**：[ADR-0028](../adr/0028-portable-closed-loop-project-config.md)｜**所走流程**：[governance.md](../../.agents/workflows/governance.md)（大改）｜**分支**：`docs/spec-0028-portable-closed-loop`（基準 `65afce8`）

## 1. 測試環境與前置條件
* **測試日期**：2026-11-20
* **作業系統與 Python 版本**：Windows 11 / Python 3.13 on PowerShell
* **外部相依服務**：不需要
* **測試資料集**：設定檔於暫存目錄動態建構；移植演練於暫存目錄建立合成假專案（`demo_proj`），不讀取 `data/`、`resume/`

---

## 2. 測試計畫摘要
* **測試範圍**：`project.toml` 與讀取模組；兩支閘門腳本設定化後的行為一致性；設定缺漏與開關；移植演練；規範文字改寫與標記覆蓋。
* **不測範圍**：

  | 不測項目 | 理由 | 風險與替代保障 |
  | :--- | :--- | :--- |
  | 在真實的另一個專案實際移植 | 本案範圍為就地重構與移植指南 | AC-6 以暫存目錄假專案依 PORTING.md 完整演練 |
  | 類別 2b 舉例中性化 | 決議第 3 項：本案不處理 | PORTING.md 第 5 步列為選擇性項目並附檔案清單 |

* **進入條件**：G2 使用者核准（2026-11-20，待決事項全數採建議）。
* **退出條件**：見第 8 節。

---

## 3. 需求驗收追溯矩陣 (RTM)

| AC | 條款說明 | 測試案例 | 測試類型 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **AC-1** | 腳本專屬值改由設定讀取 | TC-01、TC-02 | 搜尋 + 單元 | **PASS** |
| **AC-2** | 本專案執行結果與修改前一致 | TC-03 | 回歸比對 | **PASS** |
| **AC-3** | 缺檔／缺鍵／缺 reason 結束碼 2；`layers.enabled` 開關 | TC-04、TC-05 | 單元 + E2E | **PASS** |
| **AC-4** | `.gitignore` 必備清單全倉只在 `project.toml` 定義 | TC-06 | 搜尋 | **PASS** |
| **AC-5** | 2a 位置皆有標記；路徑引用註明設定鍵名 | TC-07 | 搜尋 + 人工覆核 | **PASS** |
| **AC-6** | 移植演練：兩支腳本通過，舊指紋零殘留 | TC-08 | E2E | **PASS** |
| **AC-7** | G4 六項與全套單元測試通過 | TC-09 | 回歸 | **PASS** |

> **RTM 統計**：PASS 7 / FAIL 0 / DEFERRED 0 / NOT COVERED 0（共 7 條 AC）

---

## 4. 測試案例執行矩陣

| 案例 | 名稱 | 分類 | 輸入 / 操作 | 預期 | 實際 | 判定 |
| :---: | :--- | :---: | :--- | :--- | :--- | :---: |
| **TC-01** | 腳本殘留專屬值 | Search | 搜尋兩支腳本中的 `src/`、`resume`、`ragas`、`redis`、工作區名稱、`= 23` | 只剩通用說明或測試所依賴的識別名稱 | 僅剩 `_module_name` 說明範例、變數名 `PERSONAL_RESUME_FILENAME_PATTERN` 與線索類別 `personal_resume_filename`（既有測試斷言依賴，見 G5-03）、內建地區樣式 `tw_*` | **PASS** |
| **TC-02** | 設定讀取單元測試 | Unit | `test_project_config.py` 18 項：合法設定、缺檔、語法錯誤（含例外鏈）、缺區段、缺鍵、5 種型別錯誤、缺／空白 reason、空豁免、部分區段驗證、工作區樣式（Windows／POSIX／磁碟根目錄）、空清單不命中、外層判定、豁免來源 | 全數通過 | `Ran 18 tests ... OK` | **PASS** |
| **TC-03** | 行為一致性 | Regression | 修改前後各執行兩支腳本，逐行比對輸出 | 檢查項與結束碼相同 | `verify_doc_sync.py` 輸出完全相同；`audit_guardrails.py` 僅評測依賴一行措辭不同（「src/」→「原始碼」），兩者結束碼皆 0 | **PASS** |
| **TC-04** | 設定缺漏 | E2E | 假專案中刪除 `project.toml`／刪除 `agents_max_lines`／豁免缺 reason／未知地區樣式 | 結束碼 2 並指出缺漏 | P3～P5、P7 皆符合 | **PASS** |
| **TC-05** | DDD 開關 | E2E | Domain 層加入 `import requests`，`enabled` 分別為 true／false | true：結束碼 1 並報 Domain 違規；false：結束碼 0 並印 Skip | P6 符合 | **PASS** |
| **TC-06** | 必備清單單一正本 | Search | 全倉搜尋 `appendonlydir` | 只出現在 `project.toml`、`.gitignore` 與歷史規格 | 另發現 `test_github_pre_publish_hygiene.py` 自帶一份（G5-01），修正後符合 | **PASS** |
| **TC-07** | 標記覆蓋 | Search | 搜尋 `<!-- 專案專屬`；對照 Spec 第四節清單 | 清單位置皆有標記 | 17 檔共 44 處標記；`tech_spec_template.md` 路徑表以表前一行標記涵蓋 | **PASS** |
| **TC-08** | 移植演練 | E2E | 依 PORTING.md：複製、刪業務技能、改寫設定（換分層、清指紋與豁免、門檻改 1）、建文件骨架、執行兩支腳本 | 兩支腳本結束碼 0；原指紋零殘留；門檻 1 時未宣告品質範圍的 0001 規格被判 FAIL | P1、P2、P8 符合 | **PASS** |
| **TC-09** | 全套回歸 | Regression | 全套單元測試、相關 E2E、兩支腳本、斷鏈測試 | 全數通過 | 見第 5 節 | **PASS** |

---

## 5. 實測執行日誌摘要
```text
[Unit] python -m unittest tests.unit.test_project_config              → Ran 18 tests ... OK
[Unit] python -m unittest discover -s tests/unit -t .                 → Ran 633 tests ... OK
[E2E]  python -m unittest tests.e2e.test_portable_closed_loop_e2e     → Ran 8 tests ... OK
[E2E]  python -m unittest tests.e2e.test_workflow_tracks_doc_sync_e2e → Ran 8 tests ... OK
[Doc]  verify_doc_sync.py → SUCCESS；WARN 2（ADR 編號跳號 0022→0028、docs/bugs 為空）
[AST]  audit_guardrails.py → 100% PASSED（零 P0）
```

---

## 6. 品質評測結果
不適用（規格宣告品質評測範圍：否）。

---

## 7. 失敗分析與後續事項

| # | 現象 | 根因 | 處置 |
| :---: | :--- | :--- | :--- |
| 1 | 以 PowerShell 批次改寫 review_checklist 失敗 | 自訂函式名 `R` 與內建別名 `Invoke-History` 衝突 | 改用 Python 替換腳本（每處須恰好命中一次）；檔案未被改動 |
| 2 | 全倉斷鏈測試失敗：`docs/README.md`、ADR-0028 | 先登錄 QA-0028 連結，報告尚未建立 | 建立本報告後通過 |
| 3 | `verify_doc_sync.py` 新增 WARN「ADR 編號不連續」 | ADR 依規格流水號命名（0023～0027 為規範或評測案，未寫 ADR） | 保留：與 `docs/README.md` 以流水號對應 ADR 的慣例一致；WARN 不影響結束碼 |

---

## 8. QA 驗收結論
* **驗收判定**：**【通過 (PASSED)】**
* **放行標準**：RTM 零 `FAIL`、零 `NOT COVERED` ✅；品質評測不適用
* **放行說明**：准予進入 G5 審查與程式部分的 Gate 2。

---

## 9. 規範變更檢查紀錄（G4、G5）與 Gate 2

### 9.1 G4 一致性檢查

| # | 檢查項 | 結果 |
| :---: | :--- | :--- |
| G4-1 | `verify_doc_sync.py` | **通過** |
| G4-2 | 舊名稱與舊引用殘留 | **通過**：「自規格 0023 起」零殘留；未加設定鍵名的 `src/domain/` 等路徑只剩 `tech_spec_template.md` 範例表（以表前標記涵蓋） |
| G4-3 | 新名稱撞名 | **通過**：`project.toml`、`project_config.py`、`PORTING.md` 全倉無同名檔 |
| G4-4 | AGENTS.md 大小 | **通過**：158 → 158 行（+0）、8,510 → 8,931 字元（+421，為設定鍵名與標記） |
| G4-5 | 全倉斷鏈測試 | **通過**（建立本報告後） |
| G4-6 | 程式部分單元測試與 Gate 2 | **通過**：新增 18 項單元測試、8 項 E2E；Gate 2 見 9.3 |

### 9.2 G5 審查（規則矛盾與重複）

| ID | 等級 | 發現 | 處置 |
| :--- | :---: | :--- | :--- |
| G5-01 | P1 | `test_github_pre_publish_hygiene.py` 自帶 `.gitignore` 必備清單、略過目錄與設定模組路徑，與 AC-4「單一正本」矛盾 | 已修正：改讀 `project.toml`；保留「`.env` 不得移除」為測試內最低要求 |
| G5-02 | P2 | 規格 3.3 只定義 `<!-- 專案專屬 -->`，實作另用 `<!-- 專案專屬：說明 -->`；AGENTS.md 導言以完整字串指稱 | 已修正：規格 3.3、AGENTS.md 導言與 PORTING.md 統一為「以 `<!-- 專案專屬` 開頭」 |
| G5-03 | P2 | 腳本仍有 `PERSONAL_RESUME_FILENAME_PATTERN` 變數名與 `personal_resume_filename` 線索類別 | 保留：屬識別名稱而非設定值，既有測試斷言依賴線索類別字串；改名不影響移植 |
| G5-04 | P2 | 同檔測試的工作區路徑與金鑰樣式（`test_github_pre_publish_hygiene.py`）仍為本專案寫法 | 保留：專案自身測試，作為與腳本獨立的預期值來源（Oracle Independence）；`tests/` 不在移植清單 |
| G5-05 | — | 檢查紅線是否被放寬 | 未放寬：紅線 1～7 編號與要求不變，僅值的存放位置改變並加標記 |
| G5-06 | — | 檢查 `_is_outer_layer` 改為精確比對是否改變行為 | 原為子字串比對（`"src.infrastructure" in name`），新版只接受該套件或其子模組；本專案無受影響之模組名稱，TC-03 輸出一致 |

### 9.3 Gate 2（程式部分：兩支腳本、`project_config.py`）

| 輪次 | 日期 | 審查範圍 | `audit_guardrails.py` | P0 | P1 | P2 | 判定 |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| 1 | 2026-11-20 | `65afce8..`（`.agents/lib/project_config.py`、`audit_guardrails.py`、`verify_doc_sync.py`、相關測試） | Exit 0 | 0 | 1（G5-01，已修正） | 3 | **PASS** |

**需求—斷言追溯抽查**：

| AC | 對應測試與斷言 | 預期值來源 | 判定 |
| :--- | :--- | :--- | :---: |
| AC-3 | `test_p3_missing_config_exits_2_for_both_scripts`：斷言兩支腳本結束碼為 2 且訊息含「找不到專案設定檔」 | Spec-0028 §3.1 設計要點 3 | **OK** |
| AC-3 | `test_url_exception_without_reason_raises`：斷言例外訊息含「缺少必填欄位 reason」 | Spec-0028 §3.1 設計要點 2 | **OK** |
| AC-6 | `test_p2_original_fingerprints_absent_after_porting`：斷言假專案全部檔案不含原專案任一指紋 | Spec-0028 AC-6、PORTING.md 第 3 步 | **OK** |

**審查結論**：架構靜態掃描通過；設定讀取以 `with` 管理檔案、語法錯誤保留例外鏈（`from err`）；零寫死路徑（工作區樣式改為動態推得）；測試全數於暫存目錄建構、零外部服務；零個資。
