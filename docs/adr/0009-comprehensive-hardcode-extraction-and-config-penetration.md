# ADR-0009: 全面硬編碼提取、配置貫通與文字轉檔提示詞資產解耦

## 1. 狀態
已採納 (Accepted)

## 2. 背景與問題陳述 (Context & Problem Statement)
雖然在 ADR-0007 與 ADR-0008 中已建立 Twelve-Factor 配置治理架構，但在更深入的全面代碼審查中發現以下隱患：
1. **配置貫通中斷 (P0)**：在 `convert_to_md.py --index-to-redis` 進行轉檔後入庫時，實例化 `MarkdownChunker`、`GeminiEmbeddingService` 與 `RedisVectorStore` 時未傳入 `AppConfig` 的多項設定，導致使用建構子預設值，與 `index_to_redis.py` 行為不一致。
2. **診斷閥值寫死 (P1)**：`PdfHealthProbe` 中的掃描檔字元門檻（30）與 104 混淆字型門檻（10 個 \ufffd、30 個 ~~）硬編碼在方法內部。
3. **資料庫與檢索超參數寫死 (P1)**：`RedisVectorStore` 的 HNSW 初始容量（INITIAL_CAP: 1000）與檢索過濾門檻（無過濾）寫死在代碼中。
4. **生成參數與提示詞未解耦 (P2)**：Gemini 生成缺少可控溫度與 Token 上限；且 `transform_text` 的提示詞直接寫死在 Python 模組內，未如同 `vision_convert.md` 一樣抽離至 `prompts/`。

## 3. 評估選項 (Options Evaluated)
* **選項 A：僅修復 `--index-to-redis` 的參數注入，其餘內部閥值維持常數**
  - 優點：改動最小。
  - 缺點：極端履歷場景下探測閥值不可微調，提示詞與代碼緊密耦合，違反 Twelve-Factor 配置治理原則。
* **選項 B：全盤提取至 `AppConfig`、修復穿透注入，並將純文字提示詞徹底抽離至 `prompts/` 資產目錄**
  - 優點：
    1. 提示詞 Engineering 與業務代碼解耦，便於獨立 Git 版控與優化。
    2. 所有安全與演算法門檻（包含自訂技能清單 `EXTRA_SKILL_PATTERNS` 與最低相似度 `SEARCH_MIN_SCORE`）皆可由 `.env` 動態覆寫。
    3. `--index-to-redis` 100% 貫通配置，行為與 `index_to_redis.py` 完全對齊。
  - 缺點：需同步更新多個基礎設施組件建構子、配置驗證與單元測試。

## 4. 架構決策 (Decision Outcome)
採納 **選項 B**。
1. 在 `prompts/` 建立 `text_convert.md` 與 `text_review.md`，由 `load_prompt` 快取載入。
2. 擴充 `AppConfig` 包含 `gemini_temperature`、`gemini_max_output_tokens`、`pdf_scanned_min_chars`、`pdf_obfuscated_ufffd_threshold`、`pdf_obfuscated_strikethrough_threshold`、`redis_hnsw_initial_cap`、`search_min_score`、`extra_skill_patterns` 與 `default_output_dir`。
3. `PdfHealthProbe`、`RedisVectorStore`、`MarkdownChunker`、`GeminiTransformer` 全面支援建構子依賴注入。
4. 修正 `src/interfaces/cli/runner.py` 的參數貫通漏洞。

## 5. 架構維度影響分析 (Architecture Analysis)
* **安全與防禦**：Prompt 上下文圍欄 `<resume_content>` 維持在獨立 prompt 檔案中，防範提示詞注入。
* **能耗與 Token**：可由 `.env` 動態控制 `GEMINI_TEMPERATURE` 與 `GEMINI_MAX_OUTPUT_TOKENS`，兼顧成本與生成穩定度。
* **擴展性**：企業招聘不同職類時，可透過 `EXTRA_SKILL_PATTERNS` 免改碼動態擴充技能標籤庫。
* **可維護性**：提示詞變更無須重構或編譯 Python 代碼。
