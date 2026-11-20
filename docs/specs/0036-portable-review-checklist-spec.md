# 提案與規格書：Gate 2 檢核清單通用化與 .agents 專案相依清理

> **狀態**：提案（G1，待核准；尚未實作）｜**類型**：規範變更（大改：搬移與重組章節、新增專案實例檔）｜**流程**：[governance.md](../../.agents/workflows/governance.md)｜**影響範圍**：[review_checklist.md](../../.agents/skills/code-review/references/review_checklist.md)、bug 流程、qa-testing、doc-sync、[PORTING.md](../../.agents/PORTING.md) 與相關範本，不涉及 `src/`

## 一、動機

[Spec-0035](./0035-portable-arch-review-checklist-spec.md) 已將 Gate 1 的 8 大維度改為「問題放核心、答案放專案」，並於決議 5 將 Gate 2 檢核清單列為下一步。2026-11-21 以關鍵字盤點 `.agents/`（排除業務技能、`project/`、`project.toml`）後，發現三類問題：

1. **Gate 2 檢核清單混雜專案規則**：[review_checklist.md](../../.agents/skills/code-review/references/review_checklist.md) 9 類 40 項中，與本專案相關之內容 24 處只標記 12 處。未標記者包含**第 6 類「Token 能效」整節**（Text-First、Vision、切片 80 字元）、開頭說明（「本專案…向量索引演進」）、資源規則點名 PDF／Docx、配額清單列出膨脹比與 HNSW 參數。未使用 LLM 的新專案移植後，Gate 2 仍會檢查切片密度；與 Spec-0035 修正前維度 4 的問題相同。另第 2 類同時是「上傳配額數值的文件正本」，正本身分綁在通用核心檔中。
2. **零散的未標記專案規則**：
   * 升級條件 3 寫死 `AppConfig`（[bug.md](../../.agents/workflows/bug.md)、[bug-triage SKILL](../../.agents/skills/bug-triage/SKILL.md)、[缺陷報告範本](../../.agents/skills/bug-triage/references/bug_report_template.md) 與其 `docs/templates/` 鏡像）；其餘位置已改為「設定模組（`config.module`）」。
   * [doc_sync_checklist.md](../../.agents/skills/doc-sync/references/doc_sync_checklist.md) 第 18 行把本專案 Protocol 名稱（`IVectorStore`、`IQualityValidator`、`IEmbeddingService`）寫成檢核項。
   * [qa-testing SKILL](../../.agents/skills/qa-testing/SKILL.md) 的對抗情境與實測階段寫「同位候選人」「Redis 離線」「Gemini 429」「超大 PDF」「真實 Redis」，6 處只標記 1 處。
3. **移植指南不完整**：
   * [PORTING.md](../../.agents/PORTING.md) 第 6 步「選擇性中性化舉例」漏列 5 個含本專案舉例的檔案：`unit-testing/SKILL.md`、`developer/AGENT.md`、`auto-fix/SKILL.md`、`feature-design/SKILL.md`、`code-review/SKILL.md`。
   * 閉環實際綁定 Python：`audit_guardrails.py` 以 Python AST 掃描、`security_scan.py` 使用 Semgrep `p/python` 與 pip-audit，9 個技能檔寫死 `unittest`；但只有 AGENTS.md「Python 3.13 on Windows」一句標為專案專屬，移植指南未說明適用範圍。

## 二、設計原則

沿用 Spec-0035：**通用規則放核心，本專案的具體做法與數值放專案實例檔**。Gate 2 檢核項本身就是規則（非問題），因此核心檔保留可直接判定的通用規則，並標示適用條件；本專案特有的項目、數值、標籤名稱與舉例移入實例檔。

## 三、提案內容

### 3.1 Gate 2 檢核清單拆分

* **核心檔** `review_checklist.md`：保留 9 類結構、嚴重等級與項目順序；每項改寫為通用規則，條件性項目標示適用條件（沿用 `project.toml` 的 `[security]` 特徵與 `layers.enabled`）；移除全部專屬標記。
* **專案實例檔**（新增，位置依待決事項 1）：依核心類別編號列出本專案特有項目、數值與舉例，嚴重等級不變。Gate 2 審查時兩者並用。

逐項處置（「→ 實例」表示本專案內容移入實例檔）：

