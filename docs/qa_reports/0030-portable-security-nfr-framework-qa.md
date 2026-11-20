# QA 實測驗收報告: Spec-0030 安全與非功能需求評估通用化（閉環核心層）

> 規格：[Spec-0030](../specs/0030-portable-security-nfr-framework-spec.md)｜軌別：[governance.md](../../.agents/workflows/governance.md)（大改）

## 1. 測試環境與前置條件 (Test Environment)
* **測試日期與時間**：`2026-11-20`
* **作業系統與 Python 版本**：Windows 11 / Python 3.13
* **外部相依服務狀態**：
  * Semgrep 1.186.0、pip-audit 2.10.1，安裝於獨立虛擬環境 `.venv-tools`
  * 網路：可連線（Semgrep 規則集下載、pip-audit 漏洞資料庫查詢皆實際執行）
* **測試資料集**：單元測試以記憶體與暫存目錄建構之虛構規格、設定與工具輸出；E2E 以暫存目錄之最小假專案進行移植演練

---

## 2. 測試計畫摘要 (Test Plan Summary)
* **測試範圍 (In Scope)**：`project_config.py` 之 `[security]` 驗證；`verify_doc_sync.py` 之安全評估範圍與核心檔檢查；`security_scan.py` 之解析、基準檔、判定、離線降級與 CLI；移植演練；回溯演練；G4 一致性檢查。
* **不測範圍 (Out of Scope)**：

  | 不測項目 | 理由 | 風險與替代保障 |
  | :--- | :--- | :--- |
  | 真實離線環境下執行掃描 | 無法穩定製造斷網 | 單元測試以假 runner 注入連線錯誤（`test_offline_tools_warn_but_do_not_block`） |
  | POSIX 系統之 `.venv-tools/bin` 路徑 | 本機僅 Windows | `resolve_tool` 同時嘗試 `Scripts` 與 `bin`；移植指南註明 POSIX 路徑 |

* **進入條件**：G3 修改完成；全套單元測試通過。
* **退出條件**：見第 8 節。
* **風險與優先順序**：(1) 新檢查誤擋既有規格或文件；(2) 掃描工具與執行期相依衝突；(3) 移植後核心層被刪除或設定錯誤卻無警示。

---

## 3. 需求驗收追溯矩陣 (RTM)

| 驗收條款 | 條款說明 | 覆蓋測試案例 | 測試類型 | 狀態 |
| :--- | :--- | :--- | :---: | :---: |
| **AC-1** | 框架檔無專屬標記；刪除時 FAIL | `TC-01`、`TC-02` | Unit + E2E | **PASS** |
| **AC-2** | `[security]` 缺鍵 exit 2；`not_applicable` 缺理由 FAIL | `TC-03`、`TC-04` | Unit + E2E | **PASS** |
| **AC-3** | 範圍宣告強制、威脅表與 `NFR-*` 檢查、不回溯 | `TC-05`、`TC-06` | Unit + E2E | **PASS** |
| **AC-4** | 掃描抓到 CORS 萬用字元；基準不阻斷；到期 FAIL；離線 WARN | `TC-07`～`TC-10` | Unit + E2E | **PASS** |
| **AC-4b** | 程式碼與套件分開觸發、定期完整掃描（決議 10） | `TC-16`～`TC-18` | Unit + 實測 | **PASS** |
| **AC-5** | 回溯演練：框架推導出 Bug-0029 威脅 | `TC-11` | 演練 | **PASS** |
| **AC-6** | 移植演練：三支腳本於假專案可執行並通過 | `TC-12` | E2E | **PASS** |
| **AC-7** | 本專案既有 PASS 不變；首次掃描發現全數登錄基準檔 | `TC-13`、`TC-14` | 實測 | **PASS** |
| **AC-8** | G4 六項與全套單元測試通過 | `TC-15` | 實測 | **PASS** |

---

## 4. 測試案例執行矩陣 (Test Case Execution Matrix)

