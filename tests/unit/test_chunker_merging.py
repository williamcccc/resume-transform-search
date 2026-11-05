import unittest
from src.domain.enums import ChunkType
from src.infrastructure.chunkers.markdown_chunker import MarkdownChunker


class TestChunkerMerging(unittest.TestCase):
    """
    過短切片智慧合併 (Chunk Merging) 白箱單元測試
    驗證過短區塊自動合併、跨領域類型保護與邊界條件
    """

    def setUp(self):
        self.chunker = MarkdownChunker(min_chunk_chars=80, max_chunk_chars=1500)

    def test_merge_short_experience_chunks(self):
        # 1. Arrange: 包含多個極短同公司職稱經歷之 Markdown
        md = """# 測試工程師

## 工作經歷
### 科技公司｜專案一期
這是極短的專案說明。
### 科技公司｜專案二期
這是第二個極短的專案說明。
"""
        # 2. Act
        chunks = self.chunker.chunk_markdown(md, candidate_id="test_cand")

        # 3. Assert: 由於兩個切片過短且同為 EXPERIENCE，應合併為 1 個切片
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_type, ChunkType.EXPERIENCE)
        self.assertIn("專案一期", chunks[0].content)
        self.assertIn("專案二期", chunks[0].content)
        self.assertEqual(chunks[0].chunk_id, "test_cand:0")

    def test_prevent_cross_domain_merging_between_distinct_types(self):
        # 1. Arrange: 技能與學歷皆較短，但屬於相異領域大類 (SKILLS vs EDUCATION)
        md = """# 測試工程師

## 專業技能
- Python, Docker, Redis

## 學歷背景
### 某某大學
學士學位
"""
        # 2. Act
        chunks = self.chunker.chunk_markdown(md, candidate_id="test_cand")

        # 3. Assert: 應分別保留 SKILLS 與 EDUCATION，不可跨類型混淆
        types = [c.chunk_type for c in chunks]
        self.assertIn(ChunkType.SKILLS, types)
        self.assertIn(ChunkType.EDUCATION, types)
        self.assertEqual(len(chunks), 2)

    def test_respect_max_chunk_chars_limit(self):
        # 1. Arrange: 設置極小的 max_chunk_chars，強迫即使切片短也不能合併
        strict_chunker = MarkdownChunker(min_chunk_chars=80, max_chunk_chars=50)
        md = """# 測試工程師

## 工作經歷
### 公司 A
一段稍微有些長度的經歷文字內容。
### 公司 B
另一段也具有一定長度的經歷文字內容。
"""
        # 2. Act
        chunks = strict_chunker.chunk_markdown(md, candidate_id="test_cand")

        # 3. Assert: 由於合併後長度將超出 max_chunk_chars (50)，應保持分開
        self.assertGreaterEqual(len(chunks), 2)


if __name__ == "__main__":
    unittest.main()
