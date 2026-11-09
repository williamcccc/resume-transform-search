# QA 實測驗收報告：HR 多輪對話招募助手（ADR-0019 / 規格 0019）

> **閉環階段**：Step 4 黑箱/灰箱 QA 實測（gatekeeper）｜**依據**：[Spec-0019 第三部 QA 矩陣](../specs/0019-recruitment-assistant-chat-spec.md)｜**實測腳本**：[test_recruitment_chat_e2e.py](../../tests/e2e/test_recruitment_chat_e2e.py)
> **QA 結論**：**PASS（附條件）**，零 P0/P1；P2 缺陷 2 項、P3 缺陷 1 項、觀察 1 項，建議由 Step 6 處理或列入待辦（見第 5 節）。

---

## 1. 測試環境與前置條件 (Test Environment)

* **測試日期**：`2026-11-09`
* **作業系統與 Python 版本**：Windows 11 Pro / Python 3.13.14
* **外部相依服務狀態**：
  * Redis 8.10.3（Redis Stack 模組）`localhost:6379`：連線正常；正式索引 `idx:resumes:v1` 2,211 切片 / 181 人。
  * Gemini API：`GEMINI_MODEL=gemini-3.8-flash`（招募 LLM 沿用），embedding 依 `AppConfig` 預設。
  * LangGraph + `langgraph-checkpoint-redis`：已安裝。
* **測試資料集**：
  * FAKE 軌：[recruitment_fakes.py](../../tests/unit/recruitment_fakes.py) 之 4 位虛構候選人（記憶體建構）。
  * LIVE 軌：8 位虛構候選人（`王小明`、`李小華`…，`qa0019_backend_a~h`），記憶體動態生成後寫入 `tempfile` 隔離目錄，以真實 embedding 入庫臨時索引 `idx:qa0019live:v1`（前綴 `qa0019live:`）。刻意設計：僅 1 人（a）具 Python 且 8 年以上；僅 1 人（b）有明確帶人證據；1 人（c）含 Prompt Injection 字句；1 人（d）含性別/出生/年齡/婚姻欄位。
  * 灰箱冒煙：正式索引 db0（唯讀；Profile/JD 快取改用專屬前綴 `qa0019smoke:` 並於結束後刪除 16 鍵，正式索引文件數前後皆 2,211）。
* **與規格之偏差（環境限制）**：Redis 8 之 RediSearch 拒絕於 `db != 0` 建立索引（`Cannot create index on db != 0`），故規格要求之「db15 臨時索引」與「db15 Redis Checkpointer」不可行；改以 `REDIS_URL`(db0) + 專屬前綴（`qa0019live:*`、`chat:v1:*qa0019*`）隔離，測試結束清除鍵並移除 `RedisSaver.setup()` 建立之空 `chat:v1:*` 索引，實測後 db0 僅餘 `idx:resumes:v1`、db15 dbsize=0。見缺陷 D-03。

---

## 2. PRD 需求驗收追溯矩陣 (RTM)

