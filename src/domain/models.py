from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict, Any
from src.domain.enums import DocumentType, DocumentHealth, ChunkType


@dataclass
class Document:
    """
    文件核心領域實體 (同時支援本機路徑與 Web API 記憶體位元組串流)
    """
    filename: str
    doc_type: DocumentType
    file_path: Optional[Path] = None
    content_bytes: Optional[bytes] = None
    health: DocumentHealth = DocumentHealth.HEALTHY

    @classmethod
    def from_path(cls, path: Path) -> "Document":
        suffix = path.suffix.lower().lstrip(".")
        if suffix == "pdf":
            doc_type = DocumentType.PDF
        elif suffix == "docx":
            doc_type = DocumentType.DOCX
        elif suffix == "doc":
            doc_type = DocumentType.DOC
        else:
            doc_type = DocumentType.UNKNOWN

        return cls(
            filename=path.name,
            doc_type=doc_type,
            file_path=path.resolve(),
            content_bytes=None
        )

    @classmethod
    def from_bytes(cls, filename: str, content: bytes) -> "Document":
        suffix = Path(filename).suffix.lower().lstrip(".")
        if suffix == "pdf":
            doc_type = DocumentType.PDF
        elif suffix == "docx":
            doc_type = DocumentType.DOCX
        elif suffix == "doc":
            doc_type = DocumentType.DOC
        else:
            doc_type = DocumentType.UNKNOWN

        return cls(
            filename=filename,
            doc_type=doc_type,
            file_path=None,
            content_bytes=content
        )

    def get_bytes(self) -> bytes:
        if self.content_bytes is not None:
            return self.content_bytes
        if self.file_path and self.file_path.exists():
            return self.file_path.read_bytes()
        raise FileNotFoundError(f"無法讀取文件內容: {self.filename}")


@dataclass
class ConvertedMarkdown:
    """
    轉換結果領域值物件
    """
    content: str
    doc_type: DocumentType
    health: DocumentHealth
    model_used: str
    reviewed: bool
    char_count: int = field(init=False)

    def __post_init__(self):
        self.char_count = len(self.content)


@dataclass
class QualityReport:
    """
    Markdown 品質檢核報告值物件
    """
    is_passed: bool
    score: int  # 0 ~ 100
    warnings: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)
    retention_ratio: Optional[float] = None
    missing_entities: list[str] = field(default_factory=list)

    @property
    def summary_status(self) -> str:
        if not self.is_passed:
            return "FAIL"
        elif self.warnings:
            return "WARNING"
        return "PASS"


@dataclass
class JudgeScorecard:
    """
    獨立客觀評判員 (LLM-as-a-Judge) JSON 評分卡值物件
    """
    overall_score: int          # 總體品質評分 0 ~ 100
    completeness_score: int     # 資訊完整度 0 ~ 100
    fidelity_score: int         # 事實真實度 0 ~ 100 (無幻覺)
    structure_score: int        # 結構規範度 0 ~ 100
    verdict: str                # 評判等級: PASS (>=80), WARNING (60~79), FAIL (<60)
    critique: str               # 評判員總評與缺失摘要
    missing_items: list[str] = field(default_factory=list)      # 遺漏項目清單
    hallucinations: list[str] = field(default_factory=list)     # 幻覺造假項目清單
    raw_json: Optional[str] = None                             # 原始 JSON 字串

    def to_dict(self) -> dict:
        return {
            "overall_score": self.overall_score,
            "completeness_score": self.completeness_score,
            "fidelity_score": self.fidelity_score,
            "structure_score": self.structure_score,
            "verdict": self.verdict,
            "critique": self.critique,
            "missing_items": self.missing_items,
            "hallucinations": self.hallucinations,
        }


@dataclass
class ResumeChunk:
    """
    履歷切片領域實體 (以 Markdown 語意結構為邊界)
    """
    chunk_id: str                              # 唯一鍵: <candidate_id>:<chunk_idx>
    candidate_id: str                          # 候選人 ID (檔案識別名稱)
    candidate_name: str                        # 候選人姓名
    chunk_type: ChunkType                      # 區塊類型 (PROFILE, EXPERIENCE, SKILLS, EDUCATION 等)
    section_title: str                         # 該段大綱標題 (如 "### 科技公司｜後端工程師")
    content: str                               # 原始 Markdown 內文
    skills: List[str] = field(default_factory=list) # 提取之技術標籤 (如 ["python", "docker"])
    company: Optional[str] = None              # 任職公司 (經歷區塊專用)
    job_title: Optional[str] = None            # 職務職稱 (經歷區塊專用)
    vector: Optional[List[float]] = None       # 向量 Embedding (768 維)
    file_path: Optional[str] = None            # 來源檔案路徑
    content_hash: Optional[str] = None         # 區塊/檔案內容雜湊指紋 (SHA-256)


@dataclass
class SearchResultItem:
    """
    語意檢索結果項目
    """
    candidate_id: str
    candidate_name: str
    chunk_type: str
    section_title: str
    content: str
    score: float                               # 語意相似度 (Cosine 相似度，通常 0.0 ~ 1.0)
    company: Optional[str] = None
    job_title: Optional[str] = None
    skills: List[str] = field(default_factory=list)
    file_path: Optional[str] = None


@dataclass
class SearchQuery:
    """
    履歷搜尋查詢條件
    """
    query_text: str                            # 自然語言查詢語句
    top_k: int = 5                             # 回傳最相關的切片數量
    chunk_type: Optional[str] = None           # 指定搜尋區塊 (如 "experience", "skills")
    skills_filter: List[str] = field(default_factory=list) # 指定必備技術標籤 (Tag 混合過濾)
    min_score: float = 0.0                     # 最低相似度門檻 (低於此門檻之切片將被過濾)
    min_years: Optional[float] = None          # 最低工作年資過濾 (如 3.0 代表 3 年以上)


@dataclass
class CandidateSummary:
    """
    求職候選人檢索整合實體 (Group by Candidate)
    """
    candidate_id: str
    candidate_name: str
    max_score: float
    years_of_experience: Optional[float] = None
    experience_raw: Optional[str] = None
    all_skills: List[str] = field(default_factory=list)
    matched_chunks: List[SearchResultItem] = field(default_factory=list)
    file_path: Optional[str] = None



@dataclass
class AuditRecord:
    """
    轉檔品管稽核紀錄項目
    """
    timestamp: str
    filename: str
    status: str
    score: int
    judge_score: str
    model: str
    reviewed: bool
    warnings: str


@dataclass
class DashboardSummary:
    """
    轉檔統計摘要指標
    """
    total_files: int
    success_count: int
    quarantined_count: int
    error_count: int
    success_rate: float
    avg_score: float
    avg_judge_score: float
    model_distribution: Dict[str, int] = field(default_factory=dict)


@dataclass
class SystemLogRecord:
    """
    系統技術日誌紀錄項目
    """
    timestamp: str
    level: str
    logger: str
    message: str


