import unittest
from unittest.mock import MagicMock
from src.domain.enums import ChunkType
from src.domain.models import ResumeChunk, SearchQuery
from src.infrastructure.stores.redis_vector_store import RedisVectorStore, _escape_redis_tag


class TestRedisVectorStore(unittest.TestCase):
    def setUp(self):
        self.store = RedisVectorStore(
            redis_url="redis://localhost:6379/0",
            index_name="idx:resumes_test",
            prefix="resume:chunk:",
        )
        self.mock_client = MagicMock()
        self.store._client = self.mock_client

    def test_escape_redis_tag(self):
        self.assertEqual(_escape_redis_tag("c++"), r"c\+\+")
        self.assertEqual(_escape_redis_tag("node.js"), r"node\.js")
        self.assertEqual(_escape_redis_tag("ci/cd"), r"ci\/cd")

    def test_ensure_index_creates_when_not_exists(self):
        ft_mock = MagicMock()
        self.mock_client.ft.return_value = ft_mock
        # 模擬 info() 拋出例外 (代表索引尚未存在)
        ft_mock.info.side_effect = Exception("Unknown index name")

        self.store.ensure_index(dim=768, recreate=False)
        ft_mock.create_index.assert_called_once()

    def test_ensure_index_recreate(self):
        ft_mock = MagicMock()
        self.mock_client.ft.return_value = ft_mock
        ft_mock.info.return_value = {}

        self.store.ensure_index(dim=768, recreate=True)
        ft_mock.dropindex.assert_called_once_with(delete_documents=False)

    def test_upsert_chunks(self):
        pipe_mock = MagicMock()
        self.mock_client.pipeline.return_value = pipe_mock

        chunks = [
            ResumeChunk(
                chunk_id="candidate1:0",
                candidate_id="candidate1",
                candidate_name="王小明",
                chunk_type=ChunkType.EXPERIENCE,
                section_title="後端主管",
                content="負責微服務架構與分散式系統開發",
                skills=["python", "fastapi"],
                vector=[0.1] * 768,
            )
        ]

        count = self.store.upsert_chunks(chunks)
        self.assertEqual(count, 1)
        pipe_mock.hset.assert_called_once()
        pipe_mock.execute.assert_called_once()

    def test_search_and_score_mapping(self):
        ft_mock = MagicMock()
        self.mock_client.ft.return_value = ft_mock

        # 模擬搜尋結果文件
        mock_doc = MagicMock()
        mock_doc.candidate_id = "jerry"
        mock_doc.candidate_name = "Jerry"
        mock_doc.chunk_type = "experience"
        mock_doc.section_title = "架構師"
        mock_doc.content = "Redis 快取與高併發設計"
        mock_doc.skills = "redis,python"
        mock_doc.company = "科技公司"
        mock_doc.job_title = "資深架構師"
        mock_doc.file_path = "resume/sample_resume.md"
        mock_doc.score = "0.15"  # Cosine 距離: 0.15 => 相似度 1 - 0.15 = 0.85

        mock_res = MagicMock()
        mock_res.docs = [mock_doc]
        ft_mock.search.return_value = mock_res

        query = SearchQuery(
            query_text="分散式快取設計",
            top_k=3,
            chunk_type="experience",
            skills_filter=["redis"],
        )

        results = self.store.search(query_vector=[0.1] * 768, query=query)
        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertEqual(item.candidate_id, "jerry")
        self.assertEqual(item.score, 0.85)
        self.assertIn("redis", item.skills)

    def test_delete_by_candidate(self):
        self.mock_client.scan_iter.return_value = [b"resume:chunk:jerry:0", b"resume:chunk:jerry:1"]
        pipe_mock = MagicMock()
        self.mock_client.pipeline.return_value = pipe_mock

        deleted = self.store.delete_by_candidate("jerry")
        self.assertEqual(deleted, 2)
        self.assertEqual(pipe_mock.delete.call_count, 2)
        pipe_mock.execute.assert_called_once()

    def test_default_index_versioning(self):
        default_store = RedisVectorStore()
        self.assertEqual(default_store.index_name, "idx:resumes:v1")
        self.assertEqual(default_store.prefix, "resume:v1:chunk:")



if __name__ == "__main__":
    unittest.main()
