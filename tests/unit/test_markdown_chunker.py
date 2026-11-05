import unittest
from src.domain.enums import ChunkType
from src.infrastructure.chunkers.markdown_chunker import MarkdownChunker


SAMPLE_MARKDOWN = """# 王小明 (Sample Candidate)
Email: jerry@example.com | 聯絡電話: \x30\x39\x31\x32-\x33\x34\x35-\x36\x37\x38

## 個人簡介
擁有 5 年後端架構與微服務開發經驗，擅長處理高並發系統與分散式架構。

## 工作經歷
### 某某科技股份有限公司｜資深後端工程師
2021/05 ~ 至今
- 負責設計與重構高並發金流串接核心 API，採用 Python, FastAPI 與 Redis 快取技術。
- 主導微服務架構轉型，利用 Docker 與 Kubernetes 進行容器編排，達成 99.99% 高可用性。
- 設計 PostgreSQL 與 MySQL 資料庫讀寫分離及索引最佳化，降低延遲 60%。

### 創新軟體實驗室 - 軟體工程師
2019/07 ~ 2021/04
- 使用 Golang 與 gRPC 開發實時通訊服務。
- 建立 CI/CD 自動化部署流程，提升團隊部署效率 3 倍。

## 專業技能
- 程式語言: Python, Golang, SQL, JavaScript
- 雲端與 DevOps: AWS (EC2, S3, RDS), Docker, K8s, Git, CI/CD
- 快取與儲存: Redis, PostgreSQL, MySQL, MongoDB

## 學歷背景
### 國立臺灣科技大學 - 資訊工程學系
碩士 (2017 ~ 2019)
"""


class TestMarkdownChunker(unittest.TestCase):
    def setUp(self):
        self.chunker = MarkdownChunker()

    def test_chunk_markdown_success(self):
        chunks = self.chunker.chunk_markdown(
            markdown=SAMPLE_MARKDOWN,
            candidate_id="jerry_wang",
            file_path="resume/sample_resume.md",
        )

        self.assertGreater(len(chunks), 0)
        # 驗證候選人姓名
        self.assertEqual(chunks[0].candidate_name, "王小明 (Sample Candidate)")
        self.assertEqual(chunks[0].candidate_id, "jerry_wang")

        # 驗證經歷切片與公司職稱解析
        exp_chunks = [c for c in chunks if c.chunk_type == ChunkType.EXPERIENCE]
        self.assertGreaterEqual(len(exp_chunks), 2)

        first_exp = exp_chunks[0]
        self.assertEqual(first_exp.company, "某某科技股份有限公司")
        self.assertEqual(first_exp.job_title, "資深後端工程師")
        self.assertIn("fastapi", first_exp.skills)
        self.assertIn("redis", first_exp.skills)
        self.assertIn("python", first_exp.skills)
        self.assertIn("kubernetes", first_exp.skills)

        second_exp = exp_chunks[1]
        self.assertEqual(second_exp.company, "創新軟體實驗室")
        self.assertEqual(second_exp.job_title, "軟體工程師")
        self.assertIn("golang", second_exp.skills)
        self.assertIn("grpc", second_exp.skills)
        self.assertIn("ci/cd", second_exp.skills)

        # 驗證技能區塊
        skills_chunks = [c for c in chunks if c.chunk_type == ChunkType.SKILLS]
        self.assertEqual(len(skills_chunks), 1)
        self.assertIn("aws", skills_chunks[0].skills)
        self.assertIn("mongodb", skills_chunks[0].skills)

        # 驗證學歷區塊
        edu_chunks = [c for c in chunks if c.chunk_type == ChunkType.EDUCATION]
        self.assertGreaterEqual(len(edu_chunks), 1)

    def test_chunk_empty_markdown(self):
        chunks = self.chunker.chunk_markdown("", candidate_id="empty")
        self.assertEqual(chunks, [])

    def test_chunk_unstructured_text(self):
        raw_text = "這是一份沒有 Markdown 標題的純文字自傳內容，熟悉 Python 與 MySQL。"
        chunks = self.chunker.chunk_markdown(raw_text, candidate_id="unstructured")
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0].chunk_type, ChunkType.PROFILE)
        self.assertIn("python", chunks[0].skills)
        self.assertIn("mysql", chunks[0].skills)


if __name__ == "__main__":
    unittest.main()
