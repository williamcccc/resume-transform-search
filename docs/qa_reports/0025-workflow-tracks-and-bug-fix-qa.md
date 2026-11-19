# QA 實測驗收報告：閉環流程分軌與 workflows 目錄化（Spec-0025）

> **規格**：[Spec-0025](../specs/0025-workflow-tracks-and-bug-fix-spec.md)｜**所走流程**：[feature.md](../../.agents/workflows/feature.md)｜**分支**：`docs/spec-0025-bug-fix-track`（基準 `20f629e`）

## 1. 測試環境與前置條件
* **測試日期**：2026-11-19
* **作業系統與 Python 版本**：Windows 11 / Python 3.13.14 on PowerShell
* **外部相依服務**：不需要（本案只涉及規範文件與 `verify_doc_sync.py`，無 Redis、無 LLM API）
* **測試資料集**：暫存目錄內動態建構的虛構文件；E2E 將專案規範文件複製到暫存目錄後注入錯誤，不修改專案檔案

---

## 2. 測試計畫摘要
* **測試範圍**：`verify_doc_sync.py` 新增的三項檢查（分流表 ↔ 流程檔、`docs/bugs/` 檔名／索引／品質宣告、範本鏡像一致性）；新增與修改的規範文件內容是否符合 AC；既有測試無回歸。
* **不測範圍**：

  | 不測項目 | 理由 | 風險與替代保障 |
  | :--- | :--- | :--- |
  | 以真實缺陷完整走一次 Bug 軌（含 `test:`／`fix:` commit） | 目前沒有待修的真實缺陷，為測試而製造缺陷會污染 `src/` | 以桌上演練（附錄 A）驗證 Step 1B 範本與升級規則可用；第一個真實缺陷案件即為實戰驗證 |
  | 助理是否真的會在分流後讀取流程檔 | 屬 AI 行為，無法以自動化測試確定 | AGENTS.md 明寫讀取要求，交付說明須註明所走流程檔；本報告開頭即示範 |
  | GitHub 關閉 squash merge 設定 | 屬 repo 設定，須由使用者操作 | 規則已寫入 `bug.md`；Gate 2 先紅後綠檢查可抓出被 squash 的 PR |

* **進入條件**：Spec-0025 經使用者核准；`tests/unit/` 新測試全數通過。
* **退出條件**：見第 8 節。
* **風險與優先順序**：(1) AGENTS.md 重構時遺漏原有規則 → 逐項比對（第 4 節 TC-08）；(2) 新檢查誤判既有文件 → E1 基準複本必須通過；(3) 範本鏡像斷鏈 → 全倉斷鏈測試。

---

## 3. 需求驗收追溯矩陣 (RTM)

| AC | 條款說明 | 測試案例 | 測試類型 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **AC-1** | 三個流程檔只寫編排 | TC-08 | 人工覆核 | **PASS** |
| **AC-2** | AGENTS.md 精簡並明寫讀取要求 | TC-01、TC-08 | E2E + 人工覆核 | **PASS** |
| **AC-3** | bug-triage 技能、範本、轉接層一致 | TC-07、TC-09 | E2E + 單元 | **PASS** |
| **AC-4** | bug.md 載明 PR 規則與升級規則 | TC-08 | 人工覆核 | **PASS** |
| **AC-5** | `docs/bugs/` 與分流表連結檢查，含四種負面情境單元測試 | TC-02～TC-06、TC-09 | E2E + 單元 | **PASS** |
| **AC-6** | Gate 2 新增先紅後綠 (P0)、逃逸分析 (P1) | TC-08 | 人工覆核 | **PASS** |
| **AC-7** | 兩支驗證腳本與全套單元測試通過 | TC-10 | 回歸 | **PASS** |
| **AC-8** | Step 1B 與升級路徑演練 | TC-11 | 桌上演練 | **PASS** |

