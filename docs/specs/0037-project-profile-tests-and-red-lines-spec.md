# 提案與規格書：專案概況檔、閉環自我測試隨核心移植、AGENTS.md 紅線分區

> **狀態**：已實作（G2：使用者於 2026-11-21 核准，待決事項全數採建議；QA 見 [QA-0037](../qa_reports/0037-project-profile-tests-and-red-lines-qa.md)，決策見 [ADR-0037](../adr/0037-agents-red-lines-generic-and-project-groups.md)）｜**類型**：規範變更（大改：新增專案實例檔、搬移測試、修改 AGENTS.md 第 1 節架構紅線之編排）｜**流程**：[governance.md](../../.agents/workflows/governance.md)｜**影響範圍**：`AGENTS.md`、`.agents/**`、閉環自我測試、`.github/workflows/ci.yml`，不涉及 `src/`

## 一、動機

2026-11-21 以「通用核心 + 專案實例檔」概念重掃閉環（[Spec-0035](./0035-portable-arch-review-checklist-spec.md)、[Spec-0036](./0036-portable-review-checklist-spec.md) 之後），仍有三處不符：

1. **專案概況散落於核心檔**：剩餘 23 處專屬標記中，多數描述「這個專案是什麼」，且同一事實重複出現：

   | 專案資訊 | 散落位置 | 處數 |
   | :--- | :--- | :---: |
   | CLI 入口 `convert_to_md.py` 與參數舉例 | AGENTS.md 紅線 2、feature-design、doc-sync SKILL 與檢核清單 | 4 |
   | 主要流程（轉檔、檢索），S1 判定依據 | bug-triage、hotfix.md | 2 |
   | 持久化結構（Redis 索引） | bug-triage、bug.md、缺陷報告範本（升級條件 2） | 3 |
   | 敏感資料類型（求職者、履歷） | AGENTS.md 紅線 7、developer | 2 |
   | 測試環境（Redis DB 15、隔離前綴、`data/`、`resume/`） | developer、gatekeeper、unit-testing | 4 |
   | 執行環境（Python 3.13 on Windows） | AGENTS.md 第 4 節 | 1 |

2. **閉環自我測試移植時帶不走**：驗證閘門腳本與規範結構的測試（如 `test_project_config`、`test_security_scan`、`test_review_checklist_portable`、移植演練 E2E）屬通用核心，卻放在專案 `tests/`。[PORTING.md](../../.agents/PORTING.md) 只複製 `AGENTS.md`、`.agents/`、`.claude/`，新專案拿到腳本卻沒有守護腳本的測試。

3. **AGENTS.md 通用紅線與專案紅線交錯**：第 1 節 7 條紅線中，第 2～5 條（CLI 相容、Word 補樁與索引冪等、品管閥 65 分、Text-First）為本專案專屬，與通用紅線 1、6、7 交錯排列；分層樹狀圖註解亦寫入本專案元件（`google-genai`、RediSearch、PyMuPDF、「轉檔邏輯」）。移植時需在常駐載入的憲法檔內逐條辨識。

## 二、設計原則

* 沿用 Spec-0035／0036：**通用規則放核心，本專案事實放專案實例**。
* **常駐內容留在 AGENTS.md**：紅線與執行環境須每次對話自動載入，不搬出 AGENTS.md，改為在 AGENTS.md 內集中成「本專案區塊」。技能才會讀取的描述性事實，放 `.agents/project/` 實例檔。
* **紅線只重新編排，不放寬、不刪除、不改內容**：本案由使用者明確提出（2026-11-21），符合 [governance.md](../../.agents/workflows/governance.md)「紅線特別規定」；修改第 1 節須寫 ADR。

## 三、提案內容

### 3.1 專案概況檔（新增 `.agents/project/profile.md`）

| 節 | 內容（本專案現值） | 由誰引用 |
| :--- | :--- | :--- |
| 1. 入口與介面 | CLI 入口 `convert_to_md.py`、`index_to_redis.py`、`search_resumes.py`、`web_dashboard.py`；參數舉例 `--review`、`--index-to-redis`、`--output-dir`、`--skills` | feature-design、doc-sync |
| 2. 主要流程 | 轉檔、檢索（全面失敗即 S1） | bug-triage、hotfix.md |
| 3. 持久化結構 | Redis 向量索引（`idx:resumes:v1`）與鍵前綴 | 升級條件 2 |
| 4. 敏感資料類型 | 求職者姓名、聯絡資訊、履歷全文與檔名、身分證字號；敏感目錄見 `privacy.sensitive_dirs` | developer、AGENTS.md 紅線 7 |
| 5. 測試環境 | E2E 使用 tempfile 隔離磁碟、Redis DB 15／獨立前綴；單元測試禁連 Redis、Gemini | developer、gatekeeper、unit-testing |

