# 0024 招募助理語意檢索評測與 answer_status 正確率 規格

> 狀態：已通過 Gate 1（2026-11-12 使用者確認第 4 節：單元測試放 `tests/unit/`，品質門檻採預設值）。本規格只新增 `tests/eval/` 評測腳本與合成資料，不修改 `src/`。

品質評測範圍：是

## 1. PRD

### 1.1 背景與目標

HR 招募聊天助理目前沒有量化方法回答兩件事：語意檢索有沒有把對的人選排在前面，以及追問回答的 `answer_status` 判斷是否正確。後者最危險的錯誤是「履歷沒寫，卻回答有」（應為 `NOT_MENTIONED` 卻判成 `SUPPORTED`），會讓 HR 誤信不存在的經歷。

本規格建立一套**零評審 Token** 的評測基礎：檢索用 Spec-0023 的確定性指標，`answer_status` 用人工標註的標準答案比對，不使用 LLM 評審。轉述是否誇大只輸出 CSV 供人工抽查，不自動評分。

### 1.2 範疇 (Scope)

- **In-Scope**
  1. 一份共用的合成資料集（v2）：22 份虛構履歷、檢索查詢、追問題、媒合敘述案例；題目分 basic 與 hard 兩級，分別計分。
  2. 檢索評測腳本：合成履歷寫入**獨立** Redis 索引，計算候選人層級的 Recall@K、MRR、nDCG@K（K = 3、5、10）。
  3. 追問評測腳本：呼叫 `GeminiRecruitmentLlm.answer_followup`，計算 3×3 混淆矩陣、正確率、各類 precision/recall，以及「NOT_MENTIONED→SUPPORTED」誤判率。
  4. 人工抽查 CSV：`narrate_match` 敘述與追問回答文字。
  5. Token 計量：記錄被評測程式呼叫 Gemini 的次數與 Token。
  6. `.gitignore` 加入 `tests/eval/results/`。
- **Out-of-Scope**
  1. 修改 `src/` 任何檔案（含 prompt 與模型設定）。
  2. Ragas、LangSmith、LLM 評審、自動化誇大偵測。
  3. 新增第三方依賴。
  4. 納入 CI 或 `unittest discover`。
  5. 評測完整聊天圖（LangGraph 節點、JD 抽取、Profile 抽取、條件媒合）。本次只評測檢索層與 `answer_followup`／`narrate_match` 兩個 LLM 方法本身。

### 1.3 隔離前提（Step 1 必要確認）

結論：**不需要修改 `src/`**。

- [`AppConfig.load`](../../src/infrastructure/config.py) 支援 `override_redis_index_name`、`override_redis_prefix`、`override_redis_hash_prefix` 參數，以及 `REDIS_INDEX_NAME`、`REDIS_PREFIX`、`REDIS_HASH_PREFIX` 環境變數。
- [`RedisVectorStore`](../../src/infrastructure/stores/redis_vector_store.py) 的建構子直接接收 `index_name`、`prefix`、`hash_prefix`；建立索引時以 `prefix=[self.prefix]` 限定掃描範圍，刪除與 hash 讀寫也都套用前綴。
- 評測預設值：索引 `idx:eval:resumes:v1`、切片前綴 `eval:resume:v1:chunk:`、hash 前綴 `eval:resume:v1:hash:`；候選人 ID 一律為 `eval_cand_XX`。
- 防呆：腳本啟動時讀取正式設定（`AppConfig.load()` 不帶覆寫），若評測索引名稱與正式相同，或兩邊切片前綴、hash 前綴任一方是另一方的前綴，立即中止且不連線寫入。
- 不使用 Profile/JD 快取（評測不呼叫抽取），因此 `recruit:v1:*` 鍵不受影響。

### 1.4 輸入與輸出

**指令（人工觸發）**

```bash
python tests/eval/run_retrieval_eval.py [--k 3 5 10] [--top-chunks 60] [--reindex] [--cleanup]
python tests/eval/run_followup_eval.py [--max-llm-calls 80] [--skip-narration]
```

| 參數 | 預設 | 說明 |
| :--- | :--- | :--- |
| `--k` | `3 5 10` | 候選人層級的 K 值 |
| `--top-chunks` | `60` | 每題向量檢索取回的切片數，之後依候選人去重排名 |
| `--reindex` | 否 | 先清空評測命名空間再重建索引（避免已刪除履歷的舊切片殘留）；未指定時依內容 hash 增量寫入，未變更的履歷不呼叫 Embedding |
| `--cleanup` | 否 | 執行後刪除評測索引與 `eval:` 前綴鍵 |
| `--max-llm-calls` | `80` | LLM 呼叫硬上限，超過即停止並在報告標示「未完成」 |
| `--skip-narration` | 否 | 只跑追問，不跑 `narrate_match` |

