# Spec-0021：招募助手候選人不足時自動擴大檢索 (Adaptive Candidate Search Loop)

* **狀態**：已實作（Gate 1 PASS → QA PASS → Gate 2 PASS，2026-11-10）；實作偏差見 §4 與 [QA-0021](../qa_reports/0021-recruitment-adaptive-candidate-search-qa.md)
* **關聯**：[ADR-0021](../adr/0021-recruitment-adaptive-candidate-search-loop.md)（本規格之決策紀錄）、[ADR-0019](../adr/0019-recruitment-assistant-langgraph-chat.md)（招募助手）、[ADR-0020](../adr/0020-recruitment-chat-langsmith-masked-tracing.md)（遮蔽式追蹤）
* **後續**：情境 2（放寬條件之人工決策，`interrupt()`）另立規格，沿用本規格之 `NodeUpdate.goto` 子步驟路由機制。

---

## 1. PRD

### 1.1 背景與目標
* **現況**：[`jd_match`](../../src/application/recruitment_nodes.py) 只檢索一次候選池（Top-N，`RECRUIT_CANDIDATE_POOL_SIZE=15`、相似度門檻 `RECRUIT_RETRIEVAL_MIN_SCORE=0.5`）。完全符合必要條件的人數少於需求 K 時，會直接產出放寬報告 `RelaxationReport`，請使用者考慮放寬招募條件。
* **痛點**：條件完全符合、但履歷寫法與 JD 語意不夠接近的人，可能落在 Top-N 之外（Spec-0019 風險 R3 / P3-PREFILTER）。這時候選人不足的原因其實是**檢索範圍太窄**，不是招募條件太嚴，系統卻直接要求使用者做用人決策。
* **目標**：符合人數不足時，系統先**自動擴大檢索範圍**（加大候選池、相似度門檻不夠時逐步降低），用程式重新比對，直到人數足夠或觸及停止條件；之後才產出放寬報告。
  * 擴大檢索範圍屬於技術問題，可以自動處理。
  * 放寬招募條件屬於用人決策，仍然交給人（情境 2）。
* **實作形式**：以 LangGraph 條件邊構成循環（`jd_search_round` 指回自己），每一輪在追蹤樹上是一個獨立節點。

### 1.2 範疇
* **In-Scope**
  1. 把 `jd_match` 拆成三個子步驟節點：`jd_match`（準備）→ `jd_search_round`（可循環）→ `jd_finalize`（收尾）。
  2. Domain 新增純函式擴大策略 `SearchExpansionPolicy`，負責決定下一輪參數或停止原因，可完全確定性測試。
  3. 擴大手段：
     * 加大候選池目標人數（每輪 `+POOL_STEP`，總數上限 `POOL_MAX`），檢索切片數 `top_k_chunks` 等比例放大（上限 `TOP_K_CHUNKS_MAX`）。
     * 上一輪回傳人數少於目標（飽和）時，相似度門檻降低 `MIN_SCORE_STEP`，最低到 `MIN_SCORE_FLOOR`。
  4. 只對**新進**候選人抽取 Profile 和比對；已評估過的人不重算，有快取的人 0 Token。
  5. 停止條件：人數已足夠、達最大輪數、達總人數上限、到達門檻下限仍飽和、LLM 預算只剩保留額度、剩餘時間不足。
  6. 回覆揭露：發生擴大時，加上模板段落「檢索擴大紀錄」（每輪門檻、目標人數、新增人數、累計合格人數和停止原因）。放寬報告的 `scope_note` 註明擴大輪數。
  7. 可觀測性：`chat_turn` 日誌新增 `search_rounds`、`search_stop_reason`、`pool_evaluated` 三個欄位。
  8. 8 個新設定全部經 `AppConfig` 和 `.env.example` 注入。`MAX_ROUNDS=0` 時行為與現行版本完全相同。