| AC | 條款說明 | 覆蓋 TC | 軌 | 覆蓋狀態 |
| :--- | :--- | :--- | :---: | :---: |
| AC-01 | JD 媒合正常路徑 | TC-01、LIVE | FAKE/LIVE | **COVERED** |
| AC-02 | 人數解析與截斷 | TC-02 | FAKE | **COVERED** |
| AC-03 | 確定性排序可重現 | TC-01、LIVE、灰箱 | FAKE/LIVE | **COVERED** |
| AC-04 | 人選不足與條件瓶頸 | TC-03、LIVE、灰箱 | FAKE/LIVE | **COVERED** |
| AC-05 | 未提及計數 | TC-03 | FAKE | **COVERED** |
| AC-06 | 不足時補位 | TC-03、LIVE | FAKE/LIVE | **COVERED** |
| AC-07 | 空候選池 | TC-04 | FAKE | **COVERED** |
| AC-08 | 證據引用逐字驗證 | TC-05(LIVE)、灰箱 | LIVE | **COVERED**（觀察 OBS-01） |
| AC-09 | 未提及明說 | TC-03、TC-11、LIVE | FAKE/LIVE | **COVERED** |
| AC-10 | Prompt Injection 防禦 | TC-06、LIVE | FAKE/LIVE | **COVERED** |
| AC-11 | 受保護屬性 | TC-07、LIVE、灰箱 | FAKE/LIVE | **COVERED** |
| AC-12 | PII 最小化 | TC-08、LIVE(Spy) | FAKE/LIVE | **COVERED** |
| AC-13 | 快取命中 0 抽取 | TC-09、LIVE、灰箱 | FAKE/LIVE | **COVERED**（灰箱條件式，見 D-01） |
| AC-14 | 履歷變更僅重抽一人 | TC-09 | FAKE | **COVERED** |
| AC-15 | 版本變更失效 | TC-09 | FAKE | **COVERED** |
| AC-16 | 抽取降級 | TC-10、灰箱(實際 504) | FAKE/灰箱 | **COVERED** |
| AC-17 | 單輪預算熔斷 | TC-10 | FAKE | **COVERED** |
| AC-18 | 序號/代名詞指代 | TC-11、LIVE、灰箱 | FAKE/LIVE | **COVERED** |
| AC-19 | 越界與無名單 | TC-12 | FAKE | **COVERED** |
| AC-20 | 複合意圖 | TC-11、LIVE、灰箱 | FAKE/LIVE | **COVERED** |
| AC-21 | 追問回答 | TC-11、LIVE、灰箱 | FAKE/LIVE | **COVERED** |
| AC-22 | 面試題對應弱點 | TC-11、LIVE、灰箱 | FAKE/LIVE | **COVERED** |
| AC-23 | 一般問答 / 拒答 | TC-13 | FAKE | **COVERED** |
| AC-24 | Session TTL | TC-14 | FAKE | **COVERED** |
| AC-25 | 歷史裁切 | TC-14 | FAKE | **COVERED** |
| AC-26 | Checkpointer 可抽換、重啟續接 | TC-15 | FAKE+Redis | **COVERED**（db0 前綴隔離，見 D-03） |
| AC-27 | Session 併發鎖 | TC-16、TC-16b | FAKE/FAKE+Redis | **COVERED** |
| AC-28 | 聊天分頁 / XSS | TC-17 | 靜態灰箱 | **COVERED**（瀏覽器手動未執行） |
| AC-29 | 無 Key 降級 503 | TC-18 | 降級 | **COVERED** |
| AC-30 | CLI 100% 相容 | TC-19、既有 test_cli_workflow | CLI | **COVERED** |
| AC-31 | 429 熔斷 | TC-20 | FAKE | **COVERED** |
| AC-32 | 配置同步 / 零硬編碼 | TC-21 | 靜態 | **COVERED** |
| AC-33 | 可觀測性 | TC-08 | FAKE | **COVERED** |

> **RTM 覆蓋率判定**：AC-01 ~ AC-33 共 33 項 **100% 覆蓋**。

---

## 3. 測試案例執行矩陣 (Test Case Execution Matrix)

