# QA 實測驗收報告範本 (QA Test Report Template)

> **使用說明**：當 QA 實測腳本執行完畢後，由 `qa-testing` 技能彙整執行結果，出具本報告供 Gate 2 代碼審查及最終交付之依據。

---

# QA 實測驗收報告: [功能名稱 / 變更主題]

## 1. 測試環境與前置條件 (Test Environment)
* **測試日期與時間**：`YYYY-MM-DD HH:MM:SS`
* **作業系統與 Python 版本**：Windows 11 / Python 3.13 on PowerShell
* **外部相依服務狀態**：
  * Redis (Docker): `localhost:6379` (連線正常 / 索引已就緒)
  * Gemini API: 正常連線 / 或使用本機離線模式測試
* **測試資料集**：`resume/` 目錄樣本檔案 / 動態生成的邊界測試檔案

---

## 2. PRD 需求驗收追溯矩陣 (Requirements Traceability Matrix, RTM)
驗證 PRD 中的每一項 Acceptance Criteria (AC) 是否達到 **100% 測試覆蓋**：

| PRD 驗收條款 (AC) | 條款說明 | 覆蓋測試案例 (TC ID) | 測試類型 | 覆蓋狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **AC 1.1** | 正向履歷轉檔與切片入庫 | `TC-01` | E2E | **COVERED** |
| **AC 1.2** | 既有 CLI 參數向下相容性 | `TC-02` | CLI | **COVERED** |
| **AC 2.1** | 0-byte 空檔案與壞檔防禦 | `TC-03` | Edge / Fault | **COVERED** |
| **AC 2.2** | 重複轉檔 Redis 切片冪等清理 | `TC-04` | Idempotency | **COVERED** |
| **AC 3.1** | 外部 API 429 速率超標降級 | `TC-05` | Circuit Breaker | **COVERED** |

> **RTM 覆蓋率判定**：**100% 覆蓋 (零業務需求遺漏)**

---

## 3. 測試案例執行矩陣 (Test Case Execution Matrix)

| 案例編號 | 測試案例名稱 | 分類 | 輸入條件 / 指令 | 預期結果 (Expected) | 實際結果 (Actual) | 判定 |
| :---: | :--- | :---: | :--- | :--- | :--- | :---: |
| **TC-01** | 正向路徑端到端實測 | Happy | CLI 轉換指定樣本 | 產出完整 Markdown，包含 H1 與經歷區塊 | 產出符合規範，品管得分 95 | **PASS** |
| **TC-02** | 參數向下相容性驗證 | CLI | 不帶新參數執行既有指令 | 行為與改版前 100% 一致 | 既有流程無中斷 | **PASS** |
| **TC-03** | 極限邊界 / 空檔案測試 | Edge | 傳入 0 位元組空檔案 | 優雅拋出指定例外，程序不崩潰 | 捕獲例外並輸出警告 | **PASS** |
| **TC-04** | 操作冪等性實測 | Idempotency | 連續兩次入庫相同候選人 | 切片數量恆定，舊 Hash 完整被清理 | 驗證無重複堆疊污染 | **PASS** |
| **TC-05** | 故障注入 / 429 模擬 | Fault | 模擬外部 API 配額耗盡 | 觸發熔斷或降級機制，日誌記錄明確 | 平滑降級至文字模式 | **PASS** |

---

## 4. 實測執行日誌摘要 (Execution Logs Summary)
```text
[執行指令]: python -m unittest discover -s tests/e2e -p "test_*.py"
[標準輸出]: ...
[測試結果]: Ran X tests in Ys ... OK
```

---

## 5. 失敗分析與根因定位 (Failure Analysis & RCA)
> *若測試 100% 通過，本節填寫「無失敗項目」。若有失敗，AI 必須嚴格執行以下 RCA 分析並回饋 Step 6：*

* **失敗現象 (Symptom)**：測試名稱、報錯資訊與行號。
* **根因定位 (Root Cause)**：分析是由於介面變更、例外鏈遺漏、Windows 檔案鎖死、還是 Redis 競態引發。
* **修復建言與回饋 (Remediation)**：具體應修改的檔案路徑與方法邏輯。

---

## 6. QA 驗收結論 (QA Sign-Off)
* **驗收判定**：**【通過 (PASSED)】** / **【未通過 (FAILED - 打回修正)】**
* **放行說明**：
  1. 需求追溯覆蓋率：**100% (無遺漏需求)**
  2. 邊界與異常對抗實測：**全數通過 (無崩潰或未受控例外)**
  3. Windows 資源生命週期：**驗證通過 (無控制代碼殘留與鎖定錯誤)**
  4. **准予放行進入 Gate 2 代碼審查！**
