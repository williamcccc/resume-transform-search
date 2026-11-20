# Mock 隔離模式與範本 (Mocking Patterns)

本參考文件提供常見外部依賴的標準 Mock 範本，確保單元測試具備 100% 離線純潔性。範例中的介面、類別與模組名稱均為示意，套用時換成專案實際名稱（Domain 契約檔位置見 `project.toml` 的 `layers.domain_interfaces`）：

---

## 1. Mock 領域 Protocol 契約 (Domain Protocols)

當測試 Application Use Case 時，絕不實例化真實的基礎設施類別，而是透過依賴注入傳入遵循 Protocol 的 Mock：

```python
import unittest
from unittest.mock import Mock
from app.domain.interfaces import IDataStore, IEmbeddingService  # 示意：換成專案的 Domain 契約檔

class TestSearchUseCase(unittest.TestCase):
    def setUp(self):
        # 1. Arrange: 建立 Protocol Mock 實例
        self.mock_store = Mock(spec=IDataStore)
        self.mock_embedding_service = Mock(spec=IEmbeddingService)

        # 設定預設行為（向量維度取自設定，勿在測試中另寫一份）
        self.mock_embedding_service.get_embedding.return_value = [0.1] * EMBEDDING_DIM
        self.mock_store.search.return_value = []

        # 注入至 Use Case
        self.use_case = SearchUseCase(
            store=self.mock_store,
            embedding_service=self.mock_embedding_service
        )
```

---

## 2. 模擬外部 API 429 配額用罄與故障注入 (Fault Injection)

驗證 Use Case 在外部 API 拋出異常時是否能平滑降級或保留完整例外鏈：

```python
from unittest.mock import Mock

class RateLimitError(Exception):
    """示意：換成外部 SDK 實際拋出的限流例外類別"""

def test_api_quota_exhausted_fallback(self):
    # Arrange: 注入 429 異常
    mock_client = Mock()
    mock_client.generate.side_effect = RateLimitError("429 Quota Exceeded")

    # Act: 執行評估
    service = JudgeService(client=mock_client)
    report = service.evaluate("sample content")

    # Assert: 驗證未崩潰，且回退為降級模式
    self.assertTrue(report.is_degraded)
    self.assertIn("429", report.details)
```

---

## 3. 驗證自定義例外鏈保留 (Exception Chaining)

驗證包裝為 DomainError 時是否使用 `raise ... from err` 保留了原始例外：

```python
def test_exception_chaining_preserves_cause(self):
    mock_parser = Mock()
    mock_parser.parse.side_effect = ValueError("Corrupted input stream")

    use_case = ImportDocumentUseCase(parser=mock_parser)

    with self.assertRaises(DocumentParsingError) as ctx:
        use_case.execute(file_path="dummy.bin")

    # 驗證例外鏈未斷裂
    self.assertIsNotNone(ctx.exception.__cause__)
    self.assertIsInstance(ctx.exception.__cause__, ValueError)
```

---

## 4. 暫存檔案隔離 (Temporary Filesystem)

避免在單元測試中直接寫入工作目錄：

```python
import tempfile
from pathlib import Path

def test_file_output_isolation(self):
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir) / "sample_output.md"
        # 進行檔案寫入與斷言
        tmp_path.write_text("# Sample", encoding="utf-8")
        self.assertTrue(tmp_path.exists())
    # 離開 with 後自動清理，不留殘留控制代碼
```
