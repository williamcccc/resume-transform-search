# 缺陷報告範本 (Bug Report Template)

> **使用說明**：Bug 軌 Step 1B 由 bug-triage 技能（`.agents/skills/bug-triage/SKILL.md`）產出，存於 `docs/bugs/XXXX-<slug>.md`，編號與 `docs/specs/` 共用流水號，並登錄於 `docs/README.md` 缺陷修正索引。重現資料一律使用合成內容。

---

# 缺陷報告：[缺陷摘要]

> **編號**：XXXX｜**嚴重度**：S1 / S2 / S3｜**狀態**：處理中 / 已止血，待補件 / 已結案 / 已升級 → Spec-XXXX

## 1. 受理資訊
* **現象**：使用者看到什麼（錯誤訊息、錯誤輸出、崩潰）。
* **環境**：Windows 11 / Python 3.13；Redis（Docker `localhost:6379`）；其他相依服務狀態。
* **觸發條件**：在什麼輸入或操作下發生。
* **回報來源**：使用者回報 / QA 發現 / 日誌監控。
* **嚴重度判定理由**：

## 2. 重現步驟
1. 準備輸入：`sample_resume.md`（合成內容）
2. 執行：
   ```bash
   python convert_to_md.py <sample_path>
   ```
3. **預期結果**：
4. **實際結果**：

**紅燈回歸測試**：`tests/unit/test_xxx.py::TestXxx::test_yyy`

```text
[修正前執行結果摘要]
FAIL: test_yyy (...)
AssertionError: ...
```

## 3. 根因分析
* **真因**：
* **所屬 DDD 層**：domain / application / infrastructure / interfaces
* **位置**：`src/...py:行號`
* **逃逸分析**：測試缺口 / 斷言過弱 / 規格缺口 / 防線缺口 —— 說明既有測試或防線為何沒抓到。
* **防線改善建議**（屬防線缺口時填寫，另案處理）：
* **教訓歸屬**：通用 / 專案專屬 —— 失效層：範圍宣告 / 威脅建模 / 標準對照 / 工具規則 / 規範缺漏（判定方式見 `.agents/skills/feature-design/references/security_nfr_framework.md` 第七節）；通用者記錄回寫之規範變更編號：

## 4. 修正範圍與升級判斷

| 預計修改檔案 | 修改性質 |
| :--- | :--- |
| `src/...py` | |

**升級條件檢查**：

| # | 條件 | 是否觸發 |
| :---: | :--- | :---: |
| 1 | 修改 Domain 契約檔（`project.toml` 的 `layers.domain_interfaces`）的 Protocol 或 DTO 欄位 | 否 |
| 2 | 修改資料模型或 Redis 索引結構 <!-- 專案專屬 --> | 否 |
| 3 | 新增 `AppConfig` 環境變數或 CLI 參數 | 否 |
| 4 | 「正確行為」在現有規格中未定義或定義矛盾 | 否 |
| 5 | 修正範圍跨越 3 個以上 DDD 層 | 否 |

**簡化 Gate 1 簽核**（architect）：
- [ ] 修正只恢復既有規格行為，不新增行為
- [ ] 影響面已列出：
- [ ] 無介面破壞，既有 CLI 與 API 相容

## 5. 缺陷驗收條件 (BC)
* **BC-1**：紅燈回歸測試 `test_yyy` 在 `test:` commit 失敗，在 `fix:` commit 通過。
* **BC-2**：
* **BC-3**：全套單元測試無回歸。

品質評測範圍：否

## 6. 結案
* **`test:` commit**：
* **`fix:` commit**：
* **PR**：
* **QA 報告**：`docs/qa_reports/XXXX-<slug>-qa.md`
* **結案日期**：
* **升級紀錄**（若有）：已升級 → Spec-XXXX，原因：符合升級條件第 N 條
