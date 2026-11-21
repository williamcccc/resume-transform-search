# ADR-0040：紅線 1、6 之本專案值移入本專案紅線小節

## 1. 狀態
已採納 (Accepted)

* **日期**：2026-11-21（提案與採納）
* **規格與驗收**：[Spec 0040](../specs/0040-red-lines-1-6-project-annotations-spec.md)、[QA Report 0040](../qa_reports/0040-red-lines-1-6-project-annotations-qa.md)
* **關聯**：[ADR-0037](./0037-agents-red-lines-generic-and-project-groups.md)（紅線分為通用與本專案兩組）
* **標籤**：`Governance`, `Portability`, `Red Lines`

## 2. 背景與問題陳述
ADR-0037 將紅線分組並逐字保留紅線文字，因此通用紅線 1、6 仍帶有「本專案為 `src/domain/interfaces.py`」「本專案為 `AppConfig`」附註。通用紅線因此含本專案的值，移植時須改寫通用紅線本文；中性化守護測試也只能把整個紅線小節排除在外。此外紅線 6 的 `config.module` 為檔案路徑，附註卻寫類別名，層次不一致。

## 3. 評估選項
* **選項 A：直接刪除附註**，本專案的值只留在 `project.toml`。缺點：`project.toml` 不常駐載入，對話中未必讀到本專案契約檔與設定模組名稱。
* **選項 B：附註移入本專案紅線小節**，新增「紅線 1、6 本專案對應」一條。缺點：AGENTS.md 增加 1 行。
* **選項 C：維持現狀**。缺點：通用紅線持續夾帶本專案值，且不受守護測試約束。

## 4. 架構決策
選用**選項 B**。

* 紅線 1、6 只刪除「本專案為」附註，其餘文字逐字保留。
* 本專案紅線小節新增「紅線 1、6 本專案對應」：Domain 契約檔為 `src/domain/interfaces.py`；設定模組為 `src/infrastructure/config.py` 的 `AppConfig`。值仍常駐載入；路徑正本仍為 `project.toml`。
* 中性化守護測試的排除範圍收窄為「本專案紅線」小節，通用紅線 1、6、7 納入守護。
* `audit_guardrails.py` 之寫死 URL 違規訊息改以「設定模組（config.module）」指引，不再出現原專案類別名。

本決策由使用者於 2026-11-21 明確提出並核准，符合 [governance.md](../../.agents/workflows/governance.md)「紅線特別規定」；未放寬或刪除任何紅線。

## 5. 8 大架構審查維度評估
| # | 維度 | 評估結論 |
| :---: | :--- | :--- |
| 1 | 個資與敏感資料 (Sensitive Data) | 不適用：紅線 7 未變更 |
| 2 | 容量與資源上限 (Capacity) | 不適用：只調整規範文件 |
| 3 | 解耦與非同步演進 (Async / Evolution) | 不適用：只調整規範文件 |
| 4 | 外部呼叫成本與配額 (External Cost & Quota) | AGENTS.md 由 174 行增為 175 行，常駐載入成本可忽略 |
| 5 | 可抽換性 (Portability & Decoupling) | 通用紅線不再含本專案值，移植時可原樣沿用；改寫範圍維持單一小節 |
| 6 | 惡意輸入與資源上限 (Input Security) | 不適用：只調整規範文件與訊息字串 |
| 7 | 資料結構演進 (Schema Evolution) | 不適用：無持久化結構變更 |
| 8 | 併發與可觀測性 (Concurrency & Traceability) | 不適用：只調整規範文件與訊息字串 |

## 6. 後果
* **正面**：核心文件（含通用紅線）不再含本專案識別字或「本專案為」附註，並由守護測試持續約束。
* **負面**：本專案契約檔與設定模組之值在 AGENTS.md 與 `project.toml` 各出現一次；前者為常駐對照，後者為腳本正本，移植時兩處皆須改寫（PORTING 已要求整節改寫本專案紅線）。
