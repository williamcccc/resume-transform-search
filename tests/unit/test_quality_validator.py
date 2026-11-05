import unittest
from src.infrastructure.validators.quality_validator import MarkdownQualityValidator


class TestMarkdownQualityValidator(unittest.TestCase):
    def setUp(self):
        self.validator = MarkdownQualityValidator()

    def test_perfect_markdown_passes_with_100(self):
        md = (
            "# 王小明\n\n"
            "- Email: ming@example.com\n"
            "- 電話: \x30\x39\x31\x32-\x33\x34\x35-\x36\x37\x38\n\n"
            "## 工作經歷\n\n"
            "### 科技公司｜工程師\n"
            "負責系統架構設計與開發。\n\n"
            "## 學歷背景\n\n"
            "### 國立大學｜資訊工程系\n"
        )
        raw = "王小明 ming@example.com \x30\x39\x31\x32-\x33\x34\x35-\x36\x37\x38 科技公司 工程師 系統架構設計 國立大學 資訊工程系"

        report = self.validator.validate(markdown=md, raw_text=raw)
        self.assertTrue(report.is_passed)
        self.assertEqual(report.score, 100)
        self.assertEqual(len(report.warnings), 0)
        self.assertEqual(report.summary_status, "PASS")

    def test_missing_h1_penalized(self):
        md = (
            "## 工作經歷\n"
            "### 科技公司｜工程師\n"
            "## 學歷\n"
            "國立大學\n"
        )
        report = self.validator.validate(markdown=md)
        self.assertIn("has_h1_heading", report.checks)
        self.assertFalse(report.checks["has_h1_heading"])
        self.assertLess(report.score, 100)

    def test_missing_core_sections_penalized(self):
        md = (
            "# 王小明\n"
            "這是一段沒有包含任何工作經歷或學歷的普通自我介紹文章。\n"
        )
        report = self.validator.validate(markdown=md)
        self.assertFalse(report.checks["has_core_sections"])
        self.assertLess(report.score, 80)

    def test_forbidden_noise_detected(self):
        md = (
            "# 王小明\n\n"
            "## Page 1\n\n"
            "## 工作經歷\n"
            "任職於科技公司\ufffd\n"
            "## 學歷\n"
            "國立大學\n"
        )
        report = self.validator.validate(markdown=md)
        self.assertFalse(report.checks["no_page_noise"])
        self.assertFalse(report.checks["no_ufffd_corruption"])
        self.assertIn("殘留未過濾的分頁標記 (## Page X)", report.warnings)
        self.assertIn("包含亂碼替換字元 (\\ufffd)", report.warnings)

    def test_entity_recall_missing_email_and_phone(self):
        raw = "聯絡方式: ming@example.com, 電話 \x30\x39\x38\x38-\x31\x32\x33-\x34\x35\x36"
        md = (
            "# 王小明\n\n"
            "## 工作經歷\n"
            "科技公司工程師\n"
            "## 學歷\n"
            "國立大學\n"
        )
        report = self.validator.validate(markdown=md, raw_text=raw)
        self.assertFalse(report.checks["entities_preserved"])
        self.assertTrue(any("Email" in w for w in report.warnings))
        self.assertTrue(any("手機" in w for w in report.warnings))

    def test_severely_truncated_content_flagged(self):
        raw = "這是一份非常非常長的文章內容。" * 20  # 約 300 字
        md = "# 王小明\n## 經歷\n短"               # 約 10 字

        report = self.validator.validate(markdown=md, raw_text=raw)
        self.assertFalse(report.checks["retention_ratio_ok"])
        self.assertTrue(any("保留率" in w for w in report.warnings))


if __name__ == "__main__":
    unittest.main()
