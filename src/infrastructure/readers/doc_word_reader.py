import logging
import tempfile
from pathlib import Path
from src.domain.models import Document
from src.domain.enums import DocumentType
from src.domain.interfaces import IDocumentReader

logger = logging.getLogger(__name__)


class DocWordReader(IDocumentReader):
    """
    透過 Windows Word COM 物件讀取舊版 .doc 檔案
    """
    def can_read(self, doc: Document) -> bool:
        return doc.doc_type == DocumentType.DOC

    def extract_text(self, doc: Document) -> str:
        try:
            import win32com.client
        except ImportError:
            raise RuntimeError("讀取 .doc 檔案需要 pywin32 套件，請執行: pip install pywin32")

        temp_file = None
        if doc.file_path:
            target_path = doc.file_path.resolve()
        else:
            # 若為記憶體位元組，寫入暫存檔以供 Word COM 開啟
            temp_file = tempfile.NamedTemporaryFile(suffix=".doc", delete=False)
            temp_file.write(doc.get_bytes())
            temp_file.close()
            target_path = Path(temp_file.name).resolve()

        word = win32com.client.Dispatch("Word.Application")
        word.Visible = False
        try:
            wdoc = word.Documents.Open(str(target_path))
            text = wdoc.Content.Text
            wdoc.Close(False)
            return text.replace("\xa0", " ").strip()
        finally:
            word.Quit()
            if temp_file:
                try:
                    Path(temp_file.name).unlink(missing_ok=True)
                except OSError as err:
                    logger.debug(f"清理 Windows 暫存檔失敗: {err}")
