# 提案與規格書：閉環可移植化（專案專屬內容抽離為設定與標記）

> **狀態**：已核准（G2：使用者於 2026-11-20 核准，待決事項全數採建議）｜**類型**：規範變更（大改：修改驗證腳本、修改 AGENTS.md 第 1 節紅線文字）｜**流程**：[governance.md](../../.agents/workflows/governance.md)｜**影響範圍**：`AGENTS.md`、`.agents/**`、兩支閘門腳本與其單元測試，不涉及 `src/`

## 一、動機

使用者希望將本專案的雙門禁閉環（角色、技能、流程檔、閘門腳本）移植到其他專案。逐檔掃描後發現，閉環檔案中混有大量本專案專屬內容，移植時無法辨識哪些要改：

* **腳本寫死本專案的值**：[audit_guardrails.py](../../.agents/skills/code-review/scripts/audit_guardrails.py) 寫死 `src/domain` 等分層路徑、`redis_vector_store.py` 豁免、履歷檔名樣式、受保護身分的雜湊指紋；[verify_doc_sync.py](../../.agents/skills/doc-sync/scripts/verify_doc_sync.py) 寫死品質評測自規格 0023 起強制。
* **規範文字混雜通用原則與專屬規則**：例如 AGENTS.md 紅線 4（`MarkdownQualityValidator` 65 分隔離）整條屬於本專案，紅線 1（依賴反轉）則通用，但兩者沒有區分。
* **同一份清單寫在三處**：`.gitignore` 必備項目同時出現在 AGENTS.md 紅線 7、[review_checklist.md](../../.agents/skills/code-review/references/review_checklist.md) 與 `audit_guardrails.py`。
* **個資指紋有外洩到其他專案的風險**：`FORBIDDEN_PII_HASH_PREFIXES` 是本專案受保護身分的指紋，整包複製時會一併帶走。

本案採**就地重構**：本專案行為不變，但把專屬內容集中或標記，日後移植只需改一份設定、搜尋一種標記。

## 二、內容分類

| 類別 | 判準 | 處理方式 |
| :--- | :--- | :--- |
| **0 通用** | 換專案不需改 | 不動 |
| **1 設定** | 換專案只變「值」，規則不變 | 移入 `.agents/project.toml`，腳本改讀設定 |
| **2a 專屬規則** | 規則本身屬於本專案，靠 AI 讀文件遵守 | 原文保留，加上 `<!-- 專案專屬 -->` 標記 |
| **2b 專屬舉例** | 規則通用，只是舉例用了本專案元件 | **本案不處理**（決議第 3 項），於移植指南列為選擇性調整 |
| **3 規則＋腳本** | 規則屬於本專案，且由腳本檢查 | 值移入設定 ＋ 文字改為指向設定鍵名 ＋ 必要時加標記 |

## 三、設計

### 3.1 專案設定檔 `.agents/project.toml`

唯一正本，存放所有類別 1 與類別 3 的值。採 TOML，以標準庫 `tomllib` 讀取，不新增相依套件。草案結構（值為本專案現值）：

```toml
[layers]
enabled = true                          # false 時略過 Domain 純潔性與 Application DIP 檢查
src = "src"
domain = "src/domain"
application = "src/application"
infrastructure = "src/infrastructure"
interfaces = "src/interfaces"
domain_interfaces = "src/domain/interfaces.py"

[config]
module = "src/infrastructure/config.py" # 唯一可讀環境變數的模組
env_example = ".env.example"

[guardrails]
url_schemes = ["redis", "postgres", "postgresql", "mongodb", "amqp", "http", "https"]
api_key_patterns = ['AQ\.[a-zA-Z0-9_-]{20,}', 'AIzaSy[a-zA-Z0-9_-]{33}']
prompt_indicators = ["你是一個", "<resume_content", "..."]
eval_only_modules = ["ragas"]
required_gitignore = [".env", "data/", "resume/", "..."]
ignore_scan_dirs = [".git", ".venv", "..."]

[[guardrails.url_exceptions]]
path = "src/infrastructure/stores/redis_vector_store.py"
reason = "<說明為何此檔可含連線 URL 預設值>"

[privacy]
forbidden_hash_prefixes = ["..."]       # 移植時必須清空
safe_email_domains = ["example.com", "..."]
safe_filename_stems = ["sample", "..."]
sensitive_dirs = ["resume", "resumes", "markdown_out", "markdown_output", "output_md"]
personal_filename_keywords = ["CV", "resume"]
locale_patterns = ["tw_mobile", "tw_landline", "tw_id"]  # 選用腳本內建之地區樣式組

[docs]
quality_ac_enforced_from = 23
agents_max_lines = 200
```