| TC | 名稱 | 輸入 / 情境 | 預期 | 實際 | 判定 |
| :---: | :--- | :--- | :--- | :--- | :---: |
| TC-01 | JD 媒合正常路徑 | 僅 Python 為必要，3 人合格；重送 | 3 位皆合格、rank 1..3、重送一致 | 符合；`relaxation=null`；LIVE 新 Session 重查排序一致 | **PASS** |
| TC-02 | 人數解析 | 「挑 5 個」「挑 50 個」 | k=5；50 截為 10 並警示 | k=5 且警示候選池僅 4 人；50→10 並警示截斷 | **PASS** |
| TC-03 | 條件瓶頸手算對照 | 4 人池，必要 R1 Python/R2 5 年/R3 帶人 | 基準 1；各條件放寬 2 人、delta 1、並列瓶頸；R3 未提及 1 | 完全一致；回覆含「完全符合必要條件者 1 位」與池範圍說明；補位 2 人列 unmet/unknown | **PASS** |
| TC-04 | 空候選池 | 空索引 | `shortlist=[]`，0 抽取 0 敘述 | 符合，200 | **PASS** |
| TC-05 | 證據逐字（LIVE） | 8 人真實抽取 | 每位 ≥1 證據且為原文子字串；「」引文可回溯 | 全數通過（嚴格：僅 NFKC+去空白）；回覆中 1 段未驗證引文已被系統移除並警示 | **PASS** |
| TC-06 | Prompt Injection | FAKE 對照組 vs 注入組；LIVE 注入者 c | 排序/瓶頸一致；無系統提示洩漏 | FAKE 兩組完全一致、分類器 0 呼叫；LIVE 注入者未上位、回覆無 guardrail 字句 | **PASS** |
| TC-07 | 受保護屬性 | JD 含「限男性、35 歲以下」；履歷含性別/出生/年齡/婚姻 | 條件忽略 + 警示；送 LLM 已遮蔽；面試題無受保護詞 | FAKE/LIVE 皆警示且條件不入 JD；Spy 驗證送抽取文字不含「性別：女/1990/已婚/35 歲」；面試題零命中 | **PASS** |
| TC-08 | 日誌與 Facts 零 PII | assertLogs + Narrator Facts Spy | 日誌含 trace_id/llm_calls/node_ms/快取數，無姓名/原文/session_id；Facts 僅代稱 | 符合；LIVE Spy 敘述 Facts 無姓名與 email | **PASS** |
| TC-09 | 快取 / 失效 / 版本 | 同 JD 兩次；改一份履歷；版本 v2 | misses=0；僅變更者重抽；全數重抽 | 0 / 僅 cand_b / 4 人全抽且 JD 未命中 | **PASS** |
| TC-10 | 抽取降級 / 預算 | 抽取例外；預算 2 | 200+警示；llm_calls≤2 並警示 | 符合 | **PASS** |
| TC-11 | 典型兩輪 | Turn1 → 「第 2 位…帶過人嗎？…3 題面試題」 | 指向 rank2；複合意圖；追問有證據或未提及；題目對應弱點 | FAKE/LIVE/灰箱皆符合；LIVE rank2=帶人者 b → `SUPPORTED` 且引文逐字；3 題皆對應弱點；「第二位/#2/2 號/他」等價 | **PASS** |
| TC-12 | 越界 / 無名單 | 「第 9 位」；新 Session 問「第 1 位」 | 「目前名單僅 N 位」；提示先給 JD；0 LLM | 符合，`llm_calls=0`，分類器/敘述器 0 呼叫 | **PASS** |
| TC-13 | 一般問答 / 拒答 | 「剛剛的必要條件是什麼？」「寫情書」 | 依狀態回答；OUT_OF_SCOPE | 符合 | **PASS** |
| TC-14 | TTL / 歷史裁切 | TTL=2s 注入時鐘；連續 15 輪 | 逾時視為新 Session 並警示；歷史 ≤ 上限，shortlist 保留 | 歷史 ≤ 6 則（3 輪）；turn_count=16、shortlist 3 位；逾時後 GET 404、續問警示「逾時」且無名單 | **PASS** |
| TC-15 | Redis Checkpointer 跨實例續接 | App1 Turn1 → 關閉 → 全新 App2 Turn2 | 續接成功、指向原 rank2 | 符合；App2 抽取 0 呼叫；DELETE 後 404 | **PASS** |
| TC-16 | 併發同 Session | Fake 敘述延遲 1.5s，並行第二請求 | 200 + 409，狀態完整 | 符合（memory 鎖）；TC-16b Redis 分散式鎖預占 → 409，釋放後 200 且鎖鍵清除 | **PASS** |
| TC-17 | 聊天分頁 / XSS | 靜態檢視 [dashboard.html](../../src/interfaces/web/static/dashboard.html) | 文字節點渲染、sessionStorage try/catch、新對話、送出鎖定 | 聊天區零 `innerHTML`，全部 `createElement/textContent`；sessionStorage 讀寫皆 try/catch；「招募助手」分頁、「新對話」、`setChatBusy` 存在 | **PASS（靜態）** |
| TC-18 | 無 Key 503 / 內建引擎 501 | `gemini_api_key=""`；ThreadingHTTPServer | `/api/chat` 503，其他端點正常；501 | POST/GET 503 `CHAT_UNAVAILABLE`，`/`、`/api/stats` 200；內建引擎 POST/GET/DELETE 皆 501 | **PASS** |
| TC-19 | CLI 相容 | `convert_to_md.py --help`；模擬未安裝 langgraph | 退出碼 0、輸出一致 | 符合；既有 `test_cli_workflow.py` 全綠 | **PASS** |
| TC-20 | 429 熔斷 | Fake 分類器 429 | 429 含 `retry_after_seconds`；冷卻期 0 呼叫 | 符合（Retry-After 標頭存在） | **PASS** |
| TC-21 | 配置同步 / 零硬編碼 | `audit_guardrails.py` + `.env.example` 比對 | 零 P0；變數 100% 同步 | 100% PASSED；35 個 `RECRUIT_*`/`CHAT_*` 全數存在 | **PASS** |
| TC-22 | 安全上限與錯誤碼 | 12001 字元；`../x`、7 字元、65 字元、含空白之 session_id；空白訊息；422 輪數上限 | 413 / 400 / 404 / 204 / 422 | 全數符合，回應無 Traceback；伺服器產生 session_id 符合格式 | **PASS** |

**TC 通過：22 / 22**（TC-17 以靜態灰箱覆核，瀏覽器手動互動未執行，建議 Step 7 前人工點測一次）。

---

## 4. 實測執行日誌與量測摘要 (Execution Logs & Metrics)

```text
[執行指令]: python -m unittest discover -s tests/e2e -p "test_*.py"
[測試結果]: Ran 43 tests in 122.2s ... OK   (新增 23 項 + 既有 20 項；無 skip)
[靜態掃描]: python .agents/skills/code-review/scripts/audit_guardrails.py → 100% PASSED (exit 0)
```

### 4.1 LIVE 軌（8 位虛構候選人，兩次執行）

