# 提案與規格書：feature-design 新增需求澄清階段與假設清單

> **狀態**：已實作（G2：使用者於 2026-11-21 核准，待決事項 1–4 採建議、第 5 項改採替代方案「一併寫入」；QA 見 [QA-0049](../qa_reports/0049-requirement-clarification-qa.md)）｜**類型**：規範變更（大改：修改驗證腳本 `verify_doc_sync.py`）｜**流程**：[governance.md](../../.agents/workflows/governance.md)｜**影響範圍**：`.agents/skills/feature-design/`、`.agents/architect/AGENT.md`、`docs/templates/prd_template.md`、`.agents/skills/doc-sync/scripts/verify_doc_sync.py`、`.agents/project.toml`、`.agents/PORTING.md`、`.agents/tests/`、`CLAUDE.md`、`GEMINI.md`，不涉及 `src/`、不修改紅線

## 一、動機

[feature-design](../../.agents/skills/feature-design/SKILL.md) 開宗明義要杜絕「接收到簡短使用者指令時天馬行空」，但流程為「階段 1 代碼庫探測 → 階段 2 產出 PRD」，**中間沒有向使用者澄清的步驟**：

| # | 問題 | 實例 | 影響 |
| :---: | :--- | :--- | :--- |
| 1 | 代碼探測只能回答「怎麼做」，回答不了「為什麼做、做到哪裡算完成」 | 「搜尋結果要更準一點」：準是指召回還是排序、門檻多少、用哪批資料驗證，程式碼皆無法推得 | AI 以合理猜測填滿 PRD 空白，產出看似完整但前提錯誤的規格；錯誤要到 Gate 2 或交付後才被發現，Step 2–6 整輪白做 |
| 2 | Gate 1 只檢查 PRD 是否達標，不檢查假設是否經使用者確認 | PRD 寫出 `Recall@10 ≥ 0.8`，使用者無從分辨這是需求還是 AI 自訂 | 業務決定被 AI 代為決定且不留痕跡 |
| 3 | 既有 Fast/Deep Track 以**架構衝擊**分流，無法代表**需求明確度** | 「搜尋更準一點」可能只改幾行（Fast Track），卻最需要澄清 | 若以改動大小決定是否澄清，最模糊的需求反而被略過 |

## 二、修改內容

### 2.1 新增「階段 1.5：需求澄清」（feature-design）

新增參考檔 `.agents/skills/feature-design/references/requirement_clarification.md`（澄清規則唯一正本），SKILL.md 之流程圖與階段說明插入階段 1.5，只指向參考檔：

* **時點**：階段 1 代碼探測之後、階段 2 寫 PRD 之前。能由程式碼、規範推得之事實不得拿來問使用者。
* **觸發判定**（命中任一條即須澄清，否則可略過）：
  1. 需求含未量化之形容詞或動詞（「更好」「更準」「優化」「支援」「改善」）且未給目標值。
  2. 有兩種以上合理解讀，且不同解讀導致不同 AC。
  3. 範圍邊界不明（是否包含某子功能、只改 CLI 或含 API）。
  4. 改變既有使用者可見行為（預設值、輸出格式、對外入口參數）。
  5. 品質評測範圍為「是」（門檻與標註資料來源屬業務決定）。
  6. 安全評估範圍為「是」，且有殘餘風險需人接受。
  7. 涉及刪除、覆寫既有資料或不可逆操作。
* **提問方式**：
  * 只問影響範圍、AC 或門檻之事項，**最多 5 題，原則一輪問完**。
  * 選擇題形式，每題附建議選項與一句理由，並附代碼探測查得之事實（檔案:行號），使用者不需自行翻程式碼。
  * 使用者回答「由 AI 決定」時採建議選項，記為「使用者授權」。
* **撰寫 PRD 途中新浮現之問題**：細節性者依建議選項處理，假設清單來源記為「使用者授權」、依據註明「待 Gate 1 追認」，Gate 1 時一併呈現；會推翻範圍者再問一輪。
* **與 Fast/Deep Track 正交**：是否澄清只看上述 7 條，不看架構衝擊大小。

### 2.2 PRD 新增「6. 假設清單」（範本與鏡像）

`prd_template.md`（正本）與 `docs/templates/prd_template.md`（鏡像）新增第 6 節：

```markdown
## 6. 假設清單 (Assumptions)
需求澄清：已執行（第 N 題）／略過（未命中觸發條件）

| # | 假設 | 來源 | 依據 |
| :---: | :--- | :--- | :--- |
| A-1 | 預設回傳筆數維持 5 | 程式碼 | `path/to/file.py:42` |
| A-2 | 只改 CLI，不改 API | 使用者確認 | 澄清第 2 題 |
```

* **來源**限定五值：`程式碼`、`規範`、`使用者原話`、`使用者確認`、`使用者授權`。
* 任何一條寫不出上述來源者，即代表須回階段 1.5 澄清；不允許「推測」。
* Gate 1 時使用者只需掃此表，即可分辨哪些是自己的決定、哪些是 AI 經授權代為決定。

### 2.3 驗證腳本強制（verify_doc_sync.py）

* 新增設定鍵 `.agents/project.toml` 之 `[docs].assumptions_enforced_from = 49`，PORTING 同步說明（移植專案可設為其首份新規格編號）。
* 編號 ≥ 該值之規格須含「假設清單」標題下之表格：表頭有「來源」欄、至少一列資料、每列來源為上述五值之一（可加粗）；否則 FAIL。
* 另須有「需求澄清：已執行／略過」宣告列。
* 表格解析沿用 Spec-0048 之 `markdown_tables()`。

### 2.4 多代理模式之提問轉接

子 Agent 無法直接與使用者對話：

