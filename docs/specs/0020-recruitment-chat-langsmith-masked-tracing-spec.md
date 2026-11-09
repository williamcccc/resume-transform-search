# Spec-0020：招募助手 LangSmith 遮蔽式效能追蹤 (Masked Performance Tracing)

* **狀態**：已實作（Gate 1 PASS → QA PASS → Gate 2 PASS，2026-11-09）；實作偏差見 [ADR-0020 §7](../adr/0020-recruitment-chat-langsmith-masked-tracing.md)
* **關聯**：[ADR-0020](../adr/0020-recruitment-chat-langsmith-masked-tracing.md)（本規格之決策紀錄）、[ADR-0019](../adr/0019-recruitment-assistant-langgraph-chat.md)（招募助手）、[ADR-0012](../adr/0012-centralized-system-logging-and-api-latency-tracking.md)（集中日誌）
* **方案**：A1：LangSmith 雲端，輸入/輸出全隱藏，metadata 白名單，錯誤僅保留例外類別名

---

## 1. PRD

### 1.1 背景與目標
* **現況**：招募助手只有每輪 `chat_turn` 摘要日誌（[recruitment_chat_use_case.py:75](../../src/application/recruitment_chat_use_case.py)），內容是 `node_ms`、`llm_calls` 和快取命中數。看不到單次 LLM 呼叫的延遲、token 用量、重試次數與失敗分布，也沒有跨請求的趨勢檢視。
* **目標**：開啟後，每輪對話在 LangSmith 呈現一棵追蹤樹，包含圖 → 節點 → LLM 呼叫三層的延遲、token 用量與錯誤類型，作為效能監控與成本觀測依據，且**不上傳任何履歷內容、對話內容或個資**。

### 1.2 範疇
* **In-Scope**
  1. 選用（預設關閉）的 LangSmith 追蹤：以 `AppConfig` 開關控制，透過顯式 `LangChainTracer` callback 注入 `graph.invoke`，不依賴全域環境變數。
  2. 遮蔽政策：輸入和輸出全部隱藏。metadata 以白名單過濾，只保留 token 用量、模型名稱、節點名稱、`trace_id` 和 `session_hash`。錯誤只保留例外類別名。不上傳執行環境資訊。
  3. 修正 Profile 抽取執行緒池的追蹤脈絡斷鏈：`submit` 時用 `contextvars.copy_context()` 把脈絡帶進執行緒池，讓抽取呼叫掛在所屬節點底下。
  4. 每輪追蹤 metadata 帶 `trace_id` / `session_hash`，可與 `chat_turn` 日誌互相對照。
  5. 失效安全：缺少套件、未設金鑰、Client 建立失敗或上傳失敗時，追蹤一律停用或略過，**不影響對話結果**。
  6. 偵測到全域 `LANGSMITH_TRACING` / `LANGCHAIN_TRACING_V2` 開啟時，輸出 WARNING，因為全域追蹤會繞過遮蔽政策。
* **Out-of-Scope**
  1. A2/A2′：上傳 prompt 或狀態內容（需另立 ADR）。
  2. 自架 Langfuse / OpenTelemetry / Prometheus。
  3. LangSmith 評估資料集、線上評分、告警設定（屬 LangSmith 平台操作）。
  4. CLI 轉檔與向量索引管線的追蹤（本期只涵蓋招募助手）。
  5. 串流輸出（P3-STREAM，另案）。

### 1.3 設定合約（全部同步至 `.env.example`）
| 環境變數 | AppConfig 欄位 | 型別 | 預設 | 說明 |
| :--- | :--- | :---: | :---: | :--- |
| `RECRUIT_TRACING_ENABLED` | `recruit_tracing_enabled` | bool | `false` | 招募助手遮蔽式追蹤開關 |
| `LANGSMITH_API_KEY` | `langsmith_api_key` | str | `""` | LangSmith 金鑰（機密，只放 `.env`） |
| `LANGSMITH_ENDPOINT` | `langsmith_endpoint` | str | `""` | 空值時使用 SDK 預設端點；可指向 EU 區或自架端點 |
| `LANGSMITH_PROJECT` | `langsmith_project` | str | `recruitment-assistant` | LangSmith 專案名 |
| `RECRUIT_TRACING_SAMPLING_RATE` | `recruit_tracing_sampling_rate` | float | `1.0` | 取樣率，限制在 [0, 1]；非數值時退回預設值 |
| `RECRUIT_TRACING_FLUSH_TIMEOUT_SECONDS` | `recruit_tracing_flush_timeout_seconds` | float | `5.0` | 關閉時等待上傳的秒數上限（QA D2 補強；0 表示不等待） |