> **RTM 統計**：PASS 8 / FAIL 0 / DEFERRED 0 / NOT COVERED 0（共 8 條 AC）
>
> **DEFERRED 明細**：無

---

## 4. 測試案例執行矩陣

| 案例 | 名稱 | 分類 | 輸入 / 操作 | 預期 | 實際 | 判定 |
| :---: | :--- | :---: | :--- | :--- | :--- | :---: |
| **TC-01** | 基準複本通過 | Happy | E2E `test_e1`：專案規範文件原樣複製後執行腳本 | Exit 0；分流表 3 個、鏡像 5 個一致 | 同預期 | **PASS** |
| **TC-02** | 流程檔被刪除 | Fault | E2E `test_e2`：刪除 `hotfix.md` | Exit 1；指出 `hotfix.md` 不存在 | 同預期 | **PASS** |
| **TC-03** | 缺陷報告未登錄索引 | Edge | E2E `test_e3`：新增 `0099-*.md` 未登錄 → 登錄後重跑 | 先 Exit 1「未登載於」，登錄後 Exit 0 | 同預期 | **PASS** |
| **TC-04** | 缺陷報告缺品質宣告 | Edge | E2E `test_e4` | Exit 1；指出缺宣告的檔名 | 同預期 | **PASS** |
| **TC-05** | 範本鏡像漂移 | Fault | E2E `test_e5`：鏡像多一行 | Exit 1「鏡像與正本不一致」 | 同預期 | **PASS** |
| **TC-06** | 未登錄的流程檔 | Edge | E2E `test_e6`：新增 `perf.md` | Exit 1「未登錄於 AGENTS.md 分流表」 | 同預期 | **PASS** |
| **TC-07** | 缺少 bug-triage 轉接層 | Fault | E2E `test_e7`：刪除 `.claude/skills/bug-triage/` | Exit 1「缺少 Claude Code 轉接檔」 | 同預期 | **PASS** |
| **TC-08** | 規範文件人工覆核 | Review | 逐項比對 AGENTS.md 原第 2 節與 `feature.md`；檢查三個流程檔、Checklist、角色檔 | 原 7 步驟、放行條件、退回路徑、三振熔斷皆保留；流程檔不含 Skill 作業細節 | 符合；另修正 architect 角色檔的缺陷回報入口描述，並將 ARCHITECTURE.md／REQUIREMENTS.md 原有的「Step 1A／1B」（PRD／Tech Spec 兩階段）改名為「Step 1-1／1-2」，避免與 Bug 軌 Step 1B 撞名 | **PASS** |
| **TC-09** | 白箱單元測試 | Unit | `tests/unit/test_workflow_tracks_doc_sync.py` | 16 項全數通過 | `Ran 16 tests ... OK` | **PASS** |
| **TC-10** | 全套回歸 | Regression | 全套單元測試、`verify_doc_sync.py`、`audit_guardrails.py` | 全數通過 | 見第 5 節 | **PASS** |
| **TC-11** | Step 1B 與升級演練 | Tabletop | 附錄 A 兩個虛構情境 | 範本各節可填寫；升級條件可明確判定 | 符合 | **PASS** |

---

## 5. 實測執行日誌摘要
```text
[E2E]  python -m unittest tests.e2e.test_workflow_tracks_doc_sync_e2e
       Ran 7 tests in 5.727s ... OK
[Unit] python -m unittest tests.unit.test_workflow_tracks_doc_sync
       Ran 16 tests in 0.145s ... OK
[Unit] python -m unittest discover -s tests/unit -p "test_*.py"
       Ran 608 tests ... OK
[Doc]  python .agents/skills/doc-sync/scripts/verify_doc_sync.py
       [SUCCESS] 100% In Sync（分流表 3 個、範本鏡像 5 個、Skill 轉接層 10 個）
[AST]  python .agents/skills/code-review/scripts/audit_guardrails.py
       100% PASSED（零 P0）
```

---

