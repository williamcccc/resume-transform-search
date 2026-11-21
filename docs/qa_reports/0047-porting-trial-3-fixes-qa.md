# QA 實測驗收報告：第三輪移植實測卡點修正（Spec-0047）

> **規格**：[Spec-0047](../specs/0047-porting-trial-3-fixes-spec.md)｜**所走流程**：[governance.md](../../.agents/workflows/governance.md)（大改：修改驗證腳本與設定載入器）｜**分支**：`docs/spec-0047-porting-trial-3-fixes`（G1 提案 commit `a552688`）

## 1. 測試環境與前置條件
* **測試日期**：2026-11-21
* **作業系統與 Python 版本**：Windows 11 / Python 3.13
* **外部相依服務**：Semgrep、pip-audit 2.10.1（沿用本機 `.venv-tools`，實測專案以 junction 連結）
* **測試資料集**：暫存目錄之六個實測專案（V1 扁平根目錄、V2 BOM+CRLF、V2b 僅 CRLF、V3 src-layout+pyproject、V4 內網多使用者 Web 含文件流、V5 業務技能與自訂守護），各為真實 `git init`、commit 後乾淨 clone；內容全為合成資料，不讀取本機敏感目錄

---

## 2. 測試計畫摘要
* **測試範圍**：卡點 A–F 之修正、PORTING 補述、參數化演練新增 3 個變體、以修正後核心重跑六個實測專案、全套回歸。
* **不測範圍**：重新安裝掃描工具（沿用本機 `.venv-tools`，已知偏差）。
* **進入條件**：G2 使用者核准（2026-11-21，4 項待決事項全數採建議）。
* **退出條件**：見第 8 節。

---

## 3. 需求驗收追溯矩陣 (RTM)

| AC | 條款說明 | 測試案例 | 測試類型 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **AC-1** | src-layout 與扁平根目錄宣告 `package` 後合法 import 零 P0，違規以原類別檢出；先紅後綠 | TC-01、TC-02、TC-09 | 單元 + 整合 + 實測 | **PASS** |
| **AC-2** | 未設定 `package` 時結果與修正前相同 | TC-03 | 回歸 | **PASS** |
| **AC-3** | `ignore_scan_dirs` 與 `.agents/` 不進入原始碼檢查；全倉隱私掃描不變 | TC-04 | 單元 + 整合 | **PASS** |
| **AC-4** | 帶 BOM 之 `project.toml` 正常載入 | TC-05、TC-08 | 單元 + 演練 | **PASS** |
| **AC-5** | `pyproject.toml` 以 pip-audit 專案路徑模式掃描；requirements 仍用 `-r` | TC-06、TC-09 | 單元 + 實測 | **PASS** |
| **AC-6** | STRIDE 字母於第一欄被認得；無 STRIDE 列仍 FAIL | TC-07 | 單元 | **PASS** |
| **AC-7** | 修正後重跑第三輪實測：三支腳本與核心自我測試全數通過，違規以正確類別檢出 | TC-09 | 實測 | **PASS** |
| **AC-8** | 本專案閘門腳本與全套測試、移植演練通過 | TC-10 | 回歸 | **PASS** |

> **RTM 統計**：PASS 8 / FAIL 0 / DEFERRED 0 / NOT COVERED 0（共 8 條 AC）

---

## 4. 測試案例執行矩陣

| TC | 內容 | 預期 | 實際 | 狀態 |
| :---: | :--- | :--- | :--- | :---: |
| TC-01 | `TestSrcLayoutPackage`、`TestFlatRootPackage`（各 4 項）：合法 import、Domain 引第三方、Domain 引外層、Application 引外層 | 修正前合法 import 即 P0、類別錯置；修正後零 P0 且分別為「第三方套件」「逆向依賴」「違反依賴反轉」 | 修正前 7 項失敗；修正後全過 | PASS |
| TC-02 | `layer_module`、`internal_roots`、`_in_package`、`package` 選填與非法值（`bad-name`、`pkg.`、`1pkg`、`true`） | 推導正確；非法值報 `[layers].package` | 修正前 ERROR／FAIL；修正後全過 | PASS |
| TC-03 | 本專案 `audit_guardrails.py`；既有參數化變體與閉環演練；`TestInstancePackageIgnored` | 結果不變；實例設 `package` 時假專案仍零 P0 | 100% PASSED；演練全過 | PASS |
| TC-04 | `src_python_files` 單元測試；扁平根目錄之 `vendor_env/`、`.agents/tests/` 含違規碼；根目錄 `tools/job.py` | 前兩者不報、後者報 P0 | 符合；V1 實測由 833 項 P0 降為 0 | PASS |
| TC-05 | BOM+CRLF 設定載入；UTF-16 設定 | 前者載入成功；後者「不是 UTF-8 編碼」 | 符合 | PASS |
| TC-06 | `pip_audit_target`；`dependency_files` 含 `pyproject.toml` 之掃描呼叫 | `["."]`、`["pkg"]`、`["-r", …]` | 符合 | PASS |
| TC-07 | STRIDE 第一欄（加粗）之威脅表；既有「散文中之字母不算」案例 | 前者通過；後者仍 FAIL | 符合 | PASS |
| TC-08 | 參數化演練新增「src-layout」「扁平根目錄」「設定檔BOM」變體 | 修正後全過；以舊版核心執行失敗 | 符合（BOM 變體以舊版自我測試執行失敗：3 支核心測試直接以 `tomllib.load` 讀設定） | PASS |
| TC-09 | 六個實測專案以修正後核心重跑（V1 設 `package = ""`、V3 設 `package = "widgetkit"`） | 三支腳本與核心自我測試全數通過；違規以正確類別檢出 | 六組全數 exit 0；探測 33/33 應抓皆抓（V5 未啟用 `tw_mobile`，手機號碼正確不抓） | PASS |
| TC-10 | 本專案全套回歸 | 全數通過 | 見第 5 節 | PASS |

