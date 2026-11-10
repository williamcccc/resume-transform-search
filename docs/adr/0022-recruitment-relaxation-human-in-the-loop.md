# ADR-0022：招募助手放寬條件之人工決策（LangGraph interrupt）

## 1. 狀態
已採納 (Accepted)

* **日期**：2026-11-10（提案）／2026-11-10（採納，Gate 2 PASS）
* **規格與驗收**：[Spec 0022](../specs/0022-recruitment-relaxation-human-in-the-loop-spec.md)、[QA Report 0022](../qa_reports/0022-recruitment-relaxation-hitl-qa.md)
* **關聯**：[ADR-0021](./0021-recruitment-adaptive-candidate-search-loop.md)（沿用 `goto` 子步驟路由）、[ADR-0019](./0019-recruitment-assistant-langgraph-chat.md)
* **標籤**：`LangGraph`, `Human-in-the-Loop`, `Interrupt`, `Audit`

## 2. 背景與問題陳述
合格人數不足時，系統只能顯示放寬報告，使用者無法據此行動。要放寬哪一條招募條件屬於用人決策，不應由 Agent 自動決定，但系統應該讓「人做決定 → 系統立即重新比對」成為一個可靠、可稽核的流程。

## 3. 評估選項
* **A：新增 RELAX 意圖，每輪以一般對話處理**：不需要 interrupt，但決策點沒有明確狀態。系統無法分辨「回答待決定」與「隨口提到放寬」，也無法拒絕不合法或過期的決定。
* **B：LangGraph `interrupt()` 暫停在決策點，以 `Command(resume=...)` 恢復**：決策點是 checkpoint 中明確的待執行任務；恢復前可以對照當時的選項驗證；Redis checkpointer 可以跨實例恢復；追蹤樹中可以看到暫停與恢復。
* **C：Agent 依瓶頸自動放寬**：違反「用人決策由人決定」，不採用。

## 4. 架構決策
採納 **B**：
1. **分層**：`interrupt()` 只放在 Infrastructure 的 `await_relaxation` 節點。放寬規則（產生選項、驗證、套用）是 Domain 純函式，重新比對是 Application 的 `apply_relaxation` 節點。
2. **放寬語意**：被放寬的必要條件降為加分條件（ID 不變），至少保留 1 條必要條件；在已評估的候選池上確定性地重新排序，不重新抽取 Profile。
3. **輸入方式**：只接受 UI 勾選送出的結構化 ID，並對照當時的選項驗證；不解析文字指令。待決定時送出任何文字訊息都視為放棄。
4. **稽核**：每次決定輸出 `relaxation_decision` 日誌，內容為 ID、合格人數前後與輪次，不含個資。

## 5. 8 大架構審查維度評估
詳見 [Spec-0022 §2](../specs/0022-recruitment-relaxation-human-in-the-loop-spec.md#2-gate-18-大架構維度前審)。

## 6. 後果
* **正面**：
  * 用人決策有明確的人工審核點，且有稽核紀錄。
  * 放寬後 0 次抽取，回應快。
  * 可以多輪決定，次數有上限。
* **負面**：
  * API 合約與 UI 擴充。
  * 恢復時 `await_relaxation` 會重新執行，該節點在 interrupt 之前不得有副作用。
* **風險**：
  * 放寬只作用在已評估的候選池，池外可能還有因此合格的人。回覆的 `scope_note` 已揭露這一點，需要時使用者可以重送 JD。

## 7. 實作偏差與實施後評估
* **DV-1**：每次暫停時，LangSmith 追蹤樹會在 `await_relaxation` 節點顯示一筆 `GraphInterrupt`（控制流程訊號，只有類別名）。看錯誤率時需要排除。
* **QA D1（P2）修正**：操作提示原本用了「」，違反 Spec-0019「回覆中的「」只用於可回溯引文」的規則；已改寫並補上回歸測試。
* **Gate 2 P3 修正**：恢復前改用「目前設定 + Session」重算的選項來驗證，避免待決定期間關閉 HITL 時，恢復後沒有任何動作、回傳空回覆。
* **QA**：14/14 AC PASS，含 RedisSaver 跨實例恢復，以及並行決定時一個 200、一個 409 的實測。
