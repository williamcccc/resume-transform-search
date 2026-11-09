# ADR-0019: HR 多輪對話招募助手：LangGraph 意圖路由固定節點圖與查詢期延遲結構化抽取

## 1. 狀態
已採納 (Accepted)

* **日期**：2026-11-09（提案）／2026-11-09（採納，Gate 2 PASS）
* **規格與驗收**：[Spec 0019](../specs/0019-recruitment-assistant-chat-spec.md)、[QA Report 0019](../qa_reports/0019-recruitment-assistant-chat-qa.md)
* **標籤**：`LangGraph`, `Gemini`, `Multi-turn Chat`, `Deterministic Ranking`, `Lazy Extraction`, `Content-Hash Cache`

## 2. 背景與問題陳述 (Context & Problem Statement)
既有履歷檢索（[ADR-0015](./0015-resume-search-web-interface.md)）僅提供語意相似度與年資/標籤過濾，無法依整份 JD 的必要/加分條件推薦並解釋理由、無法診斷哪個條件過嚴，也不支援多輪追問（「第 2 位」）。履歷庫缺乏「是否帶人、團隊規模、職級」等結構化欄位（P0 索引期抽取不在本期範圍）。

## 3. 評估選項 (Options Evaluated)
* **選項 A：完全自由之 Tool-calling Agent**：彈性高；但路由與排序不可重現，Prompt Injection 可影響工具呼叫，Token 成本不可控。
* **選項 B：意圖路由 + 固定節點圖（LangGraph），比對/排序/條件瓶頸全部確定性計算，LLM 僅負責抽取與敘述**：可重現、可測試、注入面小；需自行維護節點與狀態 Schema。
* **選項 C（結構化欄位來源）P0 索引期全量抽取**：查詢快；但需改寫入庫管線與索引 Schema，且未被查詢之履歷也要付費。
* **選項 D（結構化欄位來源）查詢期對候選池 Top-N 延遲抽取 + 內容 Hash 快取**：按需付費、未變更 0 Token；首次查詢有冷啟延遲。

## 4. 架構決策 (Decision Outcome)
採納 **選項 B + 選項 D**：
1. LangGraph / langchain-core / langchain-google-genai 僅存在於 `src/infrastructure/`；Domain 新增 Protocol 契約，Application 新增 `RecruitmentChatUseCase` 與純 Python 節點處理器。
2. Session State 結構化保存 `jd_requirements` 與 `shortlist`（序號 → candidate_id），指代由程式解析；Checkpointer 可抽換（預設 in-memory TTL+LRU，可選 Redis Stack）。
3. 條件瓶頸以 leave-one-out 合格人數確定性計算；引文逐字驗證，未提及明說；受保護屬性不入模型與排序。
4. 結構化抽取結果以 `recruit:v1:profile:{extractor_version}:{candidate_id}` + 內容 Hash 快取。

## 5. 8 大架構審查維度評估 (Architecture Review Analysis)
1. **個資隱私 (PII)**：敘述 LLM 僅收代稱；受保護欄位遮蔽後才送抽取；日誌不記錄原文與姓名。
2. **容量與極限 (Capacity)**：181 人 Profile 快取約 0.5MB；記憶體 Session LRU 上限與歷史裁切；Redis Checkpointer 具 TTL。
3. **非同步與演進 (Async / Evolution)**：Use Case 無狀態，節點為純函式，可演進至 SSE 串流或背景預熱。
4. **成本與熔斷 (Cost & Circuit Breaker)**：全庫暖機上限約 0.82M Token（一次性）；單輪呼叫預算；429 熔斷冷卻。
5. **可抽換性 (Portability & Decoupling)**：編排框架經 `IChatOrchestrator` 隔離；Checkpointer 工廠切換；LLM 經 Protocol 隔離。
6. **惡意輸入與配額硬上限 (Input Security & Bomb Defense)**：訊息/條件/候選池/履歷長度上限；圍欄標籤；排序與指代不經 LLM。
7. **向量索引演進與藍綠遷移 (Index Evolution & Migration)**：不改 `idx:resumes:v1`；新鍵空間帶版本、不落入索引前綴；`extractor_version` 自動失效。
8. **分散式併發與全鏈路可觀測性 (Concurrency & Observability)**：Session 鎖（Lock / Redis SET NX）；快取寫入冪等；每輪 trace_id。

## 6. 實作偏差與實施後評估 (Implementation Deviations & Post-Implementation Review)

