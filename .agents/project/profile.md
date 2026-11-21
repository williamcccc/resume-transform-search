# 專案概況 (Project Profile)

> **定位**：**專案實例檔**。記錄本專案的基本事實，供通用核心的技能、角色與流程檔引用（核心檔寫「見專案概況」之處即指本檔）。常駐載入的本專案紅線與執行環境不在本檔，位於 [AGENTS.md](../../AGENTS.md)「本專案紅線」區塊。
> **移植**：搬到其他專案時整份替換為新專案內容，見 [PORTING.md](../PORTING.md)。
> **來源**：[Spec-0037](../../docs/specs/0037-project-profile-tests-and-red-lines-spec.md)。

---

## 1. 入口與介面

* **CLI 入口**（根目錄）：`convert_to_md.py`（主要入口，指令與引數須向下相容，見 AGENTS.md 紅線 2）、`index_to_redis.py`、`search_resumes.py`、`web_dashboard.py`。
* **參數舉例**：`--review`、`--index-to-redis`、`--output-dir`、`--skills`。新增或變更參數須登載於 `REQUIREMENTS.md`。
* **Web 介面**：`web_dashboard.py` 提供轉檔儀表板、履歷檢索與招募助理對話之 Web 頁面與 HTTP API，僅綁定本機。

## 2. 主要流程

* **轉檔**：履歷檔（PDF、DOCX、DOC）轉為結構化 Markdown，經品管閥檢核。
* **檢索**：Markdown 履歷切片、向量化入庫，供語意檢索與招募助理使用。

任一主要流程全面失敗，缺陷嚴重度判定為 S1（見 bug-triage 技能嚴重度表）。

## 3. 持久化結構

* **Redis 向量索引**：索引名稱與鍵前綴具版本識別（如 `idx:resumes:v1`）；以 Hash 儲存切片。
* **檔案產出**：Markdown 產出目錄與隔離區（Quarantine）。

修改上述結構屬缺陷修正之升級條件 2（見 [bug.md](../workflows/bug.md)）。

## 4. 敏感資料類型

* 求職者姓名、聯絡資訊（電話、Email、地址）、身分證字號。
* 履歷全文與真實履歷檔名、源自真實履歷案例之特定企業名稱。
* 敏感目錄：見 `project.toml` 的 `privacy.sensitive_dirs`。
* 虛構範例一律使用 `王小明`、`sample_resume.md` 等通用名稱。

## 5. 測試環境

* **單元測試**：禁止真實網路、Gemini API 與 Redis；禁止讀取本機 `data/`、`resume/` 實體檔案，夾具於記憶體建構。
* **E2E 實測**：`tests/e2e/` 執行真實 CLI；以 `tempfile` 隔離磁碟，Redis 使用 DB 15 或獨立鍵前綴隔離。
* **對抗情境重點**：高併發競態、Redis 切片寫入冪等性、網路中斷重連、0-byte 壞檔、Zip Bomb、履歷內容提示詞注入。