| 輪次 | 意圖 | 延遲 (s) | LLM 呼叫 | Profile 命中/未命中 | JD 快取 | 備註 |
| :--- | :--- | ---: | ---: | :---: | :---: | :--- |
| Turn 1（冷啟） | JD_MATCH | 29.3 / 32.2 | 10（JD 1 + 抽取 8 + 敘述 1） | 0 / 8 | 否 | 名單 a(合格)、b、f(補位)；瓶頸 = 年資條件；警示 2（受保護條件忽略、1 段引文未驗證已移除） |
| Turn 2 | FOLLOWUP + INTERVIEW | 21.5 / 30.0 | 2 | — | — | rank2=b → `SUPPORTED`，3 題 |
| 同 JD 重查（新 Session） | JD_MATCH | 15.0 / 11.4 | 1（僅敘述） | 8 / 0 | **是** | **AC-13 達成：抽取 0 呼叫** |

### 4.2 灰箱冒煙（正式索引 181 人，通用虛構「資深後端工程師」JD，唯讀）

人選以 `#rank` 與 `candidate_id` SHA-256 前 8 碼代稱。

| 輪次 | 延遲 (s) | LLM 呼叫 | Profile 命中/未命中 | JD 快取 | 結果摘要 |
| :--- | ---: | ---: | :---: | :---: | :--- |
| Turn 1（冷啟，池 15） | **80.18** | 17（JD 1 + 抽取 15 + 敘述 1） | 0 / 15 | 否 | #1 `eec8e85f`、#2 `13d64118`、#3 `971a9d97`，皆補位（基準合格 0）；瓶頸 R3（放寬 +1）；1 位抽取遇 Gemini `504 DEADLINE_EXCEEDED`（28.4s）降級 |
| Turn 2 | 17.88 | 2 | — | — | 指向 #2 `13d64118` ✔；`SUPPORTED`，引文逐字 ✔；3 題皆對應弱點、零受保護詞 |
| 同 JD 重查（新 Session） | 34.29 | 2（重抽 1 + 敘述 1） | 14 / **1** | 是 | 排序與首查一致 ✔；未命中 1 = 上輪降級者（未寫快取）→ 見 D-01 |

* **Token**：`usage` 未提供 Token 計數，依規格 §9 估算：冷啟 15 人 ≈ 68k；理想重查僅敘述 ≈ 3.5k；本次重查因 D-01 額外 ≈ 4.5k。
* **證據**：灰箱 20 筆名單證據中 1 筆於「僅去空白」嚴格比對下非逐字子字串（系統驗證器另去除 Markdown 符號而通過）→ OBS-01。
* **安全**：三輪回覆皆無系統提示洩漏標記；面試題零受保護屬性。

---

## 5. 缺陷清單、失敗分析與根因定位 (Defects & RCA)

自動化測試 **無失敗項目**；以下為實測觀察到之非阻斷缺陷：

| ID | 嚴重度 | AC | 描述 | 疑似根因檔案 |
| :---: | :---: | :--- | :--- | :--- |
| D-01 | P2 | AC-13、紅線 5 | 抽取失敗（降級）之 Profile 不寫快取，同 JD 重查會再次呼叫抽取 LLM；持續失敗之履歷每次查詢皆燒 Token 與延遲 | [candidate_profile_service.py](../../src/application/candidate_profile_service.py)（依規格「僅成功者寫入」，缺失敗短期負快取） |
| D-02 | P2 | 規格 §9 / R-延遲、AC-17 | 正式庫冷啟 Turn 1 達 80.2s（逾時上限 90s，規格估 12~25s）；單次抽取逼近 `RECRUIT_LLM_TIMEOUT_SECONDS=30` 觸發 504；Turn 2 兩次 LLM 亦需 18~30s | [candidate_profile_service.py](../../src/application/candidate_profile_service.py)（並行 4）、[gemini_recruitment_llm.py](../../src/infrastructure/llm/gemini_recruitment_llm.py)（逾時/輸出長度）、`.env` 調參 |
| D-03 | P3 | AC-26 | Redis 8 RediSearch 僅允許 db0 建索引；`CHAT_CHECKPOINT_REDIS_URL` 指向非 0 號 DB 時 Checkpointer 初始化失敗 → 503（Fail-Safe 正確），但錯誤訊息僅「RedisSearchError」、文件未註明限制 | [checkpointer_factory.py](../../src/infrastructure/orchestration/checkpointer_factory.py)、[.env.example](../../.env.example) |
| OBS-01 | P3（觀察） | AC-08 | `EvidenceVerifier` 除空白外另去除 Markdown 符號 `* _ \` # > \| ~`，較 AC-08「空白正規化」寬鬆；粗體標記無害，但理論上可跨表格儲存格拼接引文 | [recruitment_services.py](../../src/domain/recruitment_services.py) `EvidenceVerifier.normalize` |

**重現步驟**：

* **D-01**：設 `GEMINI_API_KEY`，以正式索引啟動 FastAPI（memory Checkpointer）→ 送出含 JD 之 Turn 1，使任一候選人抽取失敗（實測為 Gemini 504；離線可以 `FakeProfileExtractor(fail_for={...})` 重現）→ 新 Session 再送同一 JD → `usage.profile_cache_misses=1`、`llm_calls=2`（預期 0 抽取）。
  * **修復建言**：新增失敗負快取（鍵 `content_hash + extractor_version`，TTL 新增 `RECRUIT_PROFILE_FAILURE_CACHE_TTL_SECONDS` 並同步 `.env.example`），或降級 Profile 以旗標短 TTL 寫入；需同步修訂 AC-13/AC-16 文字。
