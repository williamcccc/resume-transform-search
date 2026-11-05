from typing import List
import pymupdf4llm
from src.domain.models import Document, ConvertedMarkdown
from src.domain.enums import DocumentHealth
from src.domain.interfaces import IMarkdownTransformer


class FastTextTransformer(IMarkdownTransformer):
    """
    使用 PyMuPDF4LLM 進行本機原生純文字與表格快速提取
    """
    def transform_vision(self, page_pngs: List[bytes], doc: Document, enable_review: bool = False) -> ConvertedMarkdown:
        return self.transform_text("", doc, enable_review)

    def transform_text(self, text: str, doc: Document, enable_review: bool = False) -> ConvertedMarkdown:
        if doc.file_path:
            md_text = pymupdf4llm.to_markdown(str(doc.file_path))
        elif doc.content_bytes:
            md_text = pymupdf4llm.to_markdown(doc.get_bytes())
        else:
            md_text = text

        return ConvertedMarkdown(
            content=md_text,
            doc_type=doc.doc_type,
            health=DocumentHealth.HEALTHY,
            model_used="pymupdf4llm",
            reviewed=False
        )