* 規則正本（`requirement_clarification.md` 第三節）：多代理模式下，子 Agent 於階段 1.5 結束任務，回報中列出澄清問題（題目、選項、建議、查得事實），由主對話代問後新派工續行；不得自行代答。不新增交接 Schema 之 `action` 值，AGENTS.md 不改。
* `.agents/architect/AGENT.md`：輸入合約與系統提示詞加入「依階段 1.5 判定是否澄清」，只指向正本。
* `CLAUDE.md`（工具專屬覆寫）：主對話以 `AskUserQuestion` 呈現上述問題，建議選項置首並標示 `(Recommended)`。
* `GEMINI.md`（工具專屬覆寫）：主對話於對話中以編號選擇題呈現上述問題，建議選項置首並標示「（建議）」。

### 2.5 測試

* 新增 `.agents/tests/test_assumption_list_gate.py`：缺假設清單 FAIL、缺來源欄 FAIL、空表 FAIL、來源為「推測」FAIL、五種合法來源與加粗皆通過、編號低於門檻者略過、缺「需求澄清」宣告 FAIL（皆先紅後綠）。
* `test_project_config.py` 補新設定鍵之讀取測試。

## 三、衝突與重複檢查

| 檢查 | 結果 |
| :--- | :--- |
| 與既有規則矛盾 | 無。Gate 1 放行條件（AGENTS.md 第 2 節）不改文字，「PRD 達標」之內涵由範本新增第 6 節補足；Fast/Deep Track 不變，澄清判定與之正交 |
| 同一規則寫在兩處 | 澄清規則只寫在 `requirement_clarification.md`；SKILL.md、architect AGENT.md 只指向它；假設清單格式正本為 `prd_template.md`，腳本只驗證 |
| 與 Bug 軌 | Bug 軌之「正確行為」由既有規格定義，不適用本階段；升級為功能開發時才適用（見待決事項 4） |
| 治理規格 | 本規格起所有 `docs/specs/` 規格皆須附假設清單（含規範變更規格，見待決事項 3）；本規格第七節即為首例 |
| 紅線 | 不修改 AGENTS.md |

## 四、規模

**大改**：修改驗證腳本、新增技能參考檔。產出本規格與 QA 報告；不涉及紅線，不寫 ADR。AGENTS.md 預計零行數變化。

## 五、待決事項

| # | 問題 | 建議 | 替代方案 |
| :---: | :--- | :--- | :--- |
| 1 | 每輪提問上限 | **5 題** | 3 題（更省時間，但複雜需求可能需第二輪） |
| 2 | 假設清單是否由腳本強制 | **強制**（自 0049 起，缺漏或來源非法即 FAIL） | 僅寫入範本與技能，不強制（彈性高，但易被省略） |
| 3 | 規範變更規格（如本檔）是否也須附假設清單 | **須附**（G1 提案同樣含 AI 假設） | 只限功能開發規格（須在規格中另加類型標記供腳本區分） |
| 4 | Bug 軌是否適用 | **不適用**，僅升級轉功能開發時適用 | Bug 軌 Step 1B 也加假設清單 |
| 5 | GEMINI.md 是否同步加提問工具對應 | 本次不加，待有 Antigravity 實測再補 | **本次一併寫入通用說法**（G2 採此項） |

## 六、驗收條件

品質評測範圍：否

安全評估範圍：否（僅修改規範文件與文件驗證腳本，無新增跨信任邊界之資料流）

* **AC-1**：feature-design SKILL.md 流程圖與階段說明含階段 1.5，並連結 `requirement_clarification.md`；7 條觸發判定、提問方式、途中新問題處理只出現在該參考檔。
* **AC-2**：`prd_template.md` 與其鏡像含第 6 節假設清單，`verify_doc_sync.py` 鏡像檢查通過。
* **AC-3**：編號 ≥ `assumptions_enforced_from` 之規格，缺假設清單、缺來源欄、空表、來源非五值之一、缺「需求澄清」宣告時 FAIL；修正前同一輸入通過（先紅後綠）。編號較小之既有規格不受影響。
* **AC-4**：多代理提問轉接規則只寫在 `requirement_clarification.md`，architect AGENT.md 指向之；CLAUDE.md 含 `AskUserQuestion` 對應、GEMINI.md 含對話選擇題對應；轉接層一致性檢查通過。
* **AC-5**：本專案 `verify_doc_sync.py`、`audit_guardrails.py`、`security_scan.py` 通過；`tests/unit`（含斷鏈）、`.agents/tests`、`.agents/tests/e2e`、`tests/e2e` 之移植演練全數通過。

## 七、假設清單

需求澄清：已執行（於對話中確認「短需求後由 AI 回頭提問」之流程與「以待決假設而非改動大小判定」之原則）

| # | 假設 | 來源 | 依據 |
| :---: | :--- | :--- | :--- |
| A-1 | 澄清時點在代碼探測之後、寫 PRD 之前 | 使用者確認 | 對話中確認「寫簡短需求後，AI 再回頭問問題」之流程 |
| A-2 | 是否澄清以「有無需使用者決定之事」判定，不以改動大小判定 | 使用者確認 | 對話中「小需求怎麼定義」之討論 |
| A-3 | 本變更屬大改，須產出規格與 QA 報告 | 規範 | [governance.md](../../.agents/workflows/governance.md) 規模分級：修改驗證腳本 |
| A-4 | 表格解析可沿用既有 `markdown_tables()` | 程式碼 | `.agents/skills/doc-sync/scripts/verify_doc_sync.py` 之 `markdown_tables` |
| A-5 | 待決事項 1–4 採建議、第 5 項改為一併寫入 GEMINI.md | 使用者確認 | G2 對話核准 |