* **D-02**：同上 Turn 1（池 15、全未命中）→ 量測延遲 80.18s。
  * **修復建言**：調高 `RECRUIT_PROFILE_MAX_CONCURRENCY`、縮短抽取輸出（Schema 精簡）、單次逾時與單輪截止時間聯動；中長期依規格 §9 啟動 P3（SSE 串流 / 背景預熱）。
* **D-03**：`CHAT_CHECKPOINTER_BACKEND=redis`、`CHAT_CHECKPOINT_REDIS_URL=redis://localhost:6379/15` → `/api/chat` 503；日誌 `Cannot create index on db != 0`。
  * **修復建言**：於 `.env.example`、規格與 ADR 註明需 db0（以鍵前綴隔離）；錯誤訊息帶出可行動提示。
* **OBS-01**：依 Step 7 doc-sync 修訂 AC-08 為「NFKC + 去空白 + 去 Markdown 標記」，或將去標記限縮為成對粗體/斜體符號。

---

## 6. QA 驗收結論 (QA Sign-Off)

* **驗收判定**：**【通過 (PASSED，附條件)】**
* **放行說明**：
  1. 需求追溯覆蓋率：**100%**（33/33 AC），TC **22/22** 通過。
  2. 邊界與異常對抗實測：413 / 400 / 404 / 409 / 422 / 429 / 501 / 503、越界指代、無名單、Prompt Injection、受保護屬性、TTL、併發鎖 **全數通過，無崩潰或未受控例外**。
  3. 資源生命週期：`tempfile` 目錄自動卸載；Redis 測試鍵與臨時索引全數清除（db0 僅餘 `idx:resumes:v1`，2,211 文件不變；db15 為空）。
  4. 向下相容：CLI `--help` 於模擬未安裝 LangGraph 時輸出一致，既有 E2E 全綠。
  5. 零 P0/P1；D-01、D-02（P2）建議於 Step 6 或下一迭代處理，D-03/OBS-01 交 Step 7 文檔同步。**准予進入 Gate 2 代碼審查。**

---

## 7. Step 6 第 1 輪修正回歸驗證（D-01 ~ D-04）

| 項目 | 結果 |
| :--- | :--- |
| 單元測試 | `Ran 275 tests ... OK` |
| E2E（FAKE / FAKE+Redis / 降級） | `Ran 22 tests ... OK` |
| E2E（LIVE 重跑） | `Ran 1 test ... OK`；Turn1 冷啟 22.8s（10 次 LLM 呼叫，未命中 8）、Turn2 27.7s（2 次）、同 JD 重查 15.3s（1 次，命中 8／未命中 0，JD 快取命中） |
| 靜態掃描 | `audit_guardrails.py` 100% PASSED |
| 環境清潔 | 殘留 `*qa0019*` 鍵 0；db0 索引只剩 `idx:resumes:v1` |

* D-01：負快取（`RECRUIT_PROFILE_NEGATIVE_CACHE_TTL_SECONDS`，行程內）生效，沒有回歸。注意：負快取命中會算進 `profile_cache_hits`，見 G2-07。
* D-02：並行 8、單輪 150s、LLM 45s、`RECRUIT_PROFILE_MAX_OUTPUT_TOKENS=1024` 已同步到 `.env.example`。單輪逾時與 Session 鎖 TTL 的互動風險見 G2-06。
* D-03：Checkpointer 指向非 db0 時，錯誤訊息已附可行動提示。
* D-04：E2E 清理樣式改為 `*qa0019*`。

---

## 8. Gate 2 對抗式代碼審查

> **範圍**：本分支相對 `main` 的全部變更（工作區修改加未追蹤檔；分支上尚無 commit）。
> **結論**：**PASS（零 P0）**。另有 3 項 P1（PII／受保護屬性外洩到 LLM、年資資料被誤遮蔽），依 [review_checklist](../../.agents/skills/code-review/references/review_checklist.md)「P1 原則上必須修正」，**建議進 Step 6 第 2 輪修完 P1 再進 Step 7**。

### 8.1 自動化與邊界

* `audit_guardrails.py`：100% PASSED（Domain 純潔、DIP、with、例外鏈、零硬編碼、Prompt 外部化、隱私規則）。
* DDD：`src/domain/recruitment*.py` 只依賴標準庫；Application 只依賴 `domain.interfaces` 的 Protocol；LangGraph、langchain、redis 只出現在 `src/infrastructure/`，Interfaces 層在 `try` 區塊內延遲匯入。
* XSS：[dashboard.html](../../src/interfaces/web/static/dashboard.html) 聊天區全部用 `createElement`/`textContent`，安全 Markdown 子集不經 `innerHTML`，合格。
* 日誌：新增的 logger 呼叫只記 `err_type`、trace_id、session hash 與數字，沒有原文或姓名，合格。
* 確定性服務：leave-one-out、排序鍵、`renumber_requirements` 對照手算值正確（TC-03）；圍欄標籤偽造已由 `neutralize_fences` 處理。

