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

1. **個資隱私 (PII & Data Privacy)**：
   - 履歷機敏資料（身分證字號、手機號碼、通訊地址等）之傳輸、儲存、快取與日誌是否具備嚴密脫敏機制？
2. **容量與極限 (Capacity & Limits)**：
   - 評估 Redis 記憶體足跡、向量切片上限、大量檔案批次處理時的資源佔用與極限邊界。
3. **非同步與演進 (Async & Evolution)**：
   - Use Case 是否保持無狀態（Stateless）？是否利於未來無縫遷移至非同步任務隊列（如 Celery/Redis Stream）？
4. **成本與熔斷 (Cost & Circuit Breaker)**：
   - 外部付費 API（如 Gemini LLM / Embedding）的呼叫預算控制、Token 消耗硬上限與 429 配額用罄時的平滑降級與熔斷防禦。
5. **無損與容錯性 (Fail-Safe & Lossless Integrity)**：
   - 磁碟原始檔案是否保證無損？外部網路斷線或資料庫重開機時，系統是否能自動恢復與優雅降級？
6. **可稽核性 (Auditability & Observability)**：
   - 轉檔評分、關鍵異常、品管裁定是否具備完整審計日誌與 Trace ID 關聯？
7. **向下相容性 (Backward Compatibility)**：
   - 根目錄 CLI 入口指令與各項參數是否 100% 維持相容？舊有切片或格式是否能平滑遷移？
8. **安全性與注入防護 (Security & Jailbreak Defense)**：
   - Prompt 是否具備 `<resume_content>` 等上下文標籤隔離，防範候選人惡意 Prompt 注入攻擊？是否防禦 Zip Bomb 與超大惡意畸形檔案？
