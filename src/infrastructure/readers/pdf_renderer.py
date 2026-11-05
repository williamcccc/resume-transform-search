from typing import List, Optional
import pymupdf
from src.domain.exceptions import FileQuotaExceededError
from src.domain.models import Document
from src.domain.interfaces import IPdfRenderer

MAX_PDF_PAGES = 30


class PdfRenderer(IPdfRenderer):
    """
    使用 PyMuPDF 渲染 PDF 頁面為 PNG 影像位元組
    支援本機路徑與記憶體位元組串流 (Web API 友好)
    內建資源配額防護：超過頁數上限拋出 FileQuotaExceededError (可由建構子動態配置)
    """
    def __init__(self, max_pages: int = MAX_PDF_PAGES, default_dpi: int = 150):
        self.max_pages = max_pages
        self.default_dpi = default_dpi

    def render_pages_to_png(self, doc: Document, dpi: Optional[int] = None) -> List[bytes]:
        if not doc.file_path and not doc.content_bytes:
            raise ValueError("Document 缺乏可用之內容來源")

        target_dpi = dpi if dpi is not None else self.default_dpi
        png_list = []
        if doc.file_path:
            with pymupdf.open(str(doc.file_path)) as pdoc:
                if len(pdoc) > self.max_pages:
                    raise FileQuotaExceededError(
                        f"PDF 頁數 ({len(pdoc)} 頁) 超過系統硬上限 ({self.max_pages} 頁)"
                    )
                for page in pdoc:
                    pix = page.get_pixmap(dpi=target_dpi)
                    png_list.append(pix.tobytes("png"))
        else:
            with pymupdf.open(stream=doc.content_bytes, filetype="pdf") as pdoc:
                if len(pdoc) > self.max_pages:
                    raise FileQuotaExceededError(
                        f"PDF 頁數 ({len(pdoc)} 頁) 超過系統硬上限 ({self.max_pages} 頁)"
                    )
                for page in pdoc:
                    pix = page.get_pixmap(dpi=target_dpi)
                    png_list.append(pix.tobytes("png"))

        return png_list

