# 0023 檢索與抽取品質指標計算模組 規格

> 狀態：已通過 Gate 1（Step 1 自審）。本規格為純領域層計算模組，不涉及外部服務或 Use Case。

品質評測範圍：是

## 1. PRD

### 1.1 背景與目標

目前專案缺少量化「找得準不準」與「抽得對不對」的計算方法，無法判斷檢索排序或結構化抽取的改動是變好還是變差。本模組提供純函式的指標計算，供後續評測腳本（`tests/eval/`）與 QA 報告使用。

### 1.2 範疇 (Scope)

- **In-Scope**：Recall@K、Precision@K、MRR、nDCG@K（二元相關）、欄位 F1、以及彙總多筆查詢結果的函式。
- **Out-of-Scope**：LLM 評審、讀取真實資料或標註檔、評測腳本本身、CLI 或 Web 介面、任何外部服務呼叫、分級相關性。

### 1.3 API 合約

模組位置：`src/domain/evaluation_metrics.py`（純函式，零第三方依賴）。

| 函式 | 輸入 | 輸出 |
| :--- | :--- | :--- |
| `dedupe_ranked(ranked)` | 排序後的 ID 序列 | 去重後保留首次出現順序的列表 |
| `recall_at_k(relevant, ranked, k)` | 相關 ID 集合、排序列表、K（整數，≥ 1） | `float`；`relevant` 為空時回傳 `None` |
| `precision_at_k(relevant, ranked, k)` | 同上 | `float`；`relevant` 為空時回傳 `None` |
| `reciprocal_rank(relevant, ranked)` | 相關 ID 集合、排序列表 | `float`；`relevant` 為空時回傳 `None` |
| `ndcg_at_k(relevant, ranked, k)` | 同上 | `float`；`relevant` 為空時回傳 `None` |
| `field_f1(expected, actual)` | 標準欄位對映、系統輸出欄位對映 | `float`，0.0 至 1.0 |
| `summarize_retrieval(cases, k)` | `RetrievalCase` 列表、K | `RetrievalSummary`（各指標平均值、計入筆數、排除筆數） |

資料型別：`RetrievalCase`（`query_id: str`、`relevant_ids: frozenset[str]`、`ranked_ids: tuple[str, ...]`）與 `RetrievalSummary`（唯讀資料類別），皆定義於同一模組。

### 1.4 設定合約

本模組無新增環境變數，`.env.example` 不需變動。

### 1.5 驗收標準 (AC)

- **AC1（Recall@K）**：以手算小例子驗證；K 超過 `ranked` 長度時以實際長度計算；`relevant` 為空時回傳 `None`。
- **AC2（Precision@K）**：分母為實際取到的筆數 `min(K, 去重後長度)`；`ranked` 為空且 `relevant` 非空時回傳 0.0。
- **AC3（MRR）**：取第一個相關結果排名的倒數；全部未命中回傳 0.0；`relevant` 為空時回傳 `None`。
- **AC4（nDCG@K）**：採二元增益，DCG 以 `log2(i+1)` 折扣，IDCG 以相關總數與 K 的較小值計算；`relevant` 為空時回傳 `None`。
- **AC5（欄位 F1）**：字串去頭尾空白且大小寫不敏感；清單欄位以集合比對；空欄位雙方皆空時為 1.0，僅一方為空時為 0.0；`None` 與空字串視為缺漏。
- **AC6（邊界）**：`ranked` 中的重複 ID 只計第一次；`K ≤ 0` 拋出 `ValueError`；空相關集合的查詢不計入平均。
- **AC7（彙總）**：`summarize_retrieval` 回報各指標平均、計入筆數與排除筆數，排除筆數 = 相關集合為空的查詢數。
- **AC8（純度）**：模組不 import 任何第三方套件，不做檔案或網路 I/O，通過 `audit_guardrails.py` 的 domain 純度檢查。

## 2. Gate 1：8 大架構維度前審

