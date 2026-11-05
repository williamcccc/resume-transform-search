---
name: doc-sync
description: >-
  Use this skill to synchronize requirements, architecture documentation, sequence diagrams, and architecture decision records (ADR)
  with code implementation, ensuring zero documentation drift and seamless ADR lifecycle transitions.
---

# 文檔、規格與 ADR 雙向同步技能 (Documentation, Spec & ADR Sync)

本技能提供本專案實施 **「Step 7：文檔、規格與 ADR 同步 (Doc Sync)」** 時的最高作業規範。
確保每次功能交付或缺陷修復後，程式碼實作、技術文件（`REQUIREMENTS.md`、`ARCHITECTURE.md`）與架構決策紀錄（`docs/adr/`）**保持 100% 雙向即時一致**，徹底杜絕「代碼已更新、文檔卻落後」的文檔漂移（Doc Drift）問題。

---

## 一、文檔同步四階段作業流程 (4-Phase Workflow)

```mermaid
flowchart TD
    Start["進入 Step 7: 文檔同步 (Doc Sync)<br>(已通過 Gate 2 代碼審查)"] --> Phase1["階段 1: 需求與命令對齊 (Requirements Sync)<br>• 核對 REQUIREMENTS.md 命令清單與參數說明<br>• 同步新增/調整之 CLI 引數、預設值與退出碼"]
    
    Phase1 --> Phase2["階段 2: 整潔架構與時序同步 (Architecture Sync)<br>• 核對 ARCHITECTURE.md DDD 四層職責<br>• 同步 Domain 模型、DTO 契約與 Use Case 時序圖"]
    
    Phase2 --> Phase3["階段 3: ADR 生命週期歸檔 (ADR Lifecycle Sync)<br>• 將 docs/adr/ 草案正式轉為 Accepted 狀態<br>• 同步 docs/adr/README.md 索引表格與技術標籤"]
    
    Phase3 --> Phase4["階段 4: 一致性自動驗證 (Verification)<br>• 執行 python .agents/skills/doc-sync/scripts/verify_doc_sync.py<br>• 確認零文檔債、無斷鏈、格式合法"]
    
    Phase4 --> Check{"文檔同步檢驗是否通過?"}
    Check -->|"失敗/未對齊"| Fix["補全缺漏之文檔或修正索引"]
    Fix --> Phase4
    Check -->|"全部合格"| Done["完成交付準備 (Ready for Delivery)"]
```

---

## 二、各階段具體執行規範

### 階段 1：需求與命令對齊 (Requirements Sync)
* **目標檔案**：[`REQUIREMENTS.md`](../../../REQUIREMENTS.md)
* **檢核與同步要點**：
  1. **CLI 參數對齊**：若本次異動新增或修改了命令列參數（如 `--review`, `--index-to-redis`, `--skills` 等），必須在 `REQUIREMENTS.md` 中詳細列出參數名稱、型別、預設值與使用範例。
  2. **業務驗收追溯**：將本次 PRD 中的主要驗收標準（AC）成果反映至需求文檔的「核心功能實作狀態」章節。
  3. **向下相容性聲明**：確認既有命令語法與範例依然有效，無非預期的破壞性更動。

### 階段 2：整潔架構與時序同步 (Architecture Sync)
* **目標檔案**：[`ARCHITECTURE.md`](../../../ARCHITECTURE.md)
* **檢核與同步要點**：
  1. **DDD 領域實體與 DTO**：若有新增或擴充的資料模型（如 `ResumeChunk`, `SearchQuery`, `QualityReport`），必須同步更新文檔中的實體欄位定義與職責說明。
  2. **依賴反轉 Protocol 契約**：若在 `src/domain/interfaces.py` 增修了協定介面，需於基礎設施章節記錄對應的實作類別。
  3. **Mermaid 流程與時序圖**：若調度流程有異動，必須更新 Markdown 內嵌的 Mermaid `flowchart` 或 `sequenceDiagram`，維持可視化架構與代碼完全相符。

### 階段 3：ADR 生命週期歸檔 (ADR Lifecycle Sync)
* **目標目錄**：[`docs/adr/`](../../../docs/adr/) 與 [`docs/adr/README.md`](../../../docs/adr/README.md)
* **檢核與同步要點**：
  1. **狀態轉換**：若本次變更在 Step 1 草擬了架構決策紀錄（狀態為 `提案中 (Proposed)`），在通過審查與實作落地後，必須正式將狀態變更為 **`已採納 (Accepted)`**，並補全實施後的評估結論。
  2. **編號與索引維護**：檢查新 ADR 是否依照連續編號命名（如 `0006-xxxx.md`），並在 [docs/adr/README.md](../../../docs/adr/README.md) 的索引表格中追加該條目，填妥編號、標題、狀態、日期與核心技術標籤。
  3. **8 大架構維度完整性**：確保 ADR 內含 8 大維度評估（PII、Capacity、Async、Cost、Fault-Tolerance、Auditability、Compatibility、Security）。

### 階段 4：一致性自動驗證 (Automated Verification)
執行本技能內建的驗證腳本：
```bash
python .agents/skills/doc-sync/scripts/verify_doc_sync.py
```
* 該腳本將自動檢核：
  - `docs/adr/` 目錄下的所有檔案是否 100% 登錄於 `docs/adr/README.md` 索引表。
  - ADR 標題、狀態格式（Accepted / Proposed）是否合規。
  - CLI 入口點 `--help` 參數是否均存在於 `REQUIREMENTS.md`。

---

## 三、參考資料與範本
* [ADR 標準撰寫範本 (ADR Template)](./references/adr_template.md)
* [文檔同步自我檢核清單 (Doc Sync Checklist)](./references/doc_sync_checklist.md)
