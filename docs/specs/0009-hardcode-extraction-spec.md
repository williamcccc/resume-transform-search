# PRD 與 DDD 技術實作規格書 (Gate 1: Hardcode Extraction & Config Penetration)

## 1. 執行摘要 (Executive Summary)
本規格書針對全專案代碼庫進行 Twelve-Factor 配置治理深化，徹底消除剩餘之演算法診斷閥值、HNSW 容量、生成模型超參數、提示詞資產以及 CLI 入庫時配置穿透不足之硬編碼問題。

---

## 2. 產品需求規格 (PRD)

### 2.1 需求背景與痛點
1. **配置穿透中斷 (P0)**：在 `convert_to_md.py --index-to-redis` 時，因未注入 `AppConfig` 參數，導致索引名稱、切片大小、向量維度等配置退回預設值。
2. **診斷閥值硬編碼 (P1)**：PDF 掃描字數判定（30字）、104 混淆字型判定（10 個 \ufffd、30 個 ~~）無法因應極端履歷彈性微調。
3. **資料庫與檢索硬編碼 (P1)**：RediSearch HNSW 初始容量（1000）與檢索最低相似度門檻（目前無門檻）寫死在代碼中。
4. **生成參數與提示詞未解耦 (P2)**：Gemini 採樣溫度與 Token 上限未設定；純文字轉檔提示詞硬編碼在 Python 代碼中。
5. **技能標籤無法擴充 (P2)**：技能清單寫死 40 個，無法針對特定領域擴充。

### 2.2 驗收標準 (Acceptance Criteria, AC)
* **AC-1 (Twelve-Factor)**：所有新增之閥值與超參數均可由 `.env` 與 `AppConfig` 注入，且支援安全解析（非數字或缺失時回退預設值，零崩潰）。
* **AC-2 (配置完整貫通)**：CLI `convert_to_md.py --index-to-redis` 100% 採用 `AppConfig` 內的索引名稱、前綴、維度與切片上下限。
* **AC-3 (Prompt 資產獨立)**：`transform_text` 與 `review` 提示詞抽離為 `prompts/text_convert.md` 與 `prompts/text_review.md`，程式碼中 0 行硬編碼提示詞。
* **AC-4 (向下相容性)**：所有既有 CLI 命令與既有測試 100% 保持相容與綠燈。

---

## 3. DDD 技術實作規格 (Tech Spec)

### 3.1 領域層 (Domain Layer)
* `src/domain/models.py`:
  - `SearchQuery`: 新增 `min_score: float = 0.0`。

### 3.2 應用層 (Application Layer)
* `src/application/search_resumes_use_case.py`:
  - 協調 `IVectorStore.search` 時支援 `min_score` 門檻篩選。

### 3.3 基礎設施層 (Infrastructure Layer)
* `src/infrastructure/config.py`:
  - 擴充 9 項配置屬性與解析邏輯：
    - `gemini_temperature: float = 0.2`
    - `gemini_max_output_tokens: int = 8192`
    - `pdf_scanned_min_chars: int = 30`
    - `pdf_obfuscated_ufffd_threshold: int = 10`
    - `pdf_obfuscated_strikethrough_threshold: int = 30`
    - `redis_hnsw_initial_cap: int = 1000`
    - `search_min_score: float = 0.0`
    - `extra_skill_patterns: List[str]`
    - `default_output_dir: Optional[str] = None`
* `src/infrastructure/probes/pdf_probe.py`:
  - 建構子接收 `scanned_min_chars`、`ufffd_threshold`、`strikethrough_threshold`。
* `src/infrastructure/stores/redis_vector_store.py`:
  - 建構子接收 `hnsw_initial_cap`。
  - `search()` 支援依 `query.min_score` 過濾。
* `src/infrastructure/chunkers/markdown_chunker.py`:
  - 建構子接收 `extra_skill_patterns`，動態擴充技能正則。
* `src/infrastructure/transformers/gemini_transformer.py`:
  - 建構子接收 `temperature` 與 `max_output_tokens`，傳遞至 `GenerateContentConfig`。
  - 改用 `load_prompt("text_convert.md")` 與 `load_prompt("text_review.md")`。
* `prompts/text_convert.md` 與 `prompts/text_review.md`:
  - 獨立存放純文字轉換與審查提示詞。

### 3.4 表現層 (Interfaces Layer)
* `src/interfaces/cli/runner.py`:
  - 工廠函式 `build_use_case` 貫通所有參數。
  - `--index-to-redis` 貫通注入 `AppConfig`。
* `search_resumes.py`:
  - 支援 `--min-score` 引數，預設讀取 `config.search_min_score`。

---

## 4. 8 大架構前審檢核 (Gate 1 Checklist)
1. **PII 隱私安全**：通過 (Prompt 圍欄防注入，日誌零洩漏)。
2. **容量與極限**：通過 (HNSW INITIAL_CAP 可調控，Token 上限可設)。
3. **無狀態演進**：通過 (無全域可變狀態)。
4. **成本與配額**：通過 (可控溫度與 Token，Text-First 優先)。
5. **DIP 依賴反轉**：通過 (Domain 層純潔，UseCase 依賴 Protocol)。
6. **防護硬上限**：通過 (延續 25MB, 30頁, 10x 膨脹比)。
7. **冪等性**：通過 (Redis 向量寫入前清除舊切片)。
8. **配置解耦**：通過 (符合 Twelve-Factor 第三條)。
