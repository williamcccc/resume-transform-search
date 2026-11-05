from typing import List, Optional
from src.application.dto import ConversionCommand, ConversionResult
from src.domain.enums import ConversionMode, DocumentHealth, DocumentType
from src.domain.exceptions import (
    DocumentNotFoundError,
    UnsupportedDocumentTypeError,
    ConversionError,
    FileQuotaExceededError,
    DomainError,
)
from src.domain.interfaces import (
    IDocumentReader,
    IPdfRenderer,
    IPdfHealthProbe,
    IMarkdownTransformer,
    IQualityValidator,
    ILlmJudge,
)
from src.domain.models import Document, ConvertedMarkdown, QualityReport, JudgeScorecard


class ConvertDocumentUseCase:
    """
    文件轉換核心使用案例 (Use Case)
    負責接收 Command，調度 Probe 診斷健康度，分流至適當 Transformer，並執行品管檢核與獨立評判 (Guardrail & Judge)。
    完全遵循整潔架構 (Clean Architecture)，嚴禁直接依賴任何外部第三方套件。
    """
    def __init__(
        self,
        word_readers: Optional[List[IDocumentReader]] = None,
        pdf_renderer: Optional[IPdfRenderer] = None,
        pdf_probe: Optional[IPdfHealthProbe] = None,
        gemini_transformer: Optional[IMarkdownTransformer] = None,
        rapid_ocr_transformer: Optional[IMarkdownTransformer] = None,
        fast_transformer: Optional[IMarkdownTransformer] = None,
        quality_validator: Optional[IQualityValidator] = None,
        llm_judge: Optional[ILlmJudge] = None,
        readers: Optional[List[IDocumentReader]] = None,
        max_file_size_mb: int = 25,
        pdf_render_dpi: int = 150,
        pdf_ocr_dpi: int = 200,
        pdf_text_first_min_chars: int = 50,
    ):
        # 整合所有文件讀取器 (向後相容 word_readers 參數)
        all_readers: List[IDocumentReader] = []
        if readers:
            all_readers.extend(readers)
        if word_readers:
            for r in word_readers:
                if r not in all_readers:
                    all_readers.append(r)

        self.readers = all_readers
        self.pdf_renderer = pdf_renderer
        self.pdf_probe = pdf_probe
        self.gemini_transformer = gemini_transformer
        self.rapid_ocr_transformer = rapid_ocr_transformer
        self.fast_transformer = fast_transformer
        self.quality_validator = quality_validator
        self.llm_judge = llm_judge
        self.max_file_size_mb = max_file_size_mb
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024
        self.pdf_render_dpi = pdf_render_dpi
        self.pdf_ocr_dpi = pdf_ocr_dpi
        self.pdf_text_first_min_chars = pdf_text_first_min_chars

    def execute(self, command: ConversionCommand) -> ConversionResult:
        # 1. 建立 Document 實體並實施資源硬上限安全檢查
        if command.file_path:
            if not command.file_path.exists():
                raise DocumentNotFoundError(f"找不到指定檔案: {command.file_path}")
            if command.file_path.stat().st_size > self.max_file_size_bytes:
                raise FileQuotaExceededError(
                    f"檔案大小 ({command.file_path.stat().st_size / (1024 * 1024):.1f}MB) 超過系統硬上限 ({self.max_file_size_mb}MB)"
                )
            doc = Document.from_path(command.file_path)
        elif command.file_bytes and command.filename:
            if len(command.file_bytes) > self.max_file_size_bytes:
                raise FileQuotaExceededError(
                    f"檔案大小 ({len(command.file_bytes) / (1024 * 1024):.1f}MB) 超過系統硬上限 ({self.max_file_size_mb}MB)"
                )
            doc = Document.from_bytes(command.filename, command.file_bytes)
        else:
            raise ValueError("必須提供 file_path 或 (file_bytes 與 filename)")

        if doc.doc_type == DocumentType.UNKNOWN:
            raise UnsupportedDocumentTypeError(f"不支援的檔案格式: {doc.filename}")

        has_gemini = bool(command.api_key and self.gemini_transformer)
        raw_source_text: Optional[str] = None

        # 2. 處理 Word 文件 (.docx, .doc)
        if doc.doc_type in (DocumentType.DOCX, DocumentType.DOC):
            reader = next((r for r in self.readers if r.can_read(doc)), None)
            if not reader:
                raise ConversionError(f"未找到支援此 Word 格式的讀取器: {doc.filename}")

            raw_source_text = reader.extract_text(doc)

            if command.mode in (ConversionMode.GEMINI, ConversionMode.AUTO) and has_gemini:
                converted = self.gemini_transformer.transform_text(
                    text=raw_source_text,
                    doc=doc,
                    enable_review=command.enable_review
                )
            else:
                converted = ConvertedMarkdown(
                    content=raw_source_text,
                    doc_type=doc.doc_type,
                    health=DocumentHealth.HEALTHY,
                    model_used="native_word_extract",
                    reviewed=False
                )

            return self._build_result(converted, raw_source_text, doc, command, page_pngs=None)

        # 3. 處理 PDF 文件 (.pdf)
        elif doc.doc_type == DocumentType.PDF:
            # 透過基礎設施層注入之 Reader 提取原生文字層 (若可用)，嚴禁在 Use Case 直接 import pymupdf
            pdf_reader = next((r for r in self.readers if r.can_read(doc)), None)
            if pdf_reader:
                try:
                    raw_source_text = pdf_reader.extract_text(doc)
                except DomainError as de:
                    raise de
                except Exception:
                    raw_source_text = None
            else:
                raw_source_text = None

            # 強制指定模式分流
            if command.mode == ConversionMode.OCR:
                pages = self.pdf_renderer.render_pages_to_png(doc, dpi=self.pdf_ocr_dpi)
                converted = self.rapid_ocr_transformer.transform_vision(pages, doc, enable_review=False)
                return self._build_result(converted, raw_source_text, doc, command, page_pngs=pages)

            elif command.mode == ConversionMode.FAST:
                converted = self.fast_transformer.transform_text("", doc, enable_review=False)
                return self._build_result(converted, raw_source_text, doc, command, page_pngs=None)

            elif command.mode == ConversionMode.GEMINI:
                if not has_gemini:
                    raise ConversionError("已指定 Gemini 模式，但未提供有效的 GEMINI_API_KEY")
                pages = self.pdf_renderer.render_pages_to_png(doc, dpi=self.pdf_render_dpi)
                converted = self.gemini_transformer.transform_vision(pages, doc, enable_review=command.enable_review)
                return self._build_result(converted, raw_source_text, doc, command, page_pngs=pages)

            # 智慧自動模式 (AUTO)
            health = self.pdf_probe.probe(doc)
            doc.health = health
            pages = None


            if health in (DocumentHealth.SCANNED, DocumentHealth.OBFUSCATED):
                if has_gemini:
                    pages = self.pdf_renderer.render_pages_to_png(doc, dpi=self.pdf_render_dpi)
                    converted = self.gemini_transformer.transform_vision(pages, doc, enable_review=command.enable_review)
                else:
                    pages = self.pdf_renderer.render_pages_to_png(doc, dpi=self.pdf_ocr_dpi)
                    converted = self.rapid_ocr_transformer.transform_vision(pages, doc, enable_review=False)
            else:
                # 健康文字 PDF：優先採取 Text-First 策略，大幅節省 Vision 圖片 Token 並消除 OCR 錯字風險
                if has_gemini and raw_source_text and len(raw_source_text.strip()) > self.pdf_text_first_min_chars:
                    try:
                        converted = self.gemini_transformer.transform_text(
                            raw_source_text, doc, enable_review=command.enable_review
                        )
                    except Exception as ge:
                        # 若純文字轉換異常，優雅降級走多模態圖片視覺辨識
                        pages = self.pdf_renderer.render_pages_to_png(doc, dpi=self.pdf_render_dpi)
                        converted = self.gemini_transformer.transform_vision(
                            pages, doc, enable_review=command.enable_review
                        )
                elif has_gemini:
                    # 文字層不足或無文字層，退回渲染影像視覺轉換
                    pages = self.pdf_renderer.render_pages_to_png(doc, dpi=self.pdf_render_dpi)
                    converted = self.gemini_transformer.transform_vision(pages, doc, enable_review=command.enable_review)
                else:
                    converted = self.fast_transformer.transform_text("", doc, enable_review=False)

            return self._build_result(converted, raw_source_text, doc, command, page_pngs=pages)

        raise UnsupportedDocumentTypeError(f"無法處理此文件類型: {doc.doc_type}")

    def _build_result(
        self,
        converted: ConvertedMarkdown,
        raw_source_text: Optional[str],
        doc: Document,
        command: ConversionCommand,
        page_pngs: Optional[List[bytes]] = None,
    ) -> ConversionResult:
        # 防線一：確定性規則品管閥檢核
        quality_report: Optional[QualityReport] = None
        if self.quality_validator:
            quality_report = self.quality_validator.validate(
                markdown=converted.content,
                raw_text=raw_source_text,
                doc=doc
            )

        # 防線二：獨立客觀評審員 (LLM-as-a-Judge) 輸出 JSON 評分卡
        judge_scorecard: Optional[JudgeScorecard] = None
        if command.enable_judge and self.llm_judge:
            judge_scorecard = self.llm_judge.judge_document(
                markdown=converted.content,
                doc=doc,
                page_pngs=page_pngs,
                raw_text=raw_source_text
            )

        return ConversionResult(
            success=True,
            markdown=converted.content,
            doc_type=converted.doc_type,
            health=converted.health,
            model_used=converted.model_used,
            reviewed=converted.reviewed,
            quality_report=quality_report,
            judge_scorecard=judge_scorecard,
        )

