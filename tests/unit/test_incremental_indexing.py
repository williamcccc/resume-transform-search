import hashlib
import unittest
from unittest.mock import MagicMock
from src.application.dto import IndexCommand, IndexResult
from src.application.index_resumes_use_case import IndexResumesUseCase
from src.domain.enums import ChunkType
from src.domain.models import ResumeChunk


class TestIncrementalIndexing(unittest.TestCase):
    """
    向量索引增量比對 (Content-Hash Cache) 白箱單元測試
    100% 離線 Mock 隔離，涵蓋 Happy Path、Force 更新與故障注入
    """

    def setUp(self):
        self.mock_chunker = MagicMock()
        self.mock_embedding_service = MagicMock()
        self.mock_vector_store = MagicMock()

        self.use_case = IndexResumesUseCase(
            chunker=self.mock_chunker,
            embedding_service=self.mock_embedding_service,
            vector_store=self.mock_vector_store,
        )

    def test_incremental_skip_when_hash_matches(self):
        # 1. Arrange
        md_text = "# 候選人\n## 經歷\n資深工程師"
        cand_id = "test_cand"
        expected_hash = hashlib.sha256(md_text.encode("utf-8")).hexdigest()

        # 模擬 Redis 中已存在相同的 Hash 指紋
        self.mock_vector_store.get_candidate_hash.return_value = expected_hash

        cmd = IndexCommand(
            markdown_text=md_text,
            candidate_id=cand_id,
            force=False,
            recreate_index=False,
        )

        # 2. Act
        result: IndexResult = self.use_case.execute(cmd)

        # 3. Assert
        self.assertEqual(result.total_files, 1)
        self.assertEqual(result.indexed_files, 0)
        self.assertEqual(result.skipped_files, 1)
        self.assertEqual(result.total_chunks, 0)
        # 驗證 Embedding API 完全沒有被調用 (零 Token 消耗)
        self.mock_embedding_service.embed_texts.assert_not_called()
        self.mock_vector_store.upsert_chunks.assert_not_called()

    def test_incremental_index_when_content_changes(self):
        # 1. Arrange
        md_text = "# 候選人\n## 經歷\n更新後的新經歷"
        cand_id = "test_cand"
        current_hash = hashlib.sha256(md_text.encode("utf-8")).hexdigest()

        # 模擬 Redis 中儲存的是舊的 Hash
        self.mock_vector_store.get_candidate_hash.return_value = "old_outdated_hash_123"

        chunk = ResumeChunk(
            chunk_id=f"{cand_id}:0",
            candidate_id=cand_id,
            candidate_name="候選人",
            chunk_type=ChunkType.EXPERIENCE,
            section_title="經歷",
            content="更新後的新經歷",
        )
        self.mock_chunker.chunk_markdown.return_value = [chunk]
        self.mock_embedding_service.embed_texts.return_value = [[0.1] * 768]
        self.mock_vector_store.upsert_chunks.return_value = 1

        cmd = IndexCommand(markdown_text=md_text, candidate_id=cand_id, force=False)

        # 2. Act
        result: IndexResult = self.use_case.execute(cmd)

        # 3. Assert
        self.assertEqual(result.total_files, 1)
        self.assertEqual(result.indexed_files, 1)
        self.assertEqual(result.skipped_files, 0)
        self.assertEqual(result.total_chunks, 1)
        # 驗證成功調用 Embedding API 並將新 Hash 寫入 Redis
        self.mock_embedding_service.embed_texts.assert_called_once()
        self.mock_vector_store.set_candidate_hash.assert_called_once_with(cand_id, current_hash)

    def test_force_flag_bypasses_hash_check(self):
        # 1. Arrange: 即使 Hash 完全一致，若指定 force=True 仍強制重新向量化
        md_text = "# 候選人\n## 經歷\n經歷文字"
        cand_id = "test_cand"
        matching_hash = hashlib.sha256(md_text.encode("utf-8")).hexdigest()
        self.mock_vector_store.get_candidate_hash.return_value = matching_hash

        chunk = ResumeChunk(
            chunk_id=f"{cand_id}:0",
            candidate_id=cand_id,
            candidate_name="候選人",
            chunk_type=ChunkType.EXPERIENCE,
            section_title="經歷",
            content="經歷文字",
        )
        self.mock_chunker.chunk_markdown.return_value = [chunk]
        self.mock_embedding_service.embed_texts.return_value = [[0.2] * 768]
        self.mock_vector_store.upsert_chunks.return_value = 1

        cmd = IndexCommand(markdown_text=md_text, candidate_id=cand_id, force=True)

        # 2. Act
        result: IndexResult = self.use_case.execute(cmd)

        # 3. Assert
        self.assertEqual(result.indexed_files, 1)
        self.assertEqual(result.skipped_files, 0)
        self.mock_embedding_service.embed_texts.assert_called_once()

    def test_embedding_api_failure_handling(self):
        # 1. Arrange: 故障注入 - 模擬 Embedding API 拋出連線異常
        md_text = "# 候選人\n## 經歷\n內容"
        cand_id = "test_cand"
        self.mock_vector_store.get_candidate_hash.return_value = None

        chunk = ResumeChunk(
            chunk_id=f"{cand_id}:0",
            candidate_id=cand_id,
            candidate_name="候選人",
            chunk_type=ChunkType.EXPERIENCE,
            section_title="經歷",
            content="內容",
        )
        self.mock_chunker.chunk_markdown.return_value = [chunk]
        self.mock_embedding_service.embed_texts.side_effect = RuntimeError("Embedding 服務連線失敗 503")

        cmd = IndexCommand(markdown_text=md_text, candidate_id=cand_id)

        # 2. Act
        result: IndexResult = self.use_case.execute(cmd)

        # 3. Assert
        self.assertEqual(result.indexed_files, 0)
        self.assertEqual(len(result.errors), 1)
        self.assertIn("Embedding 服務連線失敗 503", result.errors[0])


if __name__ == "__main__":
    unittest.main()
