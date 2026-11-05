# 技術實作規格書範本 (Technical Specification Template)

> **使用說明**：依據 PRD 與 Clean Architecture / DDD 四層依賴反轉原則，制定具體的架構實作藍圖。

---

# Tech Spec: [功能名稱 / 模組名稱]

## 1. 架構分層變更影響矩陣 (Architecture Impact Matrix)
列出本次實作在各層需新增或調整的檔案清單：
| 分層 | 目錄路徑 | 檔案名稱 | 變更類型 (新增/修改) | 核心職責 |
| :--- | :--- | :--- | :---: | :--- |
| **Domain** | `src/domain/` | `models.py` | 修改/新增 | 定義純業務實體與值物件 |
| **Domain** | `src/domain/` | `interfaces.py` | 修改/新增 | 定義抽象 Protocol 契約介面 |
| **Application** | `src/application/`| `dto.py` | 修改/新增 | 傳入傳出資料傳輸物件 |
| **Application** | `src/application/`| `xxx_use_case.py` | 修改/新增 | 流程調度與業務規則執行 |
| **Infrastructure**| `src/infrastructure/` | `xxx_adapter.py` | 修改/新增 | 實作外部技術、檔案/DB 存取 |
| **Interfaces** | `src/interfaces/cli/` | `xxx_cli.py` | 修改/新增 | CLI 旗標解析與向後相容轉接 |
| **Tests** | `tests/unit/` | `test_xxx.py` | 新增 | 100% Mock 離線單元測試 |

---

## 2. 領域層契約規劃 (Domain Layer Design)
* **純潔性保證**：嚴禁 import 任何第三方外部套件。
* **Entity / Value Object**：
  ```python
  @dataclass
  class NewEntity:
      id: str
      name: str
  ```
* **Protocol Interface (介面契約)**：
  ```python
  class INewService(Protocol):
      def execute_action(self, target: NewEntity) -> bool:
          ...
  ```

---

## 3. 應用層規劃 (Application Layer Design)
* **DTO 結構**：
  ```python
  @dataclass
  class NewFeatureCommand:
      query: str
      limit: int = 10

  @dataclass
  class NewFeatureResult:
      success: bool
      items: List[dict]
  ```
* **Use Case 依賴注入關係**：
  ```python
  class NewFeatureUseCase:
      def __init__(self, service_adapter: INewService):
          # 僅依賴 Domain Protocol，嚴禁直接引用 Infrastructure
          self.service_adapter = service_adapter

      def execute(self, cmd: NewFeatureCommand) -> NewFeatureResult:
          # 調度邏輯
          ...
  ```

---

## 4. 基礎設施層規劃 (Infrastructure Layer Design)
* **外部套件引用**：明確列出使用的外部套件（如 `redis`, `google-genai` 等）。
* **資源生命週期管理 (Windows 防鎖死)**：
  * 所有檔案 I/O、PyMuPDF Document 物件與資料庫連線必須採用 `with` Context Manager。
* **例外處理與例外鏈完整度**：
  * 攔截底層例外並轉換為領域例外時，強制使用 `raise DomainException(...) from err` 保留原始 Call Stack。
* **日誌資安規範**：
  * 確保日誌中不輸出未脫敏之 PII（身分證、電話、原始全文）與 API 密鑰。

---

## 5. 表現層與向下相容性 (Presentation & Backward Compatibility)
* **CLI 指令設計**：
  ```bash
  python convert_to_md.py input.pdf --new-flag <value>
  ```
* **向下相容性驗證**：若不帶 `--new-flag`，既有轉檔行為 100% 保持原有邏輯。

---

## 6. 單元測試驗證計畫 (Test Plan)
單元測試必須位於 `tests/unit/`，且保持 100% Mock 離線獨立性：
1. **正向測試 (Happy Path)**：
   * `test_execute_success`：模擬外部依賴正常回傳，驗證結果符合預期。
2. **負面與故障注入測試 (Negative & Fault Injection)**：
   * `test_execute_timeout`：模擬外部依賴超時拋出連線異常，驗證降級或優雅報錯。
   * `test_execute_invalid_input`：傳入不合法參數，驗證引發預期的自定義領域例外。
   * `test_execute_rate_limit_429`：模擬外部 API 429 配額用罄，驗證熔斷防護。