## 6. 品質評測結果
不適用（規格宣告品質評測範圍：否）。

---

## 7. 失敗分析與根因定位

本輪執行期間共遇到 2 項失敗，皆已修正並重跑通過：

| # | 失敗現象 | 根因 | 修正 |
| :---: | :--- | :--- | :--- |
| 1 | 全套單元測試 `test_repository_markdown_links_resolve` 失敗：`docs/templates/` 3 個範本斷鏈 | 範本正本內有指向其他 Skill 的相對連結，複製到 `docs/templates/` 後路徑失效 | 範本內引用改為反引號專案路徑，正本與鏡像皆不含相對連結；`docs/README.md` 註明此規則 |
| 2 | E2E 7 項全部 `TypeError: argument of type 'NoneType'` | 子程序在 Windows 以主控台編碼輸出，測試以 UTF-8 解碼失敗，`stdout` 為 `None`；`-I` 模式會忽略 `PYTHONIOENCODING` | 子程序改以 `-I -X utf8` 啟動 |

另發現一項既有缺陷（非本案造成）：`docs/templates/` 鏡像早已與正本不一致，PR #15／#16 修改範本時也未同步。已於本案修正並新增 `check_template_mirrors()` 防止再犯（見 Spec-0025「實作期間追加範圍」）。

---

## 8. QA 驗收結論
* **驗收判定**：**【通過 (PASSED)】**
* **放行標準**：
  1. RTM 零 `FAIL`、零 `NOT COVERED`、零 `DEFERRED` ✅
  2. 邊界與異常對抗實測全數通過 ✅
  3. Windows 資源生命週期：E2E 以 `TemporaryDirectory` 隔離，結束後自動清除 ✅
  4. 品質評測：不適用
* **放行說明**：准予放行進入 Gate 2 代碼審查。

---

## 9. Gate 2 代碼審查紀錄

### 9.1 審查輪次

| 輪次 | 日期 | 審查範圍 | `audit_guardrails.py` | P0 | P1 | P2 | 判定 |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| 1 | 2026-11-19 | `20f629e..`（本分支全部變更） | Exit 0 | 0 | 0 | 2 | **PASS** |

### 9.2 發現項目

| ID | 等級 | 檢核項 | 檔案:行號 | 描述 | 處置 |
| :--- | :---: | :--- | :--- | :--- | :--- |
| R1-01 | P2 | 向下相容性 | `verify_doc_sync.py` `WORKFLOW_LINK_PATTERN` | 只辨識以 `.agents/workflows/` 或 `./.agents/workflows/` 開頭的連結；AGENTS.md 位於專案根目錄，現況足夠，但若日後改用其他寫法會漏判 | 保留；E2E `test_e2`／`test_e6` 可抓出漏判造成的不一致 |
| R1-02 | P2 | 測試獨立性 | `tests/unit/test_workflow_tracks_doc_sync.py` | 兩項守門測試讀取專案內的範本檔與 `docs/templates/` 檔名清單，非純記憶體 | 保留；讀取對象為版控內的範本，不涉及 `data/`、`resume/` 或個資，目的是防止範本與檢查清單脫節 |

### 9.3 需求—斷言追溯抽查

| AC | 對應測試與斷言 | 預期值來源 | 判定 |
| :--- | :--- | :--- | :---: |
| AC-5 | `test_link_to_missing_workflow_fails`：斷言回傳 `False` 且輸出含 `流程檔不存在: .agents/workflows/hotfix.md` | 規格 AC-5 (b)：連結的流程檔須存在 | **OK** |
| AC-5 | `test_report_missing_from_index_fails`：斷言 `False` 且輸出含檔名 `0027-redis-timeout.md` | 規格 AC-5 (a)：缺陷報告須登錄索引 | **OK** |
| AC-3 | E2E `test_e7`：斷言 Exit 1 且輸出指出缺少的轉接檔路徑 | 規格 AC-3：轉接層與正本一致 | **OK** |

