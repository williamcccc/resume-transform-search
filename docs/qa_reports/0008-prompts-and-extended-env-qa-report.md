# QA 實測驗收報告：類別 A/B 擴充參數提取與 Prompt 獨立版控

## 1. 測試執行總結 (Executive Summary)

- **測試日期**：2026-11-04
- **測試目標**：
  1. 驗證類別 A (4項) 與 類別 B (6項) 共 10 項擴充參數完整提取至 `.env` 與 `AppConfig`。
  2. 驗證 `vision_convert.md`, `self_review.md`, `judge_system.md` 抽離為獨立檔案後的加載、快取與 fallback 正常。
  3. 驗證所有 Readers, Use Cases, Stores 與 Validators 透過 DIP 依賴注入運作正常。
- **測試範圍**：
  1. 白箱單元測試 (`tests/unit/`)
  2. 黑箱/灰箱 E2E 端到端測試 (`tests/e2e/`) (使用獨立 DB 15 隔離庫)
  3. CLI 工具實測 (`search_resumes.py`, `convert_to_md.py`)
- **測試結果**：**100% 通過 (PASS)**，零功能瑕疵、零未預期例外。

---

## 2. 測試矩陣與覆蓋結果 (Test Matrix & Results)

| 測試編號 | 測試模組 / 項目 | 驗證情境 | 測試結果 | 備註 |
| :--- | :--- | :--- | :--- | :--- |
| **TC-ENV2-01** | `test_app_config.py` | 驗證 27 項配置欄位預設值 | **PASS** | 100% 離線 Mock 驗證 |
| **TC-ENV2-02** | `test_app_config.py` | 驗證自訂環境變數載入與覆寫 | **PASS** | 包含 HNSW, 保留率, DPI 等精準加載 |
| **TC-ENV2-03** | `test_app_config.py` | 非法字串格式容錯退避 | **PASS** | 非數字與非法 float 平穩退回預設值 |
| **TC-ENV2-04** | `test_prompt_loader.py` | 獨立 Prompt Markdown 檔案載入 | **PASS** | 3 個核心提示詞讀取正確 |
| **TC-ENV2-05** | `test_prompt_loader.py` | 缺失檔案之 Fallback 容錯 | **PASS** | 提供 fallback 文字時正常回傳 |
| **TC-ENV2-06** | `test_token_optimization_e2e.py` | E2E 測試流程 (Redis DB 15 隔離庫) | **PASS** | 6 個端到端測試 27.2s 綠燈 |
| **TC-ENV2-07** | `search_resumes.py` | CLI 自然語言即時檢索 | **PASS** | 成功檢索 2 筆切片，相似度 64.6% |

---

## 3. 測試執行數據摘要

```text
======================================================================
1. 單元測試 (Unit Tests):
   Ran 88 tests in 3.176s (OK)
   - 88/88 綠燈，新增 test_prompt_loader.py 驗證 Prompt 版控

2. E2E 端到端測試 (Integration & E2E):
   Ran 6 tests in 27.232s (OK)
   - 6/6 綠燈，Redis DB 15 建立、驗證與銷毀順暢

3. CLI 實測 (Live Search):
   python search_resumes.py "Golang" --top 2
   - 正常解析並輸出候選人切片與技術標籤
======================================================================
```