### 1.4 驗收標準 (AC)
* **AC-1 預設關閉**：未設定 `RECRUIT_TRACING_ENABLED` 時，不建立 LangSmith Client，`graph.invoke` 的 config 中沒有 tracer，行為與現行版本完全相同。
* **AC-2 追蹤樹完整**：開啟追蹤時，一輪 jd_match 對話的上報內容包含圖根節點、各節點，以及**全部** LLM 呼叫。執行緒池內的 Profile 抽取也在其中，且每一筆都有 `parent_run_id`。
* **AC-3 零內容上傳**：上報內容中的 `inputs` / `outputs` 全部為空 `{}`。整份上報內容序列化後，不得出現使用者訊息、履歷原文、候選人姓名、session_id 原值或 API 金鑰字串。
* **AC-4 metadata 白名單**：`extra.metadata` 只能包含白名單鍵。`usage_metadata` 只保留數值，其他鍵（例如 `thread_id`、`checkpoint_ns`）一律剔除。
* **AC-5 錯誤脫敏**：節點或 LLM 呼叫拋出的例外訊息就算含有個資，上報的 `error` 也只有例外類別名（例如 `ValueError`）。
* **AC-6 失效安全**：開啟追蹤但缺少金鑰時，輸出 WARNING、停用追蹤，對話正常回應。langsmith 匯入失敗或 Client 建立失敗時也一樣。上傳端點無法連線時，對話仍回 200 且結果正確。
* **AC-7 對照性**：根追蹤的 metadata 含本輪 `trace_id` 和 `session_hash`，值與 `chat_turn` 日誌相同。
* **AC-8 全域追蹤警告**：開啟追蹤時，若環境中 `LANGSMITH_TRACING` 或 `LANGCHAIN_TRACING_V2` 為真，輸出 WARNING。
* **AC-9 設定治理**：五個新變數全部記載於 `.env.example`；金鑰不出現在日誌與上報內容中；取樣率超出範圍時會被限制在 [0, 1]。
* **AC-10 回歸**：既有單元測試與 E2E 全數通過；CLI 不受影響。

---

## 2. Gate 1：8 大架構維度前審

| # | 維度 | 評估 | 結論 |
| :---: | :--- | :--- | :--- |
| 1 | PII | 輸入和輸出由 SDK 在用戶端隱藏後才送出。metadata 走白名單，錯誤只留類別名，執行環境資訊不送。全域環境追蹤會繞過遮蔽，因此提供警告（AC-8），並在 `.env.example` 註明不要設定。 | PASS |
| 2 | 容量 | SDK 在背景批次上傳，記憶體佇列由 SDK 自行管理。每輪建立一個新的 tracer，不累積狀態。 | PASS |
| 3 | 非同步/演進 | Use Case 不變。tracer 只在基礎設施層的 invoke config 注入，日後換成 OpenTelemetry 只需替換 tracing 模組。 | PASS |
| 4 | 成本/熔斷 | 不新增 LLM 呼叫，Gemini Token 為 0 增量。LangSmith 用量以取樣率控制。上傳失敗不會重試阻塞主流程。 | PASS |
| 5 | 可抽換性 | 不改 Domain。tracing 經可選建構參數注入 orchestrator，傳入 `None` 時與現行版本相同。Application 只用標準函式庫 `contextvars`。 | PASS |
| 6 | 惡意輸入 | 不新增輸入面。使用者訊息不上傳，因此不構成上報通道注入。 | PASS |
| 7 | 索引演進 | 不涉及 Redis 索引。 | N/A |
| 8 | 併發/可觀測性 | 每輪獨立的 tracer，`copy_context` 讓每個 Future 各自擁有一份脈絡副本，執行緒安全。`trace_id` 貫穿日誌與追蹤。 | PASS |

