# QA-0024：招募助理語意檢索評測與 answer_status 正確率 實測驗收報告

* **對應規格**：[Spec-0024](../specs/0024-recruitment-retrieval-and-answer-status-eval-spec.md)
* **對應實作**：[eval_support.py](../../tests/eval/eval_support.py)、[run_retrieval_eval.py](../../tests/eval/run_retrieval_eval.py)、[run_followup_eval.py](../../tests/eval/run_followup_eval.py)
* **測試檔**：[test_eval_support.py](../../tests/unit/test_eval_support.py)（21 個測試）
* **資料集**：[DATASET.md](../../tests/eval/data/DATASET.md) v1（第一～六節）與 v2（第七節）
* **結論**：AC1～AC8 全部通過，Q1～Q6 在 v1、v2 皆達標。v1 偏簡單，因此加做 v2 困難題重測（第七節）：追問困難題 28 題錯 1 題，最危險的「應為 NOT_MENTIONED 卻判成 SUPPORTED」仍為 0；檢索則暴露出向量檢索分不出否定語句的弱點。

## 一、AC 追溯矩陣

| AC | 內容 | 驗證方式 | 結果 |
| :--- | :--- | :--- | :--- |
| AC1 | 隔離 | 正式索引 `num_docs` 執行前後皆為 2211；以 `REDIS_PREFIX=eval:` 模擬衝突，腳本以結束碼 2 中止，未連線寫入；`--cleanup` 後 `eval:*` 鍵 0 個、評測索引已移除，正式索引仍為 2211 | 通過 |
| AC2 | 增量 0 Token | 第二次執行：新寫入 0 份、略過 18 份，Embedding 只剩 22 次查詢呼叫 | 通過 |
| AC3 | 資料集規模 | 載入統計：22 題（3 題相關人選 ≥ 2 位、1 題無相關），追問 SUPPORTED 11／CONTRADICTED 11／NOT_MENTIONED 12，敘述 4 案 | 通過 |
| AC4 | 指標正確使用 | 腳本 import `evaluation_metrics` 的 `summarize_retrieval`、`recall_at_k`、`ndcg_at_k`、`reciprocal_rank`，無自寫公式 | 通過 |
| AC5 | Token 記錄 | `usage.json` 與本報告第三節數字一致 | 通過 |
| AC6 | 呼叫上限 | `--max-llm-calls 3 --skip-narration`：第 3 次後停止，`incomplete=true`，結束碼 1 | 通過 |
| AC7 | 抽查 CSV | 兩份 CSV 皆以 UTF-8 BOM 寫出並含 `spot_check_notes` 欄；單元測試驗證 BOM 與欄位 | 通過 |
| AC8 | 不入 CI | `unittest discover -s tests/unit` 未收集任何 `run_*_eval` | 通過 |

## 二、品質指標

### 2.1 語意檢索（候選人層級，計入 21 題、排除 1 題）

| 指標 | @3 | @5 | @10 | 門檻 |
| :--- | ---: | ---: | ---: | :--- |
| Recall | 1.000 | 1.000 | 1.000 | Q1：@5 ≥ 0.80 |
| MRR | 0.976 | 0.976 | 0.976 | Q2：≥ 0.70 |
| nDCG | 0.982 | 0.982 | 0.982 | Q3：@5 ≥ 0.75 |
| Precision | 0.429 | 0.257 | 0.129 | 未設門檻（多數查詢只有 1 位相關人選，上限本來就低） |

唯一沒排第一的是 r21「PostgreSQL 資料庫效能調校」：標準答案 `eval_cand_01` 排第 2，第 1 名是技能清單列有 PostgreSQL、但沒寫調校經驗的 `eval_cand_03`。

### 2.2 answer_status（34 題，0 題 ERROR）

| 標準 \ 模型 | SUPPORTED | CONTRADICTED | NOT_MENTIONED |
| :--- | ---: | ---: | ---: |
| SUPPORTED | 11 | 0 | 0 |
| CONTRADICTED | 0 | 11 | 0 |
| NOT_MENTIONED | 0 | 0 | 12 |

