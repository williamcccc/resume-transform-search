# QA 實測驗收報告（QA Report 0017）

> **功能名稱**：上庫隱私掃描與文件連結防線補強
> **關聯規格書**：[Spec 0017](../specs/0017-github-publish-privacy-and-link-hardening-spec.md)
> **關聯 ADR**：[ADR-0017](../adr/0017-publish-privacy-scanner-hardening.md)
> **測試日期**：2026-11-05
> **簽核狀態**：✅ **PASS**

## 一、需求追溯矩陣

| AC | 測試案例 | 預期結果 | 實測結果 |
| :--- | :--- | :--- | :--- |
| AC-1 隱私清理 | 全專案候選文字與路徑掃描 | 本次識別的來源線索已泛化；已知規則零命中 | ✅ PASS：`audit_guardrails.py` 無 P0；錯誤輸出不含命中原文 |
| AC-2 掃描器覆蓋 | `test_github_pre_publish_hygiene.py` | 合成遮蔽文字與檔名會被攔截；通用樣本允許 | ✅ PASS |
| AC-3 連結完整 | Markdown 連結解析單元測試 | 所有本機目標存在；外部連結與程式碼範例排除 | ✅ PASS |
| AC-4 原防線保留 | `.gitignore`、`.env.example`、金鑰與路徑掃描 | 原有版控與設定檢查持續通過 | ✅ PASS |
| AC-5 品質驗證 | 單元測試、E2E、架構靜態掃描 | 全部通過 | ✅ PASS：132 項單元測試、19 項 E2E、`audit_guardrails.py` |

## 二、對抗與邊界測試

1. 於記憶體組合遮蔽 CJK 標記與合成聯絡資訊，不把完整測試值寫入原始碼。
2. 驗證個人化履歷檔名樣式會被標記，通用樣本檔名不會被標記。
3. 掃描本機候選版控文字檔及檔案路徑，忽略 `.env` 與已設定的本機資料目錄。
4. 驗證 Markdown 文件連結解析不會追蹤或開啟連結目標，也不掃描 fenced code block 範例。
5. 核對錯誤訊息僅包含相對路徑與違規類別，不包含命中原文。

## 三、執行結果

### 執行摘要

- `python -m unittest discover -s tests/unit -p "test_*.py"`：132 tests，全部通過。
- `python -m unittest discover -s tests/e2e -p "test_*.py"`：19 tests，全部通過。
- `python .agents/skills/code-review/scripts/audit_guardrails.py`：全部架構與隱私防線通過，零 P0。
- `python .agents/skills/doc-sync/scripts/verify_doc_sync.py`：通過；17 筆 ADR、13 份 Spec、13 份 QA 報告索引一致。
- 單元測試的索引技能路徑使用暫存目錄與合成 Markdown；本次未掃描本機履歷目錄。
- 測試執行環境出現既有 Starlette/httpx deprecation warning；測試結果仍為通過，與本次變更無關。

AC-1 至 AC-5 均通過；文件與 ADR 索引已同步。

## 四、Gate 2 代碼審查

- `audit_guardrails.py`：零 P0 違規。
- 隱私錯誤輸出只回報類別；若路徑本身含隱私標記，改用 `[redacted-path]`。
- DDD 邊界、設定與既有執行時行為未受變更影響；文件內部連結檢查通過。
- **Gate 2：PASS。**