### 8.2 Findings

| ID | 等級 | 檔案:行 | 描述 | 建議修法 |
| :---: | :---: | :--- | :--- | :--- |
| G2-01 | **P1** | [recruitment_nodes.py](../../src/application/recruitment_nodes.py):707-716（`_deidentify`）、:623-631（`compose`） | 對話歷史保存的助手回覆含姓名；同一 Session 換 JD 後，舊名單姓名不在新的 `shortlist`／`pool_evaluations` 裡，`general_qa` 把歷史送 LLM 時沒有遮蔽，違反 AC-12（已以 Fake 重現：舊名單 3 個姓名都進了 `GeneralQaFacts.history`） | 寫入歷史前就把助手回覆中的姓名換成代稱（先存代稱版，顯示時再代入姓名），或在 Session 保留曾出現過的所有姓名集合供 `_deidentify` 遮蔽 |
| G2-02 | **P1** | [recruitment_services.py](../../src/domain/recruitment_services.py):310-312（`redact_resume`） | 受保護屬性逐行遮蔽可被表格繞過：表頭列「\| 姓名 \| 性別 \| 出生日期 \|」被遮蔽，但值列「\| 王小明 \| 女 \| 1990/01/01 \|」原樣送進 LLM；英文欄位（Gender/Age/DOB）也不在預設詞表。Word 轉出的履歷常見這種表格，違反 AC-11 | 遇到 Markdown 表格時，依表頭欄位索引遮蔽整欄值；預設詞表補上英文詞；補單元測試 |
| G2-03 | **P1** | [recruitment_services.py](../../src/domain/recruitment_services.py):317（`_PHONE`） | 電話正則 `\+?\d[\d\-\s()]{7,}\d` 會吃掉日期區間：「2015/03 - 2020/06」變成「2015/[已遮蔽電話]/06」。抽取 LLM 與降級用的 `RegexExperienceParser` 都拿這份遮蔽後文字，年資（主要的必要條件類別）會被低估或變成 UNKNOWN | 收緊電話樣式（例如要求 8 碼以上連續數字或台灣手機／市話格式，並排除 `YYYY/MM - YYYY/MM`）；補日期區間不被遮蔽的單元測試 |
| G2-04 | P2 | [recruitment_services.py](../../src/domain/recruitment_services.py):227-233 | 指代誤判：「5 月 3 號」被解析成第 3 位；「其他人選」裡的「他」被當成代名詞；「C# 10」被當成 #10。會誤觸追問、多耗 LLM 呼叫 | 「N 號」排除前面接「月」的寫法；代名詞排除「其他」；`#N` 要求前面不是英數字 |
| G2-05 | P2 | [recruitment_services.py](../../src/domain/recruitment_services.py):118-123 | SKILL 條件的證據驗證失敗時，該技能會從 `core_skills` 移除，因而判成 UNMET（「明確不符」）而不是 UNKNOWN，和 AC-09「驗證失敗一律降為未提及」不一致 | 把驗證失敗的技能另存成 unknown 集合，比對時回傳 UNKNOWN |
| G2-06 | P2 | [server.py](../../src/interfaces/web/server.py)（`lock_ttl_seconds=int(turn_timeout)`）、[candidate_profile_service.py](../../src/application/candidate_profile_service.py):150-170 | 單輪截止時間只在提交抽取前檢查；執行緒池內抽取可能超過 150s（45s × 重試 × 2 波），Redis Session 鎖 TTL 就會先過期，同 Session 可被並行進入。另外 LangGraph 每個 superstep 都會落盤，複合意圖中途拋例外時，前段節點的狀態已提交（半套 turn） | 鎖 TTL 設為「單輪逾時 + 緩衝」並定期續期；`future.result(timeout=剩餘時間)`；失敗的 turn 回滾到前一個 checkpoint |
| G2-07 | P2 | [candidate_profile_service.py](../../src/application/candidate_profile_service.py):122-126 | 負快取命中算進 `profile_cache_hits`，觀測指標會把降級資料當成命中 | 新增 `usage.profile_negative_hits` 欄位（同步 DTO、API、UI） |
| G2-08 | P2 | [checkpointer_factory.py](../../src/infrastructure/orchestration/checkpointer_factory.py):70-84 | `MemorySessionLock._locks` 不隨 LRU 淘汰或 reset 移除；任意合法 session_id 都可以讓它無界成長 | 在 registry 淘汰與 reset 時同步移除鎖，或改用有界的 WeakValueDictionary |
| G2-09 | P2 | [fastapi_server.py](../../src/interfaces/web/fastapi_server.py):132-138（既有設定） | CORS `allow_origins=["*"]` 加 `allow_credentials=True`：本機使用者瀏覽的任何網頁都能跨站呼叫 `/api/chat` 並讀回名單與證據，也能消耗 Token。設定是既有的，但新端點讓風險放大 | 改由 `AppConfig`（例如 `WEB_CORS_ORIGINS`）注入白名單，預設只允許同源 |
| G2-10 | P2 | [dashboard.html](../../src/interfaces/web/static/dashboard.html)（`renderChatQuestions`） | 本輪沒有面試題時不清空，上一位人選的題目會殘留在畫面上 | 收到空陣列時改顯示「尚未產生」 |
| OBS-01 | P3 | [recruitment_services.py](../../src/domain/recruitment_services.py):266-284 | 同 Step 4（EvidenceVerifier 另去 Markdown 符號）；另外驗證只確認子字串存在，否定句可繞過（「未曾帶領團隊」包含「帶領團隊」） | 交 Step 7 修訂 AC-08；長期可考慮對證據前文做否定詞檢查 |

