from typing import List
from src.domain.models import Document, ConvertedMarkdown
from src.domain.enums import DocumentHealth
from src.domain.interfaces import IMarkdownTransformer


class RapidOcrTransformer(IMarkdownTransformer):
    """
    使用本機 RapidOCR 進行純離線光學字元辨識
    """
    def __init__(self):
        try:
            from rapidocr_onnxruntime import RapidOCR
            self.ocr = RapidOCR()
        except ImportError:
            self.ocr = None

    def transform_vision(self, page_pngs: List[bytes], doc: Document, enable_review: bool = False) -> ConvertedMarkdown:
        if self.ocr is None:
            raise RuntimeError("尚未安裝 rapidocr-onnxruntime，請先執行: pip install rapidocr-onnxruntime")

        pages_content = []
        for png_bytes in page_pngs:
            result, _ = self.ocr(png_bytes)
            lines = [item[1].strip() for item in result] if result else []
            pages_content.append("\n\n".join(lines))

        full_md = "\n\n---\n\n".join(pages_content)
        return ConvertedMarkdown(
            content=full_md,
            doc_type=doc.doc_type,
            health=doc.health if doc.health != DocumentHealth.HEALTHY else DocumentHealth.SCANNED,
            model_used="rapidocr-onnxruntime",
            reviewed=False
        )

    def transform_text(self, text: str, doc: Document, enable_review: bool = False) -> ConvertedMarkdown:
        return ConvertedMarkdown(
            content=text,
            doc_type=doc.doc_type,
            health=doc.health,
            model_used="rapidocr-onnxruntime",
            reviewed=False
        )
