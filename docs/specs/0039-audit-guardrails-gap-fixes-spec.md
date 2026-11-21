# 提案與規格書：audit_guardrails.py 守門缺口修正（Bug-0031、Bug-0032、Bug-0033）

> **狀態**：提案（G1，待核准；尚未實作）｜**類型**：規範變更（大改：修改驗證腳本），內含三項缺陷修正｜**流程**：[governance.md](../../.agents/workflows/governance.md)，缺陷部分依 [bug.md](../../.agents/workflows/bug.md) 的先紅後綠規則｜**影響範圍**：[audit_guardrails.py](../../.agents/skills/code-review/scripts/audit_guardrails.py)、上庫衛生測試、`.agents/tests/`、相關說明文字，不涉及 `src/`

## 一、動機

三份已登錄的缺陷報告都是 `audit_guardrails.py` 的防線缺口，修正只改 `.agents/**` 與測試，依 AGENTS.md 分流表屬規範變更；三份報告均建議併入同一份提案：

| 缺陷 | 嚴重度 | 摘要 | 根因 |
| :---: | :---: | :--- | :--- |
| [Bug-0031](../bugs/0031-layer-check-skips-nested-modules.md) | S3 | Domain／Application 分層檢查只掃第一層，子資料夾模組漏檢 | `glob("*.py")` 不遞迴 |
| [Bug-0032](../bugs/0032-env-sync-check-narrow-detection.md) | S3 | 環境變數同步檢查只認設定模組內的 `os.environ.get()` | 單一正規式比對單一檔案 |
| [Bug-0033](../bugs/0033-env-sync-check-skips-missing-files.md) | S3 | 設定模組或 `.env.example` 不存在時檢查靜默跳過 | `exists()` 條件包住檢查（fail-open） |

三者根因不同，依 bug.md 各自保留 `test:`（紅燈）→ `fix:`（綠燈）commit，放在同一個 PR（bug.md 例外條款：多個獨立 bug 同 PR 時依序 `test A → fix A → test B → fix B`，並於 PR 說明理由）。

## 二、修正內容

### 2.1 Bug-0031：分層檢查遞迴

* `check_domain_purity()`、`check_application_dip()` 改用 `rglob("*.py")`（排除 `__pycache__`）。
* 違規訊息由檔名改印專案相對路徑，避免不同子資料夾的同名檔案無法區分。
* 本專案 `src/domain/`、`src/application/` 目前無子資料夾，預期零新增違規。

### 2.2 Bug-0032：環境變數偵測改用 AST 並掃描全部原始碼

* 以 AST 收集 `layers.src` 下**所有** `.py` 檔讀取的環境變數名稱，涵蓋 `os.environ.get("X")`、`os.getenv("X")`、`os.environ["X"]`（含 `from os import environ, getenv` 之寫法）。
* 每個以**字串常值**讀取的變數都必須列於 `.env.example`，否則 P0（與現行規則同等級）。以變數或迴圈動態取名者（如 `langsmith_tracing.py` 以常數清單讀取）無法靜態判定，不列入檢查，於說明中註明。
* 上庫衛生測試改為呼叫同一個偵測函式，不再重複正規式。
* **不強制「只有設定模組能讀環境變數」**（見待決事項 1）：AGENTS.md 紅線 6 要求的是「連線字串統一由設定模組注入」，並未禁止其他模組讀取環境變數；目前另有 3 個檔案讀取（`gemini_embedding.py`、`transformers/utils.py`、`langsmith_tracing.py`），其變數皆已列於 `.env.example`。改為修正說明文字：`project.toml` 註解與 PORTING 的「唯一可讀環境變數的模組」改為「設定模組（集中讀取環境變數）」。

### 2.3 Bug-0033：設定指向的檔案或目錄不存在時回報 P0

| 情況 | 修正前 | 修正後 |
| :--- | :--- | :--- |
| `config.module` 指向的檔案不存在 | 同步檢查靜默跳過 | P0，訊息指出鍵名與路徑 |
| `config.env_example` 指向的檔案不存在 | 同步檢查靜默跳過 | P0，訊息指出鍵名與路徑 |
| `layers.src` 指向的目錄不存在 | 資源、例外、硬編碼、提示詞、評測套件檢查全部靜默跳過 | P0，訊息指出鍵名與路徑 |
| `layers.enabled = true` 而 `layers.domain`／`layers.application` 目錄不存在 | 分層檢查靜默跳過 | P0，訊息指出鍵名與路徑 |

`.gitignore` 缺檔現已回報 P0，不變。採 P0 而非結束碼 2：設定檔本身格式正確，問題在專案檔案與設定不符，屬審查違規（見待決事項 3）。

## 三、缺陷流程對應

