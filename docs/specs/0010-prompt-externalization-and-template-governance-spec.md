# PRD & DDD 技術規格書：全面提示詞抽離與資產化治理 (Gate 1)

## 1. 產品需求文件 (PRD)

### 1.1 背景與痛點
本專案為遵循 DDD 與整潔架構的履歷解析與向量檢索系統。根據架構不可變紅線第六條（Twelve-Factor 配置治理與零硬編碼防線）：
「所有外部服務連線、機密憑證、安全配額、重試策略與演算法閥值，嚴禁在業務程式碼中硬編碼；提示詞必須抽離至獨立資產目錄並具備版本可追蹤性。」

在目前的實作中：
1. `src/infrastructure/validators/llm_judge.py` 雖然將系統評審員指引抽離為 `judge_system.md`，但在 `judge_document` 方法內，仍將視覺評判 (`review_instruction`) 與純文字評判 (`full_prompt`) 的模板骨架、標籤 (`<resume_content>`) 與結構說明直接以 f-string 硬編碼在 Python 代碼中。
2. `src/infrastructure/transformers/gemini_transformer.py` 在頂層載入了三個提示詞，但 `vision_convert.md` 卻在 `__init__` 中動態載入，缺乏模組層級常數一致性。
3. `src/infrastructure/prompts/` 作為 fallback 目錄，缺乏根目錄提示詞檔案的備用同步。

### 1.2 目標 (Goal)
- **100% 提示詞外部化**：全面掃描並將所有留在 Python 代碼中的提示詞模板抽離為獨立的 Markdown 資產檔案，放置於 `prompts/` 目錄。
- **依賴注入與可抽換性**：`GeminiLlmJudge` 與 `GeminiTransformer` 支援透過參數或環境配置注入自訂 Prompt，完全符合 DIP 原則。
- **靜態防禦升級**：強化 `audit_guardrails.py`，確保未來任何提示詞或模板字串未經抽離即寫入 Python 代碼時，會被 Gate 2 靜態代碼稽核直接阻斷。

### 1.3 範疇界定 (Scope)
- **In-Scope**：
  - 抽離 `src/infrastructure/validators/llm_judge.py` 中的提示詞模板至 `prompts/judge_vision_prompt.md` 與 `prompts/judge_text_prompt.md`。
  - 重構 `GeminiLlmJudge`，使其支援 `system_prompt`、`vision_prompt_template`、`text_prompt_template` 依賴注入與外部載入。
  - 規範 `GeminiTransformer` 之提示詞常數載入風格。
  - 同步提示詞檔案至 `src/infrastructure/prompts/` 作為套件層級 Fallback。
  - 升級 `audit_guardrails.py` 之提示詞靜態檢核規則。
  - 補齊/更新對應單元測試與 E2E 測試。
- **Out-of-Scope**：
  - 不變更 CLI 指令參數名稱（保證 100% 向下相容）。
  - 不變更 Gemini API 模型參數預設值。

### 1.4 驗收標準 (Acceptance Criteria, AC)
- **AC-1**：`src/` 內所有 Python 模組 0 硬編碼提示詞文字（包含 Prompt Injection 防護宣告、標籤模板等）。
- **AC-2**：`prompts/` 目錄具備完整的提示詞資產庫（包含新增之 `judge_vision_prompt.md` 與 `judge_text_prompt.md`）。
- **AC-3**：`GeminiLlmJudge` 能在傳入自訂 Prompt 或預設 Prompt 下正確組裝並解析評分結果。
- **AC-4**：單元測試 `tests/unit/test_llm_judge.py`、`test_hardcode_extractions.py` 與 E2E 測試 100% 通過。
- **AC-5**：`audit_guardrails.py` 稽核 100% 通過 (Gate 2 PASS)。

---

## 2. 8 大架構維度前審 (Arch Review - Gate 1)

1. **PII 隱私**：所有提示詞皆維持外部資料 `<resume_content>` 隔離標記，防止 Prompt Injection 與個資洩漏。
2. **容量與極限**：提示詞檔案均透過 `functools.lru_cache` 載入記憶體，零重複磁碟 I/O 開銷。
3. **非同步演進**：提示詞範本為無狀態純字串，支援併發多執行緒/非同步安全調用。
4. **成本與熔斷**：維持既有重試與熔斷機制，抽離提示詞不影響 Token 計算。
5. **可抽換性**：完全遵守 Protocol 介面（`ILlmJudge`），更換 Prompt 或模型零改動 Use Case。
6. **惡意輸入硬上限**：外部履歷內容注入保護宣告保留在 Prompt 資產中。
7. **向量索引演進**：不涉及 Redis Schema 變更。
8. **可觀測性**：載入失敗具備 logger 警告與 fallback 機制。

---

## 3. DDD 技術規格書 (Technical Specification)

### 3.1 提示詞資產規劃
在 `prompts/` 新增：
1. `judge_vision_prompt.md`：
   用於包含原始影像時的 LLM-as-a-Judge 提示詞模板。
   變數：`{system_prompt}`, `{filename}`, `{doc_type}`, `{markdown}`
2. `judge_text_prompt.md`：
   用於純文字對照時的 LLM-as-a-Judge 提示詞模板。
   變數：`{system_prompt}`, `{filename}`, `{doc_type}`, `{markdown}`, `{raw_text}`

### 3.2 基礎設施層重構 (`src/infrastructure/validators/llm_judge.py`)
```python
JUDGE_SYSTEM_PROMPT = load_prompt("judge_system.md")
JUDGE_VISION_PROMPT_TEMPLATE = load_prompt("judge_vision_prompt.md")
JUDGE_TEXT_PROMPT_TEMPLATE = load_prompt("judge_text_prompt.md")

class GeminiLlmJudge(ILlmJudge):
    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-3.8-flash",
        system_prompt: Optional[str] = None,
        vision_prompt_template: Optional[str] = None,
        text_prompt_template: Optional[str] = None,
    ):
        ...
```
在 `judge_document` 中，完全透過模板 `.format(...)` 組裝，代碼中零字串拼接提示詞。

### 3.3 測試規劃
- `tests/unit/test_llm_judge.py`：新增自訂提示詞模板注入測試與組裝正確性斷言。
- `tests/unit/test_hardcode_extractions.py`：擴充提示詞外部化斷言。
- `tests/unit/` 全量單元測試執行。
- `tests/e2e/` CLI E2E 實測。
- `audit_guardrails.py` AST 靜態檢核。