* **Out-of-Scope**
  1. 由 LLM 改寫檢索詞（會增加 Token 成本和幻覺風險）。改寫後語意分數也無法和原查詢比較，影響排序。
  2. 自動放寬招募條件（屬於用人決策，留給情境 2 由人透過 `interrupt()` 決定）。
  3. 結構化欄位預過濾與全庫召回（P3-PREFILTER）。
  4. Web API 回應新增欄位（擴大資訊只放在回覆 Markdown 和日誌中）、前端 UI 變更。
  5. 修改敘述 Prompt（`MatchNarrationFacts` 結構不變，不影響 Prompt 版本和快取）。

### 1.3 設定合約（全部同步至 `.env.example`）
| 環境變數 | 型別 | 預設 | 合法範圍（超出時夾回） | 說明 |
| :--- | :---: | :---: | :--- | :--- |
| `RECRUIT_SEARCH_EXPANSION_MAX_ROUNDS` | int | `2` | [0, 5] | 基準輪之後最多擴大幾輪；設為 0 表示停用 |
| `RECRUIT_SEARCH_EXPANSION_POOL_STEP` | int | `10` | [1, 50] | 每輪增加的候選池目標人數 |
| `RECRUIT_SEARCH_EXPANSION_POOL_MAX` | int | `40` | [`CANDIDATE_POOL_SIZE`, 100] | 單輪對話累計評估人數的硬上限 |
| `RECRUIT_SEARCH_EXPANSION_TOP_K_CHUNKS_MAX` | int | `200` | [`RETRIEVAL_TOP_K_CHUNKS`, 1000] | 檢索切片數上限 |
| `RECRUIT_SEARCH_EXPANSION_MIN_SCORE_STEP` | float | `0.05` | (0, 0.5] | 飽和時門檻降低的幅度 |
| `RECRUIT_SEARCH_EXPANSION_MIN_SCORE_FLOOR` | float | `0.4` | [0, `RETRIEVAL_MIN_SCORE`] | 門檻下限 |
| `RECRUIT_SEARCH_EXPANSION_LLM_RESERVE` | int | `2` | [0, 10] | 保留給敘述等後續步驟的 LLM 呼叫次數 |
| `RECRUIT_SEARCH_EXPANSION_MIN_REMAINING_SECONDS` | float | `30` | [0, `TURN_TIMEOUT`] | 剩餘時間低於此值時不再開始新一輪 |

> 預算說明：預設 `MAX_LLM_CALLS_PER_TURN=25`。冷快取時，基準輪約用掉 17 次（分類 0~1、JD 1、Profile 15），擴大輪最多還能新增約 6 人的抽取。快取命中不占預算，所以熱快取時可擴大的人數較多。

