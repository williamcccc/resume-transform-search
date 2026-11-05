import pathlib
import tempfile
import unittest
from unittest.mock import MagicMock

from src.domain.enums import ConversionMode, DocumentHealth, DocumentType
from src.domain.models import QualityReport
from src.application.dto import ConversionResult
from src.infrastructure.config import AppConfig
from src.interfaces.cli.runner import discover_documents, convert_single_file, append_audit_report


class TestBatchRunner(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = pathlib.Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_discover_documents_filters_and_recursion(self):
        # 建立測試目錄架構
        (self.base_path / "doc1.pdf").touch()
        (self.base_path / "doc2.docx").touch()
        (self.base_path / "doc3.doc").touch()
        (self.base_path / "readme.txt").touch()          # 應過濾
        (self.base_path / "notes.md").touch()            # 應過濾
        (self.base_path / "~$lock.docx").touch()         # Word 暫存檔應過濾
        (self.base_path / ".hidden.pdf").touch()         # 隱藏檔應過濾

        sub_dir = self.base_path / "subfolder"
        sub_dir.mkdir()
        (sub_dir / "nested.pdf").touch()
        (sub_dir / "nested.docx").touch()
        (sub_dir / "ignore.png").touch()

        # 1. 非遞迴模式
        top_files = discover_documents(self.base_path, recursive=False)
        top_names = [f.name for f in top_files]
        self.assertEqual(len(top_files), 3)
        self.assertIn("doc1.pdf", top_names)
        self.assertIn("doc2.docx", top_names)
        self.assertIn("doc3.doc", top_names)
        self.assertNotIn("readme.txt", top_names)
        self.assertNotIn("~$lock.docx", top_names)
        self.assertNotIn("nested.pdf", top_names)

        # 2. 遞迴模式
        all_files = discover_documents(self.base_path, recursive=True)
        all_names = [f.name for f in all_files]
        self.assertEqual(len(all_files), 5)
        self.assertIn("nested.pdf", all_names)
        self.assertIn("nested.docx", all_names)

    def test_convert_single_file_success(self):
        input_file = self.base_path / "test.pdf"
        input_file.touch()
        output_file = self.base_path / "test.md"

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = ConversionResult(
            success=True,
            markdown="# 測試履歷\n\n## 經歷\n科技公司",
            doc_type=DocumentType.PDF,
            health=DocumentHealth.HEALTHY,
            model_used="fast_test",
            reviewed=False,
            quality_report=QualityReport(
                is_passed=True,
                score=95,
                warnings=[],
                checks={"has_h1": True}
            )
        )

        config = AppConfig(gemini_api_key="", gemini_model="test", gemini_review=False)

        success, quarantined, score, quota_hit = convert_single_file(
            file_path=input_file,
            target_output_path=output_file,
            use_case=mock_use_case,
            config=config,
            mode=ConversionMode.FAST,
        )

        self.assertTrue(success)
        self.assertFalse(quarantined)
        self.assertFalse(quota_hit)
        self.assertEqual(score, 95)
        self.assertTrue(output_file.exists())
        self.assertIn("# 測試履歷", output_file.read_text(encoding="utf-8"))

    def test_convert_single_file_quarantine(self):
        input_file = self.base_path / "bad.pdf"
        input_file.touch()
        output_file = self.base_path / "out" / "bad.md"
        quarantine_dir = self.base_path / "quarantine"

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = ConversionResult(
            success=True,
            markdown="內文嚴重殘缺",
            doc_type=DocumentType.PDF,
            health=DocumentHealth.OBFUSCATED,
            model_used="fast_test",
            reviewed=False,
            quality_report=QualityReport(
                is_passed=False,
                score=40,
                warnings=["缺少 H1", "字數嚴重不足"],
                checks={"has_h1": False}
            )
        )

        config = AppConfig(gemini_api_key="", gemini_model="test", gemini_review=False)

        success, quarantined, score, quota_hit = convert_single_file(
            file_path=input_file,
            target_output_path=output_file,
            use_case=mock_use_case,
            config=config,
            mode=ConversionMode.FAST,
            quarantine_dir=quarantine_dir,
        )

        self.assertTrue(success)
        self.assertTrue(quarantined)
        self.assertFalse(quota_hit)
        self.assertEqual(score, 40)
        # 應被存入隔離目錄，而非原 output_file
        self.assertFalse(output_file.exists())
        self.assertTrue((quarantine_dir / "bad.md").exists())

    def test_429_quota_exhausted_logged_to_audit_report(self):
        input_file = self.base_path / "exceeded.pdf"
        input_file.touch()
        output_file = self.base_path / "out" / "exceeded.md"
        audit_csv = self.base_path / "audit.csv"

        mock_use_case = MagicMock()
        mock_use_case.execute.side_effect = Exception(
            "429 RESOURCE_EXHAUSTED. Quota exceeded for metric: generativelanguage.googleapis.com/generate_content_free_tier_requests, limit: 20"
        )

        config = AppConfig(gemini_api_key="key", gemini_model="gemini-3.8-flash", gemini_review=False)

        success, quarantined, score, quota_hit = convert_single_file(
            file_path=input_file,
            target_output_path=output_file,
            use_case=mock_use_case,
            config=config,
            mode=ConversionMode.GEMINI,
            audit_report_path=audit_csv
        )

        self.assertFalse(success)
        self.assertFalse(quarantined)
        self.assertTrue(quota_hit)
        self.assertTrue(audit_csv.exists())
        csv_content = audit_csv.read_text(encoding="utf-8-sig")
        self.assertIn("exceeded.pdf,RESOURCE_EXHAUSTED,0", csv_content)
        self.assertIn("429 RESOURCE_EXHAUSTED", csv_content)

    def test_quota_already_exhausted_fast_records_without_calling_use_case(self):
        input_file = self.base_path / "next_file.pdf"
        input_file.touch()
        output_file = self.base_path / "out" / "next_file.md"
        audit_csv = self.base_path / "audit.csv"

        mock_use_case = MagicMock()
        config = AppConfig(gemini_api_key="key", gemini_model="gemini-3.8-flash", gemini_review=False)

        success, quarantined, score, quota_hit = convert_single_file(
            file_path=input_file,
            target_output_path=output_file,
            use_case=mock_use_case,
            config=config,
            mode=ConversionMode.GEMINI,
            audit_report_path=audit_csv,
            quota_already_exhausted=True
        )

        self.assertFalse(success)
        self.assertTrue(quota_hit)
        # 應直接記錄，不進行任何 use_case 呼叫
        mock_use_case.execute.assert_not_called()
        csv_content = audit_csv.read_text(encoding="utf-8-sig")
        self.assertIn("next_file.pdf,RESOURCE_EXHAUSTED,0", csv_content)

    def test_append_audit_report_creates_csv(self):
        csv_path = self.base_path / "reports" / "audit.csv"
        append_audit_report(csv_path, "sample1.pdf", "PASS", 90, "test-model", False, [])
        append_audit_report(csv_path, "sample2.pdf", "WARNING", 75, "test-model", True, ["少許雜訊"])

        self.assertTrue(csv_path.exists())
        lines = csv_path.read_text(encoding="utf-8-sig").strip().splitlines()
        self.assertEqual(len(lines), 3)  # 表頭 + 2 筆紀錄
        self.assertIn("Timestamp,Filename,Status,Score,JudgeScore,Model,Reviewed,Warnings", lines[0])
        self.assertIn("sample1.pdf,PASS,90", lines[1])
        self.assertIn("sample2.pdf,WARNING,75", lines[2])


if __name__ == "__main__":
    unittest.main()