### 9.4 雙門禁審查結論
* **架構靜態掃描**：通過（`audit_guardrails.py` 零 P0）
* **DDD 依賴邊界**：不適用（未修改 `src/`）
* **安全與配額硬上限**：不適用
* **資源釋放與鎖定防禦**：通過（腳本讀檔皆用 `read_text`；E2E 使用 `TemporaryDirectory`）
* **Twelve-Factor 配置治理**：通過（零寫死絕對路徑；路徑以 `Path(__file__).resolve()` 定位）
* **邊界例外與例外鏈**：不適用（未新增例外處理）
* **日誌安全合規**：通過（輸出僅含專案相對路徑與檔名）
* **資料操作與冪等性**：通過（檢查為唯讀；E2E 不修改專案檔案）
* **測試隔離與負面覆蓋**：通過（16 項單元測試 + 7 項 E2E，含 9 種負面情境）
* **需求—斷言追溯**：通過（8/8 條 AC 有對應驗證；抽查 3 項預期值皆來自規格）
* **先紅後綠與逃逸分析**：不適用（本案屬功能開發軌）
* **Git 版控衛生與零個資防線**：通過（虛構內容、相對路徑、全倉斷鏈測試通過）

---

## 附錄 A：Step 1B 桌上演練（AC-8）

以下兩個情境皆為**虛構**，用來檢驗範本與規則是否可操作，不代表系統中存在這些缺陷。

### A-1 標準 Bug 軌：輸出目錄不存在時崩潰（虛構）

| 階段 | 演練結果 |
| :--- | :--- |
| 1. 受理與分級 | 現象：指定不存在的輸出子目錄時，CLI 拋出未處理的 `FileNotFoundError`。有替代做法（先手動建立目錄）→ **S2**，走 `bug.md` |
| 2. 重現 | 步驟：以 `sample_resume.md` 搭配不存在的輸出路徑執行轉檔。預期：自動建立目錄或給出明確錯誤訊息；實際：Traceback |
| 3. 紅燈測試 | 測試放 `tests/unit/`，以暫存目錄建構不存在的子路徑，斷言「轉檔後輸出檔存在」。修正前失敗原因為 `FileNotFoundError`，符合缺陷本身 |
| 4. 根因與逃逸 | 真因在 infrastructure 層寫檔前未建立父目錄。逃逸分類：**測試缺口**（既有測試皆使用已存在的目錄） |
| 5. 範圍與升級 | 修改 1 個 infrastructure 檔案；5 條升級條件皆未觸發 |
| 6. 簡化 Gate 1 | 恢復既有行為 ✅；影響面：所有寫檔路徑 ✅；無介面破壞 ✅ |

**結論**：範本第 1–5 節皆可直接填寫；`BC-1`（紅轉綠）與 `BC-3`（無回歸）可直接沿用範本預設。

### A-2 升級路徑（情況 A）：切片標題截斷（虛構）

| 階段 | 演練結果 |
| :--- | :--- |
| 1–4 | 現象：特定長度的段落標題在切片後被截斷。根因：截斷長度寫在切片器內，且現有規格沒有定義標題最大長度 |
| 5. 升級判斷 | 觸發**條件 3**（須新增 `AppConfig` 環境變數讓長度可設定，符合零硬編碼紅線）與**條件 4**（正確長度在規格中未定義） |
| 處理 | 停下並向使用者說明觸發的兩條條件 → 經確認後，缺陷報告標「已升級 → Spec-XXXX」→ 新規格背景引用重現與根因 → 紅燈測試轉為新規格 AC-1 → 改走 `feature.md`，三振計數歸零 |

**結論**：升級條件可明確判定，產物去向有規則可循。演練中發現一點可再補強：升級後的新規格須在 `docs/README.md` 索引表註明來源缺陷編號。此點已由 `bug.md`「缺陷報告與新規格互相連結」涵蓋，不另行修改。
