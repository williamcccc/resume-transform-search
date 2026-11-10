# Spec-0022：招募助手放寬條件之人工決策 (Human-in-the-Loop Constraint Relaxation)

* **狀態**：已實作（Gate 1 PASS → QA PASS → Gate 2 PASS，2026-11-10；使用者確認：決策只接受 UI 勾選）；偏差見 [QA-0022](../qa_reports/0022-recruitment-relaxation-hitl-qa.md) 與 ADR-0022 §7
* **關聯**：[ADR-0022](../adr/0022-recruitment-relaxation-human-in-the-loop.md)（決策紀錄）、[ADR-0021](../adr/0021-recruitment-adaptive-candidate-search-loop.md)（沿用其 `NodeUpdate.goto` 子步驟路由）、[ADR-0019](../adr/0019-recruitment-assistant-langgraph-chat.md)
* **前置**：情境 1（自動擴大檢索）已先排除「只是檢索範圍太窄」的情況；本規格處理擴大後仍不足時的**用人決策**。

---

## 1. PRD

### 1.1 背景與目標
* **現況**：合格人數 < K 時，[jd_finalize](../../src/application/recruitment_nodes.py) 產出放寬報告（每條必要條件單獨放寬後的合格人數），但只能「看」不能「做」：使用者回覆「放寬 R2」時，系統沒有對應的動作，訊息會被當成一般問答或新的 JD。
* **目標**：用 LangGraph `interrupt()` 讓流程**暫停在放寬決策點**，由使用者選擇要放寬的條件（可複選），恢復後**以程式在已評估的候選池上重新比對與排序**（0 次抽取 LLM），並把決定記錄成稽核紀錄。仍不足時可以再決定一次（人工審核循環），次數有上限。
* **原則**：放寬哪一條由人決定，系統只提供數據（放寬後人數、瓶頸建議），不自動代為選擇。

### 1.2 範疇
* **In-Scope**
  1. 圖拓撲：`compose` 之後新增條件邊 → `await_relaxation`（Infrastructure，呼叫 `interrupt()`）→ 恢復後 → `apply_relaxation`（Application）→ `compose` →（必要時再次 `await_relaxation`）。
  2. 決策輸入只有一種管道：UI 勾選，送出 API 結構化欄位 `relax_requirement_ids`（Gate 1 決定：不支援文字指令）。
  3. 放寬語意：把所選必要條件**降為加分條件**（ID 不變，`priority=NICE`），不刪除；仍計入加分排序並保留於名單的符合/不符欄位。至少保留 1 條必要條件。
  4. 重新比對：沿用 session 中的 `pool_evaluations` 逐條狀態（MET/UNMET/UNKNOWN 不變），只重算合格與否、排序與新的放寬報告；新進名單者的詞面證據改由讀取履歷全文產生（只讀磁碟，不呼叫 LLM）。推薦理由重新敘述 1 次（LLM，失敗時降級為模板）。
  5. 放棄語意：待決定時送出一般訊息（不是放寬指令）→ 視為放棄本次決定，照一般流程處理，待決定狀態清除。
  6. 多輪人工審核：放寬後仍不足時，可再提出一次（排除已放寬者），上限 `RECRUIT_RELAXATION_MAX_ROUNDS`；新的 JD 會重置已放寬紀錄。
  7. API：`POST /api/chat` 新增選填 `relax_requirement_ids`；回應與 `GET /api/chat/{sid}` 新增 `pending_decision`、`relaxed_requirement_ids`；`intents` 新增 `RELAX_CONSTRAINTS`。
  8. UI：條件瓶頸面板在待決定時顯示勾選框與「放寬並重新比對」按鈕。
  9. 稽核：`relaxation_decision` 日誌（trace_id、session_hash、放寬的 ID、合格人數前後、輪次），零個資。
  10. 設定：`RECRUIT_RELAXATION_HITL_ENABLED`、`RECRUIT_RELAXATION_MAX_ROUNDS`。
