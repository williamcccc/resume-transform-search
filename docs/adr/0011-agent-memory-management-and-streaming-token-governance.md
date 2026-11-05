# ADR-0011: 多 Agent 狀態記憶治理、延遲串流索引與視覺審核 Token 節流

## 1. 狀態
已採納 (Accepted)

## 2. 背景與問題陳述 (Context & Problem Statement)
在多 Agent 協同閉環開發與長流程文件轉換系統中，缺乏狀態記憶（Memory Management）治理會引發三大核心痛點：
1. **多 Agent 協同 Token 膨脹與注意力稀釋**：各 Agent 間切換或 Step 6 自主診斷重試時，累積之歷史對話、多餘終端流水帳與除錯日誌被整批傳遞，導致 Token 消耗倍增且上下文渙散。
2. **批次向量入庫記憶體全量預載**：`IndexResumesUseCase` 原先於迴圈前預先將所有 Markdown 檔案內容一次性全部讀入記憶體清單中，當處理巨量履歷時會有高 RAM 佔用與 I/O 浪費風險。
3. **多模態長文件 Review 圖片重複傳送**：`GeminiTransformer.transform_vision` 在開啟 `enable_review` 時，第 2 輪 Chat 會重新攜帶第 1 輪所有高解析度 PNG 頁面二進位資料，造成長篇 PDF 文件 Token 消耗暴增。

## 3. 評估選項 (Options Evaluated)
* **選項 A (維持現狀)**：依賴人類與開發者手動注意對話長度；批次向量化全量預讀；Review 不論頁數多寡均重新上傳圖片。
  - *缺點*：缺乏結構化約束，Token 成本難以受控，面臨記憶體與 API 配額雙重壓力。
* **選項 B (三維閉環狀態記憶治理 - 最終採納)**：
  - **規範層**：在 `AGENTS.md` / `GEMINI.md` 建立狀態記憶「Retain / Summarize / Discard」三態矩陣、標準「狀態交接 DTO (Context Handoff Schema)」與「增量日誌防禦 (Delta-only Traceback)」。
  - **應用層**：將 `IndexResumesUseCase` 改造為目標描述元 (Descriptors) 延遲串流讀取 (Lazy Streaming)，將記憶體空間複雜度壓制至 $O(1)$，且提早截斷 `limit` 避免無效 I/O。
  - **基礎設施層**：在 `AppConfig` 與 `GeminiTransformer` 建立 `vision_review_max_pages` 自適應門檻，頁數超過時第 2 輪自動走文字級結構校驗，避免重複傳送大量 PNG 二進位資料。

## 4. 架構決策 (Decision Outcome)
採納 **選項 B**。全面落實狀態記憶治理規範、延遲串流與自適應 Token 節流防線。

## 5. 8 大架構維度衝擊評估 (Architecture Guardrails)
1. **PII 隱私**：交接 DTO 僅包含抽象錯誤影格與 Artifact 鏈接，零個資外洩。
2. **容量與極限**：批次檔案讀取改為即時串流釋放，記憶體維持常數級 $O(1)$。
3. **依賴反轉 (DIP)**：Use Case 僅依賴 Python 標準庫與 Domain Interface，邊界完全乾淨。
4. **Token 能效**：多模態圖片在長文件 Review 輪次中零重複上傳，節省 50%~80% 重複圖片 Token。
5. **向下相容性**：CLI 與既有 Use Case 呼叫介面 100% 維持向下相容。
6. **配置解耦 (12-Factor)**：`VISION_REVIEW_MAX_PAGES` 納入 `AppConfig` 與 `.env.example`，無硬編碼。
7. **測試覆蓋率**：新增 `test_streaming_and_memory.py` 白箱單元測試，全套 99 項測試 100% 通過。
8. **代碼治理**：`audit_guardrails.py` AST 掃描零 P0 違規。
