# ADR-0005: 全面安全性防禦、可觀測性演進與代碼治理規範升級

## 1. 狀態
**已採納 (Accepted)** - 2026-11-03

---

## 2. 背景與問題陳述 (Context & Problem Statement)
隨著本專案在履歷解析、兩階段自我修復（FastProbe + Gemini LLM）以及 Redis HNSW 向量檢索模組的健全建立，系統正逐步從單機 CLI 邁向具備潛在高併發 Worker（如 Celery / FastAPI）及企業級資料管線的生產就緒架構。

在實際生產與開放上傳環境中，履歷解析與 LLM/向量系統面臨多項隱形威脅與架構演進挑戰：
1. **惡意輸入與資源耗盡風險**：惡意攻擊者或畸形檔案可能夾帶 Zip Bomb（如超高壓縮比 Word 檔案）、巨型 PDF（上千頁無效內容）導致解析程序 OOM 崩潰；或在履歷中注入隱蔽惡意提示詞（Prompt Injection），企圖操控 LLM 評審員與結構化抽取結果。
2. **向量索引生命週期演進難題**：若未來更換 Embedding 模型（如升級維度或新模型），或更換 HNSW 距離演算法，如何在不中斷線上檢索的情況下完成平滑過渡（Zero-downtime Index Migration）？
3. **Windows 平台資源鎖定 (File Locking)**：檔案讀寫或串流若未嚴格納入 Context Manager (`with`) 生命週期管理，Windows 系統會引發 `PermissionError: [WinError 32]`，導致暫存檔無法清理、自動補樁失敗。
4. **例外鏈斷裂與錯誤吞噬**：捕獲例外後自訂領域例外若未保留原始 Call Stack（缺少 `raise ... from e`），會大幅增加追查線上問題的成本。
5. **日誌資安合規 (PII & Secret Leaks)**：若在除錯日誌中直接格式化印出履歷原始全文或授權標頭，會嚴重違反個資與資安規範。

因此，本決策旨在將「架構審查 (Gate 1)」擴充為 **8 大維度**，並於「代碼審查 (Gate 2)」全面強化資源防禦、例外鏈追蹤、日誌零洩漏與故障注入測試。

---

## 3. 評估選項 (Options Evaluated)

### 選項 A：僅於既有 Checklist 增加文字提醒，不改動工具與 ADR
* **優點**：改動成本最小。
* **缺點**：欠缺制度化約束，後續維護者或不同 AI 代理人極易忽視 Zip Bomb、Prompt Injection 與例外鏈問題，且無法被自動化工具攔截。

### 選項 B：全面升級雙門禁治理體系，擴充 AST 掃描工具並落地 ADR (採納)
* **優點**：
  1. **Gate 1 架構前審全面升級**：將評估維度從 5 項擴充至 8 項，納入「惡意防禦與配額硬上限」、「向量索引演進遷移」、「分散式併發與全鏈路可觀測性」。
  2. **Gate 2 代碼審查工具化**：升級 `audit_guardrails.py`，以 AST 語法樹自動掃描「非 with 管理的 open() 資源」、「例外吞噬」與「例外鏈斷裂」。
  3. **規範一致性**：同步更新 `AGENTS.md`、`GEMINI.md`、`CLAUDE.md` 與 `review_checklist.md`，杜絕任何代碼邊界漏洞。
* **缺點**：初期需編寫 AST 檢查邏輯與完善檢核清單，但可一勞永逸確保系統生產環境穩定性。

---

## 4. 架構決策 (Decision Outcome)

採納 **選項 B**。具體決策如下：

1. **架構前審 Gate 1 正式擴充為 8 大維度**：
   * 原有 5 大維度：`PII 個資隱私`、`容量與極限`、`非同步與演進`、`成本與熔斷`、`可抽換性`。
   * **新增第 6 維度 [惡意輸入與配額硬上限]**：強制設定檔案大小上限（25MB）、解壓縮膨脹比上限（10x）、最大解析頁數（30 頁），並實施 Prompt 上下文隔離（Context Fencing）。
   * **新增第 7 維度 [向量索引演進與藍綠遷移]**：Redis 向量索引命名必須附帶版本識別（如 `idx:resumes:v1`），更換模型時採藍綠雙索引切換。
   * **新增第 8 維度 [分散式併發與全鏈路可觀測性]**：多 worker 任務必須保持原子性；請求與轉檔過程必須傳遞 `Trace ID`，日誌結構化輸出。

2. **代碼審查 Gate 2 實施強制性防禦檢驗**：
   * **[P0] 資源生命週期管理**：所有檔案 I/O、Document 物件與串流強制使用 `with` Context Manager，根除 Windows File Lock 隱患。
   * **[P0] 日誌零個資外洩**：日誌嚴禁直接打印原始履歷明文、未脫敏身分證號及 API Key。
   * **[P1] 例外鏈完整度**：重新拋出領域例外時，強制使用 `raise DomainException(...) from err`。
   * **[P1] 負面故障注入測試**：新模組必須在 `tests/unit/` 提供至少一組異常/故障模擬單元測試（如網路超時、檔案損毀、配額耗盡）。

---

## 5. 8 大架構審查維度評估 (Comprehensive 8-Dimension Review Analysis)

1. **[個資隱私 (PII)]**：
   * 履歷文字傳送至外部 LLM 前必須具備遮蔽能力，Redis 向量庫避免存放明文身分證號。
   * 磁碟日誌輸出全面遵循零洩漏原則。
2. **[容量與極限 (Capacity & Limits)]**：
   * 單一候選人履歷限制在合理文字與切片大小內，Redis HNSW 記憶體預算持續監控。
3. **[非同步與演進 (Async / Evolution)]**：
   * Use Case 具備無狀態特性，支援未來向 Celery/FastAPI 無痛封裝。
4. **[成本與熔斷 (Cost & Circuit Breaker)]**：
   * Gemini API 具備用罄熔斷防禦與 429 速率平滑處理，不盲目重試。
5. **[可抽換性 (Portability & Decoupling)]**：
   * 核心業務完全依賴 `src/domain/interfaces.py`，向量庫由 Redis 替換為 Qdrant/Milvus 時 Domain 零改動。
6. **[惡意輸入與配額硬上限 (Input Security & Bomb Defense)]**：
   * 解析器在讀取檔案前檢核檔案大小與結構，防止 Zip Bomb 記憶體擴散。
   * LLM Prompt 使用 `<resume_content>` XML 標籤進行隔離，防止 Prompt Injection 劫持 System 指令。
7. **[向量索引演進與藍綠遷移 (Index Evolution & Migration)]**：
   * 索引建立腳本支援版本後綴與 Alias 機制，避免破壞性重建。
8. **[分散式併發與全鏈路可觀測性 (Concurrency & Observability)]**：
   * 轉檔與向量操作維持以候選人為單位的冪等操作，避免競爭危害。
   * 透過 Trace ID 追蹤單一文件在 FastProbe、Gemini 與 Redis 間的流轉狀態。
