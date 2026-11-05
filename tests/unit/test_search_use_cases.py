import unittest
from unittest.mock import MagicMock
from pathlib import Path
import tempfile

from src.application.dto import IndexCommand
from src.application.index_resumes_use_case import IndexResumesUseCase
from src.application.search_resumes_use_case import SearchResumesUseCase
from src.domain.enums import ChunkType
from src.domain.models import ResumeChunk, SearchQuery, SearchResultItem


class TestSearchUseCases(unittest.TestCase):
    def setUp(self):
        self.mock_chunker = MagicMock()
        self.mock_embedding = MagicMock()
        self.mock_vector_store = MagicMock()

        self.index_use_case = IndexResumesUseCase(
            chunker=self.mock_chunker,
            embedding_service=self.mock_embedding,
            vector_store=self.mock_vector_store,
        )

        self.search_use_case = SearchResumesUseCase(
            embedding_service=self.mock_embedding,
            vector_store=self.mock_vector_store,
        )

    def test_index_resumes_use_case_markdown_text(self):
        sample_chunk = ResumeChunk(
            chunk_id="candidate:0",
            candidate_id="candidate",
            candidate_name="王小明",
            chunk_type=ChunkType.EXPERIENCE,
            section_title="工作經歷",
            content="後端工程師，擅長 Python",
            skills=["python"],
        )
        self.mock_chunker.chunk_markdown.return_value = [sample_chunk]
        self.mock_embedding.embed_texts.return_value = [[0.2] * 768]
        self.mock_vector_store.upsert_chunks.return_value = 1

        cmd = IndexCommand(
            markdown_text="# 王小明\n## 工作經歷\n後端工程師，擅長 Python",
            candidate_id="candidate",
            recreate_index=False,
        )

        result = self.index_use_case.execute(cmd)
        self.assertEqual(result.total_files, 1)
        self.assertEqual(result.indexed_files, 1)
        self.assertEqual(result.total_chunks, 1)
        self.assertEqual(result.errors, [])

        self.mock_vector_store.delete_by_candidate.assert_called_once_with("candidate")
        self.mock_vector_store.upsert_chunks.assert_called_once()

    def test_index_resumes_use_case_directory_with_limit(self):
        with tempfile.TemporaryDirectory() as td:
            dir_path = Path(td)
            for i in range(5):
                (dir_path / f"resume_{i}.md").write_text(f"# 候選人 {i}\n內文", encoding="utf-8")

            sample_chunk = ResumeChunk(
                chunk_id="c:0",
                candidate_id="c",
                candidate_name="C",
                chunk_type=ChunkType.PROFILE,
                section_title="個人",
                content="內文",
            )
            self.mock_chunker.chunk_markdown.return_value = [sample_chunk]
            self.mock_embedding.embed_texts.return_value = [[0.1] * 768]
            self.mock_vector_store.upsert_chunks.return_value = 1

            # 設定 limit = 2
            cmd = IndexCommand(dir_path=dir_path, limit=2)
            result = self.index_use_case.execute(cmd)

            self.assertEqual(result.total_files, 2)
            self.assertEqual(result.indexed_files, 2)
            self.assertEqual(result.total_chunks, 2)

    def test_search_resumes_use_case_execute(self):

        self.mock_embedding.embed_query.return_value = [0.1] * 768
        mock_item = SearchResultItem(
            candidate_id="jerry",
            candidate_name="Jerry",
            chunk_type="experience",
            section_title="後端職務",
            content="FastAPI 與 Redis 開發",
            score=0.92,
            skills=["fastapi", "redis"],
        )
        self.mock_vector_store.search.return_value = [mock_item]

        query = SearchQuery(query_text="尋找 FastAPI 與 Redis 人才", top_k=5)
        results = self.search_use_case.execute(query)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].candidate_name, "Jerry")
        self.mock_embedding.embed_query.assert_called_once_with("尋找 FastAPI 與 Redis 人才")

    def test_search_resumes_use_case_grouped_by_candidate(self):
        self.mock_embedding.embed_query.return_value = [0.1] * 768
        chunk1 = SearchResultItem(
            candidate_id="cand1",
            candidate_name="Alice",
            chunk_type="experience",
            section_title="工作經歷",
            content="Python 與 Docker",
            score=0.88,
            skills=["python", "docker"],
        )
        chunk2 = SearchResultItem(
            candidate_id="cand1",
            candidate_name="Alice",
            chunk_type="skills",
            section_title="專業技能",
            content="精通 FastAPI",
            score=0.95,
            skills=["fastapi"],
        )
        self.mock_vector_store.search.return_value = [chunk1, chunk2]

        query = SearchQuery(query_text="Python 後端")
        grouped = self.search_use_case.execute_grouped_by_candidate(query)

        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["candidate_id"], "cand1")
        self.assertEqual(grouped[0]["max_score"], 0.95)
        self.assertEqual(len(grouped[0]["matched_chunks"]), 2)
        self.assertEqual(grouped[0]["all_skills"], ["docker", "fastapi", "python"])


if __name__ == "__main__":
    unittest.main()
