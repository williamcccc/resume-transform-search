import unittest
from unittest.mock import MagicMock
from src.application.convert_document_use_case import ConvertDocumentUseCase
from src.application.dto import ConversionCommand, ConversionResult
from src.domain.enums import ConversionMode, DocumentHealth, DocumentType
from src.domain.models import Document, ConvertedMarkdown


class TestPdfTextFirst(unittest.TestCase):
    """
    健康文字 PDF Text-First 策略白箱單元測試
    100% 離線 Mock 隔離，驗證優先走純文字轉檔、渲染圖片零調用與異常降級防線
    """

    def setUp(self):
        self.mock_reader = MagicMock()
        self.mock_reader.can_read.return_value = True
        self.mock_renderer = MagicMock()
        self.mock_probe = MagicMock()
        self.mock_gemini = MagicMock()
        self.mock_validator = MagicMock()
        self.mock_validator.validate.return_value = None

        self.use_case = ConvertDocumentUseCase(
            readers=[self.mock_reader],
            pdf_renderer=self.mock_renderer,
            pdf_probe=self.mock_probe,
            gemini_transformer=self.mock_gemini,
            quality_validator=self.mock_validator,
        )

    def test_healthy_pdf_uses_transform_text_without_rendering_png(self):
        # 1. Arrange: 健康 PDF 且文字層長度充足
        self.mock_probe.probe.return_value = DocumentHealth.HEALTHY
        self.mock_reader.extract_text.return_value = "這是一份健康的 PDF 原始文字層內容，包含豐富的工作經歷與專業技能清單。" * 5
        self.mock_gemini.transform_text.return_value = ConvertedMarkdown(
            content="# 候選人\n## 經歷\n轉換後的 Markdown",
            doc_type=DocumentType.PDF,
            health=DocumentHealth.HEALTHY,
            model_used="gemini-3.8-flash",
            reviewed=False,
        )

        cmd = ConversionCommand(
            filename="healthy.pdf",
            file_bytes=b"%PDF-1.4 mock",
            mode=ConversionMode.AUTO,
            api_key="mock_key",
        )

        # 2. Act
        result: ConversionResult = self.use_case.execute(cmd)

        # 3. Assert: 驗證走 transform_text，且完全沒有渲染圖片
        self.assertTrue(result.success)
        self.mock_gemini.transform_text.assert_called_once()
        self.mock_renderer.render_pages_to_png.assert_not_called()
        self.mock_gemini.transform_vision.assert_not_called()

    def test_healthy_pdf_falls_back_to_vision_when_transform_text_fails(self):
        # 1. Arrange: 文字轉換遭遇例外時，應自動降級渲染圖片並走 Vision
        self.mock_probe.probe.return_value = DocumentHealth.HEALTHY
        self.mock_reader.extract_text.return_value = "文字層內容" * 10
        self.mock_gemini.transform_text.side_effect = RuntimeError("Google API 文字安全過濾阻斷")
        self.mock_renderer.render_pages_to_png.return_value = [b"mock_png_bytes"]
        self.mock_gemini.transform_vision.return_value = ConvertedMarkdown(
            content="# 降級視覺 Markdown",
            doc_type=DocumentType.PDF,
            health=DocumentHealth.HEALTHY,
            model_used="gemini-3.8-flash",
            reviewed=False,
        )

        cmd = ConversionCommand(
            filename="healthy.pdf",
            file_bytes=b"%PDF-1.4 mock",
            mode=ConversionMode.AUTO,
            api_key="mock_key",
        )

        # 2. Act
        result: ConversionResult = self.use_case.execute(cmd)

        # 3. Assert
        self.assertTrue(result.success)
        self.mock_renderer.render_pages_to_png.assert_called_once()
        self.mock_gemini.transform_vision.assert_called_once()

    def test_scanned_pdf_bypasses_text_first_and_uses_vision(self):
        # 1. Arrange: 掃描件直接走 Vision 多模態
        self.mock_probe.probe.return_value = DocumentHealth.SCANNED
        self.mock_reader.extract_text.return_value = ""
        self.mock_renderer.render_pages_to_png.return_value = [b"mock_png_bytes"]
        self.mock_gemini.transform_vision.return_value = ConvertedMarkdown(
            content="# 掃描件 OCR Markdown",
            doc_type=DocumentType.PDF,
            health=DocumentHealth.SCANNED,
            model_used="gemini-3.8-flash",
            reviewed=False,
        )

        cmd = ConversionCommand(
            filename="scanned.pdf",
            file_bytes=b"%PDF-1.4 mock",
            mode=ConversionMode.AUTO,
            api_key="mock_key",
        )

        # 2. Act
        result: ConversionResult = self.use_case.execute(cmd)

        # 3. Assert
        self.assertTrue(result.success)
        self.mock_gemini.transform_text.assert_not_called()
        self.mock_gemini.transform_vision.assert_called_once()


if __name__ == "__main__":
    unittest.main()