**輸出（`tests/eval/results/<UTC 時間戳>/`，已列入 `.gitignore`）**

| 檔案 | 內容 |
| :--- | :--- |
| `retrieval_summary.json` | 各 K 的 Recall、Precision、MRR、nDCG、計入與排除筆數、資料集版本 |
| `retrieval_per_query.csv` | 每題的排名前 10 候選人 ID、命中位置、各指標 |
| `followup_summary.json` | 混淆矩陣（原始 status 與引文驗證後 status 各一份）、正確率、各類 precision/recall、NM→SUPPORTED 誤判率、Token 統計 |
| `followup_spot_check.csv` | 每題：case_id、候選人、問題、標準 status、模型 status、驗證後 status、回答文字、引文、引文是否逐字存在、`spot_check_notes` 空欄 |
| `narration_spot_check.csv` | 每案：case_id、輸入事實摘要、敘述全文、`spot_check_notes` 空欄 |
| `usage.json` | Embedding 呼叫次數與輸入字元數；LLM 呼叫次數、input/output/thinking Token |

### 1.5 驗收標準 (AC)

**功能 AC**

- **AC1（隔離）**：評測只寫入 `idx:eval:resumes:v1` 與 `eval:` 前綴鍵；執行前後正式索引的文件數不變。設定衝突時腳本以非零碼結束且未寫入任何鍵。
- **AC2（增量 0 Token）**：第二次執行（資料未變、未加 `--reindex`）時，履歷寫入階段 Embedding 呼叫次數為 0；只有查詢向量化會呼叫。
- **AC3（資料集）**：v2 為 22 份虛構履歷，題目有 `difficulty`（basic／hard）欄位，評測同時輸出 all、basic、hard 三組分數；檢索查詢 ≥ 20 題，其中至少 3 題的相關人選 ≥ 2 位、至少 1 題相關集合為空（驗證排除邏輯）；追問題 ≥ 30 題，三種 status 各 ≥ 8 題；媒合敘述案例 ≥ 4 案。所有姓名、公司、學校皆為虛構。
- **AC4（指標正確使用）**：檢索指標一律呼叫 [`evaluation_metrics.py`](../../src/domain/evaluation_metrics.py) 的函式，腳本內不重寫公式。
- **AC5（Token 記錄）**：`usage.json` 記錄每次 LLM 呼叫的 Token；QA 報告引用這份數字。
- **AC6（上限與降級）**：LLM 呼叫達 `--max-llm-calls` 即停止；單題 LLM 例外（含配額熔斷、截斷）記為 `ERROR` 列，不中斷整批，`ERROR` 不計入混淆矩陣但在摘要中列出筆數。
- **AC7（人工抽查輸出）**：兩份 CSV 以 UTF-8 BOM 寫出（Excel 可直接開啟中文），每列都有 `spot_check_notes` 空欄。
- **AC8（不入 CI）**：腳本檔名不以 `test_` 開頭，`python -m unittest discover -s tests/unit` 不會執行它們。

**品質 AC（首輪為基準線，未達標記為發現事項，不在本規格內修 `src/`）**

| 編號 | 指標 | 門檻 |
| :--- | :--- | :--- |
| Q1 | 候選人層級 Recall@5 | ≥ 0.80 |
| Q2 | MRR | ≥ 0.70 |
| Q3 | nDCG@5 | ≥ 0.75 |
| Q4 | `answer_status` 正確率（原始輸出） | ≥ 0.85 |
| Q5 | NOT_MENTIONED→SUPPORTED 誤判率（佔標準 NOT_MENTIONED 題數） | ≤ 0.05（約 10 題時即為 0 題） |
| Q6 | 各類 recall（SUPPORTED、CONTRADICTED、NOT_MENTIONED） | 各 ≥ 0.70 |

標註資料來源：由本規格作者依合成履歷內容人工標註，記錄於 `tests/eval/data/DATASET.md`（版本、標註者、日期、標註原則）。

## 2. Gate 1：8 大架構維度前審