核心檔改寫為通用規則並引用概況檔，移除對應專屬標記：

| 檔案 | 變更 |
| :--- | :--- |
| `.agents/skills/bug-triage/SKILL.md`、`.agents/workflows/hotfix.md` | S1：「主要流程（見專案概況）全面失敗」 |
| `.agents/workflows/bug.md`、`.agents/skills/bug-triage/SKILL.md`、缺陷報告範本與鏡像 | 升級條件 2：「需修改資料模型或持久化結構（資料庫綱要、索引；本專案見專案概況）」 |
| `.agents/skills/feature-design/SKILL.md`、`.agents/skills/doc-sync/SKILL.md`、`doc_sync_checklist.md` | CLI 入口與參數舉例改為引用專案概況 |
| `.agents/developer/AGENT.md`、`.agents/gatekeeper/AGENT.md`、`.agents/skills/unit-testing/SKILL.md` | 敏感資料類型、測試環境改為通用規則並引用專案概況 |
| `.agents/skills/feature-design/references/tech_spec_template.md` 與鏡像 | 檔案清單表的本專案路徑改為 `[layers]` 佔位符 |
| `.agents/skills/quality-evaluation/SKILL.md` | 評審 prompt 舉例改為「專案既有之評審 prompt」 |

### 3.2 閉環自我測試隨核心移植

* 新增 `.agents/tests/`（單元）與 `.agents/tests/e2e/`（移植演練等耗時測試）。
* **搬移條件**：測試對象為閉環腳本或規範結構，且在「實例檔與 `project.toml` 已替換」的移植後專案中仍能通過。候選：`test_project_config`、`test_security_scan`、`test_security_ac_gate`、`test_quality_ac_gate`、`test_workflow_tracks_doc_sync`、`test_claude_adapter_sync`、`test_audit_eval_only_imports`、`test_hardcode_extractions`、`test_arch_review_portable`、`test_review_checklist_portable`、`test_neutral_examples`，以及 E2E `test_portable_closed_loop_e2e`、`test_workflow_tracks_doc_sync_e2e`。實作時逐檔確認，不符者留原處。
* 同一測試檔中斷言**本專案實例內容**者（如實例檔含 25MB、`<resume_content>`）拆出，留在 `tests/unit/`；核心結構斷言隨核心搬移。
* 專案上庫衛生測試（`test_github_pre_publish_hygiene`）留在 `tests/unit/`。
* `.github/workflows/ci.yml` 新增一步執行 `.agents/tests/`；移植演練 E2E 於假專案中執行 `.agents/tests/`（單元），驗證核心測試移植後可通過。
* PORTING.md 第 1 步說明 `.agents/tests/` 隨 `.agents/` 一併複製；`.agents/README.md` 加入 `tests/`。

### 3.3 AGENTS.md 紅線分區

第 1 節改為兩個小節，**保留原編號 1–7**（倉內 22 處歷史文件以編號引用）：

```text
### 通用紅線
紅線 1｜依賴反轉（DIP）
紅線 6｜Twelve-Factor 配置治理與零硬編碼
紅線 7｜Git 版控衛生、零個資與跨平台路徑（敏感資料類型見專案概況）

### 本專案紅線（移植時整節改寫）
紅線 2｜向下相容性（convert_to_md.py）
紅線 3｜無損與容錯性（原始檔不篡改、索引寫入冪等）
紅線 4｜四層品管防線（品管閥 65 分）
紅線 5｜Token 能效與 Text-First
```