* **Out-of-Scope**
  1. 放寬後再自動擴大檢索（只在已評估的候選池內重新比對；需要時使用者可貼新 JD）。
  2. 修改條件門檻（例如「5 年改 3 年」）或把「履歷未提及」視為通過（另案）。
  3. 以文字下達放寬決定（不論是「放寬 R2」這類固定格式，或「年資不要那麼嚴」這類自由文字）；待決定時輸入文字一律視為一般訊息（放棄）。
  4. 復原已放寬的條件（重送 JD 即可）。

### 1.3 API 合約
**請求** `POST /api/chat`
| 欄位 | 型別 | 必填 | 說明 |
| :--- | :---: | :---: | :--- |
| `message` | str | 有 `relax_requirement_ids` 時選填 | 留空時由伺服器產生「放寬 R2、R3」作為歷史紀錄 |
| `relax_requirement_ids` | List[str] | 否 | 每項需符合 `^R\d{1,3}$`，最多 12 項；只在有待決定時有效 |

**回應新增欄位**
| 欄位 | 型別 | 說明 |
| :--- | :---: | :--- |
| `pending_decision` | object \| null | `{kind:"RELAXATION", round, max_rounds, requested_k, baseline_qualified, max_select, options:[{requirement_id, label, qualified_if_relaxed, delta, unknown_count, recommended}]}` |
| `relaxed_requirement_ids` | List[str] | 本 JD 已放寬的條件 |

**錯誤**：`422 INVALID_RELAXATION_DECISION`（ID 不在選項中、重複、為空、放寬後沒有必要條件）；`422 NO_PENDING_DECISION`（目前沒有待決定卻送出 `relax_requirement_ids`）。錯誤時狀態不變，待決定狀態保留。

### 1.4 設定合約（同步 `.env.example`）
| 環境變數 | 型別 | 預設 | 範圍 | 說明 |
| :--- | :---: | :---: | :--- | :--- |
| `RECRUIT_RELAXATION_HITL_ENABLED` | bool | `true` | - | 關閉時只顯示放寬報告（與現行相同） |
| `RECRUIT_RELAXATION_MAX_ROUNDS` | int | `2` | [1, 5] | 同一 JD 最多人工放寬幾次 |

### 1.5 驗收標準 (AC)
* **AC-1 提出決策**：合格 < K、HITL 開啟、必要條件 ≥ 2 時，回應含 `pending_decision`（選項依放寬報告順序，瓶頸條件 `recommended=true`，`max_select = 必要條件數 − 1`），圖停在 `await_relaxation`。回覆最後附一行提示，請使用者在右側勾選條件。
* **AC-2 結構化恢復**：送出 `relax_requirement_ids=["R2"]` 後，`intents=["RELAX_CONSTRAINTS"]`；R2 變為加分條件；`shortlist` 與 `relaxation` 等於以純函式對 `pool_evaluations` 重算的結果；Profile 抽取 0 次、LLM 呼叫 ≤ 1（敘述）；回覆含「已依您的決定放寬」摘要與合格人數前後；`relaxed_requirement_ids=["R2"]`。
* **AC-3 文字不會觸發放寬**：待決定時送出文字「放寬 R2」，依 AC-5 視為一般訊息（放棄），條件不會被放寬。
* **AC-4 驗證**：ID 不在選項中、重複、為空、全部放寬時回 `422 INVALID_RELAXATION_DECISION`，訊息列出合法選項；沒有待決定卻送出 ID 時回 `422 NO_PENDING_DECISION`。錯誤後 checkpoint 不變，仍可再送出合法決定。
* **AC-5 放棄**：待決定時送出一般訊息（例如「第 1 位有帶過人嗎？」），照一般流程處理，`pending_decision=null`，條件未被放寬。
* **AC-6 多輪**：放寬後仍不足時再提出決定（`round=2`，選項排除已放寬的條件）；達 `MAX_ROUNDS` 後不再提出。
* **AC-7 重置**：新的 JD 會重置 `relaxed_requirement_ids` 與輪次。
* **AC-8 不提出的情況**：合格人數足夠、必要條件 < 2、HITL 關閉時，不提出決定；HITL 關閉時回覆與現行逐字相同。
* **AC-9 持久化**：使用 Redis checkpointer 時，待決定狀態可以跨 App 實例恢復。
* **AC-10 併發**：同一 Session 同時送出兩個決定時，一個成功、一個回 409，不會重複放寬。
* **AC-11 稽核與零個資**：`relaxation_decision` 日誌含放寬 ID、合格人數前後與輪次，不含姓名；`interrupt` payload 只含條件 ID、標籤和數字，不含候選人姓名與履歷內容。
* **AC-12 查詢與 UI**：`GET /api/chat/{sid}` 回傳 `pending_decision` 與 `relaxed_requirement_ids`；UI 在待決定時顯示勾選框與按鈕，頁面重整後可還原。
* **AC-13 後續追問一致**：放寬後的追問與面試題使用放寬後的條件（被放寬的條件顯示為加分條件）。
* **AC-14 設定與回歸**：2 個變數記載於 `.env.example` 並夾回範圍；全量 unittest、既有 E2E 通過；CLI 不受影響。

