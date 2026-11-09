# ADR-0020：招募助手 LangSmith 遮蔽式效能追蹤

## 1. 狀態
已採納 (Accepted)

* **日期**：2026-11-09（提案）／2026-11-09（採納，Gate 2 PASS）
* **規格與驗收**：[Spec 0020](../specs/0020-recruitment-chat-langsmith-masked-tracing-spec.md)、[QA Report 0020](../qa_reports/0020-recruitment-chat-langsmith-tracing-qa.md)
* **關聯**：[ADR-0012](./0012-centralized-system-logging-and-api-latency-tracking.md)（補充，不取代）、[ADR-0019](./0019-recruitment-assistant-langgraph-chat.md)
* **標籤**：`Observability`, `LangSmith`, `Tracing`, `Zero-PII`

## 2. 背景與問題陳述
[ADR-0012](./0012-centralized-system-logging-and-api-latency-tracking.md) 以集中日誌與 API 延遲紀錄作為可觀測性主軸，當時沒有引入重型 APM。招募助手（ADR-0019）每輪會呼叫多次 LLM，延遲主要來自結構化抽取。現有的 `chat_turn` 日誌只有每個節點的總耗時，無法得知單次 LLM 呼叫的延遲、token 用量、重試與錯誤分布。

招募助手的 prompt 含有去識別化後的履歷內容，對話狀態也含有候選人真名。直接開啟 LangSmith 預設追蹤，會把這些內容上傳到第三方，違反零個資紅線（AGENTS.md §1-7）。

## 3. 評估選項
* **A1：LangSmith 雲端，輸入和輸出全部隱藏，metadata 白名單，錯誤只留類別名**：改動最小，可以看到延遲、token、節點樹和錯誤類型；代價是看不到 prompt 內容。
* **A2：LangSmith 雲端，不遮蔽**：除錯能力最強，但會上傳真名（存在對話狀態中）、使用者輸入和履歷經歷。違反紅線，不採用。
* **A2′：過濾後只上傳遮蔽過的 prompt**：仍會留下準識別資訊（公司、學校、年月），需要另行評估。
* **B：自架 Langfuse / OpenTelemetry**：資料不離開本機，但要多維護一套服務（Postgres、ClickHouse）。

## 4. 架構決策
採納 **A1**：
1. 預設關閉，以 `RECRUIT_TRACING_ENABLED` 開啟。透過顯式 `LangChainTracer` callback 注入每輪 `graph.invoke`，不依賴全域 `LANGSMITH_TRACING`。偵測到全域旗標時輸出警告，因為全域追蹤會繞過遮蔽。
2. 遮蔽在 SDK 用戶端完成：`hide_inputs` / `hide_outputs` 為 True，anonymizer 對 metadata 套用白名單（token 用量、模型、節點、trace_id、session_hash），錯誤只留例外類別名，`omit_traced_runtime_info` 為 True。
3. Profile 抽取執行緒池以 `contextvars.copy_context()` 傳遞追蹤脈絡，確保追蹤樹完整。
4. 追蹤只是旁路：任何建立或上傳失敗都只記錄 WARNING，對話功能不受影響。

## 5. 8 大架構審查維度評估
詳見 [Spec-0020 §2](../specs/0020-recruitment-chat-langsmith-masked-tracing-spec.md#2-gate-18-大架構維度前審)。PII 維度是本決策的核心：上傳內容只有結構與數值，沒有任何文字內容。

## 6. 後果
* **正面**：可以觀測單次 LLM 呼叫的延遲與 token 用量，作為調整 Prompt 和預算的依據；`trace_id` 可以對應回本地日誌。
* **負面**：無法在 LangSmith 檢視 prompt 或回覆內容。要做品質評估時，需要另立 ADR（A2′ 或 B）。
* **風險**：使用者若自行設定全域 `LANGSMITH_TRACING=true`，遮蔽會被繞過。目前以啟動警告和 `.env.example` 註記防範。

## 7. 實作偏差與實施後評估

| 編號 | 偏差 / 補強 | 原規劃 | 實際落地 | 理由 |
| :---: | :--- | :--- | :--- | :--- |
| DV-1 | 執行環境資訊 | 不上傳任何執行環境資訊 | 仍上傳 langchain-core 固定附帶之 `extra.runtime`（函式庫/平台版本字串） | 由 `LangChainTracer` 內部寫入，不受 langsmith `omit_traced_runtime_info` 控制且無公開關閉介面；內容無個資、無業務資料。QA TC-4 以鍵白名單鎖定 |
| DV-2 | 有界收尾 | `close()` 直接 `client.flush()` | 背景執行緒 flush，最多等待 `RECRUIT_TRACING_FLUSH_TIMEOUT_SECONDS`（預設 5 秒） | QA 實測端點不可達時 flush 退避重試阻塞 44.7 秒，會拖延服務關閉 |
| DV-3 | 依賴宣告 | 沿用 langchain-core 間接依賴 | `requirements.txt` 明列 `langsmith>=0.14,<1.0` | 直接 import 之套件需顯式約束版本 |

