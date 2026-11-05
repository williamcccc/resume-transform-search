import unittest
from pathlib import Path
from src.domain.enums import DocumentType, DocumentHealth
from src.domain.models import Document, ConvertedMarkdown


class TestDomainModels(unittest.TestCase):
    def test_document_from_path_pdf(self):
        doc = Document.from_path(Path("sample.pdf"))
        self.assertEqual(doc.doc_type, DocumentType.PDF)
        self.assertEqual(doc.filename, "sample.pdf")

    def test_document_from_path_docx(self):
        doc = Document.from_path(Path("resume.docx"))
        self.assertEqual(doc.doc_type, DocumentType.DOCX)

    def test_document_from_path_unknown(self):
        doc = Document.from_path(Path("data.xyz"))
        self.assertEqual(doc.doc_type, DocumentType.UNKNOWN)

    def test_document_from_bytes(self):
        raw = b"%PDF-1.4 test"
        doc = Document.from_bytes("uploaded.pdf", raw)
        self.assertEqual(doc.doc_type, DocumentType.PDF)
        self.assertEqual(doc.get_bytes(), raw)

    def test_converted_markdown_char_count(self):
        md = ConvertedMarkdown(
            content="# Hello World",
            doc_type=DocumentType.PDF,
            health=DocumentHealth.HEALTHY,
            model_used="gemini-3.8-flash",
            reviewed=True
        )
        self.assertEqual(md.char_count, 13)
        self.assertTrue(md.reviewed)


if __name__ == "__main__":
    unittest.main()