---

## 2. Gate 1：8 大架構維度前審

| # | 維度 | 評估 | 結論 |
| :---: | :--- | :--- | :--- |
| 1 | PII | interrupt payload 由 session 中的放寬報告產生，只含條件 ID、JD 條件標籤和人數，寫入 checkpoint 也不含個資。稽核日誌只有 ID 和數字。重新比對時讀取的履歷全文只存在單輪 `TurnContext`。 | PASS |
| 2 | 容量 | 決策狀態只是 checkpoint 中一個待執行任務與小型 payload（KB 以下）。待決定的 Session 受既有 TTL/LRU 管理，到期一併刪除。 | PASS |
| 3 | 非同步/演進 | `interrupt()` 只存在於 Infrastructure 節點；放寬規則（驗證、解析、套用）是 Domain 純函式，重新比對是 Application 節點，換編排框架時只需重寫暫停與恢復機制。`run_all` 遇到待決定時停止並回傳提示。 | PASS |
| 4 | 成本/熔斷 | 恢復時 Profile 抽取 0 次，只有 1 次敘述（可降級）。文字決定以正則解析，不經 LLM。 | PASS |
| 5 | 可抽換性 | `IChatOrchestrator` 擴充 `run_turn(..., relax_requirement_ids=None)` 與 `get_pending_decision()`，參數有預設值，向下相容。 | PASS |
| 6 | 惡意輸入 | 只接受 `^R\d{1,3}$` 且屬於當前選項的 ID；數量有上限；不解析文字指令。使用者無法藉由決定影響其他 Session 或繞過受保護屬性過濾（被放寬的只會是已通過守門的條件）。 | PASS |
| 7 | 索引演進 | 不涉及向量索引。checkpoint 格式由 LangGraph 管理。 | N/A |
| 8 | 併發/可觀測性 | 恢復也在 Session 鎖內執行，同時送出時回 409。LangGraph 恢復時會重新執行 `await_relaxation`，所以該節點在 `interrupt()` 之前不得有副作用（只做純計算）。`trace_id` 貫穿稽核日誌，追蹤樹可以看到暫停與恢復兩段。 | PASS |

**分流**：Deep Track，新增人工決策點、API 合約與圖拓撲變更，草擬 [ADR-0022](../adr/0022-recruitment-relaxation-human-in-the-loop.md)。
**可行性驗證（2026-11-10，LangGraph 1.2.20）**：
* 第一次 `invoke` 回傳 `__interrupt__`，`get_state().next == ('await_relaxation',)`，`tasks[].interrupts[].value` 可讀回 payload。
* `invoke(Command(resume=...), context=新的單輪 context)` 可以恢復，恢復時使用新的 runtime context；被中斷的節點**會從頭重新執行**。
* 在待決定的 thread 上送出新的一般輸入時，會從 START 重新執行並放棄先前的決定。

---

## 3. Tech Spec

