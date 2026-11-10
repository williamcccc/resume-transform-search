---
name: quality-evaluation
description: >-
  Use this skill when designing, running, or reviewing quality evaluations for retrieval, structured extraction, or LLM generation in this project, including Recall@K, MRR, nDCG, F1 metrics, labeled eval datasets, LLM-as-judge rubrics, human calibration, and before/after prompt or model comparison.
---

# 品質評測技能 (Quality Evaluation)

本技能是 AGENTS.md「品質評測規則」的操作手冊。硬性規則以 AGENTS.md 為準；本技能說明**怎麼做**。適用於檢索排序、結構化抽取、LLM 生成回答，以及 `prompts/` 或模型設定的變更。

## 一、何時使用

- Step 1 撰寫 PRD 時，需要定義品質目標與標註資料來源。
- Step 3 撰寫指標計算函式的單元測試。
- Step 4 在 `tests/eval/` 執行真實資料評測，或撰寫評審 prompt。
- 修改 `prompts/` 或模型設定後，需要做前後比較。

## 二、指標速查

設 `relevant` 為標註的相關 ID 集合，`ranked` 為系統排序後的 ID 列表（去重後保留第一次出現的位置）。

| 指標 | 定義 | 邊界處理 |
| :--- | :--- | :--- |
| Recall@K | 前 K 筆中命中的相關數 ÷ 相關總數 | `relevant` 為空：排除該筆並回報筆數；K 超過 `ranked` 長度：以實際長度計算 |
| Precision@K | 前 K 筆中命中的相關數 ÷ K | K 超過長度：分母仍用實際取到的筆數，並在報告註明 |
| MRR | 每筆查詢第一個相關結果排名的倒數，再取平均；全部未命中記 0 | 同上 |
| nDCG@K | 以 `log2(i+1)` 折扣累計增益，除以理想排序的增益 | 理想增益為 0 時該筆排除 |
| 欄位 F1 | 逐欄比對標準 JSON 與系統輸出，以 precision 與 recall 的調和平均計算 | 空欄位雙方皆空視為正確；只有一方為空視為錯誤 |

每個指標函式都要有手算小例子的單元測試，並覆蓋空相關集合、重複 ID、K 超過結果數三種邊界。

## 三、評測資料集格式

資料以 JSONL 存於 `tests/eval/data/`，每行一筆。資料一律使用虛構內容，例如 `王小明`、`sample_resume_01.md`，不得含真實履歷或個資。

檢索資料範例：

```json
{"query_id": "q001", "query": "熟悉 Kubernetes 的後端工程師，5 年以上經驗", "relevant_ids": ["cand_a", "cand_c"]}
```

抽取資料範例：

```json
{"doc_id": "sample_resume_01", "expected": {"name": "王小明", "years_experience": 6, "skills": ["python", "kubernetes"]}}
```

標註時應記錄標註者與日期，資料集變更時更新版本號。

## 四、LLM 評審（LLM-as-judge）

### 4.1 撰寫 rubric

每個維度列出 1 到 5 分各自的具體情況，避免「好」「差」等模糊描述。例如面試題的相關性：5 分為完全根據履歷中的具體經歷提問；3 分為與履歷有關但過於籠統；1 分為與履歷無關的通用題。

### 4.2 評審 prompt 結構

評審 prompt 包含四部分：角色設定、rubric、待評內容、輸出格式。待評內容要用既有的 fence 方式隔離，避免內容中的指令影響評審。輸出要求 JSON，並要求先寫理由再給分。溫度設為 0。可參考 `prompts/judge_system.md` 與 `prompts/judge_text_prompt.md`。

### 4.3 人工校準

評審上線前必須先校準：挑選一批樣本（建議至少 30 筆，涵蓋各分數段），由人工打分，再與評審分數比對。一致率或相關係數不足時，回頭修改 rubric 或 prompt，不要直接採用評審分數。校準結果記錄在 QA 報告中。

### 4.4 偏差處理

- 位置偏差：比較兩個答案時隨機交換順序，取平均。
- 長度偏差：在 rubric 中明確寫「不因長度加分」。
- 自我偏好：評審模型盡量與生成模型不同；若相同，在報告中註明。

## 五、執行與報告

- 評測程式放在 `tests/eval/`，不納入 `unittest` 與 CI，由人工觸發。
- 每次執行記錄 Token 消耗、API 呼叫次數與各指標分數。
- 報告依 AGENTS.md 雙寫規則：超過 30 行者寫入 `docs/qa_reports/`，並列出資料集版本、評審模型與 rubric 版本。

## 六、前後比較

修改 `prompts/` 或模型設定時：

1. 固定同一版本的資料集與評審 rubric。
2. 分別以修改前與修改後的設定執行。
3. 比較各指標的差異，並檢查是否有某個查詢大幅退步。
4. 分數下降不得合併，除非有明確理由並經 Gate 2 核准。

若 rubric 或資料集本身有變更，不得與舊分數直接比較，必須以舊設定在新資料上重跑一次作為基準。

## 七、禁忌

- 不使用真實履歷或個資作為評測資料。
- 不在單元測試中呼叫 LLM，或讀取 `tests/eval/data/` 的真實內容。
- 不為了提高分數而修改 rubric 或資料集，除非有記錄在案的原因。
- 不把 LLM 評審分數視為絕對真值，必須先經過人工校準。
