# 修復反模式紅線清單 (Fix Anti-Patterns Checklist)

在實施 Step 6 自主修復時，AI 必須嚴格自律，**以下反模式列為專案禁止之禁忌行為**：

---

### ❌ 反模式 1：削弱或刪除斷言 (Assertion Erasure / Weakening)
* **危險行為**：測試報 `AssertionError: 85 != 100` 時，直接將測試斷言改為 `self.assertTrue(result >= 0)`，或將失敗的斷言行註解掉。
* **正確做法**：測試斷言代表 PRD 的驗收標準（AC）。測試報錯代表**業務實作未達標準**，必須修復生產代碼使輸出達到預期標準，絕不能「削足適履」。

---

### ❌ 反模式 2：盲吞例外 (Exception Swallowing)
* **危險行為**：
  ```python
  try:
      do_something()
  except Exception:
      pass  # 為了讓流程不中斷而盲目吞掉例外
  ```
* **正確做法**：明確捕獲預期的特定例外類型（如 `redis.ConnectionError`, `FileNotFoundError`），並記錄日誌或優雅降級；若無法處理，應重新拋出領域自定義例外並保留原始堆疊 `raise CustomError(...) from err`。

---

### ❌ 反模式 3：在測試中使用真實 Sleep 掩蓋競態條件 (Flaky Sleep Patching)
* **危險行為**：因為多執行緒或非同步處理未就緒，在測試或程式碼中隨意加入 `time.sleep(2)`。
* **正確做法**：使用確定性機制（如 `threading.Event`, `Future`, 或顯式輪詢超時閥門），或透過 mock 確定順序。

---

### ❌ 反模式 4：單點修復卻引發連鎖回歸 (Regression Blindness)
* **危險行為**：僅單獨運行出錯的單一測試方法，看到 OK 就認為修復完成，忽略了修復改動影響到其他模組。
* **正確做法**：任何程式碼更動後，**強制執行全套單元測試**（`python -m unittest discover -s tests/unit -p "test_*.py"`），確保全數測試皆為綠燈。

---

### ❌ 反模式 5：破壞 DDD 分層依賴反轉
* **危險行為**：為求快速修復，直接在 `src/domain/` 引入第三方 SDK（如 `fitz`, `google-genai`），或在 Use Case 中直接實例化基礎設施實作類別。
* **正確做法**：維持 Domain 純潔性，透過 Protocol 介面進行依賴注入（DIP）。

---

### ❌ 反模式 6：無止盡死迴圈修復 (Infinite Fix Loops / Token Burn)
* **危險行為**：面對架構衝突或根本性語意矛盾時，反覆盲目修改、無休止重新執行測試，單一問題嘗試修復 5 輪以上，消耗巨額 Token。
* **正確做法**：嚴格實施「三振熔斷機制（最多嘗試 3 輪）」。第 3 次修復若仍未綠燈，立即停止修改，出具完整的根因診斷與方案選項，交由人類架構師決策。