### 3.1 變更矩陣
| 層 | 檔案 | 類型 | 職責 |
| :--- | :--- | :---: | :--- |
| Domain | `recruitment.py` | 修改 | `ChatIntent.RELAX_CONSTRAINTS`；`RelaxationOption`、`RelaxationPrompt`；`ChatSessionState.relaxed_requirement_ids`、`relaxation_rounds`；`ChatTurnOutcome.pending_decision` |
| Domain | `recruitment_services.py` | 修改 | `build_relaxation_prompt`、`validate_relaxation_decision`、`apply_requirement_relaxation`（純函式） |
| Domain | `recruitment_codec.py` | 修改 | 新欄位與 prompt 的序列化（舊資料缺欄位時預設值） |
| Domain | `exceptions.py` | 修改 | `RelaxationDecisionError(error_code)` |
| Domain | `interfaces.py` | 修改 | `IChatOrchestrator.run_turn(..., relax_requirement_ids=None)`、`get_pending_decision()` |
| Application | `recruitment_nodes.py` | 修改 | 共用 `_present_match`；`jd_finalize` 重置放寬紀錄；`apply_relaxation` 節點；`relaxation_prompt(state)`；`compose` 在本輪需要時回傳 `goto=await_relaxation` |
| Application | `recruitment_settings.py`、`dto.py`、`recruitment_chat_use_case.py` | 修改 | 設定；`ChatTurnCommand.relax_requirement_ids`、結果 DTO 新欄位；空訊息與決定的組合驗證；稽核日誌 |
| Infrastructure | `langgraph_recruitment_graph.py` | 修改 | `await_relaxation` 節點（`interrupt`）、compose 條件邊、`run_turn` 的恢復/放棄分流、`get_pending_decision` |
| Infrastructure | `config.py` | 修改 | 2 個設定 |
| Interfaces | `fastapi_server.py`、`server.py`、`static/dashboard.html` | 修改 | 請求/回應欄位、422 映射、設定映射、UI 勾選 |
| Tests | `tests/unit/test_recruitment_relaxation_hitl.py`、`tests/e2e/test_recruitment_relaxation_hitl_e2e.py` | 新增 | — |

### 3.2 Domain
```python
@dataclass(frozen=True)
class RelaxationOption:
    requirement_id: str; label: str; qualified_if_relaxed: int; delta: int; unknown_count: int; recommended: bool

@dataclass(frozen=True)
class RelaxationPrompt:
    round: int; max_rounds: int; requested_k: int; baseline_qualified: int; max_select: int
    options: Tuple[RelaxationOption, ...]

def build_relaxation_prompt(jd, report, rounds_used, max_rounds) -> Optional[RelaxationPrompt]:
    """report 為 None、rounds_used >= max_rounds、必要條件 < 2 時回傳 None；options 依 report.items 順序，
    recommended = requirement_id ∈ bottleneck_requirement_ids（無瓶頸時改用 strictest）"""

def validate_relaxation_decision(prompt, ids) -> Tuple[str, ...]:
    """空、重複、不在 options、數量 > max_select → raise RelaxationDecisionError("INVALID_RELAXATION_DECISION")"""

def apply_requirement_relaxation(jd, evals, ids) -> Tuple[JdRequirements, Tuple[CandidateEvaluation, ...]]:
    """所選 must 移到 nice（priority=NICE，ID 不變，依原順序附加在 nice 之後）；evals 的 must_ids/nice_ids 同步移動，statuses 不變"""
```
`ChatSessionState` 新增 `relaxed_requirement_ids: Tuple[str, ...] = ()`、`relaxation_rounds: int = 0`；codec 讀取舊資料時缺欄位用預設值。