| 案例編號 | 測試案例名稱 | 分類 | 輸入條件 / 指令 | 預期結果 | 實際結果 | 判定 |
| :---: | :--- | :---: | :--- | :--- | :--- | :---: |
| **TC-01** | 框架檔無專屬標記 | Happy | 搜尋 `security_nfr_framework.md` 之 `<!-- 專案專屬` | 0 筆 | 0 筆 | **PASS** |
| **TC-02** | 核心檔刪除即 FAIL | Edge | `test_security_ac_gate::TestCoreFiles`、E2E `test_s1` | FAIL 並指名檔案 | 符合 | **PASS** |
| **TC-03** | `[security]` 缺鍵、列舉與範圍錯誤 | Edge | `test_project_config::TestSecurityConfigSchema`（7 項）、E2E `test_s2` | 指名缺鍵，exit 2 | 符合 | **PASS** |
| **TC-04** | `not_applicable` 缺理由 | Edge | 單元 `test_not_applicable_without_reason_raises`、E2E `test_s3` | exit 2 | 符合 | **PASS** |
| **TC-05** | 範圍宣告檢查 | Happy / Edge | `test_security_ac_gate::TestSecurityScopeDeclaration`（11 項） | 缺宣告、缺威脅表、缺 `NFR-*` 各自 FAIL；舊規格不回溯；與品質宣告不互相命中 | 符合 | **PASS** |
| **TC-06** | 新專案從第一份規格起強制 | E2E | E2E `test_s4` | 宣告「是」但缺威脅表與 `NFR-*` 時 FAIL | 符合 | **PASS** |
| **TC-07** | 真實 Semgrep 抓 CORS 萬用字元 | Security | E2E `test_s5`：假專案含 `allow_origins=["*"]` + `allow_credentials=True` | 回報 `wildcard-cors` | 回報為 P1（規則嚴重度 WARNING），exit 0 | **PASS** |
| **TC-08** | 基準檔抑制與到期 | Edge | `TestClassify`、`test_baselined_finding_does_not_block` | 有效期內不阻斷；到期日當天仍有效；過期恢復阻斷 | 符合 | **PASS** |
| **TC-09** | 離線降級 | Fault | 假 runner 注入 `ConnectionError` | WARN、未執行=2、exit 0 | 符合 | **PASS** |
| **TC-10** | 工具缺失與非網路錯誤 | Fault | 移除工具、注入規則語法錯誤、刪除掃描路徑與需求檔 | FAIL、exit 1 | 符合 | **PASS** |
| **TC-11** | 回溯演練 | 演練 | 以框架評估 Spec-0015 範圍（見第 5 節） | 推導出跨來源讀取威脅 | 推導出，另發現 Host 標頭威脅 | **PASS** |
| **TC-12** | 移植演練 | E2E | `test_portable_closed_loop_e2e` 13 項 | 全數通過 | `Ran 13 tests ... OK` | **PASS** |
| **TC-13** | 本專案既有檢查不變 | Regression | `verify_doc_sync.py`、`audit_guardrails.py` | 既有 PASS 不變 | 皆通過；新增兩項 PASS | **PASS** |
| **TC-14** | 首次掃描與基準檔 | Happy | `security_scan.py` | 既有發現全數登錄 | `P0=0 P1=0 基準內=11 未執行=0 錯誤=0` | **PASS** |
| **TC-15** | G4 與全套測試 | Regression | 見第 5 節 | 全數通過 | 單元 692 項 OK；E2E 21 項 OK | **PASS** |
| **TC-16** | 差異掃描選檔 | Unit | `test_security_scan::TestTriggerModes`（11 項） | 只掃 `scan_paths` 內變更檔（含未追蹤、Windows 路徑正規化、略過已刪除）；無變更兩者皆略過；只變更需求檔時只跑該份 pip-audit | 符合 | **PASS** |
| **TC-17** | 完整掃描觸發與紀錄 | Unit | 同上 | 超過 7 天、無紀錄、紀錄損壞、git 失敗、`--full` 時完整掃描；剛好 7 天仍為差異；完整掃描成功才更新日期，離線不更新；「可移除」提示只在完整掃描 | 符合 | **PASS** |
| **TC-18** | 本專案實測耗時 | 實測 | `--full`；預設；Semgrep 掃 2 個程式檔 | 差異掃描明顯快於完整掃描 | 完整約 5 分鐘並寫入紀錄；本分支差異掃描約 1 分 8 秒（僅因新增 `requirements-dev.txt` 而跑該份 pip-audit，Semgrep 略過）；只改 2 個程式檔時 Semgrep 約 18 秒 | **PASS** |

