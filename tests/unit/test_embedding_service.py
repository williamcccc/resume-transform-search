import unittest
from unittest.mock import MagicMock, patch
from src.infrastructure.embeddings.gemini_embedding import GeminiEmbeddingService


class TestGeminiEmbeddingService(unittest.TestCase):
    def setUp(self):
        self.service = GeminiEmbeddingService(
            api_key="fake-test-key",
            model_name="gemini-embedding-001",
            dim=768,
            batch_size=2,
        )

    def test_embed_texts_empty(self):
        result = self.service.embed_texts([])
        self.assertEqual(result, [])

    @patch("google.genai.Client")
    def test_embed_texts_batching_and_response(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        self.service._client = mock_client

        # 模擬 API 回傳結構
        def make_mock_response(num_items):
            mock_resp = MagicMock()
            mock_resp.embeddings = [
                MagicMock(values=[0.1] * 768) for _ in range(num_items)
            ]
            return mock_resp

        # 傳入 3 個文本，batch_size=2，應觸發 2 次 API 呼叫 (第 1 次 2 筆，第 2 次 1 筆)
        mock_client.models.embed_content.side_effect = [
            make_mock_response(2),
            make_mock_response(1),
        ]

        texts = ["項目 1", "項目 2", "項目 3"]
        vectors = self.service.embed_texts(texts)

        self.assertEqual(len(vectors), 3)
        self.assertEqual(len(vectors[0]), 768)
        self.assertEqual(mock_client.models.embed_content.call_count, 2)

    @patch("google.genai.Client")
    def test_embed_query(self, mock_client_cls):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        self.service._client = mock_client

        mock_resp = MagicMock()
        mock_resp.embeddings = [MagicMock(values=[0.5] * 768)]
        mock_client.models.embed_content.return_value = mock_resp

        vec = self.service.embed_query("找尋具備 Redis 經驗的工程師")
        self.assertEqual(len(vec), 768)
        self.assertEqual(vec[0], 0.5)


if __name__ == "__main__":
    unittest.main()
