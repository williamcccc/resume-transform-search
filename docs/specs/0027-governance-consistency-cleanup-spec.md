# 提案與規格書：規範體系一致性清理（角色、技能、流程、範本、檢核清單）

> **狀態**：已核准（G2：使用者於 2026-11-19 核准，待決事項第 4 項依使用者回饋修訂後，全數採建議）｜**類型**：規範變更（大改：重組章節、修改多份技能與角色）｜**流程**：[governance.md](../../.agents/workflows/governance.md)｜**影響範圍**：`.agents/**`、`AGENTS.md`、`CLAUDE.md`，不涉及 `src/`

## 一、動機
PR #15～#18 在一天內新增了流程分軌、Bug 軌與規範變更流程，但只修改了直接相關的檔案。本案逐份檢查 `.agents/` 下 3 個角色、10 個技能、4 個流程檔、各技能範本與檢核清單，以及 `.agents/README.md`，找出**重複**、**不合理（含互相矛盾與過時）**與**缺漏**。

檢查範圍：`AGENTS.md`、`CLAUDE.md`、`.agents/README.md`、`.agents/<role>/AGENT.md`（3）、`.agents/skills/*/SKILL.md` 與 `references/`（10 技能、14 份參考檔）、`.agents/workflows/*.md`（4）。`resume-vector-indexing`、`resume-vector-search` 為業務操作技能，不屬閉環，只確認未與閉環規則衝突。

---

## 二、發現

嚴重度：**高** = 會讓 AI 走錯流程或得到錯誤保證；**中** = 規則不一致或缺漏，可能造成漏檢；**低** = 措辭、重複或維護負擔。

### 1. 不合理（矛盾與過時）

