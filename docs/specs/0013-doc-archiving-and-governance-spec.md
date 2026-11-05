# PRD 與 DDD 技術實作規格書：專案全景文檔體系升級

## 一、產品需求文件 (PRD)

### 1. 背景與痛點 (Problem Statement)
目前系統在執行 7 步驟閉環工作流時，Step 1（PRD 與 Tech Spec）與 Step 4（QA 實測報告）主要輸出於系統臨時 Artifacts 目錄（`<appDataDir>\brain\<conversation-id>`），導致開發者在 VS Code 或 Git 專案樹中無法直接瀏覽這些設計規格與測試驗收記錄，產生「產物不透明、找不到規格書與測試計劃」的使用者痛點。
本功能旨在將歷次與未來的規格、測試計劃與驗收報告正式納入版本控制與專案文檔體系。

### 2. 範疇界定 (Scope)
* **In-Scope**:
  1. 建立專案文檔目錄結構：`docs/specs/` 與 `docs/qa_reports/`。
  2. 提取並規範化整理 `brain/` 中的歷史 PRD、Tech Spec 與 QA 驗收報告，按 ADR 編號連續對齊入庫。
  3. 建立專案文檔總目錄清單 `docs/README.md`，達成 ADR、規格書、測試腳本與 QA 報告的四向追溯。
  4. 升級 `verify_doc_sync.py` 驗證腳本，納入 `docs/specs/` 與 `docs/qa_reports/` 的同步檢核。
  5. 升級憲法級規範 `AGENTS.md` 與 `GEMINI.md`，要求未來的 Step 1 與 Step 4 強制雙寫（Artifact + 專案目錄持久化）。
* **Out-of-Scope**:
  - 不修改核心轉換 Use Case 與業務邏輯。
  - 不變動既有 CLI 指令與對外介面相容性。

### 3. 驗收標準 (Acceptance Criteria, AC)
* **AC-1 (Directory & File Organization)**: `docs/specs/` 與 `docs/qa_reports/` 成功建立，歷史產物依編號全數完成轉移歸檔。
* **AC-2 (Unified Index Navigation)**: `docs/README.md` 與 `docs/adr/README.md` 提供完整導航，所有規格與報告具備正確超連結。
* **AC-3 (Doc Sync Verification)**: `verify_doc_sync.py` 成功擴充並通過 100% 綠燈檢驗。
* **AC-4 (Constitution Guardrails Update)**: `AGENTS.md` 與 `GEMINI.md` 載明 Step 1 / Step 4 雙重持久化要求。
* **AC-5 (Zero Code Regression)**: `audit_guardrails.py` 與現有單元測試/E2E 測試全數通過。

---

## 二、8 大架構維度前審 (Gate 1 審查)

1. **個資隱私 (PII)**：所有遷移歸檔之歷史文檔均為技術規格與虛擬/脫敏測試，無真實個資。
2. **容量與極限 (Capacity)**：文檔皆為 Markdown 格式，磁碟空間消耗極低（小於 500KB）。
3. **非同步與演進 (Async / Evolution)**：純靜態文檔與驗證腳本，支援後續任意 CI/CD 流程整合。
4. **成本與熔斷 (Cost)**：零額外 API Token 消耗。
5. **可抽換性 (Portability)**：完全標準化 Markdown 與標準相對路徑。
6. **輸入安全性 (Input Security)**：純文檔與靜態檢查，不引入任何動態代碼執行漏洞。
7. **版本相容性 (Versioning)**：檔案編號對齊 ADR 0005~0012，無縫銜接。
8. **可觀測性與追溯性 (Observability & Traceability)**：建立需求、架構、測試代碼與驗收報告 100% 雙向追溯鏈。

---

## 三、DDD 技術實作規格書 (Tech Spec)

### 1. 檔案與目錄結構
```
docs/
├── README.md                      # 全專案文檔中樞導覽 (ADR + Specs + QA Reports)
├── adr/                           # 架構決策紀錄 (0001 ~ 0012, README.md)
├── specs/                         # 需求規格與 DDD 技術實作書 (PRD & Tech Spec)
│   ├── 0005-security-observability-remediation-spec.md
│   ├── 0006-token-optimization-spec.md
│   ├── 0007-env-extraction-spec.md
│   ├── 0008-prompt-versioning-and-extended-env-spec.md
│   ├── 0009-hardcode-extraction-spec.md
│   ├── 0010-prompt-externalization-and-template-governance-spec.md
│   ├── 0011-agent-memory-and-streaming-token-spec.md
│   └── 0012-centralized-logging-and-api-latency-spec.md
└── qa_reports/                    # QA 測試計劃與驗收報告
    ├── 0005-architecture-code-review-audit-report.md
    ├── 0006-token-optimization-qa-report.md
    ├── 0007-env-extraction-qa-report.md
    ├── 0008-prompts-and-extended-env-qa-report.md
    ├── 0009-hardcode-extraction-qa-report.md
    ├── 0010-prompt-extraction-qa-report.md
    ├── 0011-agent-memory-and-streaming-token-qa-report.md
    └── 0012-centralized-logging-and-api-latency-qa-report.md
```

### 2. `verify_doc_sync.py` 檢查邏輯擴充
- 檢驗 `docs/specs/` 與 `docs/qa_reports/` 是否存在。
- 檢驗檔案編號是否為 `000X-*.md` 格式。
- 檢驗 `docs/README.md` 是否完整收錄上述規格與 QA 報告。

### 3. Gate 1 放行結論
規格清晰、無架構破壞風險，**Gate 1 審查通過 (PASS)**，放行進入 Step 2 實作。