| 步驟 | 內容 |
| :--- | :--- |
| Step 1B 第 3 階段（紅燈測試） | 各 bug 一個 `test:` commit：Bug-0031 子資料夾違規模組；Bug-0032 情境 B（`os.getenv`）、C（`os.environ[...]`）、D（其他模組讀取未列變數）；Bug-0033 情境 E、F 與 `layers.src` 不存在。測試於暫存目錄建構，不讀取 `data/`、`resume/` |
| 第 4 階段（RCA） | 確認三份報告初判根因；Bug-0033 同類疑點（`SRC_DIR`、`DOMAIN_DIR`、`APPLICATION_DIR` 不存在時靜默跳過）一併納入 |
| 第 6 階段（簡化 Gate 1） | 隨本提案 G2 核准一併簽核：只恢復或補全既有規則之防線，Bug-0032 之「正確行為」由待決事項 1 定義 |
| Step 7 | 三份缺陷報告第 6 節填寫 commit、PR、QA 與結案日期，索引狀態改為「已結案」 |

## 四、修改檔案

| 檔案 | 變更 |
| :--- | :--- |
| `.agents/skills/code-review/scripts/audit_guardrails.py` | 2.1、2.2、2.3 |
| `tests/unit/test_github_pre_publish_hygiene.py` | 環境變數同步改呼叫腳本函式 |
| `.agents/tests/test_guardrail_gaps.py`（新增） | 三個 bug 的紅燈回歸測試 |
| `.agents/project.toml`、`.agents/PORTING.md` | 「唯一可讀環境變數的模組」用詞修正 |
| `docs/bugs/0031～0033-*.md`、`docs/README.md` | 結案紀錄與索引狀態 |

## 五、衝突與重複檢查

* **與紅線 6**：本案不放寬紅線 6；只修正說明文字中超出紅線原意的「唯一」字樣（見待決事項 1）。
* **與 Spec-0034 結構檢查**：`verify_doc_sync.py` 不受影響。
* **與上庫衛生測試**：原本與腳本重複的正規式改為共用函式，消除兩處規則。
* **嚴重等級**：Bug-0033 新增之 P0 在本專案皆不觸發（相關檔案與目錄皆存在）。

## 六、規模

**大改**：修改驗證腳本。產出本規格與 `docs/qa_reports/0039-*.md`；程式部分走 Gate 2 程式檢查，加查先紅後綠與逃逸分析。不修改紅線，不另寫 ADR。

## 七、待決事項

| # | 問題 | 建議 | 替代方案 |
| :---: | :--- | :--- | :--- |
| 1 | Bug-0032：設定模組以外讀取環境變數，是否判違規 | 不判違規；只要求所有以字串常值讀取的變數列於 `.env.example`，並修正「唯一可讀」用詞 | 判 P0 並重構 3 個 `src/` 檔案改由設定模組注入（需另走 bug／feature 軌改 `src/`） |
| 2 | 動態取名的環境變數讀取 | 不列入檢查，於說明註明限制 | 判 P1 警告（`langsmith_tracing.py` 會長期出現警告） |
| 3 | Bug-0033 之等級 | P0 審查違規 | 比照設定錯誤以結束碼 2 中止 |
| 4 | Bug-0033 同類疑點（`layers.src`／`domain`／`application` 目錄不存在） | 一併納入 | 只修 `config.module`／`env_example`，其餘另開缺陷 |
| 5 | 交付方式 | 一份規格、一個 PR，依序 `test 0031 → fix 0031 → test 0032 → fix 0032 → test 0033 → fix 0033` | 三個 PR |

## 八、驗收標準（草案，G2 核准後定稿）

* **AC-1（Bug-0031）**：Domain、Application 任意深度子資料夾內的違規模組回報 P0，訊息含專案相對路徑。
* **AC-2（Bug-0032）**：任一 `src/` 檔案以 `os.environ.get`、`os.getenv`、`os.environ[...]` 讀取而未列於 `.env.example` 的變數回報 P0；上庫衛生測試與腳本共用偵測函式。
* **AC-3（Bug-0033）**：`config.module`、`config.env_example`、`layers.src`、啟用分層時之 `layers.domain`／`layers.application` 任一不存在時回報 P0，訊息指出鍵名與路徑。
* **AC-4**：每個 bug 的回歸測試在其 `test:` commit 失敗、在 `fix:` commit 通過。
* **AC-5**：本專案執行 `audit_guardrails.py` 零新增違規；全套單元測試、`.agents/tests` 與移植演練無回歸。

品質評測範圍：否（不涉及檢索、抽取或 LLM 生成）

安全評估範圍：否（只強化既有靜態檢查腳本之偵測範圍；無新增對外介面、跨信任邊界資料流、外部相依或敏感資料處理）
