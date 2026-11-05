# PRD 與 DDD 技術實作規格書 (Gate 1 規格審核)

## 一、產品需求文件 (PRD)

### 1. 商業與架構背景
為了解決多 Agent 協同對話過程中的「Token 膨脹」、「注意力稀釋」、「反覆修復失憶」以及資料載入時的「記憶體全量佔用」與多模態 Review「圖片重複傳送 Token 暴衝」，本變更聚焦落地 3 大核心風險點防護，使系統兼具極限 Token 經濟性、零記憶體洩漏與穩定聚焦的 Agent 切換。

### 2. 範疇界定 (Scope)
* **In-Scope**:
  1. **[風險點 1] 多 Agent 狀態記憶治理與上下文交接協議**：
     - 在 `AGENTS.md`、`GEMINI.md`、`.agents/` 與各 Agent/Skill 中正式建立《狀態記憶三態決策矩陣 (Retain, Summarize, Discard)》。
     - 定義標準《狀態交接 DTO (Context Handoff Schema)》與 Step 6 (Auto-Fix) 增量日誌防禦 (Delta-only Traceback)。
  2. **[風險點 2] 履歷向量入庫延遲串流讀取 (Lazy Streaming)**：
     - 將 `IndexResumesUseCase` 中目錄搜尋與批次讀取改為描述元 (Descriptor) 延遲讀取模式，避免全量檔案一次性載入 RAM，記憶體佔用降至 $O(1)$，且 `limit` 提前生效避免多餘磁碟 I/O。
  3. **[風險點 3] 多模態 Review 圖片 Token 節流與自適應保護**：
     - 在 `AppConfig` 增加 `vision_review_max_pages`（預設 5）。
     - `GeminiTransformer.transform_vision` 增加自我審查自適應保護：頁數超過門檻時，第 2 輪切換為純文字結構自我校驗，避免重複傳送所有高解析度 PNG 圖片，大幅節省 Token。
* **Out-of-Scope**:
  - 不變動對外 CLI 引數（100% 向後相容）。
  - 不修改 Redis Schema 欄位名稱。

### 3. 驗收標準 (Acceptance Criteria)
* **AC-1 (Agent Memory & Handoff)**: `AGENTS.md`、`GEMINI.md` 與 `auto-fix` 等 Agent 定義均載明 Retain/Summarize/Discard 決策矩陣、標準 JSON Handoff DTO、以及 Delta-only Traceback 機制。
* **AC-2 (Lazy Streaming Indexing)**: `IndexResumesUseCase` 處理目錄時，不預先將所有檔案 `read_text` 載入記憶體；指定 `limit` 時只讀取指定筆數之檔案，通過單元測試驗證。
* **AC-3 (Vision Review Token Optimization)**: `GeminiTransformer.transform_vision` 當頁數超過門檻時，第 2 輪不發送重複圖片，改採文字層結構優化，顯著降低多模態 Token 消耗。
* **AC-4 (DDD Architecture Guardrails)**: `audit_guardrails.py` AST 掃描 100% 通過（零 P0 違規），96+ 單元測試全數綠燈。

---

## 二、8 大架構維度前審 (Gate 1 審查)

1. **依賴反轉 (DIP)**：Use Case 依然只依賴 Protocol 契約，無外層洩漏。
2. **向下相容性**：CLI 介面與所有現有命令列引數 100% 相容。
3. **無損與容錯性**：延遲串流讀取具備嚴密例外捕捉與錯誤收集，等冪性不受影響。
4. **Token 能效**：多模態圖片在長頁數下不重複送入第 2 輪 Chat，節省數萬 Token。
5. **記憶體治理**：檔案讀取即時釋放，RAM 消耗由 $O(N)$ 降為 $O(1)$。
6. **配置解耦 (12-Factor)**：新增參數 `VISION_REVIEW_MAX_PAGES` 納入 `AppConfig` 與 `.env.example`。
7. **測試覆蓋率**：所有異動具備 100% 離線白箱單元測試。
8. **安全防護**：日誌零洩漏，交接 DTO 僅包含摘要與標籤。
* **Gate 1 審查結論**：**PASS (通過)**。

---

## 三、DDD 技術規格書 (Tech Spec)

### 1. 模組變更清單
* `AGENTS.md` & `GEMINI.md`：補充章節 3 之《多 Agent 狀態記憶治理與上下文交接協議》。
* `.agents/skills/auto-fix/SKILL.md`：規範 Delta-only Traceback。
* `.agents/architect/AGENT.md`、`.agents/developer/AGENT.md`、`.agents/gatekeeper/AGENT.md`：交接合約引用 Context Handoff DTO。
* `src/infrastructure/config.py`：新增 `vision_review_max_pages` 屬性。
* `src/infrastructure/transformers/gemini_transformer.py`：實現 `vision_review_max_pages` 自適應 Review。
* `src/application/index_resumes_use_case.py`：實現 `descriptors` 延遲讀取。
* `tests/unit/test_streaming_and_memory.py`：新增串流與記憶體治理單元測試。

---

## 四、QA 驗收測試案例矩陣 (Test Matrix)

| 測試編號 | 測試名稱 | 測試方式 | 預期結果 |
| :--- | :--- | :--- | :--- |
| **TC-01** | 延遲串流索引測試 (`test_lazy_streaming_reads_on_demand`) | 單元測試 Mock `Path.read_text` | 當 `limit=2` 時，即使目錄有 10 份文件，`read_text` 僅被呼叫 2 次 |
| **TC-02** | 多模態 Review 頁數自適應測試 (`test_vision_review_adaptive_threshold`) | 單元測試 Mock `client.models` 與 `client.chats` | 頁數 <= 門檻時走 chat；超過門檻時第 2 輪走純文字 refinement 不重發圖片 |
| **TC-03** | `AppConfig` 新增參數載入測試 (`test_vision_review_config`) | 單元測試驗證環境變數與預設值 | 預設為 5，支援 `VISION_REVIEW_MAX_PAGES` 覆蓋 |
| **TC-04** | AST 架構防線靜態掃描 | 執行 `audit_guardrails.py` | 100% 通過，零 P0 違規 |
| **TC-05** | 全套單元測試回歸驗證 | 執行 `unittest discover` | 所有既有 96 項測試 + 新增測試 100% 綠燈 |
