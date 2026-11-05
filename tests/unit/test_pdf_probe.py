import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from src.domain.enums import DocumentHealth, DocumentType
from src.domain.models import Document
from src.infrastructure.probes.pdf_probe import PdfHealthProbe


class TestPdfHealthProbe(unittest.TestCase):
    def setUp(self):
        self.probe = PdfHealthProbe()

    @patch("pymupdf.open")
    def test_probe_scanned_when_short_text(self, mock_open):
        mock_pdoc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "短文字"  # < 30 chars
        mock_pdoc.__len__.return_value = 1
        mock_pdoc.__getitem__.return_value = [mock_page]
        mock_open.return_value.__enter__.return_value = mock_pdoc

        doc = Document("scan.pdf", DocumentType.PDF, content_bytes=b"%PDF-test")
        health = self.probe.probe(doc)
        self.assertEqual(health, DocumentHealth.SCANNED)

    @patch("pymupdf4llm.to_markdown")
    @patch("pymupdf.open")
    def test_probe_obfuscated_when_too_many_corruptions(self, mock_open, mock_to_md):
        mock_pdoc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "這是一份文字長度超過三十個字元的正常履歷文字內容用來測試混淆探測"
        mock_pdoc.__len__.return_value = 1
        mock_pdoc.__getitem__.return_value = [mock_page]
        mock_open.return_value.__enter__.return_value = mock_pdoc

        # 模擬 104 混淆字型特徵 (\ufffd > 10)
        mock_to_md.return_value = "混淆內容" + "\ufffd" * 15

        doc = Document("obfuscated.pdf", DocumentType.PDF, content_bytes=b"%PDF-test")
        health = self.probe.probe(doc)
        self.assertEqual(health, DocumentHealth.OBFUSCATED)

    @patch("pymupdf4llm.to_markdown")
    @patch("pymupdf.open")
    def test_probe_healthy_when_normal(self, mock_open, mock_to_md):
        mock_pdoc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "這是一份文字長度超過三十個字元的正常履歷文字內容用來測試健康探測"
        mock_pdoc.__len__.return_value = 1
        mock_pdoc.__getitem__.return_value = [mock_page]
        mock_open.return_value.__enter__.return_value = mock_pdoc

        mock_to_md.return_value = "# 正常履歷\n這是正常的 Markdown 內容"

        doc = Document("healthy.pdf", DocumentType.PDF, content_bytes=b"%PDF-test")
        health = self.probe.probe(doc)
        self.assertEqual(health, DocumentHealth.HEALTHY)

    @patch("pymupdf4llm.to_markdown")
    @patch("pymupdf.open")
    def test_probe_obfuscated_when_too_many_strikethroughs(self, mock_open, mock_to_md):
        mock_pdoc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "這是一份文字長度超過三十個字元的正常履歷文字內容用來測試刪除線混淆探測"
        mock_pdoc.__len__.return_value = 1
        mock_pdoc.__getitem__.return_value = [mock_page]
        mock_open.return_value.__enter__.return_value = mock_pdoc

        # 模擬字型混淆導致大量異常刪除線標記 (~~ > 30)
        mock_to_md.return_value = "混淆內容 " + "~~亂碼~~ " * 20

        doc = Document("strikethrough_obfuscated.pdf", DocumentType.PDF, content_bytes=b"%PDF-test")
        health = self.probe.probe(doc)
        self.assertEqual(health, DocumentHealth.OBFUSCATED)


if __name__ == "__main__":
    unittest.main()