### 1.4 驗收標準 (AC)
* **AC-1 基準已足夠時零變更**：基準輪合格人數 ≥ K 時不擴大，只檢索 1 次。`reply_markdown` 與 `MAX_ROUNDS=0` 的結果逐字相同，`search_rounds=0`，`search_stop_reason=SATISFIED`。
* **AC-2 擴大成功**：基準輪合格人數 < K，第 1 輪擴大後新增的合格者使累計人數 ≥ K 時，停止原因為 `SATISFIED`。`shortlist` 含新增的合格者，`relaxation=None`，回覆含「檢索擴大紀錄」，且數字與實際每輪紀錄一致。
* **AC-3 飽和時降低門檻**：上一輪回傳人數少於目標時，下一輪的 `min_score` = max(前一輪 − STEP, FLOOR)。已在下限仍飽和時，停止原因為 `EXHAUSTED`。`min_score` 在任何情況下都不低於 FLOOR。
* **AC-4 最大輪數**：基準輪之後的檢索次數 ≤ `MAX_ROUNDS`，用盡時停止原因為 `MAX_ROUNDS`。之後照常產出放寬報告，其中 `pool_size` 為累計評估人數，`scope_note` 註明擴大輪數。
* **AC-5 人數上限**：累計評估人數 ≤ `POOL_MAX`，到達上限時停止原因為 `POOL_CAP`。
* **AC-6 預算保留**：剩餘預算 ≤ `LLM_RESERVE` 時不開始新一輪，停止原因為 `BUDGET`。擴大輪的抽取不會用掉保留額度：冷快取時推薦理由仍由 LLM 產生，不降級為模板。超出預算的新人選改用降級資料並發出警告（沿用現行行為）。
* **AC-7 時間保留**：剩餘秒數 < `MIN_REMAINING_SECONDS` 時，不開始新一輪，停止原因為 `DEADLINE`，本輪正常回覆，不拋出 `TurnTimeoutError`。
* **AC-8 不重複計算**：已評估的人不重新抽取或比對。每輪只對新進者呼叫 Profile 抽取，快取命中為 0 Token。`shortlist` 中同一 `candidate_id` 不重複。
* **AC-9 停用時完全相容**：`MAX_ROUNDS=0` 時，所有既有單元測試與 E2E 的斷言不需修改即可通過。
* **AC-10 圖拓撲與等價性**：編譯後的圖含 `jd_search_round → jd_search_round` 自循環邊，以及 `jd_search_round → jd_finalize` 邊。LangGraph 路徑與 `run_all` 純 Python 路徑對同一輸入產生相同的結果。設定為上限值（`MAX_ROUNDS=5`、`max_intents=2`）時不會觸發 `GraphRecursionError`。同一輪含 JD_MATCH 加其他意圖時，後續意圖只執行一次。
* **AC-11 可觀測與零個資**：`chat_turn` 日誌含 `search_rounds`、`search_stop_reason`、`pool_evaluated`。checkpoint 的 graph state 只新增 `goto`（節點名稱字串），不含履歷文字和候選池中間資料。LangSmith 追蹤樹中，每輪 `jd_search_round` 各為一個節點（沿用 ADR-0020 遮蔽，零內容上傳）。
* **AC-12 空池**：基準輪候選池為空時，可以降低門檻擴大檢索（只有檢索成本，不呼叫 LLM）。擴大後仍為空時，回覆「資料庫中無相關人選」，且不呼叫抽取和敘述 LLM（維持 Spec-0019 AC-07）。
* **AC-13 設定治理**：8 個變數記載於 `.env.example`。非法值或超出範圍時夾回合法範圍，或退回預設值，不會讓啟動失敗。
* **AC-14 回歸**：全量 unittest 和既有 E2E 通過，CLI 不受影響。

### 1.5 安全與硬上限
* 單輪累計評估人數 ≤ `POOL_MAX`（不超過 100），擴大輪數 ≤ 5，`min_score` ≥ FLOOR。
* 終止性有三道保證：Policy 依輪數硬停止、節點本身再檢查一次輪數上限，以及 LangGraph `recursion_limit`。
* 中間資料（履歷全文、遮蔽文字）只存在 `TurnContext`，屬於單輪暫態資料，不寫入 checkpoint。

---

## 2. Gate 1：8 大架構維度前審

| # | 維度 | 評估 | 結論 |
| :---: | :--- | :--- | :--- |
| 1 | PII | 迴圈中間資料（`match_texts`、`llm_texts`、候選池）放在 `TurnContext`，不放進 graph state，所以不會寫入 checkpoint，也不會被 LangSmith 擷取。graph state 只新增節點名稱 `goto`。送往 LLM 的內容與遮蔽流程和現行完全相同。 | PASS |
| 2 | 容量 | 累計評估人數 ≤ 40（上限 100），`pool_evaluations` 寫入 session 的大小約為現行的 1.3~2.7 倍，仍在 KB 等級。迴圈節點在 session 未變更時不輸出 `session` 通道，避免每一輪重複存一份 session 快照。 | PASS |
| 3 | 非同步/演進 | 業務決策全部在 Application 和 Domain 層（Policy 為純函式），LangGraph 只依 `goto` 轉送。`run_all` 維持無框架等價實作。`goto` 機制可直接沿用到情境 2 的 `interrupt()` 節點。 | PASS |
| 4 | 成本/熔斷 | 只有新進者需要抽取，已評估或已快取者 0 Token。有預算保留額度，總次數受 `MAX_LLM_CALLS_PER_TURN` 限制。不新增 LLM 呼叫類型，不改寫 Prompt，Prompt 和抽取快取版本不變。檢索屬於本地 Redis 運算，不花 Token。配額 429 沿用既有熔斷，直接往外拋，不在迴圈內重試。 | PASS |
| 5 | 可抽換性 | 沿用 `RecruitmentTools.retrieve_candidate_pool` 和 `CandidateProfileService`，不新增 Protocol。換掉向量庫時，Policy 和節點不需修改。 | PASS |
| 6 | 惡意輸入 | 不新增輸入面。輪數、人數、門檻都有硬上限並夾回合法範圍。使用者無法透過訊息控制擴大參數。 | PASS |
| 7 | 索引演進 | 唯讀檢索，不改索引結構和鍵前綴。 | N/A |
| 8 | 併發/可觀測性 | 每輪仍在 session lock 內執行。`trace_id` 貫穿日誌，追蹤樹以每輪一個節點呈現迴圈。`node_ms` 對重複執行的節點改為累加。 | PASS |

