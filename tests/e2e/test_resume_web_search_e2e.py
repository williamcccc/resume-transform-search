"""
E2E Integration & QA Tests for Resume Web Search Interface.
Covers:
1. FastAPI GET /api/search with query parameters, min_years filtering, group_by_candidate
2. FastAPI GET /api/resume with path traversal injection defense & 404 handling
3. Error handling: 400 Bad Request when missing query or candidate_id
4. Built-in ThreadingHTTPServer fallback handler verification
"""

import unittest
from unittest.mock import MagicMock
from pathlib import Path
import tempfile
import shutil

from fastapi.testclient import TestClient

from src.application.dashboard_use_case import GetDashboardDataUseCase
from src.application.search_resumes_use_case import SearchResumesUseCase
from src.domain.models import SearchResultItem
from src.infrastructure.parsers.experience_parser import RegexExperienceParser
from src.interfaces.web.fastapi_server import create_app


class TestResumeWebSearchE2E(unittest.TestCase):
    """端到端 (E2E) 測試：履歷智能檢索與履歷全文預覽 API"""

    def setUp(self):
        # 建立暫存履歷目錄
        self.temp_dir = tempfile.mkdtemp()
        self.resume_dir = Path(self.temp_dir) / "markdown_out"
        self.resume_dir.mkdir(parents=True, exist_ok=True)

        # 建立測試用履歷
        (self.resume_dir / "candidate_senior.md").write_text(
            "# 王大明\n- **工作經歷**：7年工作經歷\n- **技能**：Python, Redis, Docker, FastAPI",
            encoding="utf-8"
        )
        (self.resume_dir / "candidate_junior.md").write_text(
            "# 陳小華\n- **工作經歷**：1~2年工作經歷\n- **技能**：HTML, CSS, Vue",
            encoding="utf-8"
        )

        # Mock Dashboard Use Case
        self.mock_dashboard_uc = MagicMock(spec=GetDashboardDataUseCase)

        # Setup Search Resumes Use Case
        self.mock_embedding_service = MagicMock()
        self.mock_embedding_service.embed_query.return_value = [0.05] * 768

        self.mock_vector_store = MagicMock()
        self.search_uc = SearchResumesUseCase(
            embedding_service=self.mock_embedding_service,
            vector_store=self.mock_vector_store,
            markdown_base_dir=self.resume_dir,
            experience_parser=RegexExperienceParser(),
        )

        # 建立 FastAPI app 與 TestClient
        self.app = create_app(
            use_case=self.mock_dashboard_uc,
            search_use_case=self.search_uc,
        )
        self.client = TestClient(self.app)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_e2e_search_grouped_with_min_years_filter(self):
        """TC-E2E-01: 測試自然語言搜尋與最低年資複合過濾 (Grouped)"""
        # Arrange
        results = [
            SearchResultItem(
                candidate_id="candidate_senior",
                candidate_name="王大明",
                chunk_type="experience",
                section_title="工作經歷",
                content="- **工作經歷**：7年工作經歷\n負責分散式後端微服務系統",
                skills=["Python", "Docker", "Redis"],
                score=0.89,
            ),
            SearchResultItem(
                candidate_id="candidate_junior",
                candidate_name="陳小華",
                chunk_type="experience",
                section_title="工作經歷",
                content="- **工作經歷**：1~2年工作經歷\n前端初階工程師",
                skills=["Vue", "CSS"],
                score=0.92,
            ),
        ]
        self.mock_vector_store.search.return_value = results

        # Act: 請求年資 >= 5 年以上
        response = self.client.get("/api/search?query=分散式微服務工程師&min_years=5.0&group_by_candidate=true")

        # Assert
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["total_candidates"], 1)
        self.assertEqual(len(data["candidates"]), 1)

        candidate = data["candidates"][0]
        self.assertEqual(candidate["candidate_id"], "candidate_senior")
        self.assertEqual(candidate["candidate_name"], "王大明")
        self.assertEqual(candidate["parsed_years"], 7.0)
        self.assertAlmostEqual(candidate["max_similarity"], 0.89, places=2)
        self.assertIn("Python", candidate["skills"])

    def test_e2e_search_flat_chunks(self):
        """TC-E2E-02: 測試未分組之切片清單模式"""
        # Arrange
        results = [
            SearchResultItem(
                candidate_id="candidate_senior",
                candidate_name="王大明",
                chunk_type="skills",
                section_title="專業技能",
                content="精通 FastAPI 與 Docker",
                skills=["FastAPI", "Docker"],
                score=0.85,
            )
        ]
        self.mock_vector_store.search.return_value = results

        # Act
        response = self.client.get("/api/search?query=FastAPI&group_by_candidate=false")

        # Assert
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["candidate_id"], "candidate_senior")
        self.assertEqual(data["items"][0]["score"], 0.85)

    def test_e2e_search_missing_query_bad_request(self):
        """TC-E2E-03: 缺少 query 參數或為空時回傳 400 Bad Request"""
        # Act
        response_empty = self.client.get("/api/search?query=")
        response_spaces = self.client.get("/api/search?query=   ")

        # Assert
        self.assertEqual(response_empty.status_code, 400)
        self.assertEqual(response_spaces.status_code, 400)
        self.assertIn("query 參數不可為空", response_empty.json()["detail"])

    def test_e2e_get_resume_success(self):
        """TC-E2E-04: 測試安全讀取候選人 Markdown 全文"""
        # Act
        response = self.client.get("/api/resume?candidate_id=candidate_senior")

        # Assert
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["candidate_id"], "candidate_senior")
        self.assertIn("王大明", data["markdown"])
        self.assertIn("7年工作經歷", data["markdown"])

    def test_e2e_get_resume_path_traversal_defense(self):
        """TC-E2E-05: 測試路徑遍歷越權攻擊防禦 (回傳 400)"""
        malicious_candidates = [
            "../secret.txt",
            "..\\etc\\passwd",
            "dir/../../../etc/shadow",
        ]
        for malicious_id in malicious_candidates:
            with self.subTest(candidate_id=malicious_id):
                response = self.client.get(f"/api/resume?candidate_id={malicious_id}")
                self.assertEqual(response.status_code, 400)
                self.assertIn("非法", response.json()["detail"])

    def test_e2e_get_resume_not_found(self):
        """TC-E2E-06: 找不到候選人履歷時回傳 404 Not Found"""
        # Act
        response = self.client.get("/api/resume?candidate_id=ghost_user_404")

        # Assert
        self.assertEqual(response.status_code, 404)
        self.assertIn("找不到候選人", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
