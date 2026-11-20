# 提案與規格書：架構前審 8 大維度通用化（問題放核心，答案放專案）

> **狀態**：提案（G1，待核准；尚未實作）｜**類型**：規範變更（大改：搬移與重組章節、新增專案實例檔）｜**流程**：[governance.md](../../.agents/workflows/governance.md)｜**影響範圍**：[arch_review_checklist.md](../../.agents/skills/feature-design/references/arch_review_checklist.md)、ADR 範本、[PORTING.md](../../.agents/PORTING.md) 與引用處，不涉及 `src/`

## 一、動機

[arch_review_checklist.md](../../.agents/skills/feature-design/references/arch_review_checklist.md)（Gate 1 的 8 大架構維度）位於閉環通用核心，但內容多半是本專案的答案：

| # | 維度 | 維度本身 | 「通過標準」綁定的內容 | 專屬標記 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 個資隱私 | 通用 | 履歷、Redis、身分證號 | 有 |
| 2 | 容量與極限 | 通用 | Redis HNSW 記憶體、萬筆切片 | 有 |
| 3 | 非同步與演進 | 通用 | Celery、Redis Queue | 有 |
| 4 | Token 能效與成本熔斷 | 僅 LLM 專案適用 | Text-First、Vision、切片語意密度 | **無** |
| 5 | 可抽換性 | 僅 DDD 專案適用 | 「更換向量庫或模型」 | 無 |
| 6 | 惡意輸入與配額硬上限 | 通用 | PDF 頁數、DOCX 膨脹比、`<resume_content>` | 有 |
| 7 | 向量索引演進遷移 | 本專案專屬 | `idx:resumes:v1`、藍綠索引 | 有（整個維度） |
| 8 | 分散式併發與可觀測性 | 通用 | 候選人級冪等、多 Worker | 有 |

造成三個問題：

1. **移植會漏改**：維度 4 沒有專屬標記，依 [PORTING.md](../../.agents/PORTING.md) 第 4 步搜尋標記找不到；未使用 LLM 的新專案仍會被要求檢查 Text-First 與切片密度。第二節「輕重分流」的 Deep Track 條件「改動向量索引」也同樣未標記。
2. **移植時無從改寫**：新專案尚無程式碼，要從零寫出 6 個維度的通過標準，只能憑印象，最壞情況是整列刪除。這與 [Spec-0030](./0030-portable-security-nfr-framework-spec.md) 動機第 4 點描述的安全維度問題相同。
3. **與安全框架重複**：[security_nfr_framework.md](../../.agents/skills/feature-design/references/security_nfr_framework.md) 已以通用方法涵蓋維度 1、2、3、6、8 的「問題」（第二節 ISO 25010 宣告、第三節 STRIDE、第四節 ASVS 全章對照）；8 維度清單實為同一批問題的本專案答案，卻放在核心位置。

## 二、設計原則

沿用 Spec-0030：**方法與問題放核心，答案放專案**。

* 核心檔只寫「每個維度要問什麼、何時適用、對應哪個標準」，任何專案皆可直接使用，不含專屬標記。
* 本專案的具體通過標準整份移到**專案實例檔**；移植時整份替換，不必逐處搜尋標記。
* 維度編號 1–8 保留，既有 19 份 ADR 的第 5 節仍可對照，不回改歷史 ADR。

## 三、提案內容

### 3.1 核心檔改寫：`arch_review_checklist.md`

| # | 維度（新名稱） | 適用條件 | 要問的問題 | 對應標準 |
| :---: | :--- | :--- | :--- | :--- |
| 1 | 個資與敏感資料 | 特徵：`handles_pii` | 敏感資料在哪裡流動、儲存、記錄？送往外部服務前如何保護？ | 安全框架第三節（STRIDE-I）、ASVS V14 |
| 2 | 容量與資源上限 | 一律 | 資料量、記憶體、併發量成長時，上限在哪裡？超過時如何退化？ | ISO 25010 效能效率 |
| 3 | 解耦與非同步演進 | 一律 | Use Case 是否無狀態？能否移至背景任務或佇列而不改核心邏輯？ | ISO 25010 彈性、可維護性 |
| 4 | 外部呼叫成本與配額 | 特徵：`uses_llm`，或依賴計費外部服務 | 重複輸入會不會重複付費？配額用罄時如何熔斷？成本上限在哪裡？ | ISO 25010 效能效率（資源使用）、OWASP LLM Top 10「無上限消耗」 |
| 5 | 可抽換性 | 設定：`layers.enabled = true` | 外部技術是否只透過 Domain 契約接入？更換時 Domain 與 Use Case 是否零改動？ | ISO 25010 可維護性（可替換） |
| 6 | 惡意輸入與資源上限 | 特徵：`web_interface`、`api_service` 或 `processes_untrusted_files` 任一 | 輸入的大小、格式、內容能否造成資源耗盡或注入？ | 安全框架第三節（STRIDE-T/D）、ASVS V1、V2、V5；用 LLM 者加 LLM Top 10 |
| 7 | 資料結構演進 | 有持久化資料結構（資料庫綱要、索引、檔案格式） | 結構變更時如何遷移、維持相容、回滾？能否零停機？ | ISO 25010 可靠性、可維護性 |
| 8 | 併發與可觀測性 | 一律 | 重複執行是否冪等？多個工作者同時執行有無競態？跨模組能否以追蹤 ID 串起？ | ISO 25010 可靠性、ASVS V16 |