---

## 5. 實測執行日誌摘要

```text
[修正前]  V1 audit 833 P0 / V2 全腳本 exit 2 / V3 audit 2 P0、scan pip-audit 錯誤 / V4 規格 STRIDE 第一欄 FAIL
[修正後首輪]  V2 核心自我測試 32 ERROR（3 支核心測試繞過載入器直接讀設定；已修正並以 BOM 變體防再犯）
[修正後]  V1、V2、V2b、V3、V4、V5：verify / audit / scan --full / 核心自我測試 全數 exit 0
audit_guardrails.py         → 100% PASSED（exit 0）
verify_doc_sync.py          → [SUCCESS]（exit 0）
security_scan.py --full     → P0=0 P1=0（exit 0）
unittest tests/unit         → Ran 575 tests ... OK（含斷鏈）
unittest .agents/tests      → Ran 204 tests ... OK（新增 21 項）
unittest .agents/tests/e2e  → OK
unittest e2e porting + variants → OK（變體新增 3 個）
```

---

## 6. 品質評測結果

不適用（品質評測範圍：否）。

---

## 7. 失敗分析與後續事項

* **逃逸分析**：既有演練與參數化變體皆以「原始碼根目錄第一段即 import 根名」之佈局建立，且設定檔一律以無 BOM 之 UTF-8 寫入，故 A、B、C 未被測出；教訓屬通用，已以 3 個新變體回寫核心演練。
* **修正後首輪 V2 自我測試失敗（已修正）**：載入器已接受 BOM，但 `test_neutral_examples`、`test_review_checklist_portable`、`test_guardrail_gaps` 直接讀設定檔，改為 `utf-8-sig`。
* **殘餘風險（低）**：
  * STRIDE 樣式放寬後，安全範圍規格中若有其他首欄為單一 S/T/R/I/D/E 字母之表格，可能被誤認為威脅表；仍須有 `NFR-*`，且 Gate 1 人工審查威脅表內容。
  * 扁平根目錄（`package = ""`）下，Domain 引用倉庫根之非分層套件會被判為第三方套件（與一般佈局「src 外之模組視為外部」一致）。
  * pip-audit 專案路徑模式可能需建置專案中繼資料，耗時較 `-r` 長。

---

## 8. QA 驗收結論

**通過**。8 條 AC 全數 PASS。

---

## 9. 規範變更檢查紀錄（G4、G5）與 Gate 2

**G4 一致性檢查**

| # | 項目 | 結果 |
| :---: | :--- | :--- |
| 1 | `verify_doc_sync.py` | 通過 |
| 2 | 改名殘留 | `SRC_PACKAGE` 改為 `SRC_IMPORT_PACKAGE`／`INTERNAL_ROOTS`，全倉無殘留 |
| 3 | 新名稱撞名 | `package`（`[layers]` 選填鍵）、`src_python_files`、`layer_module`、`internal_roots`、`pip_audit_target` 無撞名 |
| 4 | AGENTS.md 行數 | 未修改，175 行 |
| 5 | Markdown 斷鏈測試 | 通過 |
| 6 | 程式變更 | 驗證腳本與設定載入器；單元測試齊備，走 Gate 2（下表） |

**Gate 2 程式檢查**

| 輪次 | 日期 | 範圍 | `audit_guardrails.py` | `security_scan.py` | P0 | P1 | P2 | 判定 |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 2026-11-21 | `a552688..HEAD` | Exit 0 | Exit 0 | 0 | 0 | 0 | **PASS** |

* 程式覆核：未設定 `package` 時推導結果與舊版等價（`src = "src"` → `src.domain`）；Domain 歸屬判定由前綴比對改為以點號為界（`_in_package`），屬收緊，本專案無受影響之模組；`src_python_files` 只排除設定之目錄名與 `.agents/`，本專案 `src/` 下無同名子目錄；設定解碼錯誤以 `ProjectConfigError` 鏈結原例外；pip-audit 參數以清單傳遞，無 shell 拼接。

**G5 審查**（gatekeeper 視角）：零矛盾、零重複。`package` 之預設值由同專案 `src` 推導，與載入器「不沿用原專案值」之原則一致並已於模組 docstring 註明；原始碼檔案列舉由 6 處收斂為 1 個函式；PORTING 新增說明與 `project.toml` 註解用語一致。