**分流**：Deep Track，因為新增外部 SaaS 整合，已草擬 ADR-0020。
**可行性驗證**：已用 fake chat model 和攔截式 Client 驗證以下四點：copy_context 能讓執行緒池內的呼叫掛在父節點下（沒複製時該呼叫完全不會被追蹤）；hide 加白名單後，上報內容不含姓名、session_id 或 prompt；`usage_metadata` 有保留；`langgraph_node` 有保留。

---

## 3. Tech Spec

### 3.1 變更矩陣
| 層 | 檔案 | 類型 | 職責 |
| :--- | :--- | :---: | :--- |
| Infrastructure | `src/infrastructure/observability/__init__.py` | 新增 | 套件 |
| Infrastructure | `src/infrastructure/observability/langsmith_tracing.py` | 新增 | 遮蔽政策純函式、`LangSmithTurnTracing`、`build_langsmith_tracing(config)` |
| Infrastructure | `src/infrastructure/config.py` | 修改 | 5 個新欄位 |
| Infrastructure | `src/infrastructure/orchestration/langgraph_recruitment_graph.py` | 修改 | 可選參數 `tracing`，`run_turn` 合併 invoke config，`close()` 時 flush |
| Application | `src/application/candidate_profile_service.py` | 修改 | `executor.submit(contextvars.copy_context().run, ...)` |
| Interfaces | `src/interfaces/web/server.py` | 修改 | `build_chat_use_case` 組裝 tracing 並注入 orchestrator |
| Config | `.env.example`、`requirements.txt` | 修改 | 新變數；把 `langsmith>=0.14,<1.0` 列為直接依賴 |
| Tests | `tests/unit/test_langsmith_tracing.py` | 新增 | 單元測試 |
| Tests | `tests/e2e/test_recruitment_tracing_e2e.py` | 新增 | 真實 LangGraph + 真實 langsmith Client（攔截上傳）灰箱實測 |

### 3.2 Domain
不變更。

### 3.3 Application
`CandidateProfileService.get_profiles` 原本呼叫 `executor.submit(self._extractor.extract, ...)`，改為：
```python
ctx = contextvars.copy_context()  # 每個 Future 各自一份，避免同一 Context 併發進入
executor.submit(ctx.run, self._extractor.extract, cand.candidate_id, llm_text, content_hash)
```
語意不變，只是讓呼叫端的 contextvars（包括 LangChain 的 runnable config）傳進工作執行緒。

### 3.4 Infrastructure：`langsmith_tracing.py`
```python
ALLOWED_METADATA_KEYS = frozenset({
    "trace_id", "session_hash", "langgraph_node", "langgraph_step",
    "ls_provider", "ls_model_name", "ls_model_type", "ls_temperature", "ls_max_tokens",
    "usage_metadata",
})

def scrub_metadata(metadata: Mapping) -> dict          # 白名單；只留純量；usage_metadata 遞迴只留數值
def scrub_error(error: object) -> str                  # 取第一行開頭的例外類別名，無法辨識時回傳 "Error"
def trace_anonymizer(payload: dict) -> dict            # {"error": ...} 交給 scrub_error，其餘交給 scrub_metadata

class LangSmithTurnTracing:
    def __init__(self, client, project_name: str, tracer_factory=None): ...
    def invoke_config(self, trace_id: str, session_id: str) -> dict:
        # {"callbacks": [LangChainTracer(client, project_name)], "run_name": "recruitment_chat_turn",
        #  "tags": ["recruitment-chat"], "metadata": {"trace_id": ..., "session_hash": session_hash(session_id)}}
    def close(self) -> None:  # client.flush()；吞下例外並記錄 WARNING (err_type)

def build_langsmith_tracing(config: AppConfig) -> Optional[LangSmithTurnTracing]:
    # 停用時 → None；缺少金鑰時 → WARNING 並回傳 None
    # 全域 LANGSMITH_TRACING/LANGCHAIN_TRACING_V2 為真 → WARNING (AC-8)
    # 延遲匯入 langsmith 和 LangChainTracer；匯入或建立失敗時 → WARNING (err_type) 並回傳 None
    # Client(api_key, api_url=endpoint or None, hide_inputs=True, hide_outputs=True,
    #        anonymizer=trace_anonymizer, omit_traced_runtime_info=True,
    #        tracing_sampling_rate=clamped)
```
* SDK 行為：`hide_inputs=True` / `hide_outputs=True` 優先於 anonymizer，因此 anonymizer 只會收到 metadata 與 `{"error": ...}`。
* 日誌只記錄 `err_type`，不記錄金鑰與例外訊息全文。

