from pathlib import Path
from typing import Protocol, List, Optional
from src.domain.models import (
    Document,
    ConvertedMarkdown,
    QualityReport,
    JudgeScorecard,
    ResumeChunk,
    SearchQuery,
    SearchResultItem,
    AuditRecord,
    DashboardSummary,
    SystemLogRecord,
)
from src.domain.enums import DocumentHealth


class IDocumentReader(Protocol):
    """文件讀取器契約"""
    def can_read(self, doc: Document) -> bool:
        ...

    def extract_text(self, doc: Document) -> str:
        ...


class IPdfRenderer(Protocol):
    """PDF 影像渲染器契約"""
    def render_pages_to_png(self, doc: Document, dpi: int = 150) -> List[bytes]:
        ...


class IPdfHealthProbe(Protocol):
    """PDF 健康度探測契約"""
    def probe(self, doc: Document) -> DocumentHealth:
        ...


class IMarkdownTransformer(Protocol):
    """Markdown 轉換器契約"""
    def transform_vision(self, page_pngs: List[bytes], doc: Document, enable_review: bool) -> ConvertedMarkdown:
        ...

    def transform_text(self, text: str, doc: Document, enable_review: bool) -> ConvertedMarkdown:
        ...


class IQualityValidator(Protocol):
    """品質品管檢核契約"""
    def validate(self, markdown: str, raw_text: Optional[str], doc: Document) -> QualityReport:
        ...


class ILlmJudge(Protocol):
    """獨立客觀評判員 (LLM-as-a-Judge) 契約"""
    def judge_document(
        self,
        markdown: str,
        doc: Document,
        page_pngs: Optional[List[bytes]] = None,
        raw_text: Optional[str] = None
    ) -> JudgeScorecard:
        ...


class IMarkdownChunker(Protocol):
    """履歷 Markdown 語意切片器契約"""
    def chunk_markdown(self, markdown: str, candidate_id: str, file_path: Optional[str] = None) -> List[ResumeChunk]:
        ...


class IEmbeddingService(Protocol):
    """文本向量化服務契約"""
    def embed_texts(self, texts: List[str], task_type: str = "retrieval_document") -> List[List[float]]:
        ...

    def embed_query(self, query: str) -> List[float]:
        ...


class IVectorStore(Protocol):
    """向量資料庫儲存與檢索契約"""
    def ensure_index(self, dim: int = 768) -> None:
        ...

    def upsert_chunks(self, chunks: List[ResumeChunk]) -> int:
        ...

    def search(self, query_vector: List[float], query: SearchQuery) -> List[SearchResultItem]:
        ...

    def delete_by_candidate(self, candidate_id: str) -> int:
        ...

    def get_candidate_hash(self, candidate_id: str) -> Optional[str]:
        ...

    def set_candidate_hash(self, candidate_id: str, content_hash: str) -> None:
        ...


class IAuditLogReader(Protocol):
    """轉檔稽核日誌讀取器契約"""
    def read_audit_records(self, csv_path: Path) -> List[AuditRecord]:
        ...


class ISystemLogReader(Protocol):
    """系統技術日誌讀取器契約"""
    def read_recent_logs(self, log_path: Path, max_lines: int = 1000) -> List[SystemLogRecord]:
        ...


class IExperienceParser(Protocol):
    """履歷年資解析器契約"""
    def parse(self, text: str) -> tuple[Optional[float], Optional[str]]:
        ...