設計要點：

1. **正規式留在腳本，設定只選用**：台灣手機、身分證等樣式結構複雜，不宜寫進設定；腳本內建具名樣式組，設定以 `locale_patterns` 選擇。
2. **豁免必須附理由**：`url_exceptions` 每筆必填 `reason`，缺少時腳本 FAIL。理由寫在設定旁，取代「規範文件另寫一份理由」，避免兩處不同步。
3. **設定檔缺漏時明確失敗**：找不到 `project.toml` 或缺必要鍵時，兩支腳本皆以非零碼結束並指出缺哪個鍵；**不提供隱含預設值**，否則新專案會在不知情下沿用本專案的值。
4. **工作區路徑改為動態推得**：`audit_guardrails.py:486` 寫死的工作區資料夾名稱，改以 `ROOT_DIR` 實際路徑組出比對樣式，不進設定。
5. **共用讀取模組**：新增 `.agents/lib/project_config.py`，負責讀檔、驗證必要鍵與 `reason` 欄位；兩支腳本皆引用，避免各寫一份（見決議第 6 項）。

### 3.2 文字端引用方式

規範文字不使用 `{{...}}` 模板語法（否則需要渲染步驟），改為**以職責指稱並註明設定鍵名**。例：

> 修改前：需修改 `src/domain/interfaces.py` 的 Protocol 或 DTO 欄位
> 修改後：需修改 Domain 契約檔（`project.toml` 的 `layers.domain_interfaces`，本專案為 `src/domain/interfaces.py`）的 Protocol 或 DTO 欄位

保留本專案現值於括號內，讓 AI 在本專案閱讀時不必另外查設定。

### 3.3 專屬規則標記

類別 2a 內容原文保留，於句末或段落後加 HTML 註解 `<!-- 專案專屬 -->`；需要說明專屬範圍時寫成 `<!-- 專案專屬：說明 -->`（如「Text-First 一句」「整個維度」）。表格內的標記放在儲存格內，避免破壞表格。渲染時不可見，AI 讀原始 Markdown 時可見；移植時全倉搜尋 `<!-- 專案專屬` 即可列出所有待改處。

**AGENTS.md 紅線不重新編號**：歷史規格、QA 報告與 ADR 多處以「紅線 5」等編號引用（如 [Spec-0019](./0019-recruitment-assistant-chat-spec.md)），拆成「通用紅線」與「本專案紅線」兩節會使舊引用失效。因此維持 1～7 編號，只在專屬條目加標記。

### 3.4 移植指南

新增 `.agents/PORTING.md`，並由 [.agents/README.md](../../.agents/README.md) 連結。內容：

1. 複製清單：`AGENTS.md`、`CLAUDE.md`（及選用 `GEMINI.md`）、`.agents/`、`.claude/`。
2. 刪除業務技能：`resume-vector-indexing`、`resume-vector-search` 及其轉接層。
3. 改寫 `project.toml`：逐鍵填寫，**清空 `privacy.forbidden_hash_prefixes`**，`docs.quality_ac_enforced_from` 改為 1。
4. 搜尋 `<!-- 專案專屬 -->`，逐處改寫或刪除。
5. 選擇性：調整類別 2b 舉例（附檔案清單）。
6. 建立空的 `docs/specs/`、`docs/qa_reports/`、`docs/adr/`、`docs/bugs/`、`docs/templates/` 與索引，執行兩支腳本確認通過。

## 四、修改檔案

