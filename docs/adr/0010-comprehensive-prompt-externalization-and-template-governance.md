# ADR-0010: 全面提示詞外部化與評判模板資產化治理 (Comprehensive Prompt Externalization & Template Governance)

## 1. 狀態
已採納 (Accepted)

## 2. 背景與問題陳述 (Context & Problem Statement)
在實施 Twelve-Factor 配置治理與架構防線規範時，專案要求「零硬編碼提示詞，100% 透過外部資產檔案管理」。
經代碼庫全面盤查，發現以下問題：
1. `src/infrastructure/validators/llm_judge.py` 雖將裁判系統指引抽離為 `judge_system.md`，但方法內部仍以 f-string 硬編碼視覺與文字評判時的使用者提示詞模板結構（包含 `=== 原始文件資訊 ===`、`<resume_content>` 標籤骨架與字段插值）。
2. `src/infrastructure/transformers/gemini_transformer.py` 的 `vision_convert.md` 提示詞未統一定義於模組頂層常數。
3. `src/infrastructure/prompts/` 套件目錄缺少獨立提示詞檔案備份，當以套件方式分發時存在 fallback 缺失風險。
4. AST 靜態稽核工具 `audit_guardrails.py` 過去對提示詞硬編碼設定了 80 字元的過高門檻，導致短字串拼接或結構性標籤模板未被及時阻斷。

## 3. 評估選項 (Options Evaluated)
* **選項 A：僅保留 system_prompt 外部化，使用者模板保留在 Python 代碼**
  - 優點：調用端不需額外載入模板檔案。
  - 缺點：違反零硬編碼防線，修改模板仍需改動 Python 代碼與重啟部署，且提示詞注入圍欄結構無法獨立版控。
* **選項 B：全面 100% 提示詞外部化 + 依賴注入模板 + AST 嚴密阻斷防禦**
  - 優點：
    1. 將視覺評判模板 (`judge_vision_prompt.md`) 與文字評判模板 (`judge_text_prompt.md`) 全數抽離至 `prompts/`。
    2. `GeminiLlmJudge` 透過建構子支援自訂模板依賴注入，遵循依賴反轉 (DIP)。
    3. 同步提示詞檔案至 `src/infrastructure/prompts/` 完善 fallback 機制。
    4. 升級 `audit_guardrails.py` 靜態掃描規則，全面杜絕硬編碼提示詞。

## 4. 架構決策 (Decision Outcome)
採納 **選項 B**。
1. 在 `prompts/` 與 `src/infrastructure/prompts/` 分別建立 `judge_vision_prompt.md` 與 `judge_text_prompt.md`。
2. 重構 `GeminiLlmJudge`，將內部寫死的提示詞模板替換為外部載入的模板與 `str.format()` 插值。
3. 規範 `GeminiTransformer` 之 `VISION_CONVERT_PROMPT` 模組頂層常數載入。
4. 升級 `audit_guardrails.py`，使 AST 掃描對 Prompt 特徵標記與長度具備更嚴格的防禦。

## 5. 8 大架構審查維度評估 (Architecture Review Analysis)
1. **個資隱私 (PII)**：外部履歷內容統一包裹於 `<resume_content>` 標籤中，防止 Prompt 注入及個資越獄。
2. **容量與極限 (Capacity)**：提示詞透過 `load_prompt()` 的 `lru_cache` 快取，無額外記憶體與磁碟 I/O 開銷。
3. **非同步與演進 (Async / Evolution)**：提示詞無狀態，支援不同業務領域或語系模板的熱插拔抽換。
4. **成本與熔斷 (Cost & Circuit Breaker)**：不改變 Token 計算與重試熔斷機制。
5. **可抽換性 (Portability & Decoupling)**：符合 Clean Architecture DIP 原則，不影響 Use Case 調用契約。
6. **惡意輸入與配額硬上限 (Input Security & Bomb Defense)**：維持既有 25MB / 30 頁等防禦限制。
7. **向量索引演進與藍綠遷移 (Index Evolution & Migration)**：不影響 Redis 向量架構。
8. **分散式併發與全鏈路可觀測性 (Concurrency & Observability)**：提示詞載入失敗具備詳細 log 記錄與備用機制。