| ID | 嚴重度 | 位置 | 問題 | 建議修正 |
| :--- | :---: | :--- | :--- | :--- |
| U1 | 高 | [arch_review_checklist.md](../../.agents/skills/feature-design/references/arch_review_checklist.md) 第二節 | 「輕量級變更 (Fast Track)」適用「單純 Bug 修復」，走簡版 Tech Spec；與 Bug 軌（Step 1B）直接矛盾 | 刪除 Bug 修復字樣；Fast Track 改為「功能開發中的小幅變更」，並註明缺陷一律走 `bug.md` |
| U2 | 高 | [feature-design/SKILL.md](../../.agents/skills/feature-design/SKILL.md) 第 11 行 | 「確保每一項新功能**或缺陷修復**在動工前…產出 PRD」，與 Bug 軌矛盾 | 改為只適用功能開發；缺陷修復指向 bug-triage |
| U3 | 高 | [.agents/README.md](../../.agents/README.md) | 全檔停留在 Spec-0025 之前：時序圖寫「使用者 → architect：業務需求 / Bug 修復 → feature-design」；目錄樹寫「8 大技能」（實為 10）；沒有 `workflows/`、bug-triage、規範變更流程 | 見 D4：改寫為精簡導覽 |
| U4 | 高 | 「8 大架構維度」 | 兩套不同定義並存：[arch_review_checklist.md](../../.agents/skills/feature-design/references/arch_review_checklist.md) 與 [feature-design/SKILL.md](../../.agents/skills/feature-design/SKILL.md) 為「PII、容量、非同步、Token 成本、可抽換性、輸入安全、索引演進、併發與追溯」；[adr_template.md](../../.agents/skills/doc-sync/references/adr_template.md) 與 [doc-sync/SKILL.md](../../.agents/skills/doc-sync/SKILL.md) 為「PII、容量、非同步、成本、無損容錯、可稽核、向下相容、安全」 | 以 arch_review_checklist 為唯一正本；ADR 範本與 doc-sync 改為引用該清單，不再列舉 |
| U5 | 高 | [doc-sync/SKILL.md](../../.agents/skills/doc-sync/SKILL.md) 階段 4 | 宣稱 `verify_doc_sync.py` 會檢查「CLI 入口點 `--help` 參數是否均存在於 REQUIREMENTS.md」，腳本**並未實作**；同時漏列 Spec-0025／0026 新增的分流表、`docs/bugs/`、範本鏡像、AGENTS.md 大小檢查 | 改為列出腳本實際檢查項目；CLI 參數比對改列為人工檢查（見 [doc_sync_checklist.md](../../.agents/skills/doc-sync/references/doc_sync_checklist.md)） |
| U6 | 中 | [auto-fix/SKILL.md](../../.agents/skills/auto-fix/SKILL.md) 階段 4 | 標題「不可踰越的**四大**修復底線」，實際列了 6 項 | 改為「修復底線」，不寫數量 |
| U7 | 中 | 負面測試數量 | [unit-testing/SKILL.md](../../.agents/skills/unit-testing/SKILL.md) 與 [unit_test_checklist.md](../../.agents/skills/unit-testing/references/unit_test_checklist.md) 要求每個新功能**至少 2 組**負面情境；[review_checklist.md](../../.agents/skills/code-review/references/review_checklist.md) P1 只要求**至少 1 組** | 統一為 2 組（以 unit-testing 為正本），review_checklist 改為引用 |
| U8 | 中 | Step 1「QA 驗收測試案例矩陣」 | AGENTS.md、`feature.md`、architect 角色檔都要求 Step 1 產出 QA 驗收矩陣，但 [tech_spec_template.md](../../.agents/skills/feature-design/references/tech_spec_template.md) 只有單元測試計畫，沒有這個章節；[test_case_template.md](../../.agents/skills/qa-testing/references/test_case_template.md) 自稱用於 Step 1，但 feature-design 沒有引用它 | Tech Spec 範本新增「QA 驗收案例矩陣」章節（AC → TC 對照表），格式與 QA 報告第 3、4 節一致 |
| U9 | 低 | 3 個角色檔的系統提示詞 | 開頭「你是由 Google Antigravity 團隊設計的…」，與 AGENTS.md「跨工具共用」定位不符，在 Claude Code 中也不正確 | 改為工具中立的「你是本專案的…」 |
| U10 | 低 | [qa-testing/SKILL.md](../../.agents/skills/qa-testing/SKILL.md) | 放行標準寫「零 P0/P1 缺陷」，但 P0/P1 只在 review_checklist 中定義（代碼審查等級），QA 缺陷的分級沒有定義；另外引用不存在的 `tests/integration/` 目錄 | 註明 QA 缺陷沿用 review_checklist 的等級定義；刪除 `tests/integration/` 字樣 |

### 2. 重複

| ID | 嚴重度 | 重複內容 | 出現位置 | 建議修正 |
| :--- | :---: | :--- | :--- | :--- |
| D1 | 中 | Gate 2 檢核項 | [code-review/SKILL.md](../../.agents/skills/code-review/SKILL.md) 階段 B 的 12 項清單與 [review_checklist.md](../../.agents/skills/code-review/references/review_checklist.md) 平行維護；PR #15、#17 每次都要改兩處 | 階段 B 改為「對照 review_checklist.md 逐項覆核」，不再自行列舉；階段 C 報告範本保留 |
| D2 | 中 | 8 大維度內容 | 4 處：feature-design SKILL、arch_review_checklist、ADR 範本、doc-sync SKILL／doc_sync_checklist | 併入 U4 處理 |
| D3 | 中 | 輸入硬上限數值（25MB、30 頁、10x） | 3 處：arch_review_checklist、review_checklist、code-review SKILL；實際值由 `AppConfig`／`.env` 決定，文件數值可能過時 | 只在 review_checklist 保留一處，並註明「預設值，以 `.env.example` 為準」；其餘改為引用 |
| D4 | 中 | 交接合約 | [.agents/README.md](../../.agents/README.md) 的「四大標準產出物交接合約」與三個角色檔的「交接合約」章節內容相同 | README 改為精簡導覽：目錄說明 + 連結到 AGENTS.md 分流表、流程檔、角色檔；刪除時序圖與交接表（以角色檔為正本） |
| D5 | 低 | 三振熔斷 | 5 處：AGENTS.md 第 3 節、`feature.md`、`bug.md`、auto-fix SKILL、fix_anti_patterns | 規則正本留在 AGENTS.md 第 3 節與 auto-fix SKILL；流程檔與 fix_anti_patterns 改為一句引用 |
| D6 | 低 | 單元測試規則 | unit-testing SKILL、unit_test_checklist、developer 角色檔系統提示詞三處各寫一次離線 Mock、負面情境要求 | 角色檔改為「依 unit-testing 技能執行」，保留最關鍵的一句紅線即可 |
| D7 | 低 | 單一測試案例格式 | [test_case_template.md](../../.agents/skills/qa-testing/references/test_case_template.md) 的逐案格式與 QA 報告第 4 節執行矩陣重疊；實際報告都只用矩陣 | 保留範本，但改定位為「複雜案例（併發、跨服務）的補充說明格式」，非必填 |