**分流**：Deep Track。改變了編排圖的拓撲（由線性節點改為子步驟循環），並新增執行期策略和設定，因此草擬 [ADR-0021](../adr/0021-recruitment-adaptive-candidate-search-loop.md)。
**可行性驗證（2026-11-10）**：以專案 venv 的 LangGraph 1.2.20 驗證過三件事：
* 節點輸出 `goto` 加上條件邊可以構成自循環，`draw_mermaid` 會畫出 `round -.-> round`。
* 超出 `recursion_limit` 時會拋出 `GraphRecursionError`。
* 使用 InMemorySaver 時可以正常完成。

**已知取捨**：
* 中間資料不放進 checkpoint，所以單輪中途當掉時無法從中途恢復，必須重送整輪。現行每一輪本來就是原子操作（持鎖），可以接受。
* 擴大輪以「新進人數」估算預算，對快取命中者比較保守，換取保留額度不會被用掉。

---

## 3. Tech Spec

### 3.1 變更矩陣
| 層 | 檔案 | 類型 | 職責 |
| :--- | :--- | :---: | :--- |
| Domain | `src/domain/recruitment.py` | 修改 | 新增 `SearchStopReason`、`SearchRoundParams`、`SearchRoundRecord`、`SearchExpansionLimits`；`TurnUsage` 加 3 個欄位 |
| Domain | `src/domain/recruitment_services.py` | 修改 | 新增 `SearchExpansionPolicy`（純函式） |
| Application | `src/application/recruitment_settings.py` | 修改 | 新增 8 個設定欄位 |
| Application | `src/application/candidate_profile_service.py` | 修改 | `TurnBudget.remaining`、`TurnBudget.reserved_view(reserve)` |
| Application | `src/application/recruitment_nodes.py` | 修改 | 拆分 `jd_match`；新增 `jd_search_round`、`jd_finalize`；`NodeUpdate.goto`；`TurnContext.jd_search`；`run_all` 支援 goto；`node_ms` 改為累加 |
| Application | `src/application/recruitment_chat_use_case.py` | 修改 | `chat_turn` 日誌加 3 個欄位 |
| Infrastructure | `src/infrastructure/orchestration/langgraph_recruitment_graph.py` | 修改 | 在 state 加入 `goto`、子步驟條件邊、佇列只在子步驟結束時彈出、重算 `recursion_limit` |
| Infrastructure | `src/infrastructure/config.py` | 修改 | 新增 8 個 `RECRUIT_SEARCH_EXPANSION_*` 欄位並夾回合法範圍 |
| Interfaces | `src/interfaces/web/server.py` | 修改 | 把設定映射到 `RecruitmentSettings`，並把 `max_expansion_rounds` 傳給 orchestrator |
| Config | `.env.example` | 修改 | 8 個變數和說明 |
| Tests | `tests/unit/test_recruitment_search_expansion.py` | 新增 | Policy、節點、圖、設定 |
| Tests | `tests/e2e/test_recruitment_search_expansion_e2e.py` | 新增 | Step 4 QA |

