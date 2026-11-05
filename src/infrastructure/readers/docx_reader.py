import io
import logging
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from src.domain.models import Document
from src.domain.enums import DocumentType
from src.domain.exceptions import FileQuotaExceededError
from src.domain.interfaces import IDocumentReader

logger = logging.getLogger(__name__)

MAX_EXPANSION_RATIO = 10.0
MAX_UNCOMPRESSED_DOCX_BYTES = 100 * 1024 * 1024  # 100MB


def _validate_docx_zip_safety(
    raw_bytes: bytes,
    max_expansion_ratio: float = MAX_EXPANSION_RATIO,
    max_uncompressed_bytes: int = MAX_UNCOMPRESSED_DOCX_BYTES,
) -> None:
    """檢查 DOCX Zip 封裝包的安全性與膨脹比，杜絕 Zip Bomb 阻斷服務攻擊"""
    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as z:
            total_uncompressed = sum(item.file_size for item in z.infolist())
            compressed_size = max(len(raw_bytes), 1)
            ratio = total_uncompressed / compressed_size
            if total_uncompressed > 5 * 1024 * 1024 and ratio > max_expansion_ratio:
                raise FileQuotaExceededError(
                    f"DOCX 解壓縮膨脹比 ({ratio:.1f}x) 超過上限 ({max_expansion_ratio:.1f}x)，疑似 Zip Bomb 阻斷服務攻擊"
                )
            if total_uncompressed > max_uncompressed_bytes:
                raise FileQuotaExceededError(
                    f"DOCX 解壓縮後總體積 ({total_uncompressed / 1024 / 1024:.1f}MB) 超過上限 ({max_uncompressed_bytes / 1024 / 1024:.0f}MB)"
                )
    except zipfile.BadZipFile:
        pass


def _heal_docx_stream(raw_bytes: bytes) -> io.BytesIO:
    """
    修復 .docx 封裝包中關係定義 (Relationships) 引用但實體缺失的媒體檔案 (如缺少 image4.jpeg)
    在記憶體中為缺失檔案自動注入虛擬空白佔位符，使 python-docx 能順利解析文字與表格，不更動磁碟原始檔案。
    """
    missing_parts = set()

    with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as zin:
        names = set(zin.namelist())
        for fname in names:
            if fname.endswith(".rels"):
                try:
                    tree = ET.fromstring(zin.read(fname))
                    base_dir = "/".join(fname.split("/")[:-1])
                    if base_dir.endswith("_rels"):
                        base_dir = "/".join(base_dir.split("/")[:-1])

                    for rel in tree:
                        if rel.attrib.get("TargetMode") == "External":
                            continue
                        target = rel.attrib.get("Target", "")
                        if not target:
                            continue

                        if target.startswith("/"):
                            resolved = target.lstrip("/")
                        else:
                            resolved = f"{base_dir}/{target}" if base_dir else target
                            parts = []
                            for seg in resolved.split("/"):
                                if seg == "..":
                                    if parts:
                                        parts.pop()
                                elif seg != ".":
                                    parts.append(seg)
                            resolved = "/".join(parts)

                        if resolved not in names:
                            missing_parts.add(resolved)
                except ET.ParseError as pe:
                    logger.warning(f"解析 docx 關聯 XML 失敗 ({fname}): {pe}")
                except Exception as e:
                    logger.warning(f"讀取 docx 關聯檔異常 ({fname}): {e}")

        if not missing_parts:
            return io.BytesIO(raw_bytes)

        out_buf = io.BytesIO()
        with zipfile.ZipFile(out_buf, "w") as zout:
            for item in zin.infolist():
                zout.writestr(item, zin.read(item.filename))
            for m in missing_parts:
                zout.writestr(m, b"")

        out_buf.seek(0)
        return out_buf



class DocxReader(IDocumentReader):
    """
    使用 python-docx 讀取 .docx 文件
    同時支援本機檔案路徑與記憶體位元組串流 (BytesIO，利於 Web API)
    內建自動容錯機制，遇到缺少媒體圖片或破圖時自動修復
    """

    def __init__(
        self,
        max_expansion_ratio: float = MAX_EXPANSION_RATIO,
        max_uncompressed_bytes: int = MAX_UNCOMPRESSED_DOCX_BYTES,
    ):
        self.max_expansion_ratio = max_expansion_ratio
        self.max_uncompressed_bytes = max_uncompressed_bytes

    def can_read(self, doc: Document) -> bool:
        return doc.doc_type == DocumentType.DOCX

    def extract_text(self, doc: Document) -> str:
        try:
            import docx
        except ImportError:
            raise RuntimeError("解析 .docx 檔案需要 python-docx 套件，請執行: pip install python-docx")

        if doc.file_path:
            with open(doc.file_path, "rb") as f:
                raw_bytes = f.read()
        elif doc.content_bytes:
            raw_bytes = doc.content_bytes
        else:
            raise ValueError("Document 缺乏可用之內容來源")

        # 先驗證 DOCX 封裝包的解壓膨脹比與 Zip Bomb 安全性
        _validate_docx_zip_safety(
            raw_bytes,
            max_expansion_ratio=self.max_expansion_ratio,
            max_uncompressed_bytes=self.max_uncompressed_bytes,
        )

        try:
            d = docx.Document(io.BytesIO(raw_bytes))
        except (KeyError, Exception) as e:
            if isinstance(e, FileQuotaExceededError):
                raise e
            # 若因缺少內部媒體元件導致 KeyError: "There is no item named '...' in the archive"
            # 呼叫自動補樁修復函式重試
            try:
                repaired_buf = _heal_docx_stream(raw_bytes)
                d = docx.Document(repaired_buf)
            except Exception as repair_err:
                raise e from repair_err


        lines = []
        for el in d.element.body:
            tag = el.tag.split("}")[-1]
            if tag == "p":
                p_obj = docx.text.paragraph.Paragraph(el, d)
                txt = p_obj.text.replace("\xa0", " ").strip()
                if txt:
                    lines.append(txt)
            elif tag == "tbl":
                tbl = docx.table.Table(el, d)
                for row in tbl.rows:
                    cells = [
                        c.text.replace("\xa0", " ").strip().replace("\n", " ")
                        for c in row.cells
                    ]
                    # 去除跨欄造成的連續重複儲存格
                    seen = []
                    for c in cells:
                        if not seen or c != seen[-1]:
                            seen.append(c)
                    if any(seen):
                        lines.append(" | ".join(seen))

        return "\n\n".join(lines)