* 各條文字內容不變；以「紅線 N｜標題」標示取代 Markdown 有序清單，避免渲染時自動重新編號。
* 本專案紅線小節以單一專屬標記標示整節，取代原 6 處逐行標記。
* 分層樹狀圖註解改為通用說法（外部 SDK、外部服務實作、核心業務邏輯）。
* 第 4 節「環境標準」移入「本專案紅線」同區塊的「本專案執行環境」一行（常駐載入）。
* 第 2 節「品質評測規則」的專屬標記改為正文適用條件（「適用於含檢索、結構化抽取或 LLM 生成之專案」）。
* 新增 `docs/adr/0037-*.md` 記錄紅線分區決策。

### 3.4 移植指南與連動

| 檔案 | 變更 |
| :--- | :--- |
| `.agents/PORTING.md` | 第 4 步實例檔清單加入 `profile.md`；第 5 步改為「改寫 AGENTS.md 本專案區塊，並搜尋其餘專屬標記」 |
| `.agents/README.md` | `project/` 說明加入概況檔；新增 `tests/` 列 |
| `.agents/project/review_criteria.md` | 「對應 AGENTS.md 紅線 3／5」引用不變（編號保留） |

## 四、衝突與重複檢查

* **概況檔與 Gate 2 實例檔**：Gate 2 實例檔「日誌零洩漏」列出的敏感資料屬檢核項，概況檔第 4 節為定義；實作時 Gate 2 實例檔改為引用概況檔，避免同一清單寫兩處。
* **AGENTS.md 與概況檔**：常駐內容（紅線、執行環境）只在 AGENTS.md；概況檔不重述，只放技能才需要的事實。
* **紅線編號**：保留 1–7，`review_criteria.md` 與 22 處歷史引用不需修改。
* **CI**：新增步驟只執行搬移後的測試，總測試數不變（搬移前後合計一致）。

## 五、規模

**大改**：新增專案實例檔、搬移測試、修改 AGENTS.md 第 1 節編排。產出本規格、`docs/qa_reports/0037-*.md` 與 `docs/adr/0037-*.md`（修改紅線章節）。AGENTS.md 行數預估減少（逐行標記與重複說明合併），不新增紅線內容。

## 六、待決事項

| # | 問題 | 建議 | 替代方案 |
| :---: | :--- | :--- | :--- |
| 1 | 概況檔位置與檔名 | `.agents/project/profile.md` | 併入 `project.toml` 為設定值（不適合描述性內容） |
| 2 | 紅線編號 | 保留 1–7，以「紅線 N｜標題」分兩小節 | 重新編號（通用 1–3、專案 P1–P4），需同步 22 處歷史引用或附對照表 |
| 3 | 執行環境（Python 3.13 on Windows）放哪裡 | AGENTS.md 本專案區塊（常駐載入） | 概況檔（需技能主動讀取） |
| 4 | 自我測試位置與 CI | `.agents/tests/`、`.agents/tests/e2e/`；CI 新增一步 | 維持 `tests/`，PORTING 改為列出要複製的測試檔 |
| 5 | 同一測試檔內的本專案實例斷言 | 拆出留在 `tests/unit/` | 整檔搬移，移植後由使用者刪改 |
| 6 | 交付方式 | 一份規格、一個 PR，分三個 commit（概況檔、測試搬移、紅線分區） | 三份規格、三個 PR |

## 七、驗收標準

* **AC-1**：概況檔涵蓋第一節表列 6 類資訊；被引用之核心檔不再含這些事實與對應專屬標記。
* **AC-2**：AGENTS.md 與 `.agents/`（不含 `project/`）之專屬標記只剩 AGENTS.md「本專案紅線」區塊之整節標記；PORTING 第 5 步據此改寫。
* **AC-3**：AGENTS.md 紅線 1–7 文字內容與改前逐字相同（只改編排與標示）；分層樹狀圖不含本專案元件名稱；ADR-0037 已登錄。
* **AC-4**：搬移後 `tests/unit` + `.agents/tests` 測試總數與搬移前相同且全數通過；CI 執行 `.agents/tests/`。
* **AC-5**：移植演練於假專案替換三份實例檔與 `project.toml` 後，`.agents/tests/` 單元測試與兩支閘門腳本皆通過。
* **AC-6**：`verify_doc_sync.py`、`audit_guardrails.py` 通過；Markdown 斷鏈測試無回歸。

品質評測範圍：否（不涉及檢索、抽取或 LLM 生成）

安全評估範圍：否（只重組規範文件與測試位置；無新增對外介面、跨信任邊界資料流、外部相依或敏感資料處理）