### 3.5 Orchestrator
```python
def __init__(self, handlers, bundle, max_intents_per_turn, tracing: Optional[LangSmithTurnTracing] = None)
# run_turn：
config = self._config(session_id)
if self._tracing is not None:
    config = {**config, **self._tracing.invoke_config(trace_id, session_id)}
# close()：先 self._tracing.close()（例外隔離），再 bundle.close()
```
`invoke_config` 本身拋例外時要隔離：記錄 WARNING，該輪改走不追蹤的路徑。

### 3.6 Interfaces
`build_chat_use_case` 在 try 區塊內呼叫 `build_langsmith_tracing(config)`，把結果傳給 orchestrator。追蹤建立失敗不影響聊天初始化。

### 3.7 單元測試計畫（`tests/unit/test_langsmith_tracing.py`）
1. `scrub_metadata`：白名單內的鍵保留，`thread_id`、`checkpoint_ns`、巢狀 dict 被剔除；`usage_metadata` 的非數值欄位被剔除。
2. `scrub_error`：含中文姓名的 `ValueError('王小明 ...')\nTraceback...` 只回傳 `ValueError`；模組路徑形式的類別名保留最後一段之前的完整名稱；空值或無法辨識時回傳 `Error`。
3. `trace_anonymizer` 能依鍵分流到 error 或 metadata 的處理。
4. `build_langsmith_tracing`：停用時回 None；開啟但無金鑰時回 None 並有 WARNING；匯入失敗（patch import）時回 None 並有 WARNING；全域旗標為真時有 WARNING；正常時 Client 參數正確（hide、anonymizer、sampling 已限制範圍、endpoint 空值時傳 None）。
5. `invoke_config`：含 tracer callback、run_name、tags，metadata 含 trace_id 和 session_hash（不是原始 session_id）；每次呼叫都是新的 tracer。
6. `close`：flush 拋例外時不往外拋，並記錄 WARNING。
7. Orchestrator：`tracing=None` 時 invoke config 不含 callbacks；有 tracing 時有合併；`invoke_config` 拋例外時該輪照常完成。
8. `CandidateProfileService`：在工作執行緒中讀得到呼叫端設定的 ContextVar 值。
9. `AppConfig`：預設值、取樣率限制範圍、非數值時退回預設。

### 3.8 QA 驗收矩陣（Step 4，`tests/e2e/test_recruitment_tracing_e2e.py`）
| TC | AC | 情境 | 方法 |
| :--- | :--- | :--- | :--- |
| TC-1 | AC-1 | 預設關閉 | 由真實 `AppConfig.from_env`（清除環境變數）組裝，確認 orchestrator 沒有 tracing |
| TC-2 | AC-2 | 追蹤樹完整（含執行緒池抽取） | 真實 LangGraph 加上真實 `RecruitmentNodeHandlers` 和 `CandidateProfileService`，LLM 換成 LangChain fake chat model 包裝的 adapter；用攔截式 langsmith Client 收集最終上報內容 |
| TC-3 | AC-3 | 零內容上傳 | 訊息和履歷中植入虛構標記（`王小明`、`sample-secret-email@example.com`、假金鑰），檢查序列化後的上報內容 |
| TC-4 | AC-4 | metadata 白名單 | 逐筆檢查 `extra.metadata` 的鍵是否都在白名單內 |
| TC-5 | AC-5 | 錯誤脫敏 | fake LLM 拋出含標記的例外，上報 error 只等於類別名 |
| TC-6 | AC-6 | 端點無法連線 | 真實 Client 指向 `127.0.0.1` 未開放的埠，對話結果與未開追蹤時一致 |
| TC-7 | AC-7 | 對照性 | 根 run 的 metadata 中 trace_id 等於 outcome/日誌值 |
| TC-8 | AC-8 | 全域旗標警告 | 設定 `LANGSMITH_TRACING=true`，assertLogs |
| TC-9 | AC-9 | 設定治理 | `.env.example` 包含 5 個鍵；金鑰不出現在日誌中 |
| TC-10 | AC-10 | 回歸 | 全量 unittest 與既有 e2e |
