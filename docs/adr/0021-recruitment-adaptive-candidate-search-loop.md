# ADR-0021：招募助手候選人不足時自動擴大檢索（LangGraph 子步驟循環）

## 1. 狀態
已採納 (Accepted)

* **日期**：2026-11-10（提案）／2026-11-10（採納，Gate 2 PASS）
* **規格與驗收**：[Spec 0021](../specs/0021-recruitment-adaptive-candidate-search-spec.md)、[QA Report 0021](../qa_reports/0021-recruitment-adaptive-candidate-search-qa.md)
* **關聯**：[ADR-0019](./0019-recruitment-assistant-langgraph-chat.md)（擴充其 jd_match 流程與圖拓撲）、[ADR-0020](./0020-recruitment-chat-langsmith-masked-tracing.md)
* **標籤**：`LangGraph`, `Cycle`, `Adaptive Retrieval`, `Deterministic Policy`

## 2. 背景與問題陳述
ADR-0019 的 jd_match 只檢索一次語意候選池 Top-N。合格人數不足時，系統直接產出放寬報告，請使用者檢討招募條件。但人數不足也可能只是檢索範圍太窄：條件完全符合的人，可能因為履歷寫法和 JD 語意不夠接近而落在池外（Spec-0019 風險 R3）。在這種情況下就要求使用者做用人決策，順序是錯的。

## 3. 評估選項
* **A：Application 內以 `for` 迴圈擴大**：改動最小，但迴圈對追蹤樹和編排器不可見，也無法作為之後人工審核節點（情境 2）的基礎。
* **B：LangGraph 子步驟循環，策略放在 Domain 純函式**：把 jd_match 拆成「準備 → 檢索輪（自循環）→ 收尾」。由 Application 回傳 `goto` 宣告下一步，編排器只負責轉送。
* **C：迴圈資料放進 graph state，由條件邊函式決策**：LangGraph 慣用寫法，但會把履歷文字寫進 checkpoint（違反零個資），業務決策也會落到 Infrastructure 層。
* **D：由 LLM 改寫檢索詞的 ReAct 迴圈**：Token 成本高、有幻覺風險，改寫後的語意分數也無法和原查詢比較。

## 4. 架構決策
採納 **B**：
1. **策略**：Domain 新增 `SearchExpansionPolicy`，完全確定性。擴大方式為加大池子；飽和時降低相似度門檻；終止條件包括人數足夠、輪數上限、人數上限、門檻下限、預算保留和時間保留。
2. **路由**：Application 以 `NodeUpdate.goto` 宣告子步驟。LangGraph 依 `goto` 條件邊形成 `jd_search_round` 自循環，`run_all` 為等價的純 Python 實作。
3. **資料**：中間資料只放在單輪暫態 `TurnContext`。graph state 只新增 `goto` 節點名稱，checkpoint 不含任何履歷內容。
4. **邊界**：自動化只擴大檢索範圍，不放寬任何招募條件；放寬招募條件仍交給人決定（情境 2，另立 ADR）。

## 5. 8 大架構審查維度評估
詳見 [Spec-0021 §2](../specs/0021-recruitment-adaptive-candidate-search-spec.md#2-gate-18-大架構維度前審)。核心是維度 1（中間資料不進 checkpoint）和維度 4（只對新進者抽取，並保留預算給後續步驟）。

## 6. 後果
* **正面**：
  * 減少「其實只是檢索範圍太窄」的誤報瓶頸。
  * 迴圈在 LangSmith 追蹤樹中，每一輪是一個節點。
  * `goto` 機制可以直接沿用到情境 2 的 `interrupt()`。
* **負面**：
  * 擴大時延遲和 Token 都會增加（以輪數、人數和預算上限約束）。
  * 降低門檻會納入語意較遠的人選，不過合格與否仍由確定性比對判斷，不影響精確度。
* **風險**：
  * 冷快取時預算可能限制擴大幅度。已以保留額度確保推薦理由不會降級，需要時可調整 `MAX_LLM_CALLS_PER_TURN`。
  * 單輪中途當掉時無法從 checkpoint 恢復到該輪中間。

## 7. 實作偏差與實施後評估
* **DV-1**：API `usage` 以 `asdict(TurnUsage)` 產生，所以會自動多出 `search_rounds`、`search_stop_reason`、`pool_evaluated` 3 個欄位。只新增欄位、向下相容。
* **DV-2**：每一輪擴大會多 1 次查詢 embedding（每輪最多 `MAX_ROUNDS` 次，每次只有幾個 Token）。查詢向量的記憶化列為後續改善項。
* **DV-3**：`recursion_limit` 由 `handlers.max_substeps_per_intent` 推導，不另外傳參數給 orchestrator。
* **Gate 2 P2 修正**：「session 未變更不輸出通道」的判斷由物件身分改為比較序列化內容，避免節點就地修改 session 時變更遺失（已補回歸測試）。
* **QA**：14/14 AC PASS，其中含真實 RediSearch 灰箱實測：基準門檻以外的合格者，在第 2 輪門檻降到 0.45 時被召回。