---

## 5. 實測執行日誌摘要 (Execution Logs Summary)

**單元與 E2E**

```text
python -m unittest discover -s tests/unit -p "test_*.py"   → Ran 681 tests ... OK
python -m unittest tests.e2e.test_workflow_tracks_doc_sync_e2e tests.e2e.test_portable_closed_loop_e2e → Ran 21 tests ... OK
```

* **安全工具掃描**（`python .agents/skills/code-review/scripts/security_scan.py`）：
  * 完整掃描（`--full`）：`P0=0 P1=0 基準內=11 未執行=0 錯誤=0`，約 4～5 分鐘（多數時間為 pip-audit 解析三份需求檔）。
  * 差異掃描（預設）：`P0=0 P1=0 基準內=7 未執行=0 錯誤=0`，約 1 分 8 秒；本分支只有 `requirements-dev.txt` 屬需求檔變更，Semgrep 因無程式變更而略過。

**首次掃描發現與處置**（登錄於 `.agents/security_baseline.json`）

| 來源 | 發現 | 處置 |
| :--- | :--- | :--- |
| Semgrep | `logger-credential-disclosure` @ `src/infrastructure/llm/gemini_recruitment_llm.py` | 誤報：記錄的是 LLM token 用量統計，非憑證；到期 2027-11-20 |
| pip-audit `requirements-eval.txt` | ragas、diskcache（上游無修正版本）、langchain-openai（有修正版本） | 評測專用相依，不進入執行期；到期 2027-02-20 |
| pip-audit `requirements-dev.txt` | mcp、opentelemetry-api 舊版（semgrep 鎖定之相依） | 工具隔離於 `.venv-tools`；到期 2027-02-20 |
| pip-audit `requirements.txt` | 無 | — |

**AC-5 回溯演練：以框架評估 Spec-0015（履歷搜尋 Web 介面）**

依框架第一節，Spec-0015 新增 Web 端點，範圍宣告為「是」。信任邊界與六問結果：

| 邊界／資料流 | STRIDE | 威脅 | 緩解措施 | 實際狀態 |
| :--- | :---: | :--- | :--- | :--- |
| 瀏覽器 ↔ 儀表板 API | **I** | 外站網頁跨來源讀取檢索結果與履歷全文 | 不開放跨來源許可（ASVS V3 瀏覽器來源隔離） | **即 Bug-0029**，已修正 |
| 瀏覽器 ↔ 儀表板 API | **S** | 外站以 DNS rebinding 偽造主機名稱，以「同源」身分存取 | 驗證 `Host` 標頭 | **未處理**：已另案追蹤，須依框架第五節判定嚴重度 |
| 瀏覽器 ↔ `/api/resume` | **E** | `candidate_id` 路徑遍歷讀取任意檔案 | 檔名字元白名單 | Spec-0015 已有防護 |
| 瀏覽器 ↔ `/api/search` | **D** | 大量請求觸發付費 Embedding 呼叫 | 速率限制 | 未處理；本機單人工具，屬 S3 候選 |
| 儀表板 ↔ 日誌 | **I** | 日誌寫入候選人個資 | 日誌脫敏 | 既有防線（Gate 2 Checklist） |
| 瀏覽器 ↔ 儀表板 API | **R** | 無存取紀錄可追查 | 存取日誌 | 未處理；本機單人工具，屬 S3 候選 |

