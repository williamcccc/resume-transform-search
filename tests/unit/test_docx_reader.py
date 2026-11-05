import io
import unittest
import zipfile
import docx
from src.domain.models import Document
from src.domain.enums import DocumentType
from src.infrastructure.readers.docx_reader import DocxReader


def _build_sample_docx_bytes(with_broken_media_rel: bool = False) -> bytes:
    """在記憶體中動態建構測試用 .docx 位元組流（可選注入殘留破圖關聯）"""
    d = docx.Document()
    d.add_heading("王小明 (Sample Candidate)", level=1)
    d.add_paragraph("具備 5 年後端系統開發與分散式微服務架構經驗。")
    table = d.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "擅長工具"
    table.cell(0, 1).text = "Python, FastAPI, Redis, Docker"
    table.cell(1, 0).text = "最高學歷"
    table.cell(1, 1).text = "國立臺灣科技大學 資訊工程學系"

    buf = io.BytesIO()
    d.save(buf)
    raw_bytes = buf.getvalue()

    if not with_broken_media_rel:
        return raw_bytes

    # 注入殘留的圖片關聯 (Target 指向不存在的 media/missing_image.jpeg)
    broken_buf = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as zin, zipfile.ZipFile(broken_buf, "w") as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            if item.filename == "word/_rels/document.xml.rels":
                rel_xml = content.decode("utf-8")
                injected_rel = (
                    '<Relationship Id="rIdBroken99" '
                    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" '
                    'Target="media/missing_image.jpeg"/></Relationships>'
                )
                rel_xml = rel_xml.replace("</Relationships>", injected_rel)
                content = rel_xml.encode("utf-8")
            zout.writestr(item, content)
    return broken_buf.getvalue()


class TestDocxReader(unittest.TestCase):
    def setUp(self):
        self.reader = DocxReader()

    def test_can_read(self):
        docx_doc = Document("test.docx", DocumentType.DOCX)
        pdf_doc = Document("test.pdf", DocumentType.PDF)
        self.assertTrue(self.reader.can_read(docx_doc))
        self.assertFalse(self.reader.can_read(pdf_doc))

    def test_extract_docx_paragraphs_and_tables(self):
        raw_bytes = _build_sample_docx_bytes(with_broken_media_rel=False)
        doc = Document("sample.docx", DocumentType.DOCX, content_bytes=raw_bytes)
        text = self.reader.extract_text(doc)
        self.assertIn("王小明", text)
        self.assertIn("擅長工具 | Python, FastAPI, Redis, Docker", text)

    def test_extract_heals_missing_media_part(self):
        # 專門測試含有殘留關聯但缺少實體圖片的 Word 檔案 (In-Memory 破圖自動補樁)
        broken_bytes = _build_sample_docx_bytes(with_broken_media_rel=True)
        doc = Document("broken_media.docx", DocumentType.DOCX, content_bytes=broken_bytes)
        text = self.reader.extract_text(doc)
        self.assertIn("王小明", text)
        self.assertIn("擅長工具", text)
        self.assertIn("|", text)


if __name__ == "__main__":
    unittest.main()
