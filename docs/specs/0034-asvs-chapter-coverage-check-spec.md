# 提案與規格書：閉環結構自動檢查（ASVS 章節歸屬、專案實例檔、專屬標記、業務技能）

> **狀態**：提案（G1，待核准；尚未實作）｜**類型**：規範變更（大改：修改驗證腳本）｜**流程**：[governance.md](../../.agents/workflows/governance.md)｜**影響範圍**：`verify_doc_sync.py`、`.agents/lib/project_config.py`、`.agents/project.toml`、[security_nfr_framework.md](../../.agents/skills/feature-design/references/security_nfr_framework.md)、`.agents/tests/` 與移植演練，不涉及 `src/`
>
> **修訂紀錄**：2026-11-20 初版（ASVS 章節歸屬 C1–C4）；2026-11-21 擴充，納入 [Spec-0035](./0035-portable-arch-review-checklist-spec.md) 決議 4、[Spec-0036](./0036-portable-review-checklist-spec.md) 決議 6 併入之腳本檢查，並對應 [Spec-0037](./0037-project-profile-tests-and-red-lines-spec.md)、[Spec-0038](./0038-closed-loop-residual-project-coupling-spec.md) 之後的現況（C5–C8）。

## 一、動機

閉環近期改為「通用核心 + 專案實例檔」結構，並在文件中寫下多條結構規則，但目前只靠人眼維持：

