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
from src.domain.recruitment import (
    CandidateProfile,
    ChatIntent,
    ChatSessionState,
    ChatTurnOutcome,
    FollowupFacts,
    FollowupNarration,
    GeneralQaFacts,
    InterviewFacts,
    InterviewQuestion,
    JdRequirements,
    MatchNarrationFacts,
)


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




# ==========================================
# 招募助手 (ADR-0019) 契約
# ==========================================

class IJdRequirementExtractor(Protocol):
    """JD -> 結構化必要/加分條件抽取器契約"""
    @property
    def extractor_version(self) -> str:
        ...

    def extract(self, jd_text: str, max_must: int) -> JdRequirements:
        ...


class ICandidateProfileExtractor(Protocol):
    """履歷 -> CandidateProfile 延遲結構化抽取器契約"""
    @property
    def extractor_version(self) -> str:
        ...

    def extract(self, candidate_id: str, resume_text: str, content_hash: str) -> CandidateProfile:
        ...


class ICandidateProfileCache(Protocol):
    """候選人 Profile 與 JD 條件之內容 Hash 快取契約"""
    def get_profile(self, candidate_id: str, content_hash: str, extractor_version: str) -> Optional[CandidateProfile]:
        ...

    def set_profile(self, profile: CandidateProfile) -> None:
        ...

    def get_jd(self, jd_hash: str, extractor_version: str) -> Optional[JdRequirements]:
        ...

    def set_jd(self, jd: JdRequirements, extractor_version: str) -> None:
        ...


class IIntentClassifier(Protocol):
    """對話意圖分類器契約 (輸出限 ChatIntent 列舉)"""
    def classify(self, message: str, has_shortlist: bool) -> List[ChatIntent]:
        ...


class IRecruitmentNarrator(Protocol):
    """招募助手敘述器契約 (僅接收代稱與已驗證證據)"""
    def narrate_match(self, facts: MatchNarrationFacts) -> str:
        ...

    def answer_followup(self, facts: FollowupFacts) -> FollowupNarration:
        ...

    def generate_interview_questions(self, facts: InterviewFacts, count: int) -> List[InterviewQuestion]:
        ...

    def answer_general(self, facts: GeneralQaFacts) -> str:
        ...


class IChatOrchestrator(Protocol):
    """多輪對話編排器契約 (可替換編排框架)"""
    def run_turn(self, session_id: str, message: str, trace_id: str) -> ChatTurnOutcome:
        ...

    def get_state(self, session_id: str) -> Optional[ChatSessionState]:
        ...

    def reset(self, session_id: str) -> None:
        ...
