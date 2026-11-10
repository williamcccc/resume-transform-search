# QA-0023：檢索與抽取品質指標計算模組 實測驗收報告

* **對應規格**：[Spec-0023](../specs/0023-retrieval-quality-metrics-spec.md)
* **對應實作**：[evaluation_metrics.py](../../src/domain/evaluation_metrics.py)
* **測試檔**：[test_evaluation_metrics.py](../../tests/unit/test_evaluation_metrics.py)
* **結論**：AC1 至 AC8 全部有對應測試並通過，共 25 個測試，0 失敗。

## 一、AC 追溯矩陣

| AC | 內容 | 對應測試 | 結果 |
| :--- | :--- | :--- | :--- |
| AC1 | Recall@K 手算、K 超過長度、空相關回傳 None | `TestRecall`（3 項） | 通過 |
| AC2 | Precision@K 分母為實際長度、空 ranked 回傳 0.0 | `TestPrecision`（3 項） | 通過 |
| AC3 | MRR 名次倒數、全未命中為 0.0、空相關回傳 None | `TestReciprocalRank`（3 項） | 通過 |
| AC4 | nDCG 完美排序、折扣手算、IDCG 以 min(K, 相關數) 計 | `TestNdcg`（4 項） | 通過 |
| AC5 | 欄位 F1：大小寫與空白不敏感、清單集合比對、雙空與單空 | `TestFieldF1`（6 項） | 通過 |
| AC6 | 重複 ID 去重、K 非法拋 ValueError、空相關排除 | `TestDedupeAndK`（3 項） | 通過 |
| AC7 | summarize_retrieval 計數與平均只計非 None | `TestSummarize`（2 項） | 通過 |
| AC8 | 模組僅匯入標準庫（AST 檢查） | `TestDomainPurity`（1 項） | 通過 |

## 二、邊界對抗補充

- K 為 0、-1、布林值 True、浮點數 2.0 均被拒絕，避免靜默錯誤。
- 重複 ID 不會因重複出現而抬高 Recall 或 MRR。
- 欄位值為 None 或空字串時視為缺漏，不會誤判為命中。

## 三、執行環境與限制

- 初次實作在沙箱的 Python 3.10 執行，只跑本模組測試（沙箱缺少 `pymupdf`）。
- 補測：於 Python 3.13.14 與完整依賴下，以 CI 相同指令 `python -m unittest discover -s tests/unit -p "test_*.py"` 執行全套回歸，**540 個測試全數通過**（含本模組 25 個），無回歸。
- 本模組為純函式，未被任何 Use Case 或介面引用，沒有 E2E 測試，驗收以單元層為主；`tests/e2e/` 既有測試與本次變更無關，未重跑（其 LIVE 軌會呼叫真實 Gemini API 消耗 Token）。

## 四、Gate 2 摘要

- `audit_guardrails.py` 掃描結果：全部 8 項檢查通過，含 Domain 層純潔性與零硬編碼。
- `verify_doc_sync.py` 結果：退出碼 0，規格 0023 的品質範圍宣告與索引登錄均已通過。
