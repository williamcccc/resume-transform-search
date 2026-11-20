# 提案與規格書：安全與非功能需求評估通用化（閉環核心層）

> **狀態**：提案（G1，待 G2 使用者核准）｜**類型**：規範變更（大改：新增技能參考檔與閘門腳本、修改驗證腳本）｜**流程**：[governance.md](../../.agents/workflows/governance.md)｜**影響範圍**：`AGENTS.md`、`.agents/**`、閘門腳本與其單元測試，不涉及 `src/`

## 一、動機

[Bug-0029](../bugs/0029-cors-allow-any-origin.md)（CORS 對任意來源放行，S1）的逃逸分析顯示，問題不在個別規格寫漏，而在閉環本身沒有「找出安全與非功能需求」的方法：

1. **需求有寫，卻沒有轉成可驗證的條件**：[Spec-0015](./0015-resume-search-web-interface-spec.md) 第 106 行寫明「履歷預覽與檢索結果只對本機／授權內網開放」，但沒有對應 AC、測試或 QA 案例；CORS 全開直接違反這句話，卻通過所有門禁。
2. **已識別的安全風險可以無條件延後**：[Spec-0019](./0019-recruitment-assistant-chat-spec.md) 風險 R7 已點出 CORS 問題，標為「中」後以「不在本期範圍」轉入 Backlog（P2），沒有嚴重度判定、沒有期限，實際為 S1。
3. **安全檢查全部是專案實例，沒有通用方法**：Gate 1 的 [8 大架構維度](../../.agents/skills/feature-design/references/arch_review_checklist.md) 有 6 項標為 `<!-- 專案專屬`，兩個安全維度（個資隱私、惡意輸入）寫的都是本專案的具體做法；Gate 2 [檢核清單](../../.agents/skills/code-review/references/review_checklist.md) 40 項中有 10 項安全相關項目標為專案專屬。PRD 範本的 AC 只有正常、邊界、錯誤三種功能情境，「安全性與限制硬上限」一節只有 3 個填空欄位。
4. **移植後會重演**：[PORTING.md](../../.agents/PORTING.md) 第 4 步要求將專屬標記「逐處改寫為新專案的規則，或連同規則一併刪除」。新專案剛起步、尚無程式碼時，改寫者只能憑印象列出項目；最壞情況是整節刪除，新專案的 Gate 1 完全沒有安全維度。
5. **教訓不會回流到閉環**：Bug-0029 的教訓適用於所有 Web 專案，但只記錄在本專案的缺陷報告中，下一個專案從乾淨的閉環開始，會再踩一次。

若只把 Bug-0029 的教訓補成新檢核項（CORS、Host 驗證……），等於「遇到一次補一個坑」，下一個不同類型的問題一樣會漏。本案改為把**方法**、**公認標準**與**自動工具**放進閉環的通用核心，專案只需宣告自身特徵。

## 二、設計原則

| 原則 | 說明 |
| :--- | :--- |
| **方法優先於清單** | 以威脅建模推導問題，而非回想問題；推導方法換專案仍有效 |
| **公認標準優先於自製項目** | 安全需求來源指向社群維護之標準，閉環只維護「本專案適用哪些章節」的對照 |
| **工具優先於記憶** | 已知漏洞類別交給靜態掃描與依賴漏洞掃描，規則由工具社群維護 |
| **專案只宣告特徵** | 移植時回答特徵是非題，由對照表決定適用範圍；不適用須寫理由 |
| **教訓分流回寫** | 每次逃逸分析判定教訓屬「通用」或「專案專屬」，通用者回寫核心層 |

## 三、設計

### 3.1 通用核心層：安全與非功能需求評估框架

新增 `.agents/skills/feature-design/references/security_nfr_framework.md`，**不帶任何專案專屬標記，移植時不得刪除**。內容分三部分：

**(1) 非功能需求宣告（依 ISO/IEC 25010:2023 產品品質模型）**

功能適合性由功能 AC 涵蓋，其餘 8 項品質特性逐項宣告：

| 品質特性 | 宣告 | 理由或對應 AC |
| :--- | :--- | :--- |
| 效能效率 | 適用／不適用 | 例：`NFR-1` 單輪延遲 P95 ≤ 30 s |
| 相容性 | | |
| 互動能力（易用性） | | |
| 可靠性 | | |
| 安全性 | | 由 (2) 威脅建模產出 |
| 可維護性 | | |
| 彈性（可攜性） | | |
| 安全防護（safety） | | |

