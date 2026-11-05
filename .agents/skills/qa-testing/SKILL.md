---
name: qa-testing
description: >-
  Use this skill to design QA test cases from PRD acceptance criteria, discover edge cases and race conditions,
  generate and review automated E2E/integration test scripts, execute live testing, analyze failures with root-cause analysis (RCA),
  and produce formal QA test reports before code review.
---

# QA 實測與智能驗收測試技能 (Intelligent QA Testing & Verification)

本技能提供本專案在實施 **「Step 4：黑箱/灰箱 QA 實測驗證」** 時的最高作業規範。
用以彌補「白箱單元測試 (Unit Test, 100% Mock)」無法驗證真實環境交互的盲點。AI 將作為自主 QA 專家，負責**需求追溯**、**對抗式邊界挖掘**、**腳本生成與 Flaky 審核**、**實測執行**以及**失敗根因定位 (RCA)**。

---

## 一、QA 核心能力四大支柱 (4 Core Pillars)

### 1. 需求對齊與 100% 驗收覆蓋 (Traceability & Coverage)
* **需求追溯矩陣 (Requirements Traceability Matrix, RTM)**：
  - 自動交叉比對前期產出的「PRD」與「Tech Spec」，逐一盤點每一條 **Acceptance Criteria (AC)**。
  - 強制保證：**每一條業務驗收條件（AC）至少具備一組對應的測試案例覆蓋**，嚴禁遺漏任何需求邊界。

### 2. 邊界與異常情境對抗挖掘 (Edge Case Discovery & Adversarial Scenarios)
發掘人類工程師容易忽略的極限盲區，自動補充以下對抗式測試案例：
* **併發競態危害 (Concurrency & Race Conditions)**：多 Worker 或多執行緒同時轉檔/更新同位候選人時的狀態衝突防護。
* **重複請求與操作冪等性 (Idempotency)**：重複執行批次轉檔或重覆寫入 Redis 時，切片不會重複堆疊或污染。
* **網路抖動與服務斷線 (Network Glitches & Reconnection)**：模擬 Redis 離線、Gemini API 429 配額用罄或連線超時的平滑降級與熔斷重連。
* **惡意與畸形輸入注入 (Adversarial Injections)**：傳入 0-byte 空檔案、損毀 ZIP、超大 PDF 頁數、特殊字元路徑與提示詞注入攻擊（Resume Jailbreak）。

### 3. 測試腳本自動生成與防 Flaky 審查 (Script Generation & Anti-Flaky Review)
* **自動轉化執行腳本**：將自然語言的測試情境自動轉化為標準 Python 測試代碼（存於 `tests/e2e/` 或 `tests/integration/`）。
* **Flaky Tests（不穩定測試）審核**：
  - 嚴禁測試間存在執行順序依賴（Order Dependency）。
  - 強制使用 `tempfile.TemporaryDirectory` 進行磁碟隔離，並在 teardown 確保完整釋放控制代碼，防止 Windows 檔案殘留鎖定。
  - 對非同步或網路呼叫設定合理超時上限，避免測試無止盡懸掛（Hang）。

### 4. 失敗分析與自動根因定位 (Automated Failure Analysis & RCA)
* 當測試執行失敗（`FAIL` / `ERROR`）時，AI 自動介入：
  - 深度研讀測試報告、標準輸出、系統 Log 與 Traceback。
  - 執行根因分析（RCA）：精準定位是哪一個模組、哪一行程式碼或哪一處邏輯不相容引發問題。
  - 產出具體修復建言，直接回饋給「Step 6 (Auto-Fix)」進行閉環修復，修復後自動重新驗證。

---

## 二、QA 實測作業流程 (QA Testing Workflow)

```mermaid
flowchart TD
    Start["進入 Step 4: QA 實測驗證<br>(單元測試已全數通過)"] --> Phase1["階段 1: 需求追溯與邊界挖掘 (Traceability & Discovery)<br>• 對照 PRD AC 盤點 RTM 覆蓋矩陣<br>• 自動挖掘併發競態、冪等性、壞檔與斷線情境"]
    
    Phase1 --> Phase2["階段 2: 產生實測腳本與防 Flaky 審核 (Script & Review)<br>• 產生/更新 tests/e2e/ 或 integration/ 腳本<br>• 審查隔離性，消除不穩定測試 (Flaky tests)"]
    
    Phase2 --> Phase3["階段 3: 實測執行 (Live Execution)<br>• 執行端到端實測腳本 (真實 CLI、真實 Sample、真實 Redis)<br>• 驗證 Windows 檔案釋放與向下相容性"]
    
    Phase3 --> Check{"實測是否 100% 通過?<br>(零功能瑕疵、零未預期例外)"}
    Check -->|"失敗 (Failures)"| RCA["階段 4A: 失敗分析與根因定位 (RCA)<br>• 解析 Traceback 與系統日誌<br>• 定位具體破壞點，產出修復建言<br>• 打回 Step 6 (Auto-Fix) 修正"]
    RCA --> Start
    
    Check -->|"全部通過"| Phase4["階段 4B: 出具 QA 實測驗收報告 (QA Sign-Off)<br>• 產出 RTM 覆蓋矩陣與極端測試成果<br>• 簽核放行進入 Gate 2 代碼審查"]
```

---

## 三、執行指令與交付規範

### 執行端到端實測指令：
```bash
python -m unittest discover -s tests/e2e -p "test_*.py"
```

### 驗收放行標準 (Sign-Off Criteria)：
1. **100% AC 覆蓋**：PRD 定義之驗收條件全數通過。
2. **零阻斷型缺陷 (Zero P0/P1 Defects)**：無崩潰、無未受控例外。
3. **Windows 資源清潔度**：測試執行完畢後無控制代碼殘留，暫存檔乾淨卸載。
4. **向下相容性保持**：既有 CLI 命令引數與回傳格式 100% 保持穩定。

---

## 相關參考資料
* [QA 測試個案設計範本 (Test Case Specification)](./references/test_case_template.md)
* [QA 實測驗收報告範本 (QA Report Template)](./references/qa_report_template.md)