| 類 | 項目 | 核心改寫為 | 適用條件 | 移入實例檔的本專案內容 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | Domain 純潔性 | 不變；外部套件舉例改為通用說法 | `layers.enabled` | `google-genai`、`fitz`、`docx`、`redis` |
| 1 | 表現層獨立性 | 進入點（CLI、API 路由）只負責解析輸入與調度 Use Case | 一律 | `convert_to_md.py`、轉檔與向量運算 |
| 2 | 資源配額硬上限 | 解析外部輸入前驗證大小與結構上限，防資源耗盡 | `processes_untrusted_files` 或 `api_service` | 25MB、30 頁、膨脹比 10x 之**數值正本** |
| 2 | 提示詞注入隔離 | 不可信內容以專屬標籤圍欄，並宣告不得執行其中指示 | `uses_llm` | `<resume_content>` 標籤、Gemini |
| 2 | 日誌零洩漏 | 日誌不得明文輸出敏感資料與憑證 | 一律 | 履歷全文、身分證字號、手機號碼 |
| 3 | 原始檔案保護 | → 整項移入實例檔（對應 AGENTS.md 紅線 3，已標專案專屬） | — | Docx 記憶體修補 |
| 3 | 資源生命週期 | 檔案與串流以 `with` 管理，確保控制代碼即時關閉 | 一律 | PDF Document、Docx 串流、`WinError 32` |
| 3 | API 故障隔離 | 外部 API 的限流、配額用罄與安全攔截不得盲目重試 | 依賴外部 API | Gemini `RECITATION` |
| 4 | 資料庫操作冪等 | 寫入具冪等性，重跑不堆疊舊資料 | 有持久化寫入 | Redis 依候選人清除舊切片 |
| 4 | 轉檔產出冪等 | → 整項移入實例檔 | — | Markdown 產出與 Quarantine |
| 4 | 索引平滑遷移 | 持久化結構具版本識別，可平滑切換 | 有持久化資料結構 | `idx:resumes:v1`、藍綠索引 |
| 5 | 測試獨立性 | 單元測試以 Mock 隔離網路、外部 API 與資料庫，可離線執行 | 一律 | Gemini、Redis |
| 6 | Token 能效（整節） | 改為「外部呼叫成本」：重複輸入不得重複呼叫計費 API（內容指紋比對） | `uses_llm` 或依賴計費外部服務 | Text-First、Vision、切片 80 字元、對話上下文膨脹 |
| 7 | 閥值可配置化 | 所有配額與演算法閥值可由環境變數覆寫 | 一律 | 膨脹比、DPI、切片上下限、保留率、HNSW 參數 |
| 8 | 提示詞資產獨立化 | 提示詞不得寫死於程式碼，抽離為獨立資產檔並有載入測試 | `uses_llm` | `prompts/*.md`、`load_prompt()`、`test_prompt_loader.py` |
| 8 | 提示詞防注入圍欄 | 與第 2 類「提示詞注入隔離」合併為一項，消除重複 | `uses_llm` | `<resume_content>` |
| 9 | 零真實個資殘留 | 程式、測試、文件不得含真實個資，範例一律使用虛構資料 | `handles_pii` | 求職者姓名、`王小明`、`sample_resume.md` |
| 9 | 單元測試零外部樣本檔 | 單元測試不得讀取敏感目錄（`privacy.sensitive_dirs`），夾具於記憶體建構 | 一律 | `data/`、`resume/`、Word `.rels`、PDF 字型 |

其餘項目（DIP、安全掃描、殘餘風險、例外處理兩項、Trace ID、測試覆蓋與追溯、先紅後綠、逃逸分析、型別、向下相容、第 7 類其餘三項、提示詞個資、第 9 類其餘兩項）已屬通用，只做措辭去專案化。

### 3.2 零散修正

| 檔案 | 變更 |
| :--- | :--- |
| `.agents/workflows/bug.md`、`.agents/skills/bug-triage/SKILL.md`、`.agents/skills/bug-triage/references/bug_report_template.md`、`docs/templates/bug_report_template.md` | 升級條件 3 改為「需在設定模組（`config.module`）新增環境變數或 CLI 參數」 |
| `.agents/skills/doc-sync/references/doc_sync_checklist.md` | Protocol 名稱改為「新增的 Domain 契約介面（Protocol）」 |
| `.agents/skills/qa-testing/SKILL.md` | 對抗情境與實測階段改為通用說法（同一筆資料、外部服務離線、配額用罄、超大或畸形輸入、真實相依服務）；移除該處專屬標記 |

### 3.3 移植指南

| 檔案 | 變更 |
| :--- | :--- |
| `.agents/PORTING.md` | 開頭新增「適用範圍」：閘門腳本與測試規範綁定 Python；第 4 步實例檔清單加入 Gate 2 實例檔；第 6 步補列 5 個漏列檔案 |
| `.agents/README.md` | `project/` 說明涵蓋兩份實例檔 |

