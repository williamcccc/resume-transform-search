from typing import Optional
import pymupdf

from src.domain.enums import DocumentType
from src.domain.exceptions import FileQuotaExceededError
from src.domain.interfaces import IDocumentReader
from src.domain.models import Document

MAX_PDF_PAGES = 30


class PdfTextReader(IDocumentReader):
    """
    使用 PyMuPDF 提取 PDF 原始純文字層的讀取器實作
    內建資源配額防護：超過頁數上限拋出 FileQuotaExceededError (可由建構子動態配置)
    """

    def __init__(self, max_pages: int = MAX_PDF_PAGES):
        self.max_pages = max_pages

    def can_read(self, doc: Document) -> bool:
        return doc.doc_type == DocumentType.PDF

    def extract_text(self, doc: Document) -> str:
        if not doc.file_path and not doc.content_bytes:
            raise ValueError("Document 缺乏可用之內容來源")

        if doc.file_path:
            with pymupdf.open(str(doc.file_path)) as pdoc:
                if len(pdoc) > self.max_pages:
                    raise FileQuotaExceededError(
                        f"PDF 頁數 ({len(pdoc)} 頁) 超過系統硬上限 ({self.max_pages} 頁)"
                    )
                return "".join(p.get_text("text") for p in pdoc)
        else:
            with pymupdf.open(stream=doc.content_bytes, filetype="pdf") as pdoc:
                if len(pdoc) > self.max_pages:
                    raise FileQuotaExceededError(
                        f"PDF 頁數 ({len(pdoc)} 頁) 超過系統硬上限 ({self.max_pages} 頁)"
                    )
                return "".join(p.get_text("text") for p in pdoc)