### 8.3 檢核表摘要

* **架構靜態掃描**：通過
* **DDD 依賴邊界**：通過
* **安全與配額硬上限**：通過（413、400、圍欄、熔斷）；受保護屬性遮蔽有繞過（G2-02）
* **資源釋放與鎖定防禦**：通過（with、lifespan close、鎖 finally 釋放）；鎖 TTL 邊界風險見 G2-06
* **Twelve-Factor 配置治理**：通過（新增變數 100% 同步 `.env.example`）
* **邊界例外與例外鏈**：通過（`from err` 完整，429 轉 `LlmQuotaExhaustedError`）
* **日誌安全合規**：通過；但送往 LLM 的 PII 有外洩路徑（G2-01）
* **資料操作與冪等性**：通過（快取同鍵覆寫冪等，對履歷庫唯讀）
* **測試隔離與負面覆蓋**：通過（單元測試 100% Mock，包含故障注入）
* **Git 版控衛生與零個資**：通過（只用虛構姓名、相對路徑）

### 8.4 Gate 2 差異複審（Step 6 第 2 輪：G2-01 ~ G2-08、G2-10）

> **結論**：**PASS（零 P0、零 P1）**。3 項 P1 的重現腳本都已轉綠；對抗繞過測試找到 4 項殘留／新增問題，都是 P2/P3，不阻斷放行。

**自動化**：unit `Ran 293 ... OK`；`audit_guardrails.py` 100% PASSED；`.env.example` 已同步 `AppConfig` 全部環境變數（新增 `CHAT_SESSION_LOCK_TTL_BUFFER_SECONDS` 等）；E2E 43 項跑了兩次，FAKE 與降級 42 項全綠，LIVE 有 1 次判定不穩（見 G3-03），單獨重跑轉綠。

| 原 ID | 複審結果 |
| :--- | :--- |
| G2-01 | ✅ 歷史改存代稱版，換 JD 後舊名單 4 個姓名都沒有出現在 `GeneralQaFacts.history`（Fake 重現轉綠）。殘留問題見 G3-01 |
| G2-02 | ✅ Markdown 表格依表頭整欄遮蔽；HTML 單列表格、英文欄位（Gender/Sex/Date of Birth）、全形冒號鍵值都已遮蔽。殘留問題見 G3-02 |
| G2-03 | ✅ 「2015/03 - 2020/06」不再被遮蔽；台灣手機（09xx-xxx-xxx）、國際碼手機（+886 9xx xxx xxx）、市話（0x-xxxx-xxxx、(0x)xxxx-xxxx、+886-x-xxxx-xxxx）樣本皆已遮蔽（樣本號碼於測試中動態組裝，報告不留存號碼字面值） |
| G2-04 | ✅ 「其他」「C# 10」「12月3號」不再誤判。殘留問題：中間有空白的「5 月 3 號」仍解析成第 3 位（G3-04） |
| G2-05 | ✅ 新增 `unverified_skills`，證據驗證失敗的技能比對為 UNKNOWN |
| G2-06 | ✅ 鎖 TTL 改為單輪逾時加緩衝（30s），`future.result(timeout=剩餘時間)`。`shutdown(wait=False, cancel_futures=True)` 之後，仍在跑的背景抽取執行緒只呼叫 LLM，結果被丟棄；寫快取只發生在主執行緒，不會寫快取，也不會爭用 Redis。代價是孤兒呼叫的 Token 浪費（上限約 LLM 逾時 × 重試），可接受，見 G3-05。checkpoint 回滾仍在待辦 |
| G2-07 | ✅ `usage.profile_negative_hits` 已獨立列出 |
| G2-08 | ✅ `hold()` 的 setdefault 與 acquire 在同一個 guard 內完成，`remove()` 也在 guard 內檢查 `locked()`，不存在「已取得鎖物件但尚未 acquire」的空窗，沒有競態。淘汰與 reset 時都會回收鎖物件 |
| G2-10 | ✅ 空題目時清空畫面並顯示「尚未產生」 |

