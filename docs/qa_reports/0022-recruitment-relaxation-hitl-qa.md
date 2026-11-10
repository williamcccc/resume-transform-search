# QA-0022：招募助手放寬條件之人工決策：QA 實測驗收報告

* **規格**：[Spec-0022](../specs/0022-recruitment-relaxation-human-in-the-loop-spec.md)，**決策**：[ADR-0022](../adr/0022-recruitment-relaxation-human-in-the-loop.md)
* **日期**：2026-11-10
* **結論**：**PASS**。14/14 AC 已覆蓋；回歸測試發現 2 項問題，Step 6 第 1 輪修正後全部通過。

## 1. 測試環境與方法
* Python 3.13 / Windows 11；LangGraph 1.2.20（`interrupt` / `Command(resume)`）；Redis 8（RedisSaver，Session ID 帶 `qa0022` 標記，測試後清除）。
* 灰箱實測檔：[test_recruitment_relaxation_hitl_e2e.py](../../tests/e2e/test_recruitment_relaxation_hitl_e2e.py)
  * **FAKE 軌**：真實 FastAPI、真實 LangGraph、真實節點與 Profile 服務，搭配 Fake 檢索與 LLM。情境 1 的自動擴大檢索維持預設開啟，用來驗證「先自動擴大 → 仍不足 → 交給人決定」的整合流程。
  * **REDIS 軌**：在 App 實例 A 提出待決定，在全新的實例 B 恢復。
* 所有樣本都是虛構資料，不讀取 `data/`、`resume/`。

## 2. 需求追溯矩陣 (RTM)
| TC | AC | 情境 | 結果 |
| :--- | :--- | :--- | :---: |
| TC-1 | AC-1, AC-2 | 自動擴大 2 輪後仍不足，暫停並提出 R1~R3（`max_select=2`，有推薦項）；勾選 R3 後，名單與純函式重算結果一致；Profile 抽取 0 次，LLM 呼叫 ≤ 1；合格人數 1 → 2；`scope_note` 同時保留「已自動擴大檢索 2 輪」和「已人工放寬 R3」 | PASS |
| TC-2 | AC-3 | 待決定時輸入文字「放寬 R3」：當成一般訊息處理，條件沒有放寬，待決定狀態清除 | PASS |
| TC-3 | AC-4 | `R9`、全部放寬、重複、`<script>`、空陣列都回 422 `INVALID_RELAXATION_DECISION`，回應不含 Traceback；之後仍待決定，`turn_count` 不變，送出合法決定可以成功；沒有待決定時回 422 `NO_PENDING_DECISION` | PASS |
| TC-4 | AC-5 | 待決定時改問追問：照追問流程處理，待決定清除；之後再送出決定回 `NO_PENDING_DECISION` | PASS |
| TC-5 | AC-6, AC-7 | 第 2 次只剩 R1、R2 可選（`max_select=1`）；達上限 2 次後不再提出；送新 JD 後放寬紀錄重置 | PASS |
| TC-6 | AC-8 | HITL 關閉時沒有待決定；兩種模式的回覆只差一行操作提示，名單相同 | PASS |
| TC-7 | AC-9 | **真實 RedisSaver**：實例 A 提出待決定，實例 B 用 GET 還原同一份 payload 並恢復成功；抽取 0 次，接著提出第 2 次決定 | PASS |
| TC-8 | AC-10 | 兩個執行緒同時送出決定：一個 200、一個 409；只放寬 1 次，`turn_count=2` | PASS |
| TC-9 | AC-11 | `relaxation_decision round=1 relaxed=R3 qualified_before=1 qualified_after=2`；日誌和 interrupt payload 都不含姓名、Email、candidate_id 或原始 session_id | PASS |
| TC-10 | AC-12 | GET 回傳的 `pending_decision` 與 POST 相同；頁面含勾選表單、送出邏輯，且 422 時只在 `SESSION_TURN_LIMIT` 才清除 Session | PASS |
| TC-11 | AC-13 | 放寬後產生面試題：題目對應的條件都屬於放寬後的條件集合；必要條件只剩 R1、R2 | PASS |
| TC-12 | AC-14 | 單元測試 500/500 OK（新增 29 個，含 Gate 2 回歸測試）；招募助手全部 E2E 61/61 OK（含 LIVE 真實 Gemini 軌，以及情境 1、追蹤） | PASS（修正後） |

## 3. 缺陷與修正（Step 6 第 1 輪）
| ID | 嚴重度 | 現象 | 根因 | 修正 |
| :---: | :---: | :--- | :--- | :--- |
| D1 | P2 | LIVE 軌 AC-08 失敗：回覆中的「條件瓶頸」無法回溯到原文 | 操作提示使用了「」，違反 Spec-0019「回覆中的「」只能用於可逐字回溯的引文」這項既有規則 | 操作提示改成不使用「」；新增單元測試防止再犯 |
| D2 | P3 | 追蹤 E2E TC-5：錯誤清單出現 `GraphInterrupt` | 圖暫停時，LangGraph 會把 `await_relaxation` 節點的 run 標記為 `GraphInterrupt`。這是控制流程訊號，內容也只有類別名，不是外洩 | 測試改成：只允許 `await_relaxation` 帶 `GraphInterrupt`，其他錯誤的脫敏檢查照舊。列為 **DV-1** |

**Gate 2 補充修正（P3）**：待決定期間如果關閉 HITL（例如重啟後設定變更），原本恢復會通過舊 payload 的驗證，但 `await_relaxation` 重算後沒有可用選項，結果是無動作的空回覆。現在恢復前改用「目前設定 + Session」重算的選項驗證，這種情況會回 `NO_PENDING_DECISION`，並已補上單元測試。

## 4. 規格偏差
* **DV-1**：LangSmith 追蹤樹中，每次暫停都會在 `await_relaxation` 節點顯示一筆 `GraphInterrupt` 錯誤。在 LangSmith 看錯誤率時，要排除這類 run。

## 5. 對抗與邊界補充
* **重新執行的副作用**：恢復時 `await_relaxation` 會從頭執行。該節點在 `interrupt()` 之前只呼叫純函式 `relaxation_prompt`；恢復結果的 `node_ms` 不含 `route`，證明使用的是新一輪的 context。
* **第二道驗證**：`apply_relaxation` 會再驗證一次決定（單元測試：直接呼叫時用不合法的 ID 會拋例外）。
* **分類器隔離**：即使 LLM 分類器輸出 `RELAX_CONSTRAINTS`，也會被過濾成 GENERAL_QA，不會繞過人工決策點。

## 6. 殘餘風險
* 放寬只在已評估的候選池內重新比對，池外可能還有因放寬而合格的人；`scope_note` 已揭露這點。
* 尚未用真實 Gemini 跑完整的放寬流程，只有 FAKE 和 Redis 軌。決策點本身不呼叫 LLM，恢復時只有 1 次敘述，與既有 LIVE 軌使用相同的敘述路徑。
