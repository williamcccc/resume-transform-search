# QA-0021：招募助手候選人不足時自動擴大檢索：QA 實測驗收報告

* **規格**：[Spec-0021](../specs/0021-recruitment-adaptive-candidate-search-spec.md)，**決策**：[ADR-0021](../adr/0021-recruitment-adaptive-candidate-search-loop.md)
* **日期**：2026-11-10
* **結論**：**PASS**。14/14 AC 已覆蓋，未發現功能缺陷；有 3 項規格偏差（DV-1~3），都已在規格中記錄。

## 1. 測試環境與方法
* Python 3.13 / Windows 11；LangGraph 1.2.20；Redis 8（本機 db0，以 `qa0021:` 前綴與臨時索引 `idx:qa0021:v1` 隔離，測試後清除）。
* 灰箱實測檔：[test_recruitment_search_expansion_e2e.py](../../tests/e2e/test_recruitment_search_expansion_e2e.py)
  * **FAKE 軌**：真實 FastAPI `/api/chat`、真實 LangGraph 編排器（InMemorySaver）、真實節點處理器和 `CandidateProfileService`。向量檢索使用依 `min_score` / `top_k` / `pool_size` 實際篩選的記憶體 Fake，LLM 使用確定性 Fake。
  * **REDIS 軌**：真實 `IndexResumesUseCase`、`RedisVectorStore`（RediSearch HNSW KNN）、`SearchResumesUseCase`。Embedding 改用可控餘弦相似度的確定性 Fake（離線，0 Token），讓「基準門檻以外的合格者」可以精確擺放。
* 所有履歷和姓名都是在記憶體中動態建構的虛構樣本（`張小強NN`），不讀取 `data/`、`resume/`。

## 2. 需求追溯矩陣 (RTM)
| TC | AC | 情境 | 結果 |
| :--- | :--- | :--- | :---: |
| TC-1 | AC-1, AC-9 | 基準輪已有 3 人合格：只檢索 1 次；`reply_markdown`、`shortlist`、`warnings` 與 `MAX_ROUNDS=0` 時逐字相同 | PASS |
| TC-2 | AC-2, AC-8 | 第 16~18 名中有 2 位合格，第 1 輪補足；`relaxation=None`；抽取 18 次且沒有重複；擴大紀錄表的數字正確；同一 Session 重送時抽取 0 次（快取） | PASS |
| TC-3 | AC-3 | 飽和時門檻依序為 0.50 → 0.45 → 0.40，從未低於下限；在下限仍飽和時停止原因為 `EXHAUSTED` | PASS |
| TC-4 | AC-4, AC-5 | 2 輪後停止原因為 `MAX_ROUNDS`；放寬報告 `pool_size=35`，等於 `pool_evaluated`，`scope_note` 有附註；`POOL_MAX=30` 時累計評估 30 人，停止原因為 `POOL_CAP` | PASS |
| TC-5 | AC-6, AC-7 | 預設預算 25：停止原因為 `BUDGET`，推薦理由仍由 LLM 產生，`degraded=false`，`llm_calls ≤ 25`；剩餘時間不足時停止原因為 `DEADLINE`，只檢索 1 次 | PASS |
| TC-6 | AC-10 | Mermaid 圖含 `jd_search_round -.-> jd_search_round`；`MAX_ROUNDS=5` 加雙意圖時未發生 `GraphRecursionError`，GENERAL_QA 只執行 1 次 | PASS |
| TC-7 | AC-11 | `chat_turn` 日誌含 `search_rounds=1 search_stop_reason=SATISFIED pool_evaluated=N`，不含姓名；所有 checkpoint 快照都不含履歷內文標記，state 鍵只有 `session`、`queue`、`goto`；結束時 `goto=None` | PASS |
| TC-8 | AC-12 | 空池：降低門檻 2 次後仍為空，回覆「資料庫中無相關人選」；抽取 0 次、敘述 0 次，`llm_calls=1`（只有 JD 抽取） | PASS |
| TC-9 | AC-13 | 負數、科學記號、`inf` 和越界值都夾回合法範圍或退回預設值；`.env.example` 恰好含 8 個鍵 | PASS |
| TC-10 | AC-14 | 單元測試 470/470 OK（新增 43 個）；既有招募助手與追蹤 E2E 37/37 OK | PASS |
| TC-11 | AC-2 | **真實 RediSearch**：基準輪 15 人只有 1 人合格；第 1 輪放大池子仍飽和；第 2 輪門檻降到 0.45，召回 0.46~0.48 的 3 位合格者，停止原因為 `SATISFIED` | PASS |
| TC-12 | 對抗 | 擴大輪檢索拋出 `ConnectionError`：以基準輪結果收尾並發出警告，API 回 200，正常產出放寬報告 | PASS |
| TC-13 | 對抗 | 同一 Session 連送兩輪 JD：迴圈暫態資料不殘留，兩輪結果逐字相同 | PASS |

## 3. 規格偏差（已回寫 Spec-0021 §4）
| ID | 偏差 | 判定 |
| :---: | :--- | :--- |
| DV-1 | API 回應的 `usage` 以 `asdict(TurnUsage)` 產生，所以會自動多出 `search_rounds`、`search_stop_reason`、`pool_evaluated` 3 個欄位（規格原列為 Out-of-Scope） | 只新增欄位、向下相容，接受 |
| DV-2 | 每一輪擴大都會重新把查詢轉成向量，多 1 次 embedding 呼叫（TC-11 實測 3 輪共 3 次）；每輪最多 `MAX_ROUNDS` 次，每次只有幾個 Token | 已知成本；查詢向量的記憶化列為後續改善項 |
| DV-3 | `recursion_limit` 改由 `handlers.max_substeps_per_intent` 推導，不另外傳 `max_expansion_rounds` 給 orchestrator；設定夾回範圍時不寫 WARNING（沿用 `config.py` 既有的 `_clamp_unit` 慣例，該模組沒有 logger） | 介面更簡單，接受 |

## 4. 對抗與邊界補充
* **終止性**：有三道保證：Policy 依輪數停止、節點檢查 `round_no > max_rounds`、`recursion_limit`。單元測試另外驗證未知 `goto` 在 `run_all` 和 LangGraph 兩條路徑都會拋出 `ValueError`。
* **併發**：`SearchExpansionPolicy` 不保存狀態（基準參數取自 `history[0]`），可以在多個 Session 間共用。`ReservedBudgetView` 以 8 執行緒共 160 次扣抵實測，恰好留下保留額度。
* **錯誤分流**：基準輪檢索失敗時往外拋（與現行行為相同）；擴大輪的 `LlmQuotaExhaustedError` / `TurnTimeoutError` 往外拋；其他例外降級收尾。

## 5. 殘餘風險
* 冷快取時，預設預算只夠擴大輪新增約 7 人。要更大範圍時需要調高 `RECRUIT_MAX_LLM_CALLS_PER_TURN`。
* REDIS 軌使用可控的 Fake Embedding，沒有用真實 Gemini embedding 驗證「真實分數分布下，降低 0.05 能召回多少人」。這項需要用正式資料觀察 `chat_turn` 日誌來調整參數。