| 維度 | 結論 |
| :--- | :--- |
| PII 隱私 | 全部為虛構資料；CSV 只含虛構內容。送往 Gemini 的追問履歷以代稱取代姓名，與正式流程一致。 |
| 容量與極限 | 22 份履歷約 70 個切片，Redis 記憶體影響可忽略；`--cleanup` 可完全移除。 |
| 非同步演進 | 腳本為一次性批次，不影響正式服務。 |
| 成本與熔斷 | LLM 約 66 次呼叫（v2）；`--max-llm-calls` 硬上限；沿用 `GeminiRecruitmentLlm` 內建熔斷與重試；Embedding 依 hash 增量。 |
| 可抽換性 | 直接使用既有 Adapter（`GeminiEmbeddingService`、`RedisVectorStore`、`GeminiRecruitmentLlm`）與 Use Case（`IndexResumesUseCase`、`SearchResumesUseCase`），不新增介面。 |
| 惡意輸入上限 | 資料集為版控內的固定檔案；載入時檢查欄位與 status 枚舉值，格式錯誤即中止。 |
| 向量索引遷移 | 獨立索引與前綴，含 `v1` 版本號；與正式索引零交集，並有啟動防呆。 |
| 併發與可觀測性 | 單程序循序執行；每題記錄 case_id 作為追蹤鍵。 |

結論：不屬於重大架構變更，不需 ADR。

## 3. Tech Spec

### 3.1 變更矩陣

| 檔案 | 異動 |
| :--- | :--- |
| `tests/eval/__init__.py` | 新增 |
| `tests/eval/eval_support.py` | 新增：資料載入與驗證、隔離防呆、混淆矩陣、Token 計量、CSV/JSON 輸出 |
| `tests/eval/run_retrieval_eval.py` | 新增 |
| `tests/eval/run_followup_eval.py` | 新增 |
| `tests/eval/data/DATASET.md` | 新增：資料集版本與標註紀錄 |
| `tests/eval/data/resumes/`（22 份 Markdown，檔名主幹 `eval_cand_01`～`eval_cand_22`） | 新增：合成履歷 |
| `tests/eval/data/retrieval_queries.jsonl` | 新增 |
| `tests/eval/data/followup_questions.jsonl` | 新增 |
| `tests/eval/data/narration_cases.jsonl` | 新增 |
| `tests/unit/test_eval_support.py` | 新增（**待使用者確認**，見第 4 節） |
| `.gitignore` | 加入 `tests/eval/results/` |
| `docs/specs/0024-…-spec.md`、`docs/qa_reports/0024-…-qa.md`、`docs/README.md` | 規格、QA 報告與索引 |

### 3.2 資料格式

```json
// retrieval_queries.jsonl
{"query_id": "r01", "query": "熟悉 Kubernetes 與 Go 的後端工程師", "relevant_ids": ["eval_cand_03", "eval_cand_11"]}
// followup_questions.jsonl
{"case_id": "f01", "candidate_id": "eval_cand_03", "question": "他有帶過團隊嗎？", "expected_status": "SUPPORTED",
 "profile_summary": {"years_of_experience": "6", "has_led_team": "True", "max_team_size": "5", "seniority": "SENIOR", "core_skills": "go、kubernetes"},
 "met_labels": [], "unmet_labels": [], "unknown_labels": []}
// narration_cases.jsonl：欄位直接對應 MatchNarrationFacts 與 CandidateFact
```

標註原則（寫入 `DATASET.md`）：`SUPPORTED` = 履歷有明確文字支持；`CONTRADICTED` = 履歷有明確文字與問題相反（如問「有沒有 Java 經驗」，履歷寫「未使用過 Java」，或問「超過 10 年」而履歷年資為 4 年）；`NOT_MENTIONED` = 履歷完全沒寫。`NOT_MENTIONED` 題目刻意包含「相近但不同」的陷阱（例如履歷寫 AWS，問 GCP），以測出誤判 `SUPPORTED`。

### 3.3 檢索評測流程

1. `AppConfig.load(override_redis_index_name=…, override_redis_prefix=…, override_redis_hash_prefix=…)`，先跑隔離防呆。
2. 以正式組裝方式建立 `GeminiEmbeddingService`、`MarkdownChunker`、`RedisVectorStore`，用 `IndexResumesUseCase` 從 `tests/eval/data/resumes/` 寫入（hash 增量）。
3. 以 `SearchResumesUseCase.execute(SearchQuery(query_text, top_k=--top-chunks))` 取切片，依分數順序以候選人 ID 去重為排名，交給 `evaluation_metrics.summarize_retrieval`。
4. Embedding 計量：以包裝物件（實作同一 `IEmbeddingService` 方法並轉呼叫）計數呼叫次數與輸入字元數。google-genai 的 embed 回應不保證有 Token 數，報告以字元數與呼叫數呈現並註明。

### 3.4 追問與敘述評測流程

