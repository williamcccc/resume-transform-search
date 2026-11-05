from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict
from src.domain.enums import ConversionMode, DocumentHealth, DocumentType
from src.domain.models import (
    QualityReport,
    JudgeScorecard,
    AuditRecord,
    DashboardSummary,
    SystemLogRecord,
    SearchResultItem,
    CandidateSummary,
)


@dataclass
class ConversionCommand:
    """轉換指令資料傳輸物件 (DTO)"""
    file_path: Optional[Path] = None
    file_bytes: Optional[bytes] = None
    filename: Optional[str] = None
    mode: ConversionMode = ConversionMode.AUTO
    api_key: Optional[str] = None
    model_name: Optional[str] = None
    enable_review: bool = False
    enable_judge: bool = False


@dataclass
class ConversionResult:
    """轉換結果資料傳輸物件 (DTO)"""
    success: bool
    markdown: str
    doc_type: DocumentType
    health: DocumentHealth
    model_used: str
    reviewed: bool
    quality_report: Optional[QualityReport] = None
    judge_scorecard: Optional[JudgeScorecard] = None
    error_message: Optional[str] = None


@dataclass
class IndexCommand:
    """向量索引建置指令 DTO"""
    file_path: Optional[Path] = None
    dir_path: Optional[Path] = None
    markdown_text: Optional[str] = None
    candidate_id: Optional[str] = None
    recreate_index: bool = False
    limit: Optional[int] = None
    force: bool = False


@dataclass
class IndexResult:
    """向量索引建置結果 DTO"""
    total_files: int
    indexed_files: int
    total_chunks: int
    errors: list[str]
    skipped_files: int = 0


@dataclass
class DashboardQueryDTO:
    """儀表板資料查詢 DTO"""
    status: Optional[str] = None
    search: Optional[str] = None
    log_level: Optional[str] = None
    log_search: Optional[str] = None
    limit: int = 50
    offset: int = 0
    max_log_lines: int = 200


@dataclass
class DashboardResultDTO:
    """儀表板資料結果 DTO"""
    summary: DashboardSummary
    audit_records: List[AuditRecord]
    total_audit_records: int
    recent_logs: List[SystemLogRecord]
    total_log_records: int


@dataclass
class WebSearchRequestDTO:
    """履歷 Web 複合檢索請求 DTO"""
    query_text: str
    min_years: Optional[float] = None
    skills: List[str] = field(default_factory=list)
    chunk_type: Optional[str] = None
    min_score: float = 0.5
    top_k: int = 20
    group_by_candidate: bool = True


@dataclass
class WebSearchResponseDTO:
    """履歷 Web 複合檢索回傳結果 DTO"""
    total_candidates: int
    total_chunks: int
    query_text: str
    candidates: List[CandidateSummary] = field(default_factory=list)
    raw_chunks: List[SearchResultItem] = field(default_factory=list)




