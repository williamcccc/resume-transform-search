# 8 大架構維度前審檢核清單 (Architecture Review Checklist - Gate 1)

> **使用說明**：在完成 PRD 與 Tech Spec 草案後，進入 Gate 1 審查時，必須逐項檢核以下 8 大架構維度。重大架構異動需於 `docs/adr/` 產出 ADR 草案。
>
> **定位**：閉環**通用核心**，只定義每個維度「何時適用、要問什麼、對應哪個標準」，任何專案皆可直接使用。**本專案**對各維度的具體通過標準記錄於專案實例檔 [arch_review_criteria.md](../../../project/arch_review_criteria.md)，Gate 1 審查時兩者並用。
>
> **與安全框架的分工**：維度 1、6 的判定方法以 [security_nfr_framework.md](./security_nfr_framework.md) 為準（於 feature-design 階段 2.5 先行執行），本清單只指向該框架，不重複列舉安全項目。
>
> **本清單為「8 大架構維度」定義的唯一正本**；feature-design 技能、ADR 範本與 doc-sync 技能皆引用本清單，不另行列舉。

---

## 一、8 大維度審查表

| # | 審查維度 | 適用條件 | 要問的問題 | 對應標準 |
| :---: | :--- | :--- | :--- | :--- |
| **1** | **個資與敏感資料 (Sensitive Data)** | 特徵：`handles_pii` | 敏感資料在哪裡流動、儲存、記錄？送往外部服務前如何保護？ | 安全框架第三節（STRIDE-I）、ASVS V14 |
| **2** | **容量與資源上限 (Capacity)** | 一律 | 資料量、記憶體、併發量成長時，上限在哪裡？超過時如何退化？ | ISO 25010 效能效率 |
| **3** | **解耦與非同步演進 (Async / Evolution)** | 一律 | Use Case 是否無狀態？能否移至背景任務或佇列而不改核心邏輯？ | ISO 25010 彈性、可維護性 |
| **4** | **外部呼叫成本與配額 (External Cost & Quota)** | 特徵：`uses_llm`，或依賴計費外部服務 | 重複輸入會不會重複付費？配額用罄時如何熔斷？成本上限在哪裡？ | ISO 25010 效能效率（資源使用）、OWASP Top 10 for LLM Applications「無上限消耗」 |
| **5** | **可抽換性 (Portability & Decoupling)** | 設定：`project.toml` 的 `layers.enabled = true` | 外部技術是否只透過 Domain 契約檔（`layers.domain_interfaces`）接入？更換時 Domain 與 Use Case 是否零改動？ | ISO 25010 可維護性（可替換） |
| **6** | **惡意輸入與資源上限 (Input Security)** | 特徵：`web_interface`、`api_service` 或 `processes_untrusted_files` 任一 | 輸入的大小、格式、內容能否造成資源耗盡或注入？ | 安全框架第三節（STRIDE-T/D）、ASVS V1、V2、V5；`uses_llm` 者加 OWASP Top 10 for LLM Applications |
| **7** | **資料結構演進 (Schema Evolution)** | 有持久化資料結構（資料庫綱要、索引、檔案格式） | 結構變更時如何遷移、維持相容、回滾？能否零停機？ | ISO 25010 可靠性、可維護性 |
| **8** | **併發與可觀測性 (Concurrency & Traceability)** | 一律 | 重複執行是否冪等？多個工作者同時執行有無競態？跨模組能否以追蹤 ID 串起？ | ISO 25010 可靠性、ASVS V16 |

* 特徵指 `project.toml` 的 `[security]` 特徵（見安全框架第四節）。
* **不適用**的維度於 Tech Spec 或 ADR 寫一句理由，不得留白。
* **適用**的維度依專案實例檔的通過標準判定；實例檔尚無該維度標準時，以「要問的問題」逐一作答，並於本次規格交付時補入實例檔。

---

## 二、輕重分流判定原則 (Routing Decision)

> 缺陷修復不適用本節，一律走 Bug 軌 Step 1B（`.agents/workflows/bug.md`）。

* **輕量級變更 (Fast Track)**：
  * 適用：功能開發中的小幅變更，例如單一既有參數微調、小範圍重構。
  * 流程：執行上述 8 維度的快速自檢，確認不破壞 DDD 邊界與資源管理，免寫 ADR，直接產出簡版 Tech Spec；**安全評估範圍宣告與理由須書面記錄**，不得只做心智自檢。
* **重大架構變更 (Deep Track)**：
  * 適用：新增外部 API / SDK 整合、資料庫綱要異動、新增 Use Case、引入任務隊列、改動資料結構或索引（本專案舉例見專案實例檔）。
  * 流程：強制撰寫完整 PRD、填寫 8 大維度評估表，並於 [`docs/adr/`](../../../../docs/adr/) 建立 ADR 草案，待 Gate 1 審查合格後始得動工。