| 編號 | 偏差 / 補強 | 原規劃 | 實際落地 | 理由 |
| :---: | :--- | :--- | :--- | :--- |
| DV-1 | 依賴版本 | `langchain-google-genai>=3.0,<4.0` | `langchain-google-genai>=4.4,<5.0`、`langgraph>=1.2,<2.0`、`langchain-core>=1.7.5,<2.0`、`langgraph-checkpoint-redis>=0.6,<1.0`（選用） | 4.x 為與 `google-genai` 2.x 相容之穩定線，要求 `google-genai>=2.20.0`；SDK 仍只在單一 Adapter 內，變動面可控 |
| DV-2 | 抽取失敗負快取（D-01） | 降級 Profile 不寫快取 | 新增行程內負快取，TTL 由 `RECRUIT_PROFILE_NEGATIVE_CACHE_TTL_SECONDS`（600）控制；`usage.profile_negative_hits` 獨立列出（G2-07） | 持續失敗之履歷每次查詢都重抽，違反紅線 5 |
| DV-3 | 延遲調參（D-02） | 並行 4、單輪 90 s、LLM 30 s | 並行 `RECRUIT_PROFILE_MAX_CONCURRENCY=8`、單輪 `RECRUIT_TURN_TIMEOUT_SECONDS=150`、LLM `RECRUIT_LLM_TIMEOUT_SECONDS=45`、抽取輸出上限 `RECRUIT_PROFILE_MAX_OUTPUT_TOKENS=1024`；Session 鎖 TTL = 單輪逾時 + `CHAT_SESSION_LOCK_TTL_BUFFER_SECONDS`（30） | 正式庫 181 人冷啟實測 80 s，原估 12~25 s 過於樂觀 |
| DV-4 | 歷史代稱化（G2-01） | 送 LLM 前以目前名單姓名遮蔽 | 助手回覆以「候選人 #N」代稱版寫入歷史，顯示時再代入姓名 | 換 JD 後舊名單姓名不在新名單中，原遮蔽法會漏 |
| DV-5 | 追問證據回退（G3-03） | 引文驗證失敗即 `NOT_MENTIONED` | 帶人 / 團隊規模類追問驗證失敗時，改用 Profile 已驗證之 `has_led_team` / `team_size` 證據走模板回答 | 降低 LLM 非逐字引文造成之假陰性；其他類別仍保守降級（列入待辦） |
| DV-6 | 受保護屬性遮蔽強化（G2-02、G3-02） | 逐行遮蔽 | Markdown/HTML 表格依表頭整欄遮蔽；詞表補英文與「生日」等詞 | Word 轉出之履歷常見表格欄位 |
| DV-7 | Redis 隔離（D-03） | 測試與 Checkpointer 用 db15 | Redis 8 RediSearch 不允許在 `db != 0` 建索引，Redis Checkpointer 與 E2E 臨時索引改用 db0 + 專屬前綴隔離；非 db0 時錯誤訊息附可行動提示 | 環境限制 |

### Rev2 偏差紀錄（實測缺陷修正：SKILL 比對、敘述截斷、引文驗證範圍；[Spec-0019 第六部](../specs/0019-recruitment-assistant-chat-spec.md)）

| 編號 | 偏差 / 補強 | 原規劃 | 實際落地 | 理由 |
| :---: | :--- | :--- | :--- | :--- |
| DV-8 | 抽取器版本拆分與 Profile 快取一次性失效 | JD 與 Profile 共用 `_version = sha256(system + jd + profile + model)` | 拆為 `jd_extractor_version`（含 `JD_SCHEMA_REVISION`）與 `profile_extractor_version`；Protocol 簽章不變，`extractor_version` 保留為等同 JD 版本之相容屬性 | 日後 JD Prompt 迭代不再使 181 份 Profile 快取失效。**本次公式變更使 Profile 快取一次性全量失效並重抽（已知且接受之成本）**，舊鍵依 TTL 自然過期 |
| DV-9 | `RECRUIT_LLM_THINKING_BUDGET` 作用範圍 | 僅影響敘述輸出 | 套用於主模型所有 LLM 操作（意圖分類、JD 抽取、敘述）；空值＝不傳、`0`＝關閉 thinking、正整數＝上限 | 單一建構參數。**風險**：不支援 thinking 的模型設為正整數時，可能使每次呼叫失敗；預設空值行為不變。已於 `.env.example` 註明 |
| DV-10 | SKILL 三態判定與次級瓶頸診斷 | 精確集合包含，僅 leave-one-out | `skills` OR 選項；結構化命中 → 全文詞面回退（非歧義 MET、歧義短詞或未驗證宣稱 UNKNOWN）→ 全文可得且零命中 UNMET；`RelaxationReport.strictest_requirement_ids` 與 `RelaxationItem.met_count`（全部 delta=0 時指出通過率最低條件）；詞面證據為中心視窗片段 | 修正 `baseline_qualified=0`、delta 全 0 導致瓶頸診斷失效。已接受風險（擴充 R9）：履歷詞面「提及」不等於「具備」，由 HR 依證據片段判讀；殘餘 P2 見 [Spec-0019 Backlog](../specs/0019-recruitment-assistant-chat-spec.md) |

**Rev2 實施後評估**：unit 398 項 OK、`audit_guardrails.py` Exit 0；QA 與 Gate 2（含複審）零 P0/P1，RTM 43/43。詳見 [QA-0019 §10~§12](../qa_reports/0019-recruitment-assistant-chat-qa.md)。

**實施後評估**：unit 298 項 OK、E2E FAKE 22 項 OK、LIVE 兩輪對話達標；`audit_guardrails.py` 100% PASSED；Gate 2 零 P0/P1（Step 6 共 3 輪）。LIVE 冷啟 Turn 1 約 23~28 s，同 JD 重查 0 次抽取，延遲抽取 + 快取策略確認可行。未結項目見 [QA-0019 待辦 Backlog](../qa_reports/0019-recruitment-assistant-chat-qa.md)。
