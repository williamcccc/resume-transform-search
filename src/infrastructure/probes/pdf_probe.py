import pymupdf
import pymupdf4llm
from src.domain.models import Document
from src.domain.enums import DocumentHealth
from src.domain.interfaces import IPdfHealthProbe


class PdfHealthProbe(IPdfHealthProbe):
    """
    診斷 PDF 文字層健康度：
    - HEALTHY: 正常文字層
    - SCANNED: 純掃描檔 (字數少於 scanned_min_chars)
    - OBFUSCATED: 104 防爬混淆字型 (大量 \ufffd 或 ~~ 標記)
    """
    def __init__(
        self,
        scanned_min_chars: int = 30,
        ufffd_threshold: int = 10,
        strikethrough_threshold: int = 30,
    ):
        self.scanned_min_chars = scanned_min_chars
        self.ufffd_threshold = ufffd_threshold
        self.strikethrough_threshold = strikethrough_threshold

    def probe(self, doc: Document) -> DocumentHealth:
        try:
            if not doc.file_path and not doc.content_bytes:
                return DocumentHealth.HEALTHY

            total_text = ""
            if doc.file_path:
                with pymupdf.open(str(doc.file_path)) as pdoc:
                    if len(pdoc) == 0:
                        return DocumentHealth.HEALTHY
                    total_text = "".join(p.get_text("text") for p in pdoc[:2])
            else:
                with pymupdf.open(stream=doc.content_bytes, filetype="pdf") as pdoc:
                    if len(pdoc) == 0:
                        return DocumentHealth.HEALTHY
                    total_text = "".join(p.get_text("text") for p in pdoc[:2])

            if len(total_text.strip()) < self.scanned_min_chars:
                return DocumentHealth.SCANNED

            # 檢測 104 典型混淆特徵：大量替代字元或異常字碼
            if doc.file_path:
                sample_md = pymupdf4llm.to_markdown(str(doc.file_path), pages=[0])
            else:
                sample_md = pymupdf4llm.to_markdown(doc.get_bytes(), pages=[0])

            ufffd_count = sample_md.count("\ufffd")
            strikethrough_count = sample_md.count("~~")

            if ufffd_count > self.ufffd_threshold or strikethrough_count > self.strikethrough_threshold:
                return DocumentHealth.OBFUSCATED

            return DocumentHealth.HEALTHY

        except Exception:
            return DocumentHealth.HEALTHY