| 檔案 | 變更 |
| :--- | :--- |
| `.agents/project.toml` | 新增；本專案現值 |
| `.agents/lib/project_config.py` | 新增；設定讀取與驗證 |
| [audit_guardrails.py](../../.agents/skills/code-review/scripts/audit_guardrails.py) | 第 39–42、222–240、285、307、319、329–394、470、486、519 行等寫死值改讀設定；新增 `layers.enabled` 開關 |
| [verify_doc_sync.py](../../.agents/skills/doc-sync/scripts/verify_doc_sync.py) | `QUALITY_AC_ENFORCED_FROM`、`AGENTS_MAX_LINES` 改讀設定 |
| `tests/unit/test_project_config.py` | 新增；設定讀取、缺鍵、缺 `reason`、`layers.enabled=false` 略過分層檢查 |
| `tests/unit/test_github_pre_publish_hygiene.py` | `.gitignore` 必備清單、掃描略過目錄、設定模組路徑改讀 `project.toml`（G5-01） |
| `tests/e2e/test_portable_closed_loop_e2e.py` | 新增；AC-3 設定缺漏與開關、AC-6 移植演練 |

> 實作後修訂：其餘既有測試（`test_audit_eval_only_imports.py`、`test_quality_ac_gate.py`、`test_claude_adapter_sync.py`、`test_workflow_tracks_doc_sync_e2e.py`）因腳本仍讀取真實專案之 `project.toml`、E2E 複製整個 `.agents/`，無須修改。
| [AGENTS.md](../../AGENTS.md) | 紅線 1、6、7 與 §2 品質評測第 1 條改為指向設定鍵名；紅線 2、3、4 與紅線 5 的 Text-First 部分、§4 第 1 條加標記；紅線 7 的 `.gitignore` 清單改為指向 `guardrails.required_gitignore` |
| [review_checklist.md](../../.agents/skills/code-review/references/review_checklist.md) | 第 73 行 `.gitignore` 清單改為指向設定；第 18–20、24、65 行改為指向設定鍵名；第 23、28–30、35–37、41、70–71 行加標記 |
| 角色檔 [developer](../../.agents/developer/AGENT.md)、[gatekeeper](../../.agents/gatekeeper/AGENT.md) | 路徑改指設定；Redis、PyMuPDF、履歷相關條目加標記 |
| feature-design：[SKILL.md](../../.agents/skills/feature-design/SKILL.md)、[arch_review_checklist.md](../../.agents/skills/feature-design/references/arch_review_checklist.md)、[tech_spec_template.md](../../.agents/skills/feature-design/references/tech_spec_template.md) | 路徑改指設定；維度 7 與維度 1/2/3/6/8 專屬檢核項加標記 |
| doc-sync：[SKILL.md](../../.agents/skills/doc-sync/SKILL.md)、[adr_template.md](../../.agents/skills/doc-sync/references/adr_template.md)、[doc_sync_checklist.md](../../.agents/skills/doc-sync/references/doc_sync_checklist.md) | 路徑改指設定；CLI 參數舉例與維度 7 加標記 |
| bug 軌：[bug.md](../../.agents/workflows/bug.md)、[hotfix.md](../../.agents/workflows/hotfix.md)、[bug-triage/SKILL.md](../../.agents/skills/bug-triage/SKILL.md)、[bug_report_template.md](../../.agents/skills/bug-triage/references/bug_report_template.md) | 升級條件 1 改指設定；升級條件 2 與 S1 定義加標記 |
| [unit-testing/SKILL.md](../../.agents/skills/unit-testing/SKILL.md)、[qa-testing/SKILL.md](../../.agents/skills/qa-testing/SKILL.md)、[quality-evaluation/SKILL.md](../../.agents/skills/quality-evaluation/SKILL.md)、[fix_anti_patterns.md](../../.agents/skills/auto-fix/references/fix_anti_patterns.md) | 專屬條目加標記；路徑改指設定 |
| `docs/templates/*` | 範本正本修改後重新複製鏡像 |
| `.agents/PORTING.md`、[.agents/README.md](../../.agents/README.md) | 新增移植指南並連結 |
| `docs/adr/0028-*.md`、[docs/adr/README.md](../adr/README.md) | 依決議第 7 項新增 ADR |