1. **ASVS 章節歸屬**（[PR #28](https://github.com/williamcccc/resume-transform-search/pull/28)）：安全框架第四節規定 V1–V17 每章須歸入「一律／特徵／技術」之一；「技術」類章節（V9、V10、V17）未使用時須於 `project.toml` 的 `not_applicable` 登錄。改版前 V11 密碼學就是「對照表沒列、專案也沒宣告」而無人發現。
2. **專案實例檔必須存在**（Spec-0035、0036、0037）：核心檔多處寫「見專案概況」「本專案通過標準見實例檔」。移植時若誤刪 `.agents/project/` 下的實例檔，要到 Gate 1／Gate 2 審查時才會發現。
3. **核心不得含專屬標記**（Spec-0035～0037）：專屬標記已由 47 處收斂為 AGENTS.md「本專案紅線」小節的 1 處整節標記。日後修改規範時若又在核心檔寫入本專案內容並加標記，結構會逐步退化，目前只有個別單元測試守住部分檔案。
4. **業務技能清單與實際一致**（Spec-0038）：`project.business_skills` 是移植時刪除業務技能的依據；清單與實際資料夾不一致時（漏列、改名、已刪），移植步驟會漏刪或報錯。

## 二、提案內容

`verify_doc_sync.py` 新增以下檢查，皆於 `main` 與移植後專案執行：

### 2.1 ASVS 章節歸屬（初版）

| # | 檢查 | 失敗時 |
| :---: | :--- | :--- |
| C1 | 框架第四節對照表恰好列出 V1–V17 各一列，無缺號、無重複 | FAIL |
| C2 | 每列「適用條件」欄以「一律」「特徵」「技術」之一開頭 | FAIL |
| C3 | 適用條件為「技術」的每一章，在 `project.toml` 有明確宣告（宣告方式見待決事項 2） | FAIL |
| C4 | `not_applicable` 的 `item` 提及之章節編號皆在 V1–V17 範圍內 | FAIL |

章節編號以正規式 `V(\d+)` 自對照表與 `item` 文字擷取；章節總數（17）與 ASVS 版本寫於框架檔，新版發布時以規範變更更新。

### 2.2 專案實例檔與通用核心（擴充）

| # | 檢查 | 失敗時 |
| :---: | :--- | :--- |
| C5 | 必備專案實例檔存在：`.agents/project/profile.md`、`arch_review_criteria.md`、`review_criteria.md`（`security_baseline.json` 移植後可不存在，不列入） | FAIL |
| C6 | 既有「閉環通用核心檔」存在檢查（`CORE_FILES`）加入 `arch_review_checklist.md`、`review_checklist.md` | FAIL |
| C7 | 掃描 `AGENTS.md` 與 `.agents/**/*.md`（不含 `project/`），排除行內程式碼（反引號內）與程式碼區塊後，`<!-- 專案專屬` 標記只允許出現在 AGENTS.md「本專案紅線」小節標題，且恰好 1 處 | FAIL |
| C8 | `project.business_skills` 每一項在 `.agents/skills/` 與 `.claude/skills/` 皆有同名資料夾 | FAIL |

C7 排除行內程式碼，是因為 [PORTING.md](../../.agents/PORTING.md) 以反引號說明標記寫法（如「以 `<!-- 專案專屬` 整節標記」），屬說明文字而非標記。

## 三、修改檔案（預估）

| 檔案 | 變更 |
| :--- | :--- |
| `.agents/skills/doc-sync/scripts/verify_doc_sync.py` | 新增 C1–C5、C7、C8；`CORE_FILES` 擴充（C6）；載入 `project` 區段（已於 Spec-0038 加入） |
| `.agents/lib/project_config.py`、`.agents/project.toml` | 依待決事項 2 新增技術章節使用宣告之鍵 |
| `.agents/skills/feature-design/references/security_nfr_framework.md` | 第四節註明本檢查；必要時調整表格格式以利解析 |
| `.agents/PORTING.md` | 第 8 步驗證說明新增檢查項目與失敗時的處理方式 |
| [AGENTS.md](../../AGENTS.md) | 依待決事項 4 精確化安全規則第 2 條用詞 |
| `.agents/tests/`（新增或擴充） | C1–C8 正反案例，設定檔、框架表、標記樣本於暫存目錄或記憶體建構 |
| `tests/e2e/test_portable_closed_loop_e2e.py` | 移植演練涵蓋 C3、C5、C8（替換實例檔、清空業務技能清單後仍通過；刪除實例檔時 FAIL） |

## 四、衝突與重複檢查

* **`project_config.py`**：已檢查 `not_applicable` 每筆有 `item` 與 `reason`、`business_skills` 型別（Spec-0030 AC-2、Spec-0038）；本案只新增「章節是否歸屬」「清單是否對應實際資料夾」之語意檢查，不重複格式檢查。
* **既有單元測試**：`.agents/tests/test_arch_review_portable.py`、`test_review_checklist_portable.py`、`test_neutral_examples.py` 已守護個別核心檔無標記；C7 改為全核心一致檢查，單元測試保留（測試的是規範結構，C7 是交付閘門），實作時評估是否精簡重疊斷言。
* **`CORE_FILES`**：C6 沿用既有機制擴充，不另立第二份清單。
* **[AGENTS.md](../../AGENTS.md) 安全規則第 2 條**：「專案只宣告特徵：適用標準由 `project.toml` 的 `[security]` 特徵對照決定，不適用者須附理由」，未提及技術條件章節；見待決事項 4。

## 五、規模

**大改**：修改驗證腳本（[governance.md](../../.agents/workflows/governance.md) 規模分級）。產出本規格與 `docs/qa_reports/0034-*.md`；程式部分走 Gate 2 程式檢查。若採待決事項 4，修改 AGENTS.md 第 2 節（非第 1 節紅線），不需 ADR。

## 六、待決事項

| # | 問題 | 建議 | 替代方案 |
| :---: | :--- | :--- | :--- |
| 1 | 檢查範圍 | C1–C8 全做 | 只做 2.2（C5–C8），ASVS 部分另案 |
| 2 | 專案「有使用」某技術章節時如何宣告，使 C3 能分辨「有用」與「漏填」 | `[security]` 新增 `tech_chapters_in_use = []`（例如 `["V9"]`），技術章節須出現在此清單或 `not_applicable` 之一 | 不新增鍵，技術章節未登錄即視為「使用中」（無法偵測漏填，C3 形同虛設） |
| 3 | 失敗等級 | 全部 FAIL（目前狀態已乾淨，不會一上線就擋住） | 先以 WARN 試行一版 |
| 4 | 是否一併精確化 AGENTS.md 安全規則第 2 條用詞（加入技術條件章節） | 一併修改 | 維持現狀 |
| 5 | 是否與 [Bug-0031](../bugs/0031-layer-check-skips-nested-modules.md)～[Bug-0033](../bugs/0033-env-sync-check-skips-missing-files.md)（`audit_guardrails.py` 守門缺口）合併處理 | 分開處理：修改不同腳本，避免單一 PR 過大 | 合併為同一份規範變更 |
| 6 | C5 必備實例檔清單放哪裡 | 寫在 `verify_doc_sync.py` 常數（實例檔名稱是核心與實例之間的契約，移植時不變） | 新增 `project.toml` 鍵（每個專案可自訂，但契約可被改掉） |
| 7 | C7 允許的標記位置 | 只允許 AGENTS.md「本專案紅線」小節標題 1 處 | 允許任意處但計數不得增加（以基準數比對） |

## 七、驗收標準（草案，G2 核准後定稿）

* **AC-1**：對照表缺一章、重複一章、或適用條件欄不屬三類之一時，`verify_doc_sync.py` 回報 FAIL 並指出章節。
* **AC-2**：技術條件章節未於 `project.toml` 宣告時回報 FAIL 並指出章節；`not_applicable` 提及 V1–V17 以外之編號時回報 FAIL。
* **AC-3**：刪除任一必備實例檔或新增之核心檢核清單時回報 FAIL 並指出檔案。
* **AC-4**：於 `.agents/` 任一核心 Markdown 新增 `<!-- 專案專屬` 標記（非行內程式碼）時回報 FAIL 並指出檔案與行號；PORTING.md 反引號內的說明文字不觸發。
* **AC-5**：`business_skills` 列出不存在的技能時回報 FAIL；清單為空時通過。
* **AC-6**：本專案現行設定與文件執行結果為 PASS；移植演練（替換實例檔、清空業務技能清單）結果為 PASS；全套單元測試、`.agents/tests` 與移植演練無回歸。

品質評測範圍：否（不涉及檢索、抽取或 LLM 生成）

安全評估範圍：否（只修改文件一致性檢查腳本；無新增對外介面、跨信任邊界資料流、外部相依或敏感資料處理）