- Q4 正確率 1.00（≥ 0.85）；Q5 NOT_MENTIONED→SUPPORTED 0／12（≤ 0.05）；Q6 三類 recall 皆 1.00（≥ 0.70）。
- 引文驗證後的矩陣相同；全部引文都能在遮蔽後的履歷中逐字找到。

## 三、Token 與呼叫用量

| 項目 | 數量 |
| :--- | :--- |
| LLM（`answer_followup` 34 次 + `narrate_match` 4 次） | 38 次邏輯呼叫、38 次實際請求（無重試） |
| LLM Token | 輸入 32,786、輸出 18,732（其中 thinking 14,935）、合計 51,518 |
| Embedding 首次寫入 | 18 次呼叫、57 個切片、7,296 字元 |
| Embedding 查詢 | 每次執行 22 次呼叫、375 字元 |
| Embedding 重跑寫入 | 0 次（hash 增量） |
| AC6 驗證額外花費 | 3 次 LLM 請求、3,793 Token |

Gemini Embedding 回應沒有提供 Token 數，因此以呼叫次數與字元數記錄。thinking Token 約佔輸出的 80%。

## 四、發現事項

1. **資料集 v1 偏簡單（影響結論可信度）**：合成履歷的否定說得很直白（例如「未曾使用 Java」），陷阱題只是替換技術名詞；檢索查詢也大多直接對上履歷用語。建議 v2 加入：需要推論的追問（做過支付系統算不算金融經驗）、數值剛好在邊界的追問（問 5 年以上，履歷正好 5 年）、同義詞或描述性查詢（「容器編排」而非「Kubernetes」）。
2. **檢索沒有「查無人選」訊號**：r22「會計師事務所審計經驗」無相關人選，但仍回傳全部 18 人（`min_score` 預設 0）。候選人層級指標不受影響，但正式聊天流程若直接採用前幾名，可能推薦完全不相關的人。
3. **敘述洩漏內部欄位名稱**：n02 的 `narrate_match` 輸出寫出「relaxation 為 null」，這段文字是給 HR 看的。屬於 `prompts/` 的問題，不在本規格範圍。
4. **技能清單比經歷描述更容易被檢索到**：見 2.1 的 r21。資料量小，暫不下結論，建議 v2 多放幾題同類查詢再觀察。

## 五、執行環境與限制

- Windows 11、Python 3.13、本機 Redis Stack；LLM 與 Embedding 模型依 `.env` 設定（模型名稱記錄於 `followup_summary.json`）。
- `profile_summary` 為人工標註，不經 Profile 抽取；評測範圍只到 `answer_followup` 與 `narrate_match` 本身。
- 每題只跑一次；同一資料重跑可能因模型隨機性略有差異，本報告未做重複取樣。
- 原始輸出在 `tests/eval/results/`（不納入版控）。

## 六、Gate 2 摘要

- `audit_guardrails.py` 零 P0；全部單元測試通過。
- 對抗覆核發現 1 項 P2 並已修正：資料集刪除履歷時，`--reindex` 只重建索引定義，舊切片 key 仍留在評測前綴下並被新索引收錄。改為 `--reindex` 先清空評測命名空間；實測清除 75 個舊鍵後重新寫入 18 份、57 個切片，指標不變。
- 接受的設計取捨：評測命名空間名稱以常數寫在 `eval_support.py`，未進 `AppConfig`。理由是它們不是連線字串或機密，且有 `check_isolation` 啟動防呆；若改為環境變數，須同步 `.env.example`，反而擴大變更範圍。
- 驗證修正額外花費：Embedding 寫入 2 次全量（各 18 次呼叫）與查詢 2 次（各 22 次呼叫），無 LLM 呼叫。

## 七、資料集 v2 困難題重測

針對第四節發現事項 1，資料集升為 v2（變更內容見 [DATASET.md](../../tests/eval/data/DATASET.md) 版本紀錄）：

- **修正 v1 標註瑕疵**：01～18 號履歷的任職日期與摘要年資不一致（例如摘要寫 6 年，日期推算超過 8 年），年資類題目的標準答案因此有爭議。已調整日期使兩者一致。
- **新增 4 份陷阱履歷**：剛好 5 年且明寫非管理職、只用 Snowflake、參與 Selenium 專案但腳本由同事開發、只自學過 React。
- **新增 hard 題**：檢索 15 題（描述性與同義說法），追問 28 題（推論、數值邊界、字面出現但事實相反、相近但未提及）。

