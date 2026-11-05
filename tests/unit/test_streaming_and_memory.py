import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from src.application.dto import IndexCommand, IndexResult
from src.application.index_resumes_use_case import IndexResumesUseCase
from src.domain.models import Document, ConvertedMarkdown
from src.domain.enums import DocumentType, DocumentHealth
from src.infrastructure.transformers.gemini_transformer import GeminiTransformer


class TestStreamingAndMemoryManagement(unittest.TestCase):
    """
    狀態記憶與串流讀取單元測試 (TC-01, TC-02, TC-03)
    100% 離線 Mock 隔離，涵蓋 Lazy Streaming 磁碟能效與多模態 Review 自適應 Token 節流
    """

    def setUp(self):
        self.mock_chunker = MagicMock()
        self.mock_embedding_service = MagicMock()
        self.mock_embedding_service.dim = 768
        self.mock_embedding_service.embed_texts.return_value = [[0.1] * 768]
        self.mock_vector_store = MagicMock()
        self.mock_vector_store.get_candidate_hash.return_value = None
        self.mock_vector_store.upsert_chunks.return_value = 1

        self.index_use_case = IndexResumesUseCase(
            chunker=self.mock_chunker,
            embedding_service=self.mock_embedding_service,
            vector_store=self.mock_vector_store,
        )

    def test_lazy_streaming_reads_on_demand_with_limit(self):
        """TC-01: 驗證批次處理目錄時，於讀檔前即套用 limit 截斷，不預先讀取無關檔案"""
        # 建立模擬 Path 物件清單
        mock_files = []
        for i in range(10):
            p = MagicMock(spec=Path)
            p.is_file.return_value = True
            p.stem = f"cand_{i}"
            p.read_text.return_value = f"# 履歷 {i}\n內容"
            # 支援 __str__
            p.__str__.return_value = f"C:/mock/cand_{i}.md"
            mock_files.append(p)

        mock_dir = MagicMock(spec=Path)
        mock_dir.exists.return_value = True
        mock_dir.is_dir.return_value = True
        mock_dir.rglob.return_value = mock_files

        cmd = IndexCommand(
            dir_path="C:/mock",
            limit=3,  # 僅處理 3 筆
        )

        with patch("src.application.index_resumes_use_case.Path", return_value=mock_dir):
            result: IndexResult = self.index_use_case.execute(cmd)

        self.assertEqual(result.total_files, 3)
        self.assertEqual(result.indexed_files, 3)
        # 前 3 個檔案有調用 read_text
        for i in range(3):
            mock_files[i].read_text.assert_called_once()
        # 超過 limit 的檔案完全沒有被 read_text (達成 O(1) 記憶體與 0 浪費 I/O)
        for i in range(3, 10):
            mock_files[i].read_text.assert_not_called()

    @patch("src.infrastructure.transformers.gemini_transformer.genai.Client")
    def test_vision_review_uses_chat_when_pages_within_threshold(self, mock_client_cls):
        """TC-02A: 頁數 <= vision_review_max_pages 時，使用多輪 Chat 進行對照原圖之深度審查"""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_chat = MagicMock()
        mock_client.chats.create.return_value = mock_chat

        mock_res1 = MagicMock()
        mock_res1.text = "# 初稿"
        mock_res1.candidates = [MagicMock()]
        mock_res1.candidates[0].finish_reason = "STOP"

        mock_res2 = MagicMock()
        mock_res2.text = "# 審查後完整 Markdown"
        mock_chat.send_message.side_effect = [mock_res1, mock_res2]

        transformer = GeminiTransformer(
            api_key="mock_key",
            vision_review_max_pages=3,
        )

        doc = Document(filename="doc.pdf", doc_type=DocumentType.PDF, health=DocumentHealth.OBFUSCATED)
        # 傳入 2 頁 (<= 3 頁門檻)
        pages = [b"png_page_1", b"png_page_2"]

        result = transformer.transform_vision(pages, doc, enable_review=True)

        self.assertEqual(result.content, "# 審查後完整 Markdown")
        mock_client.chats.create.assert_called_once()
        self.assertEqual(mock_chat.send_message.call_count, 2)
        mock_client.models.generate_content.assert_not_called()

    @patch("src.infrastructure.transformers.gemini_transformer.genai.Client")
    def test_vision_review_uses_adaptive_text_review_when_pages_exceed_threshold(self, mock_client_cls):
        """TC-02B: 頁數 > vision_review_max_pages 時，第 2 輪切換為文字級結構自我校驗，不重發圖片"""
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        mock_res1 = MagicMock()
        mock_res1.text = "# 初稿長篇內容"
        mock_res1.candidates = [MagicMock()]
        mock_res1.candidates[0].finish_reason = "STOP"

        mock_res2 = MagicMock()
        mock_res2.text = "# 結構修復後長篇內容"

        mock_client.models.generate_content.side_effect = [mock_res1, mock_res2]

        transformer = GeminiTransformer(
            api_key="mock_key",
            vision_review_max_pages=2,
        )

        doc = Document(filename="long_doc.pdf", doc_type=DocumentType.PDF, health=DocumentHealth.OBFUSCATED)
        # 傳入 4 頁 (> 2 頁門檻)
        pages = [b"p1", b"p2", b"p3", b"p4"]

        result = transformer.transform_vision(pages, doc, enable_review=True)

        self.assertEqual(result.content, "# 結構修復後長篇內容")
        # 驗證完全沒有建立多輪 Chat (不重覆快取發送圖片)
        mock_client.chats.create.assert_not_called()
        # 驗證兩次呼叫均為 generate_content，且第 2 輪為文字 prompt
        self.assertEqual(mock_client.models.generate_content.call_count, 2)
        call_args_2 = mock_client.models.generate_content.call_args_list[1]
        self.assertIn("【初稿內容如下】", call_args_2.kwargs["contents"])


if __name__ == "__main__":
    unittest.main()
