# 缺陷修正流程 (Bug Track)

> **適用**：既有行為違反規格、文件或合理預期（如崩潰、資料錯誤），且「正確行為」無須重新定義；嚴重度 S2、S3。S1 改走 [hotfix.md](./hotfix.md)。
> **本檔只寫編排**；各步驟怎麼做，以對應 Skill 為準。

## 步驟與 Skill

| 步驟 | 角色 | Skill | 本軌差異 |
| :--- | :--- | :--- | :--- |
| **1B** 缺陷分析 | developer（階段 1–5）、architect（階段 6 簽核） | [bug-triage](../skills/bug-triage/SKILL.md) | 重現 → 紅燈測試 → RCA → 修正範圍 → 簡化 Gate 1；缺陷報告寫入 `docs/bugs/XXXX-*.md` |
| **2** 實作 | developer | *(DDD 架構約制)* | 只改修正範圍內的檔案；超出範圍回 1B 第 5 階段重新判斷 |
| **3** 單元測試 | developer | [unit-testing](../skills/unit-testing/SKILL.md) | 紅燈測試須轉綠；全套單元測試無回歸 |
| **4** QA 實測 | gatekeeper | [qa-testing](../skills/qa-testing/SKILL.md) | RTM 對象為缺陷驗收條件 `BC-*` 加上受影響功能原規格的 AC；測試計畫只涵蓋受影響範圍；S3 可縮為受影響範圍 |
| **5** Gate 2 | gatekeeper | [gate2-code-review](../skills/code-review/SKILL.md) | 加查「先紅後綠」與「逃逸分析」 |
| **6** 修正 | developer | [auto-fix](../skills/auto-fix/SKILL.md) | 不變，三振熔斷照常 |
| **7** 文件同步 | architect | [doc-sync](../skills/doc-sync/SKILL.md) | 缺陷報告結案並登錄 `docs/README.md` 缺陷索引；僅在文件描述有誤時更新 `REQUIREMENTS.md`／`ARCHITECTURE.md`；不產出 ADR |

退回路徑與 [feature.md](./feature.md) 相同；另外 1B 第 2 階段**無法重現即停止**，請使用者補充資訊。

## PR 與 commit 規則

| 規則 | 內容 |
| :--- | :--- |
| **先 test 後 fix** | 回歸測試與修正分成兩個 commit：先 `test:`（紅燈），再 `fix:`（轉綠），一起推進同一個 PR。Gate 2 於 `test:` commit 重跑該測試，須為失敗 |
| **一個 bug 一個 PR** | 同根因的多個症狀視為一個 bug，多個測試放同一個 `test:` commit；不同根因各自開缺陷報告與 PR；修 A 時發現 B，另開 B 排隊處理 |
| **不得 squash** | 以一般 merge 合併，保留 `test:` commit 作為紅燈證據 |

例外：確需在同一 PR 修多個獨立 bug 時，順序為 `test A → fix A → test B → fix B`，並於 PR 描述說明理由。

## 升級回 Feature 軌

**升級條件**（任一成立）：
1. 需修改 Domain 契約檔（`project.toml` 的 `layers.domain_interfaces`，本專案為 `src/domain/interfaces.py`）的 Protocol 或 DTO 欄位。
2. 需修改資料模型或持久化結構（資料庫綱要、索引；本專案見專案概況）。
3. 需在設定模組（`config.module`）新增環境變數，或新增 CLI 參數。
4. 「正確行為」在現有規格中未定義或定義矛盾。
5. 修正範圍跨越 3 個以上 DDD 層。

**依發現時機處理**：

| 情況 | 處理 |
| :--- | :--- |
| **A. Step 1B 發現** | 停下並向使用者說明符合哪條升級條件；**經使用者確認**後，開新功能規格並改走 [feature.md](./feature.md) |
| **B. Step 2–6 才發現** | 立即停止實作，不得為繞過升級條件而硬改；回 1B 第 5 階段，比照情況 A |
| **C. S1 但根治需升級** | 見 [hotfix.md](./hotfix.md)「根治需升級」 |

**產物處理**：

| 項目 | 處理方式 |
| :--- | :--- |
| 缺陷報告 | 保留，狀態標為「已升級 → Spec-XXXX」，與新規格互相連結 |
| 編號 | 缺陷保留原號；功能規格取下一個流水號；QA 報告跟功能規格的編號 |
| 紅燈測試 | 保留，轉成新規格的 AC（如「AC-1：原缺陷情境 `test_xxx` 須通過」） |
| 已寫的程式碼 | 留在分支不合併，由新規格決定是否沿用 |
| 三振計數 | 換軌後歸零（升級不算修正失敗） |