v1 與 v2 分數不可直接比較；basic 子集即 v1 原題，但候選池從 18 人變為 22 人。

### 7.1 檢索（K=5）

| 子集 | 計入 | Recall@5 | MRR | nDCG@5 |
| :--- | ---: | ---: | ---: | ---: |
| all | 35 | 1.000 | 0.986 | 0.986 |
| basic | 21 | 1.000 | 0.976 | 0.979 |
| hard | 14 | 1.000 | 1.000 | 0.998 |

hard 題沒有讓分數下降，原因是候選池只有 22 人，Recall@5 太容易達成。真正的發現在排名順序：

- **向量檢索分不出否定語句**：r02「React 前端工程師」中，22 號履歷寫「自學 React，尚未用於正式專案」，卻排第 2，壓過真正有 React 經驗的 15 號（第 3），這題 nDCG@5 從 v1 的 1.000 降到 0.919。x04「能帶團隊的後端主管」中，19 號明寫「非管理職」，卻排第 3，在相關人選 09 號之前。
- 這是 Embedding 檢索的本質限制。正式流程後續有 Profile 抽取與條件比對可以修正，但檢索層本身不能依賴語意相似度判斷「有沒有」。
- r21 仍是唯一 MRR 未滿分的題目（同第二節）；x12（區塊鏈）與 r22 一樣沒有相關人選，但仍回傳全部人選（同發現事項 2）。

### 7.2 answer_status

| 子集 | 題數 | 正確率 | NM→SUPPORTED | 錯題 |
| :--- | ---: | ---: | ---: | :--- |
| all | 62 | 0.984 | 0 / 22 | h11 |
| basic | 34 | 1.000 | 0 / 12 | — |
| hard | 28 | 0.964 | 0 / 10 | h11 |

hard 子集混淆矩陣：SUPPORTED 10/10；CONTRADICTED 7/8（1 題判成 NOT_MENTIONED）；NOT_MENTIONED 10/10。引文驗證後結果相同。

- **h11（問 01 號「帶過 5 人以上的團隊嗎」，履歷寫帶領 4 人）**：模型回答文字已寫出「僅記載曾帶領 4 人的後端小組」，status 卻標 `NOT_MENTIONED` 而非 `CONTRADICTED`。也就是回答內容對了，標籤沒有跟著做數值比較。錯誤方向偏保守，不會誤導 HR 以為「有」，但 status 與文字不一致。同類的年資數值題（h12、h16、h17）都判對，只有團隊人數這題失誤。
- **陷阱題全數通過**：h13（Selenium 腳本由同事開發）、h15（明寫非管理職）、h14（自學 React）都正確判為 `CONTRADICTED`，並引用正確原文；h19（Kubeflow ≠ Kubernetes）、h22（韌體 ≠ 電路設計）、h23（產品經理是否寫過程式）都正確判為 `NOT_MENTIONED`。
- **評估**：在 22 題 NOT_MENTIONED（含 10 題困難陷阱）中，最危險的 NM→SUPPORTED 仍為 0。現有證據支持模型在這一格表現穩定，但每題只跑一次，未評估隨機性。

### 7.3 敘述人工抽查

4 案中有 3 案（n02、n03、n04）出現「relaxation」或「relaxation 為 null」等內部欄位名稱，v1 執行時只有 n02 一案。同一輸入在不同執行間結果不同，發現事項 3 應優先處理。

### 7.4 v2 用量

| 項目 | 數量 |
| :--- | :--- |
| LLM（追問 62 次 + 敘述 4 次） | 66 次請求（無重試） |
| LLM Token | 輸入 57,165、輸出 32,480（其中 thinking 26,143）、合計 89,645 |
| Embedding 寫入（`--reindex`） | 22 次呼叫、69 個切片、8,552 字元 |
| Embedding 查詢 | 37 次呼叫、531 字元 |

正式索引文件數執行前後皆為 2211。