「適用」者必須有至少一條可驗證的 `NFR-*` 驗收條件；「不適用」必須寫理由。敘述性需求（如「只對本機開放」）一律要轉成 `NFR-*`，否則 Gate 1 不通過。

**(2) 威脅建模（STRIDE 精簡版）**

1. 列出本次變更涉及的資料流與**信任邊界**（例：瀏覽器↔Web 服務、服務↔外部 API、使用者檔案↔解析器、服務↔資料庫）。
2. 對每條跨越信任邊界的資料流，逐一回答六問：冒充（Spoofing）、竄改（Tampering）、否認（Repudiation）、資訊洩漏（Information disclosure）、阻斷服務（Denial of service）、權限提升（Elevation of privilege）。
3. 以表格記錄：

| 邊界／資料流 | STRIDE 類別 | 威脅 | 緩解措施 | 對應 NFR／測試 | 殘餘風險與嚴重度 |
| :--- | :---: | :--- | :--- | :--- | :--- |

4. 每一列的緩解措施須對應 `NFR-*` 或測試案例；不處理者列為殘餘風險，並依 3.5 判定嚴重度。

**(3) 標準對照（依專案特徵選用）**

| 專案特徵（3.2） | 參照標準 | 用途 |
| :--- | :--- | :--- |
| 一律適用 | OWASP ASVS 5.0（等級依 `asvs_level`） | 安全需求的完整來源；威脅建模的緩解措施優先引用 ASVS 條目編號 |
| `web_interface = true` | ASVS V3 網頁前端安全、V4 API 與 Web 服務；OWASP Top 10 | 跨來源、標頭、CSRF 等 |
| `api_service = true` | OWASP API Security Top 10 | 授權、資源消耗 |
| `uses_llm = true` | OWASP Top 10 for LLM Applications | 提示詞注入、敏感資訊外洩、過度授權、無上限消耗 |
| `handles_pii = true` | ASVS V14 資料保護 | 儲存、傳輸、保留期限 |
| `processes_untrusted_files = true` | ASVS V5 檔案處理 | 檔案炸彈、路徑遍歷 |

