# 根因分析與故障診斷手冊 (RCA Guide)

本手冊彙整常見核心異常的根因定位路徑（5-Whys）與診斷技巧：

---

## 一、Windows 檔案鎖死與權限問題 (PermissionError: [WinError 32])

### 症狀 (Symptom)
在 Windows 環境下執行檔案覆寫、重命名或刪除暫存檔時，拋出：
`PermissionError: [WinError 32] 程序無法存取檔案，因為檔案正由另一個程序使用。`

### 根因分析 (RCA Path)
1. **為什麼 Windows 會鎖定檔案？** 因為某個檔案 Handle 仍處於開啟狀態未被 close。
2. **為什麼 Handle 未被 close？**
   - 使用了 `open(f)` 或文件解析函式庫的開檔函式但未置於 `with` Context Manager 中。
   - 例外發生在中途，流程直接跳出導致外層 `close()` 未被執行。
   - 物件被全域變數或垃圾回收器延遲持有。
3. **標準修復方針**：
   - 強制將所有檔案與 Document 串流收斂至 `with ... as doc:` 區塊內。
   - 若使用 `tempfile.TemporaryDirectory`，在離開 context 前確保所有子檔案控制代碼已釋放。

---

## 二、字元編碼與特殊路徑異常 (UnicodeDecodeError / Windows Path)

### 症狀 (Symptom)
讀取輸入檔案或寫出產出檔案時拋出 `UnicodeDecodeError: 'cp950' / 'gbk' codec can't decode...`。

### 根因分析 (RCA Path)
1. **為什麼會使用 cp950？** 在 Windows 系統上，Python 的 `open()` 預設編碼依賴系統語系設定（預設為 ANSI/cp950）。
2. **標準修復方針**：
   - 所有文字讀寫強制指定 `encoding="utf-8"`。
   - 所有路徑操作強制使用 `pathlib.Path` 物件，避免手動字串拼接造成的反斜線轉義錯誤。

---

## 三、資料庫索引或資料表不存在 (例：Redis `ResponseError: no such index`)

### 症狀 (Symptom)
執行查詢或寫入時，資料庫回報索引（或資料表）不存在，或資料遺失。

### 根因分析 (RCA Path)
1. **為什麼找不到索引？** 
   - 資料庫服務剛啟動或剛重建，尚未建立索引或執行綱要遷移。
   - 或者查詢傳入了錯誤的索引名稱（如測試環境傳入了開發環境的索引名）。
2. **標準修復方針**：
   - 在資料存取類別初始化或初次查詢前，加入「索引存在性檢查」與「自動冪等建構（Lazy Index Creation）」。
   - 查詢條件中的使用者輸入須依資料庫語法跳脫保留字元。

---

## 四、外部 API 429 配額用罄與中斷 (ResourceExhausted / RateLimit)

### 症狀 (Symptom)
大量批次處理或呼叫 LLM 評審時，拋出 `429 Too Many Requests` 或 `ResourceExhausted`。

### 根因分析 (RCA Path)
1. **為什麼會觸發 429？** 請求頻率超過了外部 API 方案的 RPM/TPM 硬限制。
2. **標準修復方針**：
   - 實作平滑降級與重試機制（Exponential Backoff with Jitter）。
   - 當 LLM Judge 遭遇 429 時，平滑回退至「純確定性規則驗證（Rule-Based Fallback）」，並在報告中明確標註 `degraded: True`，保證主流程不崩潰中斷。
