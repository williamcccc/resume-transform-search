import logging
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.infrastructure.config import AppConfig
from src.infrastructure.logging import setup_logging, get_logger, close_logging
from src.infrastructure.transformers.utils import retry_call
from src.infrastructure.stores.redis_vector_store import RedisVectorStore
from src.domain.models import SearchQuery, ResumeChunk
from src.domain.enums import ChunkType


class TestLoggingAndLatency(unittest.TestCase):
    """
    系統技術日誌與 API 請求耗時日誌白箱單元測試
    100% 離線 Mock 隔離，涵蓋 TC-LOG-01 ~ TC-LOG-04
    """

    def setUp(self):
        # 建立獨立的測試用 Logger 避免干擾全域
        self.test_logger = logging.getLogger("test_logger")

    def test_setup_logging_file_creation_and_formatting(self):
        """TC-LOG-01: 驗證 setup_logging 成功建立滾動日誌檔案並格式化輸出"""
        with tempfile.TemporaryDirectory() as td:
            try:
                log_file = Path(td) / "test_app.log"
                cfg = AppConfig(
                    gemini_api_key="mock_key",
                    gemini_model="gemini-3.8-flash",
                    gemini_review=False,
                    log_level="DEBUG",
                    log_file=str(log_file),
                    log_max_bytes=1024 * 1024,
                    log_backup_count=2,
                )

                logger = setup_logging(config=cfg, force_reinit=True)
                self.assertIsNotNone(logger)

                # 寫入一筆測試訊息
                logger.info("測試日誌訊息 - 業務啟動")

                # 驗證日誌檔已建立且內容包含時間戳與等級
                self.assertTrue(log_file.exists())
                content = log_file.read_text(encoding="utf-8")
                self.assertIn("[INFO]", content)
                self.assertIn("測試日誌訊息 - 業務啟動", content)
                self.assertIn("系統技術日誌初始化完成", content)
            finally:
                close_logging()

    def test_retry_call_latency_logging_on_success(self):
        """TC-LOG-02A: 驗證 retry_call 成功時精確記錄耗時秒數與 op_name"""
        mock_func = MagicMock(return_value="api_success_data")

        with self.assertLogs("src.infrastructure.transformers.utils", level="INFO") as cm:
            result = retry_call(mock_func, max_retries=2, op_name="test_gemini_call")

        self.assertEqual(result, "api_success_data")
        self.assertTrue(any("API 請求成功 [test_gemini_call]" in msg for msg in cm.output))
        self.assertTrue(any("當次耗時" in msg and "秒" in msg for msg in cm.output))

    def test_retry_call_latency_logging_on_transient_retry(self):
        """TC-LOG-02B: 驗證暫時性錯誤 (503 / 429 RPM) 觸發退避重試並記錄 warning 日誌"""
        mock_func = MagicMock()
        # 第一次拋出 503 暫時性錯誤，第二次成功
        mock_func.side_effect = [RuntimeError("503 Service Unavailable"), "recovered_data"]

        with self.assertLogs("src.infrastructure.transformers.utils", level="WARNING") as cm:
            result = retry_call(
                mock_func,
                max_retries=3,
                initial_delay=0.01,
                op_name="test_transient_call",
            )

        self.assertEqual(result, "recovered_data")
        self.assertTrue(any("API 請求暫時性異常 [test_transient_call]" in msg for msg in cm.output))
        self.assertTrue(any("將於" in msg and "次重試" in msg for msg in cm.output))

    def test_retry_call_latency_logging_on_daily_quota_exhausted(self):
        """TC-LOG-02C: 驗證每日配額耗盡時 (requests per day) 不重試，並記錄 error 日誌"""
        mock_func = MagicMock()
        mock_func.side_effect = RuntimeError("429 ResourceExhausted: requests per day quota exceeded")

        with self.assertLogs("src.infrastructure.transformers.utils", level="ERROR") as cm:
            with self.assertRaises(RuntimeError):
                retry_call(mock_func, max_retries=3, op_name="test_quota_call")

        self.assertEqual(mock_func.call_count, 1)  # 不做無謂重試
        self.assertTrue(any("API 請求每日配額用罄 [test_quota_call]" in msg for msg in cm.output))

    def test_redis_store_latency_logging(self):
        """TC-LOG-03: 驗證 RedisVectorStore 向量寫入與搜尋操作記錄耗時日誌"""
        store = RedisVectorStore()
        mock_client = MagicMock()
        store._client = mock_client

        mock_pipe = MagicMock()
        mock_client.pipeline.return_value = mock_pipe

        chunk = ResumeChunk(
            chunk_id="chunk_1",
            candidate_id="cand_1",
            candidate_name="王小明",
            chunk_type=ChunkType.EXPERIENCE,
            section_title="工作經歷",
            content="5 年 Python 後端開發經驗",
            vector=[0.1] * 768,
        )

        # 1. 驗證 upsert_chunks 記錄耗時日誌
        with self.assertLogs("src.infrastructure.stores.redis_vector_store", level="INFO") as cm_upsert:
            count = store.upsert_chunks([chunk])

        self.assertEqual(count, 1)
        self.assertTrue(any("Redis 向量切片批次寫入成功" in msg and "耗時:" in msg for msg in cm_upsert.output))

        # 2. 驗證 search 記錄檢索耗時日誌
        mock_ft = MagicMock()
        mock_search_res = MagicMock()
        mock_search_res.total = 1
        mock_doc = MagicMock()
        mock_doc.score = "0.2"
        mock_doc.candidate_id = "cand_1"
        mock_doc.candidate_name = "王小明"
        mock_doc.chunk_type = "experience"
        mock_doc.section_title = "工作經歷"
        mock_doc.company = "Example Organization"
        mock_doc.job_title = "工程師"
        mock_doc.skills = "python,redis"
        mock_doc.content = "經歷內容"
        mock_doc.file_path = "resume.md"
        mock_search_res.docs = [mock_doc]
        mock_ft.search.return_value = mock_search_res
        mock_client.ft.return_value = mock_ft

        query = SearchQuery(query_text="尋找 Python 工程師", top_k=3)
        with self.assertLogs("src.infrastructure.stores.redis_vector_store", level="INFO") as cm_search:
            res_items = store.search([0.1] * 768, query)

        self.assertEqual(len(res_items), 1)
        self.assertTrue(any("Redis KNN 向量檢索成功" in msg and "檢索耗時:" in msg for msg in cm_search.output))


if __name__ == "__main__":
    unittest.main()