結論：框架在「資訊洩漏」一問直接推導出 Bug-0029，不需事先知道 CORS 這個名詞；同時在「冒充」一問推導出 Bug-0029 審查時才偶然發現的 Host 標頭問題。

---

## 6. 品質評測結果 (Quality Evaluation)
不適用（品質評測範圍：否）。

---

## 7. 失敗分析與根因定位 (Failure Analysis & RCA)

| # | 現象 | 根因 | 處置 |
| :---: | :--- | :--- | :--- |
| 1 | 以 `pip install -r requirements-dev.txt` 安裝至主環境後，`pip check` 報 fastapi 需要 `opentelemetry-api>=1.44`，實際被降為 1.37.0 | Semgrep 鎖定 `opentelemetry-api~=1.37`，與執行期相依衝突 | 主環境移除 semgrep、pip-audit 與其 OpenTelemetry 附屬套件，重裝 `opentelemetry-api>=1.44` 與 `requirements.txt`；`pip check` 無衝突、fastapi 搭配 otel 1.45.2 匯入正常、全套單元測試通過。工具改裝於獨立虛擬環境 `.venv-tools`，新增設定鍵 `tools_venv`（規格「實作後修訂」第 1 項） |
| 2 | pip-audit 讀取需求檔時 `UnicodeDecodeError: 'cp950'` | Windows 預設編碼讀取含中文註解之需求檔 | `security_scan.py` 以 `PYTHONUTF8=1` 執行工具 |
| 3 | pip-audit 對同一漏洞重複列出 | 工具輸出中同一漏洞出現兩次 | 新增 `dedupe()`，同指紋只保留一筆 |
| 4 | 隱私掃描將基準檔指紋判為身分證號 | 某筆雜湊恰以「一個字母＋1 或 2＋8 位數字」開頭，符合證號樣式 | 指紋改為 `fp` 前綴，基準檔轉換格式（規格「實作後修訂」第 2 項） |
| 5 | `test_workflow_tracks_doc_sync_e2e::test_e3` 失敗 | 測試寫死「缺陷報告 1 個」；Bug-0029 合併後倉庫已有 1 份，演練新增後為 2 份。屬 Bug-0029（PR #23）時未執行此 E2E 而遺留的既有失敗，與本案無關 | 改為依實際檔案數判斷 |

---

## 8. QA 驗收結論 (QA Sign-Off)
* **驗收判定**：**【通過 (PASSED)】**
* **放行標準**：
  1. RTM 零 `FAIL`、零 `NOT COVERED` ✅
  2. 邊界與異常對抗實測全數通過（離線、工具缺失、設定錯誤、基準檔錯誤） ✅
  3. Windows 資源生命週期：檔案讀寫皆以 `with` 管理（`audit_guardrails.py` 通過） ✅
  4. 品質評測：不適用
* **放行說明**：**准予進入 G5 審查與程式部分的 Gate 2。**

---

## 9. Gate 2 代碼審查紀錄 (Code Review Record)

### 9.1 審查輪次

| 輪次 | 日期 | 審查範圍 (commit / diff) | `audit_guardrails.py` | `security_scan.py` | P0 | P1 | P2 | 判定 |
| :---: | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | 2026-11-20 | `main..docs/spec-0030-security-nfr-framework`（程式部分：`project_config.py`、`verify_doc_sync.py`、`security_scan.py` 與測試） | Exit 0 | Exit 0 | 0 | 0 | 1 | **PASS** |
| 2 | 2026-11-20 | `01cd612..` 工作目錄（決議 10：觸發方式、設定鍵 `diff_base`、`full_scan_max_age_days` 與測試） | Exit 0 | Exit 0 | 0 | 0 | 0 | **PASS** |

### 9.2 發現項目

