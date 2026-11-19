# ADR-XXXX: [架構決策簡明標題]

## 1. 決策狀態
* **狀態**：[提案中 (Proposed) | 已採納 (Accepted) | 已廢止 (Deprecated) | 被取代 (Superseded by ADR-YYYY)]
* **日期**：YYYY-MM-DD
* **決策負責人**：[AI Assistant / Development Team]
* **標籤**：`Tag1`, `Tag2`, `Tag3`

---

## 2. 背景與問題陳述 (Context & Problem Statement)
* **背景脈絡**：描述系統目前面臨的技術挑戰、業務需求演進或瓶頸。
* **觸發原因**：為什麼既有設計無法滿足需求？（例如：高併發競態危害、記憶體瓶頸、外部 API 配額限制）。

---

## 3. 評估之架構選項 (Options Evaluated)

### 選項 A: [方案名稱]
* **優點**：
  - 優點 1
  - 優點 2
* **缺點 / 代價**：
  - 缺點 1

### 選項 B: [方案名稱]
* **優點**：
  - 優點 1
  - 優點 2
* **缺點 / 代價**：
  - 缺點 1

---

## 4. 最終決策結果 (Decision Outcome)
* **選定方案**：選用 [選項 X]，因為其在 [核心考量維度] 表現最佳。
* **正面衝擊**：
  - 帶來的主要效益與效能提升。
* **負面衝擊與緩解措施**：
  - 需承擔的技術代價與對應之防禦措施。

---

## 5. 8 大架構審查維度評估 (8-Dimension Architecture Review)

逐項對照 8 大架構維度的唯一正本 `.agents/skills/feature-design/references/arch_review_checklist.md`，每個維度寫出評估結論：

| # | 維度 | 評估結論 |
| :---: | :--- | :--- |
| 1 | 個資隱私 (PII) | |
| 2 | 容量與極限 (Capacity) | |
| 3 | 非同步與演進 (Async / Evolution) | |
| 4 | Token 能效與成本熔斷 (Token Economics & Cost) | |
| 5 | 可抽換性 (Portability & Decoupling) | |
| 6 | 惡意輸入與配額硬上限 (Input Security) | |
| 7 | 向量索引演進遷移 (Index Evolution) | |
| 8 | 分散式併發與可觀測性 (Concurrency & Traceability) | |