### 3.2 Domain（零外部依賴）
```python
class SearchStopReason(str, Enum):
    SATISFIED = "SATISFIED"; MAX_ROUNDS = "MAX_ROUNDS"; POOL_CAP = "POOL_CAP"
    EXHAUSTED = "EXHAUSTED"; BUDGET = "BUDGET"; DEADLINE = "DEADLINE"; DISABLED = "DISABLED"

@dataclass(frozen=True)
class SearchRoundParams:
    round_no: int          # 0 = 基準輪
    pool_target: int       # 本輪檢索取前幾名候選人（含已評估者）
    top_k_chunks: int
    min_score: float

@dataclass(frozen=True)
class SearchRoundRecord:
    params: SearchRoundParams
    returned: int          # 本輪檢索回傳之不重複候選人數
    new_candidates: int    # 其中首次評估者
    qualified_total: int   # 本輪結束後累計完全合格人數

@dataclass(frozen=True)
class SearchExpansionLimits:
    max_rounds: int; pool_step: int; pool_max: int; top_k_max: int
    min_score_step: float; min_score_floor: float

class SearchExpansionPolicy:
    def __init__(self, limits: SearchExpansionLimits): ...
    def initial(self, pool_size: int, top_k_chunks: int, min_score: float) -> SearchRoundParams: ...
    def decide(self, history: Sequence[SearchRoundRecord], requested_k: int, evaluated_total: int,
               affordable_calls: int, seconds_left: float, min_seconds: float
               ) -> Tuple[Optional[SearchRoundParams], Optional[SearchStopReason]]:
        """恰回傳 (params, None) 或 (None, reason) 其一"""
```
`decide` 依序判斷（先符合者先回傳）：
1. `last.qualified_total >= k` → `SATISFIED`
2. `max_rounds == 0` → `DISABLED`；擴大輪數 `len(history) - 1 >= max_rounds` → `MAX_ROUNDS`
3. `seconds_left < min_seconds` → `DEADLINE`
4. `affordable_calls < 1` → `BUDGET`
5. `saturated = last.returned < last.params.pool_target`。若已飽和且 `last.min_score <= floor + 1e-9`，回傳 `EXHAUSTED`。
6. `target = min(last.pool_target + step, pool_max, evaluated_total + affordable_calls)`。若 `target <= evaluated_total`，在 `evaluated_total >= pool_max` 時回傳 `POOL_CAP`，否則回傳 `BUDGET`。
7. 計算下一輪參數：
   * `min_score`：飽和時為 `max(floor, round(last.min_score - step, 4))`，否則維持不變。
   * `top_k`：`min(top_k_max, max(last.top_k, ceil(base_top_k * target / base_pool)))`。`base_top_k` 和 `base_pool` 在 `initial` 時記下。

### 3.3 Application
* **`TurnBudget`**：
  * 新增 `remaining` 屬性。
  * 新增 `reserved_view(reserve)`，回傳只有 `try_consume()` 方法的物件，語意為「在鎖內檢查 `limit - used > reserve` 才扣抵」。
  * `get_profiles` 的參數型別放寬為具備 `try_consume` 的鴨子型別，邏輯不變。
* **`TurnContext.jd_search: Optional[JdSearchProgress]`**：單輪暫態資料，不持久化。欄位如下：
  ```python
  @dataclass
  class JdSearchProgress:
      jd: JdRequirements; requested_k: int
      params: SearchRoundParams                      # 下一輪要執行的參數
      history: List[SearchRoundRecord]
      candidates: Dict[str, CandidateSummary]        # 依首次出現順序
      evals: Dict[str, CandidateEvaluation]
      llm_texts: Dict[str, str]; match_texts: Dict[str, str]
      stop_reason: Optional[SearchStopReason] = None
  ```
* **`NodeUpdate.goto: Optional[str] = None`**：子步驟路由。`SUBSTEP_NODES = ("jd_search_round", "jd_finalize")`。
* **`jd_match`（準備）**：
  * 解析 K、載入 JD、套用受保護屬性過濾、重新編號 R1..Rn（與現行版本相同）。
  * JD 失敗時沿用現行降級，回傳 `goto=None`。
  * 成功時建立 `JdSearchProgress`（`params = policy.initial(...)`），回傳 `goto="jd_search_round"`，session 不變。
