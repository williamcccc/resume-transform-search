import unittest
from pathlib import Path
from typing import List

from src.application.convert_document_use_case import ConvertDocumentUseCase
from src.application.dto import ConversionCommand
from src.domain.enums import ConversionMode, DocumentHealth, DocumentType
from src.domain.exceptions import DocumentNotFoundError, UnsupportedDocumentTypeError
from src.domain.interfaces import IDocumentReader, IMarkdownTransformer, IPdfHealthProbe, IPdfRenderer
from src.domain.models import ConvertedMarkdown, Document


class MockWordReader(IDocumentReader):
    def can_read(self, doc: Document) -> bool:
        return doc.doc_type == DocumentType.DOCX

    def extract_text(self, doc: Document) -> str:
        return "# Mocked Word Content"


class MockPdfRenderer(IPdfRenderer):
    def render_pages_to_png(self, doc: Document, dpi: int = 150) -> List[bytes]:
        return [b"fake_png_page_1", b"fake_png_page_2"]


class MockPdfHealthProbe(IPdfHealthProbe):
    def __init__(self, health_to_return: DocumentHealth = DocumentHealth.HEALTHY):
        self.health_to_return = health_to_return

    def probe(self, doc: Document) -> DocumentHealth:
        return self.health_to_return


class MockTransformer(IMarkdownTransformer):
    def __init__(self, name: str = "mock"):
        self.name = name
        self.last_vision_call = None
        self.last_text_call = None

    def transform_vision(self, page_pngs: List[bytes], doc: Document, enable_review: bool = False) -> ConvertedMarkdown:
        self.last_vision_call = {"pages": len(page_pngs), "review": enable_review}
        return ConvertedMarkdown(
            content=f"# Transformed by {self.name} (Vision)",
            doc_type=doc.doc_type,
            health=doc.health,
            model_used=self.name,
            reviewed=enable_review
        )

    def transform_text(self, text: str, doc: Document, enable_review: bool = False) -> ConvertedMarkdown:
        self.last_text_call = {"text": text, "review": enable_review}
        return ConvertedMarkdown(
            content=f"# Transformed by {self.name} (Text)",
            doc_type=doc.doc_type,
            health=doc.health,
            model_used=self.name,
            reviewed=enable_review
        )


class TestConvertDocumentUseCase(unittest.TestCase):
    def setUp(self):
        self.word_reader = MockWordReader()
        self.pdf_renderer = MockPdfRenderer()
        self.pdf_probe = MockPdfHealthProbe(DocumentHealth.HEALTHY)
        self.mock_gemini = MockTransformer("mock-gemini")
        self.mock_ocr = MockTransformer("mock-ocr")
        self.mock_fast = MockTransformer("mock-fast")

        self.use_case = ConvertDocumentUseCase(
            word_readers=[self.word_reader],
            pdf_renderer=self.pdf_renderer,
            pdf_probe=self.pdf_probe,
            gemini_transformer=self.mock_gemini,
            rapid_ocr_transformer=self.mock_ocr,
            fast_transformer=self.mock_fast,
        )

    def test_word_document_routing(self):
        cmd = ConversionCommand(
            filename="resume.docx",
            file_bytes=b"fake_docx",
            mode=ConversionMode.AUTO,
            api_key="fake_key",
            enable_review=True
        )
        result = self.use_case.execute(cmd)

        self.assertTrue(result.success)
        self.assertEqual(result.doc_type, DocumentType.DOCX)
        self.assertEqual(result.model_used, "mock-gemini")
        self.assertTrue(result.reviewed)

    def test_pdf_auto_routing_healthy(self):
        self.pdf_probe.health_to_return = DocumentHealth.HEALTHY
        cmd = ConversionCommand(
            filename="healthy.pdf",
            file_bytes=b"%PDF-1.4",
            mode=ConversionMode.AUTO,
            api_key="fake_key",
            enable_review=False
        )
        result = self.use_case.execute(cmd)

        self.assertTrue(result.success)
        self.assertEqual(result.model_used, "mock-gemini")
        self.assertEqual(self.mock_gemini.last_vision_call["pages"], 2)

    def test_pdf_auto_routing_obfuscated_with_gemini(self):
        self.pdf_probe.health_to_return = DocumentHealth.OBFUSCATED
        cmd = ConversionCommand(
            filename="104.pdf",
            file_bytes=b"%PDF-1.4",
            mode=ConversionMode.AUTO,
            api_key="fake_key",
            enable_review=True
        )
        result = self.use_case.execute(cmd)

        self.assertTrue(result.success)
        self.assertEqual(result.health, DocumentHealth.OBFUSCATED)
        self.assertEqual(result.model_used, "mock-gemini")
        self.assertTrue(result.reviewed)

    def test_pdf_auto_routing_obfuscated_without_api_key_falls_back_to_ocr(self):
        self.pdf_probe.health_to_return = DocumentHealth.OBFUSCATED
        cmd = ConversionCommand(
            filename="104.pdf",
            file_bytes=b"%PDF-1.4",
            mode=ConversionMode.AUTO,
            api_key=None,  # 無 API Key
            enable_review=False
        )
        result = self.use_case.execute(cmd)

        self.assertTrue(result.success)
        self.assertEqual(result.model_used, "mock-ocr")

    def test_unsupported_file_extension(self):
        cmd = ConversionCommand(
            filename="unknown.zip",
            file_bytes=b"PK...",
            mode=ConversionMode.AUTO
        )
        with self.assertRaises(UnsupportedDocumentTypeError):
            self.use_case.execute(cmd)

    def test_nonexistent_file_path(self):
        cmd = ConversionCommand(
            file_path=Path("non_existent_file.pdf"),
            mode=ConversionMode.AUTO
        )
        with self.assertRaises(DocumentNotFoundError):
            self.use_case.execute(cmd)


if __name__ == "__main__":
    unittest.main()