| 維度 | 結論 |
| :--- | :--- |
| PII 隱私 | 僅接收 ID 與欄位值，不產生新的個資輸出；標註資料由呼叫端負責使用虛構內容。 |
| 容量與極限 | 各函式為 O(N log N) 以內的單次遍歷；無快取、無全域狀態。 |
| 非同步演進 | 純函式，無狀態，天然可並行。 |
| 成本與熔斷 | 零外部呼叫、零 Token 消耗。 |
| 可抽換性 | 不依賴任何介面，無需 Protocol。 |
| 惡意輸入上限 | K 非法值拒絕；超長列表不設硬上限，由呼叫端讀檔時負責限制。 |
| 向量索引遷移 | 不涉及 Redis 或索引結構。 |
| 併發與可觀測性 | 無共享狀態；純計算不需 Trace ID。 |

結論：無架構債，不屬於重大架構變更（Deep Track），不需撰寫 ADR。

## 3. Tech Spec

### 3.1 變更矩陣

| 檔案 | 異動 |
| :--- | :--- |
| `src/domain/evaluation_metrics.py` | 新增 |
| `tests/unit/test_evaluation_metrics.py` | 新增 |
| `docs/specs/0023-retrieval-quality-metrics-spec.md` | 新增（本檔） |
| `docs/README.md` | 登錄本規格索引 |
| `docs/qa_reports/0023-retrieval-quality-metrics-qa.md` | 新增（Step 4 產出） |

### 3.2 Domain

- `RetrievalCase`、`RetrievalSummary`：`@dataclass(frozen=True)`。
- `dedupe_ranked`：以 `dict.fromkeys` 保留首次出現順序。
- `recall_at_k`、`precision_at_k`、`reciprocal_rank`、`ndcg_at_k`：內部先呼叫 `_validate_k` 與 `dedupe_ranked`。
- `field_f1`：將每個欄位展開為事實集合 `(欄位名, 正規化值)`（`None` 與正規化後的空字串略過），清單欄位逐項展開；`tp = |E ∩ A|`，`precision = tp/|A|`，`recall = tp/|E|`，F1 為調和平均；兩邊皆空回傳 1.0，任一邊為空且另一邊非空時 tp 為 0，回傳 0.0。
- `summarize_retrieval`：對每筆 case 計算四項指標，排除 `None` 值後取平均。

### 3.3 Application

本次不新增 Use Case，評測腳本於後續規格中定義。

### 3.4 Infrastructure

本次不涉及。

### 3.5 Interfaces

本次不涉及。

### 3.6 單元測試計畫（`tests/unit/test_evaluation_metrics.py`）

- Recall：手算例子（3 個相關中命中 2 個，K=3 得 2/3）、K 超過長度、空相關集合回傳 `None`。
- Precision：K 超過長度時分母為實際長度、`ranked` 為空回傳 0.0。
- MRR：第一個相關在第 2 位得 0.5、全未命中得 0.0、空相關回傳 `None`。
- nDCG：完美排序得 1.0、手算例子驗證折扣、IDCG 以 min(K, 相關數) 計算、空相關回傳 `None`。
- 去重：重複 ID 只計第一次，不影響 Recall 與 MRR 的名次。
- K 非法：K = 0、K = -1 拋出 `ValueError`。
- 欄位 F1：完全相同得 1.0、大小寫與空白不敏感、清單順序不影響、雙空得 1.0、單空得 0.0、部分命中的手算例子。
- 彙總：排除筆數與計入筆數正確，平均值只計入非 `None` 值。
- 純度：以 `ast` 檢查模組 import 清單，確認無第三方套件。

以上測試全部使用記憶體內的虛構資料，零網路、零磁碟讀取。

### 3.7 QA 驗收矩陣（Step 4）

| AC | 對應測試 |
| :--- | :--- |
| AC1 | Recall 手算例子、K 超過長度、空相關 |
| AC2 | Precision 分母測試、空 ranked |
| AC3 | MRR 名次測試、全未命中、空相關 |
| AC4 | nDCG 完美排序、折扣手算、IDCG 上限 |
| AC5 | 欄位 F1 各子案例 |
| AC6 | 去重測試、K 非法測試、空相關排除 |
| AC7 | 彙總計數測試 |
| AC8 | 純度 AST 測試與 `audit_guardrails.py` |

由於本模組為純函式，Step 4 以單元層的邊界對抗與 AC 追溯為主，不另建 E2E 測試；QA 報告記錄 AC 追溯結果。