* **`jd_search_round`**：
  1. 先檢查輪數上限（防禦用）和 deadline。
  2. 呼叫 `retrieve_candidate_pool(query, params.top_k_chunks, params.pool_target, params.min_score)`。
  3. `new = [c for c in pool if c.candidate_id not in candidates]`，並截斷到 `pool_max - evaluated_total`。
  4. 有新進者時，以 `budget.reserved_view(reserve if round_no > 0 else 0)` 呼叫 `get_profiles(new, ...)`。基準輪不保留額度，與現行行為相同。
  5. 逐一 `evaluate_candidate`，累加到 `evals`，然後追加 `SearchRoundRecord`。
  6. 呼叫 `policy.decide(...)`，其中 `affordable_calls = budget.remaining - reserve`：
     * 回傳下一輪參數時，更新 `params`，`goto="jd_search_round"`。
     * 回傳停止原因時，記錄 `stop_reason`，`goto="jd_finalize"`。
* **`jd_finalize`**：
  * 累計評估人數為 0 時，回覆「資料庫中無相關人選…」（同現行）。
  * 否則執行現行流程：排序、組證據、`ConstraintRelaxationAnalyzer`、渲染、敘述、更新 session。另有三點調整：
    * 「候選池僅 N 人」警告改用累計人數判斷。
    * `history` 長度 > 1 時，在名單之後插入模板段落「檢索擴大紀錄」，並把 `relaxation.scope_note` 附註為「（已自動擴大檢索 r 輪）」。
    * 寫入 `turn.usage.search_rounds`、`search_stop_reason`、`pool_evaluated`。
  * 回傳 `goto=None`。
* **`run_all`**：每個意圖節點執行後，只要 `update.goto` 有值就繼續執行該節點。步數上限為 `max_rounds + 3`，超過時拋出 `RuntimeError`，屬程式錯誤防線。
* **`execute_node`**：`node_ms[name]` 改為累加。

### 3.4 Infrastructure：`langgraph_recruitment_graph.py`
* `RecruitmentGraphState` 加 `goto: Optional[str]`。
* `make_node` 的處理：
  * 只有 `update.session is not session` 時才輸出 `session`（route 和 compose 維持一律輸出）。
  * 一律輸出 `goto=update.goto`。
  * 佇列只在「非 route/compose 且 `goto is None`」時彈出。
* `next_step`：`goto` 在 `SUBSTEP_NODES` 內時回傳它；其他非 None 值拋出 `ValueError`（程式錯誤）；否則依佇列決定。
* 條件邊：為 `jd_match` 和兩個子步驟節點加上 `destinations + SUBSTEP_NODES`。
* `recursion_limit = max_intents * (max_expansion_rounds + 3) + 4`。

### 3.5 Interfaces / Config
* `config.py` 依 §1.3 讀取並夾回合法範圍，以 `_safe_int` / `_safe_float` 處理非數值。夾回時以 `logger.warning` 記錄鍵名，不記錄值以外的資訊。
* `server.py` 把設定映射到 `RecruitmentSettings`，並把 `settings.search_expansion_max_rounds` 傳給 orchestrator 建構子。新參數有預設值，維持向下相容。

### 3.6 單元測試計畫（`tests/unit/test_recruitment_search_expansion.py`，100% 離線）
1. **Policy**：
   * 七種停止原因各一個案例。
   * 飽和時降低門檻，且不低於 floor。
   * 非飽和時維持門檻並加大目標人數。
   * `top_k` 等比例放大並受上限限制。
   * `target` 受 `affordable_calls` 限制。
   * 判斷順序：SATISFIED 優先於 MAX_ROUNDS。