| ID | 等級 | 檢核項 | 檔案:行號 | 描述 | 處置 |
| :--- | :---: | :--- | :--- | :--- | :--- |
| R1-01 | P2 | 效率 | `security_scan.py` `run_pip_audit` | 三份需求檔逐一由 pip-audit 解析，全程約 4 分鐘 | 第 2 輪已處理：使用者核准決議 10，改為分開觸發，平常只改程式時約 18 秒 |
| R2-01 | 確認 | 差異掃描盲點 | `security_scan.py` `decide_mode` | 差異掃描不會發現既有套件事後公布之漏洞，也不會以新規則重掃未變更檔案 | 已由「超過 7 天自動完整掃描」涵蓋；QA 第 2 節不測範圍未受影響 |

**G5 規範審查**（規則矛盾、重複、用詞一致）：

| ID | 類型 | 描述 | 處置 |
| :--- | :--- | :--- | :--- |
| G5-01 | 矛盾 | Gate 2 放行條件在 7 處只寫 `audit_guardrails.py`（AGENTS.md 雙門禁表、CLAUDE.md 分級表、gatekeeper 角色、auto-fix、feature.md、hotfix.md、QA 報告範本） | 已全數補上 `security_scan.py` |
| G5-02 | 重複 | 「S1 不得延後」與 P1 處置方式在 feature-design、PRD 範本、code-review 技能重複陳述 | 收斂為引用框架第五節與 Checklist「安全工具掃描」項；AGENTS.md 與角色檔保留摘要並附連結 |
| G5-03 | 用詞 | 檢查「安全評估範圍」「非功能驗收條件」 | 全倉一致（19 處、7 處），無混用 |

### 9.3 需求—斷言追溯抽查

| 驗收條款 | 對應測試與斷言 | 預期值來源 | 判定 |
| :--- | :--- | :--- | :---: |
| AC-3 | `test_security_ac_gate::test_in_scope_without_nfr_fails` 斷言 FAIL 訊息含「缺少 NFR-*」且不含「缺少 STRIDE 威脅表」 | 規格 3.3 | **OK** |
| AC-4 | `test_security_scan::test_active_baseline_suppresses_and_expired_blocks` 斷言到期日當天仍屬基準內、前一日到期者為 P0 | 規格 3.4（到期即恢復阻斷） | **OK** |
| AC-6 | E2E `test_s5` 以真實 Semgrep 斷言輸出含 `wildcard-cors` 與 `[P1]` | Bug-0029 之程式碼型態 | **OK** |

### 9.4 雙門禁審查結論

### 🛡️ Code Review 雙門禁審查結果
* **架構靜態掃描**： 通過 (`audit_guardrails.py` 零 P0 違規)
* **安全工具掃描**： 通過 (`security_scan.py` 零 P0；首次發現 11 項皆已處置並登錄基準檔；完整與差異兩種模式皆實測；未執行項目：無)
* **DDD 依賴邊界**： 不適用 (未修改 `src/`)
* **資源釋放與鎖定防禦**： 通過 (檔案讀寫皆使用 `with`)
* **Twelve-Factor 配置治理**： 通過 (工具、路徑、規則集、等級、門檻皆由 `project.toml` 注入；零寫死金鑰與絕對路徑)
* **邊界例外與例外鏈**： 通過 (`BaselineError` 以 `from err` 保留原因；工具錯誤分網路與非網路處理)
* **日誌安全合規**： 通過 (輸出僅含規則、路徑與漏洞編號)
* **測試隔離與負面覆蓋**： 通過 (單元測試以假 runner 注入，零網路；負面案例涵蓋離線、工具缺失、設定錯誤、基準檔錯誤、到期)
* **需求—斷言追溯**： 通過 (9/9 條 AC（含 AC-4b）具備直接驗證預期結果之斷言或實測；抽查 AC-3、AC-4、AC-6 預期值來源獨立)
* **Git 版控衛生與零個資防線**： 通過 (`.venv-tools/` 已列入 `.gitignore`；測試資料全為虛構；隱私掃描通過)