### 3.3 Application
* **`relaxation_prompt(state)`**：HITL 關閉時回傳 None；否則 `build_relaxation_prompt(state.jd_requirements, state.relaxation, state.relaxation_rounds, max_rounds)`。
* **`jd_finalize`**：新 JD 時把 `relaxed_requirement_ids=()`、`relaxation_rounds=0`；排序/證據/渲染抽成 `_present_match(state, turn, jd, evals, candidates, match_texts, llm_texts, k, header_sections)` 與 `apply_relaxation` 共用。提示可用時設定 `turn.offer_relaxation=True`，並在放寬報告後附一行：「請在右側勾選要放寬的條件，按「放寬並重新比對」。」
* **`apply_relaxation(state, turn)`**：
  1. 讀取 `turn.relaxation_decision`（由編排器在恢復時填入）；以 `relaxation_prompt(state)` 重新驗證（第二道防線）。
  2. `apply_requirement_relaxation` 產生新的 JD 與評估結果。
  3. 對**排序後進入名單**的人選讀取履歷全文（`tools.load_resume_text` → `profiles.prepare_match_text`，不呼叫 LLM），以產生詞面證據和引文來源。
  4. 呼叫 `_present_match`：先放模板段落「### 已依您的決定放寬條件」（列出 ID、標籤，以及合格人數前後），再放名單、放寬報告和敘述。
  5. 更新 session：`jd_requirements`、`pool_evaluations`、`shortlist`、`relaxation`、`relaxed_requirement_ids += ids`、`relaxation_rounds += 1`。
  6. 寫入 `turn.relaxation_audit = (ids, before, after, round)`，由 Use Case 輸出稽核日誌。
  7. 提示仍可用時設定 `turn.offer_relaxation=True`。
* **`compose`**：結尾 `goto = NODE_AWAIT_RELAXATION if turn.offer_relaxation and relaxation_prompt(new_state) else None`。
* **`run_all`**：compose 回傳 goto 時停止，提示放在 `turn.pending_decision`。另提供 `resume_relaxation(state, turn, ids)`，依序執行 `apply_relaxation` 和 `compose`，作為等價的純 Python 實作。
* **Use Case**：
  * `relax_requirement_ids` 非空而 `message` 為空時，產生「放寬 R2、R3」。
  * 驗證 ID 格式與數量，不合法時拋 `RelaxationDecisionError`。
  * 呼叫 `run_turn(..., relax_requirement_ids)`；結果 DTO 帶出 `pending_decision`、`relaxed_requirement_ids`。
  * 有 `relaxation_audit` 時輸出 `relaxation_decision` 日誌。

### 3.4 Infrastructure：編排器
```python
def await_relaxation(state, runtime):            # 不呼叫 handlers.execute_node，interrupt 前不得有副作用
    session = session_from_dict(state["session"], ...)
    prompt = handlers.relaxation_prompt(session)
    if prompt is None:                             # 防禦：條件已不成立
        return {"goto": None}
    ids = interrupt(relaxation_prompt_to_dict(prompt))
    runtime.context.turn.relaxation_decision = tuple(ids)
    return {"goto": handlers.NODE_APPLY_RELAXATION}
```
* 邊的調整：
  * `compose` 改為條件邊，依 goto 前往 `await_relaxation` 或 END。
  * `await_relaxation` 依 goto 前往 `apply_relaxation` 或 END。
  * `apply_relaxation` 依 goto 前往 compose（Application 回傳 `goto=compose`）。
  * `SUBSTEP_NODES` 加入 `apply_relaxation`、`compose`。由於 compose 是固定的收尾節點，next_step 遇到 `goto=compose` 時直接放行。
* **`run_turn(session_id, message, trace_id, relax_requirement_ids=None)`**：在 Session 鎖內先讀取 `get_pending_decision`，再分流：
  * 有待決定，且有結構化 ID → 用 `validate_relaxation_decision` 驗證（錯誤時往外拋，checkpoint 不變），然後 `invoke(Command(resume=list(ids)), context=新的 turn)`；`turn.intents=[RELAX_CONSTRAINTS]`。
  * 有待決定但沒有結構化 ID → 照一般方式 invoke，從 START 開始，放棄待決定狀態。
  * 沒有待決定卻有結構化 ID → 拋 `RelaxationDecisionError("NO_PENDING_DECISION")`。