2. **TurnBudget**：`reserved_view` 不會吃到保留額度；多執行緒下 `remaining` 一致。
3. **節點**（fake tools 依 `min_score` / `pool_size` 回傳不同人數，fake LLM 計數）：
   * 對應 AC-1、AC-2、AC-3、AC-4、AC-5、AC-6、AC-7、AC-8、AC-12。
   * 檢索擴大紀錄的數字與 history 一致。
   * `scope_note` 有附註。
4. **圖**：
   * 自循環邊存在（`get_graph()` 的 edges）。
   * LangGraph 和 `run_all` 的結果等價。
   * 上限設定下不會發生 `GraphRecursionError`。
   * 雙意圖時佇列正確。
   * session 未變更時不輸出 session 通道。
   * 未知 `goto` 拋出 `ValueError`。
5. **故障注入**：
   * 擴大輪檢索拋例外時，停止並以已評估結果收尾（停止原因沿用 `EXHAUSTED`，並發出警告）。
   * 擴大輪拋出 `LlmQuotaExhaustedError` / `TurnTimeoutError` 時照常往外拋。
6. **設定**：預設值、夾回範圍、非數值退回預設值、`.env.example` 含 8 個鍵。

### 3.7 QA 驗收矩陣（Step 4，`tests/e2e/test_recruitment_search_expansion_e2e.py`）
| TC | AC | 情境 | 方法 |
| :--- | :--- | :--- | :--- |
| TC-1 | AC-1, AC-9 | 基準已足夠，以及停用時 | 真實 LangGraph 加真實 handlers，fake 向量檢索；比對 `MAX_ROUNDS=0` 與 `=2` 的回覆是否逐字相同 |
| TC-2 | AC-2, AC-8 | 第 1 輪補足 | fake 檢索在 pool_target 25 時多回傳 2 位合格者；Profile 抽取次數 = 新進人數 |
| TC-3 | AC-3 | 飽和時降低門檻直到 EXHAUSTED | fake 檢索依 min_score 過濾分數 |
| TC-4 | AC-4, AC-5 | 最大輪數與人數上限 | 檢查放寬報告的 pool_size 和 scope_note |
| TC-5 | AC-6, AC-7 | 預算與時間 | 小預算加冷快取，確認推薦理由仍來自 LLM；以假時鐘模擬剩餘時間不足 |
| TC-6 | AC-10 | 拓撲與雙意圖 | `get_graph().draw_mermaid()` 含自循環邊；JD_MATCH 加 GENERAL_QA 同一輪 |
| TC-7 | AC-11 | 零個資 checkpoint 與日誌 | 讀 InMemorySaver 的 checkpoint，序列化後不含植入標記（`王小明`、履歷句子）；`chat_turn` 日誌含 3 個欄位 |
| TC-8 | AC-12 | 空池 | 基準輪為 0，降低門檻後仍為 0，LLM 呼叫次數只有路由和 JD 抽取 |
| TC-9 | AC-13 | 設定治理 | `AppConfig.from_env` 讀取非法值和越界值 |
| TC-10 | AC-14 | 回歸 | 全量 unittest 和既有 e2e |
| TC-11 | AC-2 | 真實 Redis 煙霧測試（選用） | 對本機索引用虛構 JD 實跑一次，檢查擴大紀錄合理；索引不存在時 skip |

---

## 4. 實作偏差（QA 時回寫，詳見 [QA-0021](../qa_reports/0021-recruitment-adaptive-candidate-search-qa.md)）
* **DV-1**：API `usage` 以 `asdict(TurnUsage)` 產生，所以會自動多出 3 個欄位。只新增欄位、向下相容。
* **DV-2**：每一輪擴大會多 1 次查詢 embedding 呼叫（每輪最多 `MAX_ROUNDS` 次，每次只有幾個 Token）。查詢向量的記憶化列為後續改善項。
* **DV-3**：`recursion_limit` 改由 `handlers.max_substeps_per_intent` 推導，不另外傳參數給 orchestrator。設定夾回範圍時不寫 WARNING，沿用 `config.py` 既有的 `_clamp_unit` 慣例。
* **TC-11**：改用真實 RediSearch 臨時索引，搭配可控相似度的 Fake Embedding（離線，0 Token），不使用正式索引。