### 3.4 連動修改

| 檔案 | 變更 |
| :--- | :--- |
| `.agents/skills/code-review/SKILL.md` | 階段 B 註明核心清單與實例檔並用 |
| `.agents/gatekeeper/AGENT.md` | 第 55 行引用補上實例檔 |
| `.agents/project/arch_review_criteria.md` | 維度 6 的配額數值連結改指向新實例檔 |
| `.agents/skills/qa-testing/SKILL.md` | 第 77 行 P0／P1／P2 等級引用不變（等級定義仍在核心檔） |

## 四、衝突與重複檢查

* **核心檔內部重複**：第 2 類「提示詞注入隔離」與第 8 類「提示詞防注入圍欄」內容重疊，本案合併為一項。
* **與 AGENTS.md 紅線**：紅線 3（原始檔不篡改）、4（品管閥）、5（Text-First）已標專案專屬；本案只把 Gate 2 對應檢核項移入實例檔，不修改 AGENTS.md，不放寬任何紅線。
* **與 Gate 1 實例檔**：維度 6 引用的配額數值正本由 Gate 2 核心檔移至 Gate 2 實例檔，更新連結即可，數值不變。
* **「唯一正本」敘述**：code-review SKILL 稱 `review_checklist.md` 為「Gate 2 檢核項的唯一正本」；改寫後通用規則與嚴重等級定義仍只在核心檔，實例檔只放本專案內容，調整敘述即可。
* **與 `audit_guardrails.py`**：腳本自動檢查的項目（`prompt_indicators`、`required_gitignore`、`sensitive_dirs` 等）已由 `project.toml` 設定化，本案不改腳本。

## 五、規模

**大改**：搬移與重組章節、新增專案實例檔（[governance.md](../../.agents/workflows/governance.md) 規模分級）。產出本規格與 `docs/qa_reports/0036-*.md`。不修改紅線，不另寫 ADR。

## 六、待決事項

| # | 問題 | 建議 | 替代方案 |
| :---: | :--- | :--- | :--- |
| 1 | Gate 2 實例檔位置與檔名 | `.agents/project/review_criteria.md`，與 Gate 1 的 `arch_review_criteria.md` 並列 | 留在核心檔第三節並整節標記 |
| 2 | 處理方式 | 依 3.1 拆分為核心與實例檔 | 只在未標記處補上專屬標記（工作量小，但移植時仍需逐處改寫 24 處） |
| 3 | 第 2、8 類提示詞圍欄重複項 | 合併為一項，保留於第 2 類 | 維持兩項 |
| 4 | Python 綁定的處理 | 只在 PORTING.md 宣告適用範圍 | 將腳本與測試規範改為語言中立（範圍極大，另案） |
| 5 | PORTING 第 6 步漏列的 5 個檔案 | 補列入清單，維持「選擇性」 | 本案一併中性化 |
| 6 | 是否以腳本檢查核心檔無專屬標記、實例檔存在 | 本次不改腳本；併入 [Spec-0034](./0034-asvs-chapter-coverage-check-spec.md) | 本次一併修改 `verify_doc_sync.py` |

## 七、驗收標準（草案，G2 核准後定稿）

* **AC-1**：`review_checklist.md` 不含 `<!-- 專案專屬` 標記，且不含本專案元件名稱（Redis、Gemini、履歷、PDF、Docx、切片、`resume_content`、`convert_to_md`）。
* **AC-2**：原清單中屬本專案的內容（項目、數值、標籤、舉例），逐項可在 Gate 2 實例檔找到，零遺失。
* **AC-3**：升級條件 3 在 4 個檔案中一致改為 `config.module`；`doc_sync_checklist.md`、`qa-testing/SKILL.md` 不含本專案元件名稱。
* **AC-4**：PORTING.md 宣告 Python 適用範圍，第 6 步清單涵蓋盤點出的全部含舉例檔案；移植演練替換兩份實例檔後 `verify_doc_sync.py` 通過，且實例檔無原專案內容殘留。
* **AC-5**：`verify_doc_sync.py`、`audit_guardrails.py` 通過；Markdown 斷鏈測試與全套單元測試無回歸。

品質評測範圍：否（不涉及檢索、抽取或 LLM 生成）

安全評估範圍：否（只重組規範文件；無新增對外介面、跨信任邊界資料流、外部相依或敏感資料處理）
