import json
import pathlib
import tempfile
import unittest
from unittest.mock import MagicMock

from src.application.dto import ConversionCommand, ConversionResult
from src.application.convert_document_use_case import ConvertDocumentUseCase
from src.domain.enums import ConversionMode, DocumentHealth, DocumentType
from src.domain.models import Document, ConvertedMarkdown, JudgeScorecard, QualityReport
from src.infrastructure.config import AppConfig
from src.infrastructure.validators.llm_judge import GeminiLlmJudge
from src.interfaces.cli.runner import convert_single_file


class TestLlmJudge(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = pathlib.Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_json_scorecard_valid(self):
        judge = GeminiLlmJudge(api_key="mock")
        sample_json = json.dumps({
            "overall_score": 92,
            "completeness_score": 95,
            "fidelity_score": 90,
            "structure_score": 92,
            "verdict": "PASS",
            "critique": "整體結構優良，未見重大缺失。",
            "missing_items": [],
            "hallucinations": []
        })

        card = judge._parse_json_scorecard(sample_json)
        self.assertEqual(card.overall_score, 92)
        self.assertEqual(card.completeness_score, 95)
        self.assertEqual(card.fidelity_score, 90)
        self.assertEqual(card.structure_score, 92)
        self.assertEqual(card.verdict, "PASS")
        self.assertEqual(len(card.missing_items), 0)

    def test_parse_json_scorecard_with_fences(self):
        judge = GeminiLlmJudge(api_key="mock")
        raw = "```json\n{\"overall_score\": 55, \"verdict\": \"FAIL\", \"critique\": \"遺漏重要經歷\", \"missing_items\": [\"2020 科技公司\"]}\n```"
        card = judge._parse_json_scorecard(raw)
        self.assertEqual(card.overall_score, 55)
        self.assertEqual(card.verdict, "FAIL")
        self.assertIn("2020 科技公司", card.missing_items)

    def test_parse_json_scorecard_malformed_fallback(self):
        judge = GeminiLlmJudge(api_key="mock")
        card = judge._parse_json_scorecard("這不是合法的 JSON")
        self.assertEqual(card.verdict, "WARNING")
        self.assertEqual(card.overall_score, 70)
        self.assertIn("無法完全解析", card.critique)

    def test_use_case_invokes_judge_when_enabled(self):
        mock_reader = MagicMock()
        mock_reader.can_read.return_value = True
        mock_reader.extract_text.return_value = "段落文字"

        mock_transformer = MagicMock()
        mock_transformer.transform_text.return_value = ConvertedMarkdown(
            content="# 王小明\n## 經歷\n科技公司",
            doc_type=DocumentType.DOCX,
            health=DocumentHealth.HEALTHY,
            model_used="gemini-test",
            reviewed=False
        )

        mock_judge = MagicMock()
        mock_judge.judge_document.return_value = JudgeScorecard(
            overall_score=85,
            completeness_score=85,
            fidelity_score=90,
            structure_score=80,
            verdict="PASS",
            critique="評審通過"
        )

        use_case = ConvertDocumentUseCase(
            word_readers=[mock_reader],
            pdf_renderer=MagicMock(),
            pdf_probe=MagicMock(),
            gemini_transformer=mock_transformer,
            rapid_ocr_transformer=MagicMock(),
            fast_transformer=MagicMock(),
            quality_validator=MagicMock(),
            llm_judge=mock_judge
        )

        doc_file = self.base_path / "resume.docx"
        doc_file.touch()

        # 啟用 judge
        cmd = ConversionCommand(
            file_path=doc_file,
            mode=ConversionMode.GEMINI,
            api_key="mock_key",
            enable_judge=True
        )

        result = use_case.execute(cmd)
        self.assertTrue(result.success)
        mock_judge.judge_document.assert_called_once()
        self.assertIsNotNone(result.judge_scorecard)
        self.assertEqual(result.judge_scorecard.overall_score, 85)

    def test_judge_fail_triggers_quarantine_and_saves_json(self):
        input_file = self.base_path / "candidate.pdf"
        input_file.touch()
        output_file = self.base_path / "out" / "candidate.md"
        quarantine_dir = self.base_path / "quarantine"
        scorecard_dir = self.base_path / "scorecards"

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = ConversionResult(
            success=True,
            markdown="# 候選人\n內文",
            doc_type=DocumentType.PDF,
            health=DocumentHealth.HEALTHY,
            model_used="gemini-3.8-flash",
            reviewed=False,
            quality_report=QualityReport(is_passed=True, score=90),
            judge_scorecard=JudgeScorecard(
                overall_score=45,
                completeness_score=40,
                fidelity_score=50,
                structure_score=45,
                verdict="FAIL",
                critique="經歷有重大造假幻覺",
                hallucinations=["fabricated executive experience at a major technology company"]
            )
        )

        config = AppConfig(gemini_api_key="key", gemini_model="test", gemini_review=False, gemini_judge=True)

        success, quarantined, score, quota_hit = convert_single_file(
            file_path=input_file,
            target_output_path=output_file,
            use_case=mock_use_case,
            config=config,
            mode=ConversionMode.GEMINI,
            quarantine_dir=quarantine_dir,
            save_scorecard_path=scorecard_dir
        )

        self.assertTrue(success)
        self.assertTrue(quarantined)
        self.assertTrue((quarantine_dir / "candidate.md").exists())
        # 評分卡 JSON 檔案應存在
        saved_card = scorecard_dir / "candidate_scorecard.json"
        self.assertTrue(saved_card.exists())
        data = json.loads(saved_card.read_text(encoding="utf-8"))
        self.assertEqual(data["verdict"], "FAIL")
        self.assertIn("fabricated executive experience at a major technology company", data["hallucinations"])

    def test_judge_document_vision_mode_uses_external_prompt(self):
        judge = GeminiLlmJudge(api_key="mock_key")
        mock_response = MagicMock()
        mock_response.text = json.dumps({"overall_score": 90, "verdict": "PASS"})
        judge.client.models.generate_content = MagicMock(return_value=mock_response)

        doc = Document.from_bytes("test.pdf", b"fake-pdf")
        doc.doc_type = DocumentType.PDF
        scorecard = judge.judge_document(
            markdown="# 測試履歷",
            doc=doc,
            page_pngs=[b"png1", b"png2"],
        )

        self.assertEqual(scorecard.overall_score, 90)
        self.assertEqual(scorecard.verdict, "PASS")
        judge.client.models.generate_content.assert_called_once()
        call_kwargs = judge.client.models.generate_content.call_args.kwargs
        contents = call_kwargs["contents"]
        self.assertEqual(len(contents), 3)  # 2 PNG parts + 1 prompt string
        prompt_str = contents[2]
        self.assertIn("=== 原始文件資訊 ===", prompt_str)
        self.assertIn("test.pdf", prompt_str)
        self.assertIn("# 測試履歷", prompt_str)

    def test_judge_document_custom_prompt_templates_injection(self):
        custom_system = "自訂系統評審專家指引"
        custom_vision = "[自訂視覺] {system_prompt} 檔案={filename} 成果={markdown}"
        custom_text = "[自訂文字] {system_prompt} 檔案={filename} 原文={raw_text} 成果={markdown}"

        judge = GeminiLlmJudge(
            api_key="mock_key",
            system_prompt=custom_system,
            vision_prompt_template=custom_vision,
            text_prompt_template=custom_text,
        )
        mock_response = MagicMock()
        mock_response.text = json.dumps({"overall_score": 88, "verdict": "PASS"})
        judge.client.models.generate_content = MagicMock(return_value=mock_response)

        doc = Document.from_bytes("resume.docx", b"fake-docx")
        doc.doc_type = DocumentType.DOCX
        scorecard = judge.judge_document(
            markdown="# 客製化內容",
            doc=doc,
            raw_text="原始提取文字內容",
        )

        self.assertEqual(scorecard.overall_score, 88)
        call_kwargs = judge.client.models.generate_content.call_args.kwargs
        prompt_sent = call_kwargs["contents"][0]
        self.assertIn("[自訂文字]", prompt_sent)
        self.assertIn("自訂系統評審專家指引", prompt_sent)
        self.assertIn("resume.docx", prompt_sent)
        self.assertIn("原始提取文字內容", prompt_sent)
        self.assertIn("# 客製化內容", prompt_sent)


if __name__ == "__main__":
    unittest.main()
