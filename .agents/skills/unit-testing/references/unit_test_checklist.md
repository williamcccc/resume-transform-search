# 單元測試品質檢核清單 (Unit Test Quality Checklist)

在宣告 Step 3 完成前，必須逐項對照本清單進行自我審查：

---

### 一、獨立性與離線純潔性 (Isolation)
- [ ] **無真實網路呼叫**：是否完全不發起真實 HTTP/HTTPS 請求？
- [ ] **無真實外部資料庫**：是否完全未連接真實 Redis、PostgreSQL 或向量資料庫？
- [ ] **無付費 API 消耗**：是否完全 Mock 了 Gemini LLM 與 Embedding 服務？
- [ ] **無執行順序相依 (Order Independence)**：測試方法之間是否完全無狀態殘留？任意順序執行皆能獨立通過？

---

### 二、結構與命名語意 (Structure & Naming)
- [ ] **AAA 結構清楚**：每個測試函式內部是否明確分為 Arrange、Act、Assert 三大區塊？
- [ ] **語意化命名**：測試函式名稱是否清楚表達 `test_<功能>_<情境>_<預期結果>`？
- [ ] **測試檔案命名**：測試檔名是否符合 `test_*.py` 格式以利自動探索？

---

### 三、負面情境與邊界覆蓋 (Negative Cases & Boundaries)
- [ ] **負面情境覆蓋**：是否包含至少 2 組負面情境（超時、資料毀損、非法空值等）？
- [ ] **例外斷言精確度**：使用 `assertRaises` 時是否斷言了特定的領域例外類別，而非籠統的 `Exception`？
- [ ] **例外鏈檢核**：重新拋出的自定義例外是否斷言了 `ctx.exception.__cause__` 不為空（保留原始呼叫堆疊）？
- [ ] **邊界值測試**：是否涵蓋了 0-byte 檔案、空字串、超出長度上限等邊界？

---

### 四、執行效能與清潔度 (Performance & Cleanup)
- [ ] **毫秒級快速執行**：全套單元測試是否可在數秒內快速執行完畢？
- [ ] **檔案 Handle 清潔**：若使用 `tempfile`，是否確保已退出 Context Manager，無 Windows 檔案殘留鎖死？
- [ ] **執行指令通過**：
  ```bash
  python -m unittest discover -s tests/unit -p "test_*.py"
  ```
  輸出為 `Ran X tests in Y.YYYs ... OK`。
