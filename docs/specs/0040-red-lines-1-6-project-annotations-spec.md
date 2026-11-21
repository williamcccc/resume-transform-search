# 提案與規格書：紅線 1、6 之「本專案為」附註移入本專案紅線小節

> **狀態**：已實作（G2：使用者於 2026-11-21 核准，3 項待決事項全數採建議；QA 見 [QA-0040](../qa_reports/0040-red-lines-1-6-project-annotations-qa.md)；決策見 [ADR-0040](../adr/0040-red-lines-1-6-project-values-moved.md)）｜**類型**：規範變更（大改：修改 AGENTS.md 第 1 節架構紅線，須 ADR）｜**流程**：[governance.md](../../.agents/workflows/governance.md)｜**影響範圍**：[AGENTS.md](../../AGENTS.md) 第 1 節、[test_neutral_examples.py](../../.agents/tests/test_neutral_examples.py)、`docs/adr/`，不涉及 `src/`

## 一、動機

[ADR-0037](../adr/0037-agents-red-lines-generic-and-project-groups.md) 把紅線分為「通用紅線」與「本專案紅線」兩組，但通用紅線 1、6 的文字仍夾帶本專案的值：

| 紅線 | 現行文字片段 | 問題 |
| :---: | :--- | :--- |
| 1 | Domain 契約檔（`layers.domain_interfaces`，本專案為 `src/domain/interfaces.py`） | 通用紅線含本專案路徑；移植時須改通用紅線本文 |
| 6 | 設定模組（`config.module`，本專案為 `AppConfig`） | 同上；且 `config.module` 是檔案路徑（`src/infrastructure/config.py`），附註寫類別名，兩者層次不一致 |

[Spec-0038](./0038-closed-loop-residual-project-coupling-spec.md) 已把其他核心檔的「本專案為」附註全數移除，並以 [test_neutral_examples.py](../../.agents/tests/test_neutral_examples.py) 守護；唯獨紅線小節因改字屬大改而整段排除在守護範圍外。這兩處是核心文件中最後的本專案殘留。

## 二、修改內容

### 2.1 AGENTS.md 第 1 節

* **紅線 1**：刪除「，本專案為 `src/domain/interfaces.py`」，其餘逐字保留。
* **紅線 6**：刪除「，本專案為 `AppConfig`」，其餘逐字保留。
* **本專案紅線小節**：於「紅線 7 本專案補充」之前新增一條（沿用 ADR-0037「紅線 N 本專案補充」寫法）：

  > * **紅線 1、6 本專案對應**：Domain 契約檔為 `src/domain/interfaces.py`；設定模組為 `src/infrastructure/config.py` 的 `AppConfig`。

  本專案的值仍常駐載入，約束強度不變；路徑正本仍為 `project.toml`，此條只作對照。

* AGENTS.md 行數：174 → 175（+1）。

### 2.2 守護測試收窄排除範圍

[test_neutral_examples.py](../../.agents/tests/test_neutral_examples.py) 的排除範圍由整個「核心不可變紅線」小節，收窄為只排除「#### 本專案紅線」小節。通用紅線 1、6、7 從此納入守護：日後若有人在通用紅線寫回本專案識別字或「本專案為」附註，測試失敗。docstring 同步更新。

### 2.3 ADR

新增 `docs/adr/0040-red-lines-1-6-project-values-moved.md`，記錄決策與替代方案；ADR-0037「後果」不改，以新 ADR 之「關聯」連回。

### 2.4 不改的項目

* `project.toml`、PORTING.md：值與移植步驟不變（PORTING 已要求改寫「本專案紅線」整節）。
* 歷史規格與 QA 報告中引用的舊紅線文字：屬歷史紀錄，不改。

## 三、衝突與重複檢查

| 檢查 | 結果 |
| :--- | :--- |
| 與既有規則矛盾 | 無。紅線 1、6 規範內容不變，只移動本專案值的位置；未放寬或刪除任何紅線 |
| 同一規則寫在兩處 | 新增條目與 `project.toml` 的 `layers.domain_interfaces`、`config.module` 為同值。`project.toml` 為腳本正本；AGENTS.md 條目為常駐對照，與原附註角色相同，未新增重複 |
| 專屬標記數 | 不變（仍只有「#### 本專案紅線」一處）；`verify_doc_sync.py` 單一標記檢查不受影響 |
| 紅線特別規定 | 本變更由使用者於對話中明確提出（「現在來處理紅線 1 6 二處的問題」），且不放寬紅線 |

## 四、規模

**大改**：修改 AGENTS.md 第 1 節架構紅線。產出本規格、QA 報告與 ADR-0040。

## 五、待決事項

| # | 問題 | 建議 | 替代方案 |
| :---: | :--- | :--- | :--- |
| 1 | 本專案的值放哪裡 | **移入本專案紅線小節**（新增「紅線 1、6 本專案對應」一條），維持常駐載入 | 直接刪除附註，只以 `project.toml` 為正本（AGENTS.md 少 1 行，但對話中不一定會讀到 `project.toml`） |
| 2 | 守護測試是否同步收窄排除範圍 | **收窄**，讓通用紅線也受守護 | 維持整節排除（下次又有人寫回附註時不會被抓到） |
| 3 | `audit_guardrails.py` 違規訊息「必須透過 AppConfig 注入」是否一併改為「必須透過設定模組（config.module）注入」 | **一併改**：同屬核心殘留，改訊息字串並補一項單元測試斷言 | 不改，留待日後修改驗證腳本時處理 |

## 六、驗收條件

品質評測範圍：否

安全評估範圍：否

* **AC-1**：AGENTS.md 紅線 1、6 不含「本專案為」；本專案紅線小節含 `src/domain/interfaces.py` 與 `AppConfig` 之對應條目；紅線 1、6 其餘文字逐字不變（比對腳本驗證）。
* **AC-2**：`test_neutral_examples.py` 只排除本專案紅線小節；以「在通用紅線插入『本專案為』」之情境驗證測試會失敗。
* **AC-3**：（待決 3 採建議時）`audit_guardrails.py` 違規訊息不含 `AppConfig`，單元測試斷言訊息含「設定模組」。
* **AC-4**：`verify_doc_sync.py`、`audit_guardrails.py`、`security_scan.py` 通過；`tests/unit`、`.agents/tests`、移植演練全數通過；斷鏈測試通過。