### 3. 缺漏

| ID | 嚴重度 | 缺漏 | 建議修正 |
| :--- | :---: | :--- | :--- |
| M1 | 高 | [governance.md](../../.agents/workflows/governance.md) 沒有角色對應（feature／bug 都有角色欄）；[CLAUDE.md](../../CLAUDE.md) 模型分級表也沒有規範變更各步驟 | 新增角色欄：G1、G3 由 architect；G2 由使用者；G4 為機械化檢查；G5 由 gatekeeper（獨立視角）。CLAUDE.md 分級表依決議第 4 項補列 |
| M2 | 中 | [quality-evaluation](../../.agents/skills/quality-evaluation/SKILL.md) 技能沒有綁定任何角色或流程步驟，只在 AGENTS.md 與兩份範本中被提及 | `feature.md` Step 1、Step 4 加註「規格宣告屬品質評測範圍時，使用 quality-evaluation」；architect（Step 1 定義品質 AC）與 gatekeeper（Step 4 執行評測）角色檔加入此技能 |
| M3 | 中 | [doc-sync](../../.agents/skills/doc-sync/SKILL.md) 與 [doc_sync_checklist.md](../../.agents/skills/doc-sync/references/doc_sync_checklist.md) 只涵蓋 REQUIREMENTS、ARCHITECTURE、ADR；沒有 `docs/README.md` 索引、`docs/bugs/`、`docs/templates/` 鏡像，也沒有 Bug 軌精簡同步與規範變更的差異 | 兩份文件各新增：索引與鏡像同步項目；「依軌別的同步範圍」小表（功能：完整；缺陷：精簡；規範變更：轉接層、鏡像、索引） |
| M4 | 低 | AGENTS.md 第 3 節第 9 條「規範與角色檔零重複讀取」只列角色檔與 Skill 檔，沒有流程檔 | 加入流程檔 |
| M5 | 低 | 規範變更 G1 沒有提案格式；小改要寫在 PR 描述中，但沒有範本 | `governance.md` 附一段 5 欄的 G1 提案格式（動機、修改檔案、衝突檢查、規模、待決事項），不另建範本檔 |
| M7 | 中 | [verify_doc_sync.py](../../.agents/skills/doc-sync/scripts/verify_doc_sync.py) 的 `quality_scope()` 取全文**第一個**品質評測範圍宣告字樣（冒號後接是或否），不限驗收標準段落。本提案草稿在發現表中引用了這個字樣，就被誤判為「宣告屬範圍但缺指標」而 FAIL（撰寫本案時實際發生） | `quality_scope()` 改為先在驗收標準段落內搜尋，找不到才退回全文；補單元測試（宣告前方出現引用字樣的情境） |
| M6 | 低 | Hotfix「合併後 3 個工作天內補件」沒有追蹤機制，逾期無人發現 | 暫不自動化；`docs/README.md` 缺陷索引的狀態欄標「已止血，待補件（期限 YYYY-MM-DD）」，於下次規範檢查時人工確認 |

---

## 三、規模與檔案清單

