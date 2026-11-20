# 文檔雙向同步檢核清單 (Documentation Sync Checklist)

在宣告任務交付（Step 7 結束）前，必須逐項對照本清單進行檢查，確認零文檔債：

---

### 一、REQUIREMENTS.md 同步檢核
- [ ] **CLI 入口命令同步**：所有新增或變更的命令列參數（如 `--review`, `--index-to-redis`, `--output-dir`<!-- 專案專屬 -->）是否已登載至 `REQUIREMENTS.md`？
- [ ] **參數預設值與型別標註**：每個參數的型別（String, Flag, Integer）與預設行為是否說明清晰？
- [ ] **業務需求狀態**：PRD 中定義的本次功能是否已納入「已實作功能矩陣」？
- [ ] **CLI 使用範例更新**：文檔中的命令列操作範例是否經測試可實際執行？

---

### 二、ARCHITECTURE.md 同步檢核
- [ ] **DDD 四層邊界維持**：新增之模組是否被精準分類至 Domain / Application / Infrastructure / Interfaces 四層？
- [ ] **Domain 實體與 Value Objects**：新增或擴充的實體、值物件與資料欄位是否已反映於架構文檔的類別圖或資料結構章節？
- [ ] **Protocol 協定介面**：新增的 Domain 契約介面（Protocol，定義於 `layers.domain_interfaces`）是否已記錄於依賴反轉說明中？
- [ ] **Mermaid 流程圖/時序圖同步**：系統的 Use Case 流程圖或處理時序圖是否更新？（確保無語法錯誤且與程式碼一致）

---

### 三、docs/adr/ 架構決策紀錄同步檢核
- [ ] **狀態正規化**：已落地的 ADR 狀態是否已由 `提案中 (Proposed)` 正式變更為 **`已採納 (Accepted)`**？
- [ ] **編號連續性**：ADR 檔名是否依循 `XXXX-kebab-case.md` 連續編號命名？
- [ ] **索引表格同步**：[`docs/adr/README.md`](../../../../docs/adr/README.md) 的索引表格是否已新增該 ADR 條目（包含編號、標題、狀態、日期、技術標籤）？
- [ ] **8 大維度完整度**：ADR 第 5 節是否依 `.agents/skills/feature-design/references/arch_review_checklist.md`（維度定義唯一正本；本專案通過標準見 `.agents/project/arch_review_criteria.md`）逐項填寫評估結論，不適用者寫理由？

---

### 四、索引與範本鏡像同步檢核
- [ ] **`docs/README.md` 索引**：本次新增的規格、QA 報告、缺陷報告是否已登錄，並填妥測試檔與 QA 報告連結？
- [ ] **缺陷報告狀態**（Bug 軌、Hotfix）：缺陷索引的狀態欄是否已更新（處理中／已止血，待補件（期限 YYYY-MM-DD）／已結案／已升級）？
- [ ] **範本鏡像**：若修改了 `.agents/skills/*/references/` 下的範本，是否已重新複製至 `docs/templates/`？
- [ ] **轉接層**（規範變更）：新增技能或修改技能的 `name`／`description` 時，`.claude/skills/` 轉接檔是否同步？

---

### 五、自動化驗證執行
- [ ] **執行驗證腳本**：
  ```bash
  python .agents/skills/doc-sync/scripts/verify_doc_sync.py
  ```
  回傳值為 `0` 且無任何報錯。
