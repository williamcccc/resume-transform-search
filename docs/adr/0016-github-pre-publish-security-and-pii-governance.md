# ADR-0016: GitHub 上庫前全方位安全脫敏、個資 (PII) 清零與跨平台路徑治理

## 1. 狀態
**已採納 (Accepted)** — 2026-11

> **隱私掃描更正**：本 ADR 的初始零命中結果不代表全面清零；掃描防線與歷史 QA 結論已由 [ADR-0017](./0017-publish-privacy-scanner-hardening.md) 及 [QA Report 0017](../qa_reports/0017-github-publish-privacy-hardening-qa-report.md) 更正。

## 2. 背景與問題陳述 (Context & Problem Statement)
在將專案推送至 GitHub 公開或團隊版控前，除了確保業務原始碼不寫死 API 金鑰外，針對履歷處理系統特有的高敏感特性，必須防範：
1. 開發與實測期間殘留於 API 路由說明、單元測試、CLI Help 或規格書中的**真實求職者姓名與履歷檔名**。
2. 提示詞模板（`prompts/*.md`）中引用自真實履歷案例的**特定企業名稱**。
3. 測試腳本與文檔中寫死的**本機工作區絕對路徑**，造成跨平台 CI/CD 失敗或 GitHub 網頁點擊斷鏈。
4. `.gitignore` 與 `.env.example` 對衍生目錄（如 `resume/`、`markdown_out/`、`dump.rdb`）與新增配置項（`WEB_ENGINE`）的邊界缺漏。

## 3. 評估選項 (Options Evaluated)
* **選項 A：僅依賴 `.gitignore` 忽略 `data/` 與 `.env`**
  * *優點*：零額外改動成本。
  * *缺點*：無法清除已散落於文檔、測試及 API 說明中的真實人名與本機路徑，上 GitHub 後仍有個資外洩與跨機器測試失敗風險。
* **選項 B：全專案個資清零、Prompt 泛化、文檔連結相對路徑化，並建立 SHA-256 指紋單元測試防線（選定方案）**
  * *優點*：降低已知個資與本機絕對路徑殘留風險；單元測試改為純記憶體構造（`BytesIO`），不依賴本機檔案；透過 `test_github_pre_publish_hygiene.py` 永久自動化守護。
  * *缺點*：需一次性重構測試與批次更新文檔連結。

## 4. 架構決策 (Decision Outcome)
採納 **選項 B**：
1. **個資與來源資訊脫敏**：代碼、測試、Prompt 與文檔採用通用範例，並由本機掃描防線檢查已知識別線索。掃描結果須由人工覆核，不能視為所有個資格式均已清零的證明。
2. **單元測試純記憶體自給自足**：`test_docx_reader.py` 透過 `zipfile` 在記憶體構造破損 `.rels` 關聯驗證自動補樁，徹底脫離外部樣本檔依賴。
3. **跨平台相對路徑統一**：全專案程式碼、測試與 Markdown 連結移除本機磁碟路徑，100% 採用 `Path(__file__).resolve()` 或專案相對路徑。
4. **自動化版控衛生測試 (`test_github_pre_publish_hygiene.py`)**：以 SHA-256 雜湊前綴（不儲存個資明文）與正則表達式，持續檢驗 `.gitignore`、`.env.example` 同步性與零絕對路徑/零機密洩漏。

## 5. 8 大架構審查維度評估 (Architecture Review Analysis)
1. **個資隱私 (PII)**：原始指紋掃描曾回報零命中，但後續審核發現其未涵蓋遮蔽字串與個人化檔名；修正決策與新驗收方式記錄於 ADR-0017。
2. **容量與極限 (Capacity)**：無影響。
3. **非同步與演進 (Async / Evolution)**：無影響。
4. **成本與熔斷 (Cost & Circuit Breaker)**：全套 128 項單元測試 100% 離線執行，0 API Token 消耗。
5. **可抽換性 (Portability & Decoupling)**：可在任意路徑與作業系統 Clone 並通過全套測試。
6. **惡意輸入與配額硬上限 (Input Security)**：`.gitignore` 嚴密阻擋 `resume/`、`markdown_out/` 與 Redis RDB/AOF 檔案誤入版控。
7. **向量索引演進與藍綠遷移 (Index Evolution)**：無影響。
8. **分散式併發與全鏈路可觀測性 (Observability)**：由 `test_github_pre_publish_hygiene.py`、`audit_guardrails.py` 與 `verify_doc_sync.py` 形成三重自動化守門防線。
