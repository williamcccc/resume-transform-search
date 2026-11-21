# 提案與規格書：STRIDE 威脅表以欄名判定、扁平根目錄內部模組判定

> **狀態**：G1 提案（待使用者 G2 核准）｜**類型**：規範變更（大改：修改驗證腳本 `verify_doc_sync.py`、`audit_guardrails.py`）｜**流程**：[governance.md](../../.agents/workflows/governance.md)｜**影響範圍**：`.agents/skills/doc-sync/scripts/verify_doc_sync.py`、`.agents/skills/code-review/scripts/audit_guardrails.py`、`.agents/tests/`、`.agents/PORTING.md`，不涉及 `src/`、不修改紅線

## 一、動機

[QA-0047](../qa_reports/0047-porting-trial-3-fixes-qa.md) 第 7 節登錄之兩項低風險殘餘，經複查後判定應修：

| # | 問題 | 實例 | 影響 |
| :---: | :--- | :--- | :--- |
| 1 | STRIDE 威脅表誤認（**偽陰性**） | 規格宣告「安全評估範圍：是」但未寫威脅表；另一張表（如待決事項、卡點表）第一欄為單一字母 `D` 或 `E`，再有一條 `NFR-*`，`verify_doc_sync.py` 即通過 | 安全門檻被無聲繞過。根因：Spec-0047 將樣式放寬為「任一儲存格只含單一 S/T/R/I/D/E 字母」，未要求該表為威脅表 |
| 2 | 扁平根目錄之內部模組誤判（**偽陽性**） | `layers.src = "."`、`package = ""` 時，Application 之 `from shared import util`（倉庫根之非分層套件）被判「引入外部第三方套件」；一般佈局之對應寫法 `from app.shared import util` 則允許 | 兩種佈局判定不一致，且無設定可繞過，只能搬移目錄。根因：`package` 為空時內部根名只取四層之頂層名稱 |

## 二、修改內容

### 2.1 威脅表以欄名判定（問題 1）

* `verify_doc_sync.py`：以表格為單位解析（連續之 `|` 開頭列；第 2 列為分隔列）。表頭任一欄名含「STRIDE」者為威脅表；其資料列中，該欄儲存格只含單一 S/T/R/I/D/E 字母（可加粗）者，計為威脅列。宣告屬安全範圍之規格須至少一個威脅列。
* 取代 `STRIDE_ROW_PATTERN` 之逐列樣式；STRIDE 欄位置不限（第一欄亦可，保留 Spec-0047 AC-6 之行為）。
* FAIL 訊息改為「缺少 STRIDE 威脅表（表頭須有 STRIDE 欄，且至少一列該欄標註 S/T/R/I/D/E）」。
* 範本（`prd_template.md`）與框架（`security_nfr_framework.md`）之威脅表表頭已含「STRIDE」欄，不需修改。

### 2.2 扁平根目錄內部模組（問題 2）

* `audit_guardrails.py`：`package` 為空時，專案內部根名改為**原始碼根目錄下實際存在之頂層套件（目錄）與模組（`.py`）名稱**，排除 `ignore_scan_dirs`、閉環核心 `.agents/` 與隱藏目錄；與一般佈局「`package` 第一段之下皆屬內部」語意一致。
* 判定後之規則不變：Domain 引用非 Domain 之內部模組為「逆向依賴外層模組」；Application 引用 Infrastructure／Interfaces 為「違反依賴反轉」，引用其他內部模組允許。
* PORTING 第 3 步補一句：扁平根目錄時，根目錄下之頂層套件與模組皆視為專案內部。

### 2.3 測試

* `test_security_ac_gate`：其他表格首欄為 `D`／`E` 但無 STRIDE 欄 → FAIL（先紅後綠）；STRIDE 欄位於第一欄、第二欄、表頭為「STRIDE 類別」→ 通過；有 STRIDE 欄但無資料列（空範本）→ FAIL；表格解析函式之單元測試（分隔列、跳脫之 `\|`、表格間以空行分隔）。
* `test_guardrail_gaps` 之 `TestFlatRootPackage`：Application 引用根目錄 `shared/` 零 P0、Domain 引用 `shared/` 為逆向依賴（先紅後綠）；`ignore_scan_dirs` 下之同名目錄不視為內部。
* `internal_roots` 單元測試改為涵蓋目錄列舉。

## 三、衝突與重複檢查

| 檢查 | 結果 |
| :--- | :--- |
| 與既有規則矛盾 | 無。威脅表判定較 Spec-0047 收緊、較 Spec-0030 原樣式（任一非首欄單字母）亦收緊；現有編號 ≥ `security_ac_enforced_from` 且宣告「是」之規格為 0 份，無既有文件受影響。內部模組判定只影響 `package = ""` 之專案 |
| 同一規則寫在兩處 | 無：威脅表格式之正本仍為範本與框架，腳本只驗證 |
| 紅線 | 不修改 AGENTS.md |

## 四、規模

**大改**：修改驗證腳本。產出本規格與 QA 報告；不涉及紅線，不寫 ADR。

## 五、待決事項

| # | 問題 | 建議 | 替代方案 |
| :---: | :--- | :--- | :--- |
| 1 | 威脅列之判定範圍 | **只看 STRIDE 欄之儲存格**（最嚴格，與範本一致） | 表頭含 STRIDE 之表格中任一儲存格為單字母即算（較寬，同表其他欄之單字母亦計入） |
| 2 | 扁平根目錄內部模組來源 | **自動列舉根目錄之頂層套件與模組**（零設定） | 新增設定鍵明列內部模組（較明確，但移植者多一項設定） |

## 六、驗收條件

品質評測範圍：否

安全評估範圍：否

* **AC-1**：無 STRIDE 欄之表格首欄為 `D`／`E` 時，宣告屬安全範圍之規格 FAIL；修正前通過（先紅後綠）。
* **AC-2**：STRIDE 欄位於任一欄、表頭為「STRIDE」或「STRIDE 類別」、儲存格加粗時皆通過；有 STRIDE 欄而無威脅列時 FAIL。
* **AC-3**：`package = ""` 時 Application 引用根目錄之非分層套件零 P0；Domain 引用之為「逆向依賴外層模組」；`ignore_scan_dirs` 與 `.agents/` 下之名稱不視為內部。修正前 Application 案例為 P0（先紅後綠）。
* **AC-4**：`package` 非空時之稽核結果與修正前相同。
* **AC-5**：本專案 `verify_doc_sync.py`、`audit_guardrails.py`、`security_scan.py` 通過；`tests/unit`（含斷鏈）、`.agents/tests`、`.agents/tests/e2e`、`tests/e2e` 之移植演練全數通過。
