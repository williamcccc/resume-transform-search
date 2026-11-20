# 提案與規格書：ASVS 章節歸屬自動檢查

> **狀態**：提案（G1，待核准；尚未實作）｜**類型**：規範變更（大改：修改驗證腳本）｜**流程**：[governance.md](../../.agents/workflows/governance.md)｜**影響範圍**：`verify_doc_sync.py`、`.agents/lib/project_config.py`（視待決事項 2）、`.agents/project.toml`、[security_nfr_framework.md](../../.agents/skills/feature-design/references/security_nfr_framework.md) 與其單元測試，不涉及 `src/`

## 一、動機

[security_nfr_framework.md](../../.agents/skills/feature-design/references/security_nfr_framework.md) 第四節已改為 OWASP ASVS 5.0 V1–V17 全章對照（[PR #28](https://github.com/williamcccc/resume-transform-search/pull/28)），並規定：

1. 每章須歸入「一律／特徵／技術」三種適用條件之一，不得有未歸屬的章節。
2. 適用條件為「技術」的章節（V9、V10、V17），專案未使用該技術時須於 `project.toml` 的 `[[security.not_applicable]]` 登錄。

這兩條目前只寫在文件，沒有自動檢查。改版前 V11 密碼學就是「對照表沒列、專案也沒宣告」而無人發現；同類情況（例如日後 ASVS 新版增加章節、移植時漏填技術章節）仍只能靠人眼發現。

## 二、提案內容

`verify_doc_sync.py` 新增「ASVS 章節歸屬檢查」：

| # | 檢查 | 失敗時 |
| :---: | :--- | :--- |
| C1 | 框架第四節對照表恰好列出 V1–V17 各一列，無缺號、無重複 | FAIL |
| C2 | 每列「適用條件」欄以「一律」「特徵」「技術」之一開頭 | FAIL |
| C3 | 適用條件為「技術」的每一章，在 `project.toml` 有明確宣告（宣告方式見待決事項 2） | FAIL |
| C4 | `not_applicable` 的 `item` 提及之章節編號皆在 V1–V17 範圍內 | FAIL |

章節編號以正規式 `V(\d+)` 自對照表與 `item` 文字擷取；章節總數（17）與 ASVS 版本寫於框架檔或 `project.toml`，新版發布時以規範變更更新。

## 三、修改檔案（預估）

| 檔案 | 變更 |
| :--- | :--- |
| `.agents/skills/doc-sync/scripts/verify_doc_sync.py` | 新增章節歸屬檢查 C1–C4 |
| `.agents/lib/project_config.py` | 若採待決事項 2 方案 A，新增鍵之 schema |
| `.agents/project.toml` | 若採方案 A，新增技術使用宣告 |
| `.agents/skills/feature-design/references/security_nfr_framework.md` | 第四節註明本檢查；必要時調整表格格式以利解析 |
| `.agents/PORTING.md` | 補述移植時本檢查的要求 |
| `tests/unit/`（新增或擴充） | C1–C4 正反案例，設定檔與框架表於暫存目錄動態建構 |
| `tests/e2e/test_portable_closed_loop_e2e.py` | 移植演練涵蓋 C3 |

## 四、衝突與重複檢查

* `project_config.py` 已檢查 `not_applicable` 每筆有 `item` 與 `reason`（Spec-0030 AC-2）；本案只新增「章節是否歸屬」之語意檢查，不重複格式檢查。
* [AGENTS.md](../../AGENTS.md) 安全規則第 2 條「專案只宣告特徵：適用標準由 `project.toml` 的 `[security]` 特徵對照決定，不適用者須附理由」，未提及技術條件章節；見待決事項 4。

## 五、規模

**大改**：修改驗證腳本（[governance.md](../../.agents/workflows/governance.md) 規模分級）。產出本規格與 `docs/qa_reports/0034-*.md`。

## 六、待決事項

| # | 問題 | 建議 | 替代方案 |
| :---: | :--- | :--- | :--- |
| 1 | 檢查範圍 | C1–C4 全做 | 只做 C1、C2（框架表完整性），C3 留給人工 |
| 2 | 專案「有使用」某技術章節時如何宣告，使 C3 能分辨「有用」與「漏填」 | **方案 A**：`[security]` 新增 `tech_chapters_in_use = []`（例如 `["V9"]`），技術章節須出現在此清單或 `not_applicable` 之一 | 方案 B：不新增鍵，技術章節未登錄於 `not_applicable` 即視為「使用中」（無法偵測漏填，C3 形同虛設） |
| 3 | 失敗等級 | FAIL（與其他設定錯誤一致） | 先以 WARN 試行一版 |
| 4 | 是否一併精確化 AGENTS.md 安全規則第 2 條用詞（加入技術條件章節） | 一併修改 | 維持現狀 |
| 5 | 是否與 [Bug-0031](../bugs/0031-layer-check-skips-nested-modules.md)～[Bug-0033](../bugs/0033-env-sync-check-skips-missing-files.md)（`audit_guardrails.py` 守門缺口）合併處理 | 分開處理：修改不同腳本，避免單一 PR 過大 | 合併為同一份規範變更 |

## 七、驗收標準（草案，G2 核准後定稿）

* **AC-1**：對照表缺一章、重複一章、或適用條件欄不屬三類之一時，`verify_doc_sync.py` 回報 FAIL 並指出章節。
* **AC-2**：技術條件章節未於 `project.toml` 宣告時回報 FAIL 並指出章節。
* **AC-3**：`not_applicable` 提及 V1–V17 以外之編號時回報 FAIL。
* **AC-4**：本專案現行設定與框架執行結果為 PASS；全套單元測試無回歸。

品質評測範圍：否（不涉及檢索、抽取或 LLM 生成）

安全評估範圍：否（只修改文件一致性檢查腳本；無新增對外介面、跨信任邊界資料流、外部相依或敏感資料處理）