> 章節編號於 G3 實作時，以 [OWASP ASVS 官方儲存庫](https://github.com/OWASP/ASVS) 之 5.0 正式版逐一核對；本表以章節名稱為準。

### 3.2 專案設定檔：`project.toml` 新增 `[security]`

移植時只回答特徵是非題，不重寫檢核項目。本專案現值：

```toml
[security]
asvs_level = 1                      # 本機單人工具取 L1；對外服務建議 L2
network_exposure = "local"          # local | lan | internet
web_interface = true
api_service = true
uses_llm = true
handles_pii = true
processes_untrusted_files = true
multi_user = false
# 不適用之標準章節須附理由；verify_doc_sync.py 檢查每筆皆有 reason
[[security.not_applicable]]
item = "ASVS V6 身分驗證"
reason = "目前僅綁定 127.0.0.1 之單人本機工具；network_exposure 改為 lan/internet 時須重新評估"
```

`network_exposure` 或任一特徵變更時，視為觸發全專案安全重新評估（另開規格）。

### 3.3 規格範本與 Gate 1 整合

* **PRD 範本**：「5. 安全性與限制硬上限」改為「5. 非功能需求與威脅建模」，內含 3.1 (1) 宣告表與 3.1 (2) 威脅表；原有之檔案大小、頁數、個資欄位移入宣告表對應列。
* **範圍宣告**：比照品質評測，每份規格須於驗收標準段落宣告 `安全評估範圍：是` 或 `安全評估範圍：否`。符合下列任一項必須為「是」：新增或變更對外介面（CLI 參數除外）、新增跨信任邊界之資料流、新增外部相依服務或套件、新增敏感資料之儲存或傳輸。
* **Fast Track 也要書面化**：原「快速心智自檢」改為至少寫下範圍宣告與一句理由；宣告為「是」時仍須填寫威脅表（可只列受影響的邊界）。
* **feature-design 流程**：在「階段 2 產出 PRD」與「階段 3 架構維度前審」之間，新增「安全與非功能需求評估」階段，依 3.1 執行。8 大架構維度不改名、不重新編號（待決事項 5）。
* **`verify_doc_sync.py`**：自 `docs.security_ac_enforced_from` 所設編號起，規格須有範圍宣告；宣告為「是」者，須含威脅表（至少一列 STRIDE 類別）與至少一條 `NFR-*`，缺漏為 FAIL。

### 3.4 通用工具閘門：Gate 2 新增安全掃描

* 新增 `.agents/skills/code-review/scripts/security_scan.py`，依 `project.toml` 的 `[security.tools]` 執行：
  * **靜態掃描**：Semgrep（2025 秋季版起原生支援 Windows），規則集由設定指定（建議 Python 與 OWASP Top 10 規則集）。
  * **依賴漏洞掃描**：`pip-audit`，比對 `requirements*.txt` 的已知漏洞。
* **基準檔**：`.agents/security_baseline.json` 記錄導入前的既有發現，每筆附理由與到期日；閘門只阻斷**新增**發現，避免導入當天全面卡住。到期未處理者轉為 FAIL。
* **判定**：新增之高嚴重度發現為 P0，其餘為 P1（待決事項 3）。
* **離線**：`pip-audit` 需連網查詢漏洞資料庫；無法連線時印 WARN 不阻斷，並於 QA 報告記錄未執行。
* **Gate 2 流程**：code-review 技能階段 A 由「執行 `audit_guardrails.py`」擴充為「執行 `audit_guardrails.py` 與 `security_scan.py`」，兩者皆零 P0 始得進入階段 B。
* **工具安裝**：新增 `requirements-dev.txt`，與執行期相依分開（待決事項 9）。

### 3.5 安全風險不得無條件延後

* Gate 1 威脅表的殘餘風險、Gate 2 與 QA 發現的安全問題，一律以 [bug-triage](../../.agents/skills/bug-triage/SKILL.md) 嚴重度表判定 S1／S2／S3。
* **S1 不得延後**：須於本案修正，或立即依 [hotfix.md](../../.agents/workflows/hotfix.md) 開缺陷處理。
* **S2／S3 延後**：Backlog 須記錄嚴重度、判定理由與處理期限；不得只標「不在本期範圍」。
* Gate 2 [檢核清單](../../.agents/skills/code-review/references/review_checklist.md) 新增 P0 項：「規格與 QA 報告中列為殘餘風險之安全項目，皆有嚴重度判定；無 S1 被延後」。

### 3.6 教訓回流

* [缺陷報告範本](../../.agents/skills/bug-triage/references/bug_report_template.md) 第 3 節新增「**教訓歸屬**：通用／專案專屬」，並在逃逸分析中指出失效的是哪一層：威脅建模未涵蓋該邊界、標準對照誤標不適用、工具缺少規則，或規範本身缺漏。
* 歸屬「通用」者，須開規範變更回寫核心層（3.1 框架、3.4 工具規則或基準設定），缺陷報告記錄該規範變更編號。
* 跨專案回流機制（閉環正本儲存庫）列為待決事項 7。

### 3.7 移植指南

[PORTING.md](../../.agents/PORTING.md) 修改：

* 新增步驟：逐項回答 `[security]` 特徵，`not_applicable` 每筆附理由；安裝 `requirements-dev.txt` 並執行 `security_scan.py` 建立基準檔。
* 第 4 步補充：**未帶專屬標記之核心檔（含 `security_nfr_framework.md`）不得刪除**；`verify_doc_sync.py` 檢查核心檔存在，缺少即 FAIL。
* `docs.security_ac_enforced_from` 改為 `1`（新專案從第一份規格起強制）。

## 四、修改檔案

| 檔案 | 變更 |
| :--- | :--- |
| `.agents/skills/feature-design/references/security_nfr_framework.md` | 新增；3.1 通用框架 |
| [feature-design/SKILL.md](../../.agents/skills/feature-design/SKILL.md) | 新增「安全與非功能需求評估」階段；Fast Track 書面化 |
| [prd_template.md](../../.agents/skills/feature-design/references/prd_template.md) | 第 5 節改為非功能需求與威脅建模；驗收標準段落新增安全評估範圍宣告 |
| [tech_spec_template.md](../../.agents/skills/feature-design/references/tech_spec_template.md) | QA 案例矩陣須涵蓋 `NFR-*` |
| [arch_review_checklist.md](../../.agents/skills/feature-design/references/arch_review_checklist.md) | 開頭註明維度 1、6 為專案實例，方法以框架為準；Fast Track 改為書面宣告 |
| [code-review/SKILL.md](../../.agents/skills/code-review/SKILL.md)、[review_checklist.md](../../.agents/skills/code-review/references/review_checklist.md) | 階段 A 加入 `security_scan.py`；新增 3.5 之 P0 項；需求—斷言追溯涵蓋 `NFR-*` |
| `.agents/skills/code-review/scripts/security_scan.py` | 新增；3.4 工具閘門 |
| [verify_doc_sync.py](../../.agents/skills/doc-sync/scripts/verify_doc_sync.py) | 安全評估範圍宣告檢查；核心檔存在檢查；`[security]` 鍵與 `not_applicable` 理由檢查 |
| [project_config.py](../../.agents/lib/project_config.py)、[project.toml](../../.agents/project.toml) | 新增 `[security]`、`[security.tools]`、`docs.security_ac_enforced_from` |
| [qa-testing/SKILL.md](../../.agents/skills/qa-testing/SKILL.md)、[qa_report_template.md](../../.agents/skills/qa-testing/references/qa_report_template.md) | RTM 涵蓋 `NFR-*`；記錄 `security_scan.py` 結果與離線未執行項 |
| [bug-triage/SKILL.md](../../.agents/skills/bug-triage/SKILL.md)、[bug_report_template.md](../../.agents/skills/bug-triage/references/bug_report_template.md) | 逃逸分析新增教訓歸屬與失效層 |
| 角色檔 [architect](../../.agents/architect/AGENT.md)、[gatekeeper](../../.agents/gatekeeper/AGENT.md) | 提示詞補上框架與安全掃描步驟 |
| [AGENTS.md](../../AGENTS.md) | 第 2 節新增「安全與非功能需求規則」短節（約 6 行），指向框架；不改紅線 |
| [PORTING.md](../../.agents/PORTING.md) | 3.7 |
| `requirements-dev.txt`、`.agents/security_baseline.json` | 新增 |
| `tests/unit/`：`test_security_scan.py`（新增）、`test_project_config.py`、`test_quality_ac_gate.py` 或新檔 `test_security_ac_gate.py` | 掃描結果解析、基準比對、到期、離線降級；範圍宣告檢查；`[security]` 缺鍵與缺理由 |
| `tests/e2e/test_portable_closed_loop_e2e.py` | 移植演練涵蓋 `[security]` 與核心檔不可刪 |
| `docs/templates/*` | 範本正本修改後重新複製鏡像 |

不新增或刪除流程檔、技能、角色。AGENTS.md 預估由 158 行增至約 164 行。

## 五、衝突與重複檢查

| 檢查 | 結果 |
| :--- | :--- |
| 是否放寬紅線 | 否。紅線不變；是否新增紅線列為待決事項 6 |
| 與 8 大架構維度第 1、6 項 | 不重複：維度 1、6 保留為本專案的具體檢核實例；框架提供推導方法與標準來源，兩者為「方法」與「實例」關係，於清單開頭註明 |
| 與 Gate 2 檢核清單第 2、9 類 | 不重複：既有 P0 項維持；新增項只涵蓋「殘餘風險判定」與「掃描結果」，屬新責任 |
| 與 `audit_guardrails.py` | 分工：`audit_guardrails.py` 檢查本閉環自訂的架構與衛生規則；`security_scan.py` 執行外部工具的通用安全規則，兩者不互相取代 |
| 與品質評測範圍宣告 | 機制比照（宣告字樣、起始編號、缺漏 FAIL），字樣不同（`安全評估範圍` 與 `品質評測範圍`），正規式不互相命中，於 G4 以單元測試確認 |
| 新名稱撞名 | `security_nfr_framework.md`、`security_scan.py`、`security_baseline.json`、`requirements-dev.txt`、`NFR-*` 編號樣式於 G4 全倉搜尋確認 |
| AGENTS.md 行數 | 增加約 6 行，未超過 20 行門檻 |

## 六、驗收標準

* **AC-1**：`security_nfr_framework.md` 含 3.1 三部分，全檔無 `<!-- 專案專屬` 標記；刪除該檔時 `verify_doc_sync.py` FAIL。
* **AC-2**：`project.toml` 缺 `[security]` 任一必要鍵時，腳本以結束碼 2 中止並指出缺鍵；`not_applicable` 缺 `reason` 時 FAIL。
* **AC-3**：規格編號 ≥ `security_ac_enforced_from` 且缺少安全評估範圍宣告者 FAIL；宣告「是」但缺威脅表或 `NFR-*` 者 FAIL；宣告「否」者 PASS。既有規格（0030 以前）不受影響。
* **AC-4**：`security_scan.py` 對含 `CORSMiddleware(allow_origins=["*"], allow_credentials=True)` 的測試夾具回報發現（重現 Bug-0029 之程式碼型態）；對基準檔已登錄的發現不阻斷；基準項目到期後 FAIL；無法連網時 `pip-audit` 部分 WARN 不阻斷。
* **AC-5**：**回溯演練**：以框架重新評估 Spec-0015 之變更範圍，威脅表在「瀏覽器↔儀表板」邊界的「資訊洩漏」類別產出跨來源讀取威脅，並對應到 `NFR-*`。演練結果記錄於 QA 報告。
* **AC-6**：**移植演練**：將閉環檔案複製至暫存目錄的最小假專案，依更新後之 `PORTING.md` 填寫 `[security]` 後，`verify_doc_sync.py`、`audit_guardrails.py`、`security_scan.py` 皆可執行並通過。
* **AC-7**：本專案執行 `verify_doc_sync.py` 與 `audit_guardrails.py`，既有 PASS 項目不變；`security_scan.py` 首次執行之發現全數登錄於基準檔（附理由與到期日）。
* **AC-8**：G4 六項檢查通過；全套單元測試通過。

安全評估範圍：否（本案修改規範與閘門腳本，不新增對外介面或跨信任邊界之資料流）

品質評測範圍：否

## 七、規模

**大改**：新增技能參考檔與閘門腳本、修改驗證腳本。產出本規格與 `docs/qa_reports/0030-*.md`。不修改紅線，不另寫 ADR（除非待決事項 6 選擇新增紅線）。

## 八、待決事項

| # | 問題 | 建議 | 替代方案 |
| :---: | :--- | :--- | :--- |
| 1 | 安全需求標準來源 | OWASP ASVS 5.0，等級由 `asvs_level` 設定（本專案 L1），依特徵加選 Top 10 系列 | 自製通用清單（維護成本高，涵蓋面受限於撰寫者） |
| 2 | 掃描工具 | Semgrep（靜態）＋ `pip-audit`（依賴） | 只用 Bandit（純 Python、可離線，但規則較少，無法涵蓋 CORS 這類框架設定） |
| 3 | 掃描發現的阻斷等級 | 新增之高嚴重度發現為 P0，其餘 P1；既有發現登錄基準檔 | 導入後先設 30 天觀察期，全部 P1 |
| 4 | 強制起始編號 | `security_ac_enforced_from = 31`（本案之後的規格起）；既有規格不回溯 | 同時回溯檢查 0014～0022 之 Web 相關規格（建議另案以基準安全檢查處理） |
| 5 | 新階段放在哪裡 | feature-design 新增獨立階段，8 大架構維度不改名、不重編號（影響 6 個檔案的引用） | 將框架併為「第 9 維度」並全倉改名（變動面大） |
| 6 | 是否新增紅線 | 否，以 Gate 1／Gate 2 規則與腳本落實 | 新增紅線 8「安全與非功能需求須經威脅建模並轉為可驗證條件」，需另寫 ADR |
| 7 | 跨專案教訓回流 | 本案只建立「教訓歸屬」欄位；另案建立閉環正本儲存庫，各專案歸屬「通用」之規範變更回寫正本，移植一律從正本複製 | 不設正本，各專案自行維護（教訓無法跨專案累積） |
| 8 | 需連網之掃描於離線時 | WARN 不阻斷，QA 報告記錄未執行 | 離線即 FAIL（本機開發常離線，易誤擋） |
| 9 | 開發工具相依如何管理 | 新增 `requirements-dev.txt`，與執行期相依分開 | 併入 `requirements.txt`（執行環境會多裝不需要的工具） |

### 不在本案範圍

* 對現有系統做基準安全檢查（以框架走過目前架構並處理發現）：建議於本案合併後另案進行，結果作為 3.4 基準檔的初始內容依據。
* 伺服器未驗證 `Host` 標頭（Bug-0029 另案追蹤項目）：依 Bug 軌另行處理。
* 建立 CI：本專案目前無 CI，閘門腳本仍於本機執行。