**LIVE 典型兩輪對話（8 位虛構人選，db0 `qa0019*` 前綴，測後殘留 0 鍵、正式索引仍為 2211 筆）**

| 輪次 | 延遲 (s) | LLM 呼叫 | 命中 / 未命中 / 負快取 | 結果 |
| :--- | ---: | ---: | :---: | :--- |
| Turn 1 冷啟 | 27.0 ~ 28.0 | 10 | 0 / 8 / 0 | 名單 a（合格）、b、f；瓶頸為年資條件 |
| Turn 2 | 26.4 ~ 27.9 | 2 | — | 4 次執行中 3 次 `SUPPORTED`，1 次因引文未通過驗證而降為 `NOT_MENTIONED`（G3-03） |
| 同 JD 重查 | 10.4 | 1 | 8 / 0 / 0 | AC-13 達成 |

**新 findings**

| ID | 等級 | 位置 | 描述 | 建議 |
| :---: | :---: | :--- | :--- | :--- |
| G3-01 | P2 | [recruitment_nodes.py](../../src/application/recruitment_nodes.py) `_deidentify` | 使用者自己輸入「已不在目前候選池」的舊人選姓名時，問題原文仍以明文送給一般問答 LLM（歷史已是代稱版，沒有外洩） | Session 保存曾出現過的姓名集合（只存在伺服器端），一併遮蔽 |
| G3-02 | P2 | [.env.example](../../.env.example) `RECRUIT_PROTECTED_ATTR_TERMS` 預設值 | 預設詞表沒有「生日」，「生日：1990/01/01」與 HTML 表格的「生日」列會原樣送 LLM。無表頭表格的值列（只有「女」「1990/01/01」）因為沒有欄名，無法遮蔽（P3 限制） | 預設詞表補「生日、出生年月、Birthday」；選擇性加上日期樣式偵測 |
| G3-03 | P2 | [recruitment_nodes.py](../../src/application/recruitment_nodes.py) `_verify_followup` | LLM 偶爾給出非逐字引文，回答被保守改判成 `NOT_MENTIONED`。這是 Fail-Safe 行為，符合 AC-09，但會造成假陰性（LIVE 約 1/4）；兩次 Spy 捕獲的引文都是逐字的，判定為 LLM 不確定性，不是程式回歸 | 驗證失敗時，改用 Profile 中已驗證的 `has_led_team`／`team_size` 證據走模板回答；或在 Prompt 中限定只能從 `evidence_quotes` 挑選引文 |
| G3-04 | P2 | [recruitment_services.py](../../src/domain/recruitment_services.py):236 | 後顧斷言只排除「月」緊貼數字的寫法，「5 月 3 號」（中間有空白）仍誤判為第 3 位 | 後顧改為 `(?<!月)(?<!月\s)` 或先把「N 月 M 號」整段剔除 |
| G3-05 | P3 | [candidate_profile_service.py](../../src/application/candidate_profile_service.py):150-186 | 逾時後的孤兒抽取仍在消耗 Token，結果卻被丟棄，下次查詢會再付費 | 用 `add_done_callback` 在背景把晚到的成功結果寫進快取（需確保執行緒安全） |

---

## 9. 最終簽核與待辦 Backlog（Step 7 歸檔）

* **最終結論**：Gate 2 **PASS**（零 P0/P1；Step 6 共 3 輪，三振額度用滿且全數通過）。unit 298 項 OK、E2E FAKE 22 項 OK、LIVE 兩輪對話達標（冷啟約 23~28 s、同 JD 重查 0 次抽取）、`audit_guardrails.py` 100% PASSED。
* **文檔同步**：[ADR-0019](../adr/0019-recruitment-assistant-langgraph-chat.md) 轉為已採納並記錄實作偏差 DV-1~DV-7；[Spec-0019 第五部](../specs/0019-recruitment-assistant-chat-spec.md) 記錄修訂 REV-1~REV-8。
* **待辦 Backlog**（詳細影響與處置見 Spec-0019 第五部第 2 節）：

| 編號 | 等級 | 項目 |
| :---: | :---: | :--- |
| G2-09 | P2 | CORS 白名單（既有債，影響 `/api/chat`） |
| G2-06 | P2 | 失敗 turn 之 checkpoint 回滾 |
| G3-01 | P2 | 使用者自行輸入之舊人選姓名以明文送 LLM |
| G3-03 | P2 | 非帶人類追問仍因非逐字引文降為 `NOT_MENTIONED` |
| G3-05 | P3 | 逾時後孤兒抽取浪費 Token |
| TC-17 | P3 | 瀏覽器手動點測未執行 |
| P3-STREAM | P3 | 串流回覆（SSE） |
