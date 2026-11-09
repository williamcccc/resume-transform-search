# QA-0020：招募助手 LangSmith 遮蔽式效能追蹤：QA 實測驗收報告

* **規格**：[Spec-0020](../specs/0020-recruitment-chat-langsmith-masked-tracing-spec.md)，**決策**：[ADR-0020](../adr/0020-recruitment-chat-langsmith-masked-tracing.md)
* **日期**：2026-11-09
* **結論**：**PASS**。10/10 AC 已覆蓋；第 1 輪發現 2 項缺陷，Step 6 修正後全數通過。

## 1. 測試環境與方法
* Python 3.13 / Windows 11；langsmith 0.14.17、langchain-core 1.7.6、langgraph 1.x。
* 灰箱實測檔：[test_recruitment_tracing_e2e.py](../../tests/e2e/test_recruitment_tracing_e2e.py)。
  * **真實元件**：LangGraph 編排器、節點處理器、`CandidateProfileService`（真實執行緒池）、LangChain chat model 呼叫鏈（以 `BaseChatModel` 子類模擬 Gemini，產生真實 LLM run 與 `usage_metadata`），以及用 production 同組遮蔽參數建立的真實 langsmith `Client`（含 auto-batch 背景上傳）。
  * **雙層攔截**：(1) HTTP 位元組層：攔截式 `requests.Session` 記錄 SDK 實際送出的 multipart 位元組；(2) 序列化層：攔截 `langsmith.client.serialize_run_dict`，取得已遮蔽的 run payload 做結構驗證。
  * **植入標記**：虛構候選人姓名、使用者訊息標記 Email、LLM 輸出標記、例外訊息標記、原始 session_id、假 API 金鑰。
* 不連任何外網；所有樣本都在記憶體中動態建構，不讀取 `data/`、`resume/`。

## 2. 需求追溯矩陣 (RTM)
| TC | AC | 情境 | 結果 |
| :--- | :--- | :--- | :---: |
| TC-1 | AC-1 | 預設關閉時不建立 Client，invoke config 沒有 callbacks | PASS |
| TC-2 | AC-2 | 單一根 run（`recruitment_chat_turn`），含 route、jd_match、compose 節點；4 次執行緒池抽取加 1 次敘述，LLM run 全部有 parent | PASS |
| TC-3 | AC-3 | HTTP 位元組與 run payload 都不含任何植入標記；`inputs`/`outputs` 全為 `{}` | PASS |
| TC-4 | AC-4 | metadata 鍵都在白名單內；`usage_metadata.total_tokens=150` 有保留 | PASS（修正後） |
| TC-5 | AC-5 | 執行緒池內 LLM 拋出含個資的 `ValueError`，上報 error 只有 `ValueError`；該候選人降級，對話完成 | PASS |
| TC-6 | AC-6 | 端點不可達時，回覆與 shortlist 和未開追蹤時一致；回合 0.02s；收尾 3.01s（上限 3s） | PASS（修正後） |
| TC-7 | AC-7 | 根 run metadata 的 `trace_id`、`session_hash` 與日誌識別碼相同 | PASS |
| TC-8 | AC-8 | 全域 `LANGSMITH_TRACING=true` 時輸出 WARNING | PASS |
| TC-9 | AC-9 | `.env.example` 含 6 個鍵且金鑰為空值；DEBUG 層級的全部日誌不含金鑰與姓名 | PASS |
| TC-10 | AC-10 | 單元測試 427/427 OK；既有招募助手 E2E 28/28 OK（含真實 Gemini 的 LIVE 軌） | PASS |

補充驗證：真實 `ChatGoogleGenerativeAI` 的 `invocation_params`（會寫入 run `extra`）不含 API 金鑰。

## 3. 缺陷與修正（Step 6 第 1 輪）
| ID | 嚴重度 | 現象 | 根因 | 修正 |
| :--- | :---: | :--- | :--- | :--- |
| D1 | P3 | run `extra.runtime` 仍上傳函式庫和平台版本字串 | `runtime` 是 langchain-core `LangChainTracer._persist_run_single` 固定附加的，不受 langsmith `omit_traced_runtime_info` 控制，也沒有公開的關閉介面 | 列為 **DV-1 規格偏差**：內容只有版本與平台字串，沒有個資或內容。TC-4 改為嚴格限制 `runtime` 只能出現函式庫/平台版本鍵，`extra` 只能出現已知鍵 |
| D2 | P2 | 端點不可達時 `close()` 阻塞 44.7s，拖慢服務關閉 | SDK flush 對失敗的上傳做退避重試 | `close()` 改為在背景執行緒 flush，最多等 `RECRUIT_TRACING_FLUSH_TIMEOUT_SECONDS`（預設 5s）；逾時輸出 WARNING 並捨棄資料。新增單元測試與 TC-6 上限斷言 |

## 4. 對抗與邊界
* **執行緒池斷鏈突變測試**：把 `copy_context` 移除後，單元測試 `test_worker_threads_should_see_caller_contextvars` 隨即失敗，證明這個測試確實守住 AC-2。
* **錯誤訊息注入**：例外訊息內含姓名、Email 和 traceback，只保留類別名。
* **metadata 夾帶**：白名單內的鍵如果帶有巢狀或非純量值，一律剔除（單元測試）。

## 5. 殘餘風險
* 使用者若自行設定全域 `LANGSMITH_TRACING=true`，會繞過遮蔽。已有啟動警告和 `.env.example` 註記，但無法強制禁止。
* 尚未對真實 LangSmith 雲端做 LIVE 上傳實測（缺少帳號金鑰）。上傳格式由 SDK 負責，遮蔽在用戶端完成，已在 HTTP 位元組層驗證。