**規模**：大改（修改 4 份技能、3 份角色檔、`.agents/README.md` 重寫、章節重組）。

| 檔案 | 對應發現 |
| :--- | :--- |
| `.agents/README.md` | U3、D4 |
| `.agents/{architect,developer,gatekeeper}/AGENT.md` | U9、D6、M2 |
| `.agents/skills/feature-design/SKILL.md`、`references/arch_review_checklist.md`、`references/tech_spec_template.md` | U1、U2、U4、U8、D3 |
| `.agents/skills/doc-sync/SKILL.md`、`references/adr_template.md`、`references/doc_sync_checklist.md` | U4、U5、M3 |
| `.agents/skills/code-review/SKILL.md`、`references/review_checklist.md` | U7、D1、D3 |
| `.agents/skills/auto-fix/SKILL.md`、`references/fix_anti_patterns.md` | U6、D5 |
| `.agents/skills/unit-testing/SKILL.md` | U7 |
| `.agents/skills/qa-testing/SKILL.md`、`references/test_case_template.md` | U10、D7 |
| `.agents/workflows/feature.md`、`bug.md`、`governance.md` | D5、M1、M2、M5 |
| `AGENTS.md`、`CLAUDE.md` | M1、M4 |
| `docs/templates/*` | 範本修改後重新複製鏡像 |
| `.agents/skills/doc-sync/scripts/verify_doc_sync.py`、`tests/unit/test_quality_ac_gate.py` | M7（程式部分須有單元測試並走 Gate 2 程式檢查項） |

不新增技能、角色或流程檔。AGENTS.md 預估增加 1 行（M4）。

---

## 四、驗收標準
* **AC-1**：第二章 U1～U10、D1～D7、M1～M7 逐項處理，或於 QA 報告註明決議不處理的理由。
* **AC-2**：「8 大架構維度」全倉只有一份定義（arch_review_checklist），其餘位置皆為引用。
* **AC-3**：全倉搜尋「單純 Bug 修復」「或缺陷修復」「8 大技能」「四大修復底線」「Google Antigravity 團隊設計」「CLI 入口點 `--help`」無殘留。
* **AC-4**：`governance.md` 具備角色欄；CLAUDE.md 模型分級表涵蓋規範變更步驟。
* **AC-5**：G4 六項檢查通過；全套單元測試、`verify_doc_sync.py`、`audit_guardrails.py` 通過。

品質評測範圍：否

---

## 五、決議事項

> 2026-11-19 使用者核准。第 4 項原建議為「G1/G3 architect `opus`、G5 gatekeeper `sonnet`」，經使用者質疑「審查者是否該升級」後修訂：G3 照已核准提案執行，降為 `sonnet`；G5 為獨立審查，比照 Gate 2 首審升為 `opus`，使審查者不弱於提案者。

| # | 問題 | 決議 | 未採用方案 |
| :---: | :--- | :--- | :--- |
| 1 | `.agents/README.md` 如何處理？ | 改寫為約 20 行的精簡導覽，交接細節以角色檔為正本 | 刪除整份檔案，由 AGENTS.md 承擔導覽 |
| 2 | 「8 大維度」以哪一套為正本？ | arch_review_checklist 那套（較新，含 Token 能效與索引演進，且是 Gate 1 實際使用的） | ADR 範本那套（含可稽核、向下相容） |
| 3 | 負面測試最低數量？ | 2 組（unit-testing 現行規定） | 1 組（review_checklist 現行規定） |
| 4 | M1 規範變更的模型分級？ | G1 architect `opus`；G3 architect `sonnet`；G4 不指定角色 `haiku`；G5 gatekeeper `opus`（大改或首審）、`sonnet`（小改或僅驗證前次修正的複審） | G1/G3 architect `opus`、G5 gatekeeper `sonnet`（原建議：審查者弱於提案者） |
| 5 | 一次全部處理，還是分批？ | 一次處理（單一 PR），因為多數項目互相牽動（如 U4 與 D2） | 先處理「高」6 項，其餘另案 |
