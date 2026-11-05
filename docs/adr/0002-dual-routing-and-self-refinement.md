# ADR-0002: 文件轉檔智慧自動判別管線與兩階段自我審核修復

## 1. 狀態
已採納 (Accepted)

## 2. 背景與問題陳述 (Context & Problem Statement)
企業內部履歷來源極為複雜，包含：
1. 104 人力銀行之防爬混淆字型 PDF（文字層為亂碼）。
2. 紙本掃描檔（無文字層）。
3. 排版良好之健康 PDF。
4. Word 檔案（`.docx` 與舊版 `.doc`），且經常伴隨破圖或關聯殘留（Dangling Media Corruption）。

若統一採用傳統 OCR，速度極慢且遺漏多欄結構；若統一採用純文字抽取，遇到 104 亂碼時產出廢料。此外，LLM 視覺轉換可能偶爾遭遇版權背誦安全阻斷（`FinishReason.RECITATION`）或幻覺。

## 3. 評估選項 (Options Evaluated)
* **選項 A：人工指定模式**：使用者必須透過命令列參數手動指定 `--ocr` 或 `--fast`。缺點：大量批次處理時無法自動化。
* **選項 B：全交由單次 Gemini Vision 處理**：成本高昂，且健康純文字 PDF 也耗費視覺配額，且長文可能產生細微遺漏。
* **選項 C：智慧探測（Fast Probe）＋ 雙模分流 ＋ 兩階段自我審核修復（推薦）**：
  * 先以 `PdfHealthProbe` 在毫秒內檢查字數與字型編碼（Unicode 替代字元與混淆頻率）。
  * 異常者自動走 Gemini Vision；健康文字檔走純文字提取。
  * 啟用 `--review` 時，提供 Chat 兩階段自動校正（對照原圖 5 大維度修正），並對 RECITATION 進行文字平滑降級。

## 4. 架構決策 (Decision Outcome)
**採納選項 C**。
* 在 `DocxReader` 內建記憶體 In-Memory 破圖自動補樁機制，絕不篡改原始檔案。
* 在 `GeminiTransformer` 建立 RECITATION 偵測與平滑降級 Fallback 鏈，保證高可用性。

## 5. 5 大架構審查維度評估 (Architecture Review Analysis)
1. **個資隱私 (PII)**：兩階段審核自動比對姓名、Email 與電話，確保轉檔不遺漏關鍵聯絡方式。
2. **容量與極限 (Capacity)**：自動探測分流大幅降低了不必要的視覺渲染（將不需要圖片的檔案直接導向文字流），節省 80% 記憶體。
3. **非同步與演進 (Async / Evolution)**：轉檔流程封裝於 `ConvertDocumentUseCase`，易於包裝成背景工作。
4. **成本與熔斷 (Cost & Circuit Breaker)**：文字健康檔不耗費 Vision Tokens，大幅壓低 API 成本。遇到每日配額用罄自動停止並記錄。
5. **可抽換性 (Portability & Decoupling)**：離線狀態下自動平滑降級至本機 RapidOCR，具備 100% 離線可用性。
