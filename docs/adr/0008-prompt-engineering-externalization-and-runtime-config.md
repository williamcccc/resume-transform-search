# ADR-0008: Prompt Engineering 獨立檔案化與運行時演算法配置治理

## 1. 狀態
已採納 (Accepted)

## 2. 背景與問題陳述 (Context & Problem Statement)
隨著 LLM 應用深度演進，Prompt Engineering 已成為核心業務競爭力之一。然而過往 `SELF_REVIEW_PROMPT`（自我審核修復）與 `JUDGE_SYSTEM_PROMPT`（獨立評判員）直接以 Python 多行字串嵌入代碼內部，面臨以下挑戰：
1. **版控與審查困難**：工程師或提示詞調優專家難以在 Git 提交中清晰比較 Prompt 的語義微調與變更歷史。
2. **缺乏多版本支援**：無法在不修改 Python 原始代碼的情況下，透過載入不同 `.md` 檔案進行 A/B Testing 或專業領域切換。
3. **運行時參數殘留硬編碼**：DOCX 未壓縮上限、HNSW 拓撲參數（M、EF_CONSTRUCTION）、向量度量距離、品管保留率上下限等尚未對接 `.env`。

## 3. 評估選項 (Options Evaluated)
* **選項 A：繼續以 Python 模組常數管理 Prompt**
  - 優點：免去檔案 I/O。
  - 缺點：Prompt 與代碼混雜，無法獨立版本化，IDE 缺少 Markdown 語法高亮。
* **選項 B：Prompt 獨立檔案化 (專案根目錄 `prompts/*.md`) + 10 項擴充參數納入 `AppConfig`**
  - 優點：
    1. 提示詞提升至專案一級目錄（`prompts/`），享有純淨 Markdown 渲染與獨立 Git commit 記錄，易於追蹤與跨角色協作。
    2. 提供 `load_prompt()` 載入器，內建 LRU 記憶體快取與安全 fallback 機制。
    3. HNSW 索引、篇幅保留率、Word 記憶體上限等 10 項參數 100% 對接 Twelve-Factor `.env`。

## 4. 架構決策 (Decision Outcome)
採納 **選項 B**。
1. 建立專案根目錄 `prompts/`，一目了然收納 `vision_convert.md`、`self_review.md`、`judge_system.md`。
2. 在 `GeminiTransformer` 與 `GeminiLlmJudge` 透過建構子注入 prompt 文字或使用 `load_prompt` 動態加載。
3. 擴充 `AppConfig`，將 `REDIS_HASH_PREFIX`、`MAX_DOCX_UNCOMPRESSED_MB`、`REDIS_HNSW_M` 等 10 項參數完整納管。

## 5. 8 大架構審查維度評估 (Architecture Review Analysis)
1. **個資隱私 (PII)**：Prompt 檔案僅含審查規則與防注入圍欄，嚴禁內含特定人員個資。
2. **容量與極限 (Capacity)**：`MAX_DOCX_UNCOMPRESSED_MB` 可動態壓低，防禦超大 Word 檔案導致 OOM。
3. **非同步與演進 (Async / Evolution)**：Prompt 獨立後，可熱插拔抽換不同語言或行業別的提示詞。
4. **能耗與 Token (Token Economics)**：可微調 `PDF_TEXT_FIRST_MIN_CHARS` 與 `PDF_OCR_DPI` 精確調控 Token 消耗。
5. **可觀測性 (Observability)**：Prompt 載入失敗具備 logger 警告，絕不靜默失敗。
6. **成本與計費 (Cost & Billing)**：支援從外部配置停用高成本步驟。
7. **彈性與容錯 (Resilience)**：Prompt 檔案讀取失敗時可退回 fallback 文字。
8. **安全性與防護 (Security)**：Prompt 檔案完整保留 `<resume_content>` 資安隔離圍欄，杜絕提示詞注入。
