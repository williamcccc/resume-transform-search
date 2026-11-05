"""
Unit tests for Resume Web Search capabilities.
Covers:
1. Experience years parser logic and boundary cases
2. SearchResumesUseCase execute_web_search with min_years filtering and grouping
3. Path traversal defense and safe markdown loading in get_resume_markdown
100% offline isolated unit testing using AAA pattern.
"""

import unittest
from unittest.mock import MagicMock
from pathlib import Path
import tempfile
import shutil

from src.domain.models import SearchResultItem
from src.application.dto import WebSearchRequestDTO
from src.application.search_resumes_use_case import SearchResumesUseCase
from src.infrastructure.parsers.experience_parser import parse_experience_years, RegexExperienceParser


class TestExperienceParser(unittest.TestCase):
    """白箱測試年資正則解析器 (ExperienceParser)"""

    def test_parse_range_format(self):
        # Arrange
        text = "- **工作經歷**：4~5年工作經歷\n- **學歷**：大學"
        # Act
        years, raw_str = parse_experience_years(text)
        # Assert
        self.assertEqual(years, 4.0)
        self.assertIn("4~5年工作經歷", raw_str)

    def test_parse_plus_format(self):
        # Arrange
        text = "擁有 5 年以上 Java 後端微服務開發經驗"
        # Act
        years, raw_str = parse_experience_years(text)
        # Assert
        self.assertEqual(years, 5.0)

    def test_parse_years_and_months(self):
        # Arrange
        text = "總工作年資：3年6個月"
        # Act
        years, raw_str = parse_experience_years(text)
        # Assert
        self.assertEqual(years, 3.5)

    def test_parse_single_year(self):
        # Arrange
        text = "累積 2 年相關經歷"
        # Act
        years, raw_str = parse_experience_years(text)
        # Assert
        self.assertEqual(years, 2.0)

    def test_parse_no_experience_info(self):
        # Arrange
        text = "剛畢業於資訊工程學系，具備各項開源專案經驗"
        # Act
        years, raw_str = parse_experience_years(text)
        # Assert
        self.assertIsNone(years)
        self.assertIsNone(raw_str)

    def test_parse_empty_string(self):
        # Arrange & Act & Assert
        y1, r1 = parse_experience_years("")
        self.assertIsNone(y1)
        self.assertIsNone(r1)

        y2, r2 = parse_experience_years(None)
        self.assertIsNone(y2)
        self.assertIsNone(r2)


class TestSearchResumesUseCaseWebSearch(unittest.TestCase):
    """白箱測試 SearchResumesUseCase.execute_web_search 與安全履歷載入"""

    def setUp(self):
        self.mock_embedding_service = MagicMock()
        self.mock_embedding_service.embed_query.return_value = [0.1] * 768

        self.mock_vector_store = MagicMock()

        # 建立臨時履歷目錄供測試 get_resume_markdown
        self.temp_dir = tempfile.mkdtemp()
        self.resume_dir = Path(self.temp_dir) / "markdown_out"
        self.resume_dir.mkdir(parents=True, exist_ok=True)

        self.use_case = SearchResumesUseCase(
            embedding_service=self.mock_embedding_service,
            vector_store=self.mock_vector_store,
            markdown_base_dir=self.resume_dir,
            experience_parser=RegexExperienceParser(),
        )

        # 寫入合格測試履歷
        (self.resume_dir / "candidate_001.md").write_text(
            "# 張三\n- **工作經歷**：5年以上\n熟悉 Python 與 Redis",
            encoding="utf-8"
        )
        (self.resume_dir / "candidate_002.md").write_text(
            "# 李四\n- **工作經歷**：1~2年工作經歷\n熟悉前端開發",
            encoding="utf-8"
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_execute_web_search_grouped_with_min_years(self):
        # Arrange: 模擬向量搜尋回傳 3 筆切片 (2 位候選人)
        results = [
            SearchResultItem(
                candidate_id="candidate_001",
                candidate_name="張三",
                chunk_type="experience",
                section_title="工作經歷",
                content="- **工作經歷**：5年以上 工作經歷\n領導後端團隊",
                skills=["Python", "Redis"],
                score=0.88,
            ),
            SearchResultItem(
                candidate_id="candidate_001",
                candidate_name="張三",
                chunk_type="skills",
                section_title="專業技能",
                content="精通 FastAPI, Docker 與分散式架構",
                skills=["FastAPI", "Docker"],
                score=0.82,
            ),
            SearchResultItem(
                candidate_id="candidate_002",
                candidate_name="李四",
                chunk_type="experience",
                section_title="工作經歷",
                content="- **工作經歷**：1~2年工作經歷\n初階工程師",
                skills=["JavaScript", "React"],
                score=0.91,
            ),
        ]
        self.mock_vector_store.search.return_value = results

        # Act 1: 搜尋 min_years=3 (李四僅 1 年應被排除)
        req_dto = WebSearchRequestDTO(
            query_text="尋找資深後端工程師",
            min_years=3.0,
            group_by_candidate=True,
        )
        res_dto = self.use_case.execute_web_search(req_dto)

        # Assert 1
        self.assertEqual(len(res_dto.candidates), 1)
        cand1 = res_dto.candidates[0]
        self.assertEqual(cand1.candidate_id, "candidate_001")
        self.assertEqual(cand1.years_of_experience, 5.0)
        self.assertEqual(cand1.max_score, 0.88)
        self.assertEqual(len(cand1.matched_chunks), 2)
        self.assertIn("Python", cand1.all_skills)
        self.assertIn("FastAPI", cand1.all_skills)

    def test_execute_web_search_flat_items(self):
        # Arrange
        results = [
            SearchResultItem(
                candidate_id="candidate_001",
                candidate_name="張三",
                chunk_type="experience",
                section_title="工作經歷",
                content="5年經驗",
                skills=["Python"],
                score=0.85,
            )
        ]
        self.mock_vector_store.search.return_value = results

        # Act
        req_dto = WebSearchRequestDTO(
            query_text="Python 開發者",
            group_by_candidate=False,
        )
        res_dto = self.use_case.execute_web_search(req_dto)

        # Assert
        self.assertEqual(len(res_dto.raw_chunks), 1)
        self.assertEqual(res_dto.raw_chunks[0].candidate_id, "candidate_001")
        self.assertEqual(len(res_dto.candidates), 0)

    def test_get_resume_markdown_success(self):
        # Act
        content = self.use_case.get_resume_markdown("candidate_001")

        # Assert
        self.assertIsNotNone(content)
        self.assertIn("張三", content)

    def test_get_resume_markdown_path_traversal_defense(self):
        # Act & Assert: 惡意路徑必須直接被阻斷返回 None
        malicious_inputs = [
            "../secret.txt",
            "..\\config.py",
            "subdir/../../evil",
            "c:/boot.ini",
            "\\\\network\\share",
        ]
        for malicious_id in malicious_inputs:
            with self.subTest(candidate_id=malicious_id):
                result = self.use_case.get_resume_markdown(malicious_id)
                self.assertIsNone(result)

    def test_get_resume_markdown_not_found(self):
        # Act
        result = self.use_case.get_resume_markdown("non_existent_candidate_999")

        # Assert
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