不新增或刪除技能、角色、流程檔。AGENTS.md 預估增加 0～3 行（標記以行內註解附加，不新增行）。

## 五、衝突與重複檢查

| 檢查 | 結果 |
| :--- | :--- |
| 是否放寬紅線 | 否。紅線內容不變，只改變值的存放位置與標記方式；依 [governance.md](../../.agents/workflows/governance.md)「紅線特別規定」，本案未放寬或刪除任何紅線 |
| 紅線 6「零硬編碼」 | 本案正是將腳本內寫死值移至設定，與紅線 6 方向一致 |
| 與 Spec-0027 D3（輸入上限數值只留一處） | 不衝突；上限數值本來就以 `.env.example` 為準，本案不搬動 |
| 重複消除 | `.gitignore` 必備清單由三處收斂為 `project.toml` 一處 |
| 新名稱撞名 | `project.toml`、`project_config.py`、`PORTING.md` 全倉無同名檔（G4 第 3 項再確認） |
| 歷史文件引用 | 紅線不重新編號，歷史文件的「紅線 N」引用維持有效 |

## 六、驗收標準

* **AC-1**：`audit_guardrails.py`、`verify_doc_sync.py` 中第二節列為類別 1、3 的值，全數改由 `project.toml` 讀取；腳本內不再出現 `redis_vector_store`、`resume`、工作區資料夾名稱、`ragas`、`23` 等專屬值（測試與內建地區樣式組除外）。
* **AC-2**：本專案執行兩支腳本，結果與修改前一致（同樣的 PASS／FAIL 項目與退出碼）。
* **AC-3**：刪除 `project.toml` 或其任一必要鍵時，兩支腳本以非零碼結束並指出缺少的鍵；`url_exceptions` 缺 `reason` 時 FAIL；`layers.enabled = false` 時略過分層檢查。
* **AC-4**：`.gitignore` 必備清單全倉只在 `project.toml` 定義，AGENTS.md 與 review_checklist 改為引用。
* **AC-5**：第三節列出的 2a 位置皆有 `<!-- 專案專屬 -->` 標記；規範文字中引用分層路徑處皆註明設定鍵名。
* **AC-6**：**移植演練**：將閉環檔案複製到暫存目錄中的最小假專案，依 `PORTING.md` 操作後，兩支腳本通過，且全倉搜尋不到 `forbidden_hash_prefixes` 的舊值。
* **AC-7**：G4 六項檢查通過；全套單元測試通過。

品質評測範圍：否

## 七、規模

**大改**：修改驗證腳本、修改 AGENTS.md 第 1 節紅線文字（未放寬）。產出本規格與 `docs/qa_reports/0028-*.md`。

## 八、待決事項

使用者已於對話中確認前 5 項（2026-11-20），以下記錄決議；第 6、7 項為撰寫本規格時新發現，待 G2 一併核准。

| # | 問題 | 決議／建議 | 替代方案 |
| :---: | :--- | :--- | :--- |
| 1 | 文字如何引用設定值 | **已決**：以職責指稱並註明設定鍵名與本專案現值，不用模板語法 | `{{...}}` 佔位符＋渲染步驟 |
| 2 | DDD 分層檢查開關 | **已決**：`layers.enabled`，非 DDD 專案可關閉 | 一律強制 DDD |
| 3 | 2b 舉例是否改寫 | **已決**：本案不改，移植指南列為選擇性 | 本案一併改為中性舉例（約 15 檔） |
| 4 | `.gitignore` 清單正本 | **已決**：`project.toml` | 保留 AGENTS.md 為正本、腳本另存一份 |
| 5 | 立案時機 | **已決**：Spec-0027 已於 PR #19 合併，本案即刻立案 | — |
| 6 | 設定讀取模組放哪裡 | **建議**：`.agents/lib/project_config.py` 共用 | 兩支腳本各自內嵌讀取函式（技能資料夾可獨立搬移，但驗證邏輯重複） |
| 7 | 是否寫 ADR | **建議**：寫。紅線 6、7 的文字改為指向設定，屬「修改架構紅線」，依 governance.md 規模分級須記錄於 `docs/adr/` | 不寫 ADR，僅在本規格記錄（理由：紅線實質未變） |