* **結果**：`ChatTurnOutcome.pending_decision` 取自 invoke 結果的 `__interrupt__`（或在 invoke 後呼叫 `get_pending_decision`）。
* **`get_pending_decision(session_id)`**：從 `get_state().tasks[*].interrupts[*].value` 反序列化。

### 3.5 Interfaces
* `ChatRequestBody.relax_requirement_ids: Optional[List[str]]`；`map_chat_exception` 新增 `RelaxationDecisionError → 422`。
* 回應和 GET 加上 `pending_decision`、`relaxed_requirement_ids`。
* `dashboard.html`：
  * `renderChatRelaxation(rep, pending, relaxed)`：有待決定時，每個選項顯示一個 checkbox（推薦的選項加註），並提供「放寬並重新比對」按鈕，送出 `{session_id, relax_requirement_ids}`；已放寬的條件顯示為標籤。
  * `restoreChatSession` 一併還原。

### 3.6 單元測試計畫（`tests/unit/test_recruitment_relaxation_hitl.py`）
1. **Domain**：
   * `build_relaxation_prompt`：None 的各種情況、`recommended` 的判定、`max_select`。
   * `validate_relaxation_decision`：5 種錯誤。
   * `apply_requirement_relaxation`：ID 與 statuses 不變，`fully_qualified` 重算正確。
   * codec：舊資料可以讀取。
2. **Application**：
   * `apply_relaxation` 結果等於純函式重算的結果，抽取次數 0。
   * 摘要中的合格人數前後正確。
   * 第二輪的選項排除已放寬的條件；達上限後不再提出。
   * 新 JD 時重置放寬紀錄。
   * HITL 關閉時回覆與現行逐字相同。
   * 敘述失敗時降級為模板。
   * 讀取履歷失敗時降級（不拋例外）。
3. **編排器**（InMemorySaver）：
   * 提出決定後 `next==('await_relaxation',)`。
   * 結構化恢復；待決定時送出文字「放寬 R2」視為放棄。
   * ID 不合法時拋例外且 checkpoint 不變。
   * 放棄待決定。
   * `NO_PENDING_DECISION`。
   * 恢復時使用新的 turn context。
   * payload 不含姓名。
   * `await_relaxation` 重新執行時沒有副作用。
4. **Use Case / API**：空訊息加 ID；ID 格式與數量；422 映射；GET 回傳的欄位。
5. **設定**：預設值、夾回範圍、`.env.example`。

### 3.7 QA 驗收矩陣（Step 4，`tests/e2e/test_recruitment_relaxation_hitl_e2e.py`）
| TC | AC | 情境 | 方法 |
| :--- | :--- | :--- | :--- |
| TC-1 | AC-1, AC-2 | 提出決定，勾選 R2 後恢復 | FastAPI + LangGraph + Fake；手算重新排序的期望值 |
| TC-2 | AC-3 | 文字「放寬 R2」不觸發 | 條件未放寬、待決定清除 |
| TC-3 | AC-4 | 不合法的決定與 NO_PENDING | 422 之後仍可送出合法決定 |
| TC-4 | AC-5 | 放棄 | 待決定時改為追問 |
| TC-5 | AC-6, AC-7 | 多輪與重置 | 兩次放寬直到上限，接著送新 JD |
| TC-6 | AC-8 | 不提出的情況 | 停用時與現行逐字比對 |
| TC-7 | AC-9 | Redis checkpointer 跨實例恢復 | 實例 A 提出決定，實例 B 恢復（Redis 無法連線則 skip） |
| TC-8 | AC-10 | 併發恢復 | 兩個執行緒同時送出決定：一個 200、一個 409；放寬次數為 1 |
| TC-9 | AC-11 | 稽核與 checkpoint 零個資 | assertLogs；序列化 checkpoint 後檢查植入的標記 |
| TC-10 | AC-12 | GET 還原與 UI | GET 欄位；以靜態檢查確認 dashboard 含勾選渲染與送出邏輯 |
| TC-11 | AC-13 | 放寬後產生面試題 | 面試題的條件來源為放寬後的 JD |
| TC-12 | AC-14 | 回歸 | 全量 unittest 與既有 e2e |