* 不適用的維度於 Tech Spec 或 ADR 寫一句理由，不得留白。
* 第二節「輕重分流」Deep Track 條件「改動向量索引」改為「改動資料結構或索引」。
* 維度 1、6 的判定方法以安全框架為準，本檔只指向該框架，不重複列舉。

### 3.2 新增專案實例檔

現有 8 列「通過標準」原文整份移入專案實例檔（位置見待決事項 1），內容不刪減，只調整為依維度編號排列。Gate 1 審查時「核心問題 + 本專案通過標準」並用。

### 3.3 連動修改

| 檔案 | 變更 |
| :--- | :--- |
| `.agents/skills/doc-sync/references/adr_template.md` | 第 5 節維度名稱改為新名稱；移除維度 7 的專屬標記；加註「不適用者寫理由」 |
| `.agents/skills/feature-design/SKILL.md` | 階段 3 註明核心問題與專案實例檔並用 |
| `.agents/architect/AGENT.md` | 第 51 行引用補上專案實例檔 |
| `.agents/skills/doc-sync/SKILL.md`、`references/doc_sync_checklist.md` | 「唯一正本」敘述改為「核心問題以 arch_review_checklist 為準，本專案標準見實例檔」 |
| `.agents/PORTING.md` | 第 4 步改為：專案實例檔整份替換為新專案內容（可先留空表，隨首份規格補齊） |
| `.agents/README.md` | 目錄說明加入專案實例檔 |

## 四、衝突與重複檢查

* **與安全框架**：維度 1、6 改為指向框架，不再各自列舉安全項目，消除重複。維度 2、3、5、7、8 對應 ISO 25010 品質特性；框架第二節是「每份規格逐項宣告」，本檔是「Gate 1 架構風險視角」，用途不同，以「對應標準」欄互相引用，不重複內容。
* **「唯一正本」敘述**：feature-design、ADR 範本、doc-sync 三處稱本檔為 8 維度唯一正本；改寫後維度定義仍只在本檔，專案實例檔只放答案，正本地位不變，只需調整敘述。
* **歷史 ADR**：19 份既有 ADR 第 5 節使用舊維度名稱，維度編號不變，不回改。
* **Gate 2 檢核清單**：[review_checklist.md](../../.agents/skills/code-review/references/review_checklist.md) 有 13 處專屬標記，問題性質相同；見待決事項 5。

## 五、規模

**大改**：搬移與重組章節、新增專案實例檔（[governance.md](../../.agents/workflows/governance.md) 規模分級）。產出本規格與 `docs/qa_reports/0035-*.md`。不修改紅線，不另寫 ADR。

## 六、待決事項

| # | 問題 | 建議 | 替代方案 |
| :---: | :--- | :--- | :--- |
| 1 | 專案實例檔放哪裡 | 新增 `.agents/project/arch_review_criteria.md`；`.agents/project/` 作為日後所有專案實例檔的集中處（與 `project.toml` 並列「移植時整份替換」） | (a) 留在 `arch_review_checklist.md` 第三節並整節標記；(b) 放 `docs/architecture/` |
| 2 | 維度編號與數量 | 保留 8 個維度與編號 1–8，歷史 ADR 可對照 | 維度 1、6 併入安全框架，縮為 6 個維度（需重新編號，歷史 ADR 對照斷裂） |
| 3 | 維度 4 的範圍 | 改為「外部呼叫成本與配額」，適用於 LLM 或任何計費外部服務；Text-First、切片密度等移入專案實例檔 | 維持「Token 能效」，只在 `uses_llm` 時適用 |
| 4 | 是否以腳本檢查專案實例檔存在、核心檔無專屬標記 | 本次不改腳本；併入 [Spec-0034](./0034-asvs-chapter-coverage-check-spec.md) 一起評估 | 本次一併修改 `verify_doc_sync.py` |
| 5 | Gate 2 `review_checklist.md`（13 處專屬標記）是否一併處理 | 本次不處理，另開提案；先以本案驗證「核心問題 + 專案實例檔」模式 | 一併納入，範圍加倍 |

## 七、驗收標準（草案，G2 核准後定稿）

* **AC-1**：`arch_review_checklist.md` 不含 `<!-- 專案專屬` 標記；8 個維度皆有適用條件、要問的問題與對應標準。
* **AC-2**：原 8 列「通過標準」的每一項，都能在專案實例檔找到（逐項比對，零遺失）。
* **AC-3**：ADR 範本第 5 節維度名稱與核心檔一致；所有引用處指向正確檔案，Markdown 斷鏈測試通過。
* **AC-4**：依 PORTING.md 於暫存專案執行移植演練，替換專案實例檔後 `verify_doc_sync.py` 通過。
* **AC-5**：`verify_doc_sync.py` 通過；全套單元測試無回歸。

品質評測範圍：否（不涉及檢索、抽取或 LLM 生成）

安全評估範圍：否（只重組規範文件；無新增對外介面、跨信任邊界資料流、外部相依或敏感資料處理）