1. 依 [`server.py`](../../src/interfaces/web/server.py) 相同參數建立 `GeminiRecruitmentLlm`，但自行建立 `ChatGoogleGenerativeAI` 並掛上 `langchain_core.callbacks.UsageMetadataCallbackHandler` 後以 `chat_model` 注入（`model_copy` 會保留 callbacks，所以敘述用模型也會計量）。不改 `src/`。
2. `FollowupFacts`：`profile_summary` 與各 labels 取自標註檔；`resume_excerpt` 依正式 `CandidateProfileService.prepare_llm_text` 的相同步驟產生：`ProtectedAttributeGuard(settings.protected_attr_terms).redact_resume` → `mask_contact_info(text, [姓名], "候選人 #1")` → 截斷到 `settings.profile_max_resume_chars`。`settings` 以 `server.build_recruitment_settings(config)` 建立，與正式組裝一致。
3. 逐題呼叫 `answer_followup`，記錄原始 status。
4. 引文驗證後 status：以 domain 的 `EvidenceVerifier(recruit_evidence_min_chars)` 檢查引文；若 status 為 `SUPPORTED`/`CONTRADICTED` 但沒有任何引文逐字存在，改記為 `NOT_MENTIONED`。這模擬正式流程 `_verify_followup` 的主要分支，不含其模板回退。Q4～Q6 以原始輸出計算，驗證後矩陣作為參考列在報告中。
5. `narrate_match`：每案以標註的 `MatchNarrationFacts` 呼叫一次，全文寫入 CSV。

### 3.5 `eval_support.py` 純函式（Step 3 單元測試對象）

- `confusion_matrix(pairs, labels)`：回傳 `{expected: {predicted: count}}`，含全部 3×3 格子（缺的補 0）；未知 label 拋 `ValueError`。
- `classification_summary(matrix)`：正確率、各類 precision/recall（分母為 0 時回傳 `None`）、`false_support_rate`（標準 NOT_MENTIONED 中被判 SUPPORTED 的比例）。
- `subsets_by(rows, key, levels)`：依難度分組，回傳 all 與各層級（無資料時為空列表）。
- `candidate_ranking(candidate_ids)`：輸入依分數排序的切片候選人 ID，依原順序去重。
- `check_isolation(eval_cfg, prod_cfg)`：名稱相同或前綴互相包含時拋 `ValueError`。
- `load_jsonl(path, required_fields, enum_fields)`：欄位缺漏、status 非法、重複 ID 時拋 `ValueError` 並指出行號。

### 3.6 單元測試計畫（`tests/unit/test_eval_support.py`，全離線）

- 混淆矩陣：手算 6 筆例子、空輸入（全 0 格）、未知 label 拒絕。
- 摘要：正確率手算、某類無預測時 precision 為 `None`、無 NOT_MENTIONED 標準題時誤判率為 `None`。
- 候選人排名：重複候選人只留第一次、空輸入。
- 隔離防呆：同名、`resume:v1:chunk:` 與 `resume:v1:chunk:eval:` 互為前綴、合法組合三種。
- JSONL 驗證：以 `tmp` 目錄內動態建立的虛構檔案測缺欄、非法 status、重複 ID。

### 3.7 QA 驗收矩陣（Step 4）

| AC | 驗證方式 |
| :--- | :--- |
| AC1 | 執行前後以 `FT.INFO` 比對正式索引 `num_docs`；以衝突設定執行確認非零碼且 `SCAN eval:*` 無新鍵 |
| AC2 | 連續執行兩次，比對 `usage.json` 的寫入階段 Embedding 呼叫次數 |
| AC3 | 載入資料集時的統計輸出 |
| AC4 | 程式碼檢視：腳本 import `evaluation_metrics` 而無自寫公式 |
| AC5 | `usage.json` 與 QA 報告數字一致 |
| AC6 | 以 `--max-llm-calls 3` 執行，確認停止並標示未完成 |
| AC7 | 以 Excel 開啟兩份 CSV 檢查中文與欄位 |
| AC8 | 執行 CI 指令確認未收集到 eval 腳本 |
| Q1～Q6 | 實際執行結果，寫入 `docs/qa_reports/0024-recruitment-retrieval-and-answer-status-eval-qa.md` |

## 4. Gate 1 決議

1. **單元測試位置**：任務限制「只新增 `tests/eval/` 底下的檔案」，但 AGENTS.md 品質評測規則第 3 條要求指標函式須有單元測試，而 CI 只收集 `tests/unit/`。使用者同意新增 `tests/unit/test_eval_support.py`（純離線），為唯一超出 `tests/eval/` 的程式檔。
2. **品質門檻**：第 1.5 節 Q1～Q6 採預設值。
