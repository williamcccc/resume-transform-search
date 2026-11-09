"""
招募助手領域模型 (ADR-0019)

純標準函式庫之實體、值物件與列舉；嚴禁依賴任何第三方 SDK。
明確禁止：任何受保護屬性欄位（年齡、性別、婚姻、照片、國籍、宗教等）。
"""
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Dict, List, Mapping, Optional, Tuple


class RequirementCategory(str, Enum):
    SKILL = "SKILL"
    YEARS = "YEARS"
    LEADERSHIP = "LEADERSHIP"
    TEAM_SIZE = "TEAM_SIZE"
    SENIORITY = "SENIORITY"


class RequirementPriority(str, Enum):
    MUST = "MUST"
    NICE = "NICE"


class MatchStatus(str, Enum):
    MET = "MET"
    UNMET = "UNMET"
    UNKNOWN = "UNKNOWN"


class ChatIntent(str, Enum):
    JD_MATCH = "JD_MATCH"
    CANDIDATE_FOLLOWUP = "CANDIDATE_FOLLOWUP"
    INTERVIEW_QUESTIONS = "INTERVIEW_QUESTIONS"
    GENERAL_QA = "GENERAL_QA"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class SeniorityLevel(IntEnum):
    """確定性比較用之序數階梯"""
    JUNIOR = 1
    MID = 2
    SENIOR = 3
    LEAD = 4
    PRINCIPAL = 5


class AnswerStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    NOT_MENTIONED = "NOT_MENTIONED"
    CONTRADICTED = "CONTRADICTED"


class ReferenceKind(str, Enum):
    RESOLVED = "RESOLVED"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    NO_SHORTLIST = "NO_SHORTLIST"
    NONE = "NONE"


@dataclass(frozen=True)
class JobRequirement:
    requirement_id: str
    category: RequirementCategory
    priority: RequirementPriority
    label: str
    skill: Optional[str] = None
    min_value: Optional[float] = None
    min_level: Optional[SeniorityLevel] = None
    skills: Tuple[str, ...] = ()  # OR 選項：任一命中即 MET（Rev2）；skill 保留為相容欄位 = skills[0]

    @property
    def skill_options(self) -> Tuple[str, ...]:
        """skills 優先；為空時回退 (skill,)；皆無則 ()"""
        if self.skills:
            return tuple(self.skills)
        return (self.skill,) if self.skill else ()


@dataclass(frozen=True)
class SkillMention:
    """履歷全文詞面掃描命中（Rev2）：term 為命中詞、snippet 為所在行片段、ambiguous 表示詞長過短"""
    term: str
    snippet: str
    ambiguous: bool = False


@dataclass(frozen=True)
class JdRequirements:
    jd_hash: str
    title: str
    must: Tuple[JobRequirement, ...]
    nice: Tuple[JobRequirement, ...]
    retrieval_query: str
    ignored_protected_terms: Tuple[str, ...] = ()

    @property
    def all_requirements(self) -> Tuple[JobRequirement, ...]:
        return tuple(self.must) + tuple(self.nice)

    def find(self, requirement_id: str) -> Optional[JobRequirement]:
        for req in self.all_requirements:
            if req.requirement_id == requirement_id:
                return req
        return None


@dataclass(frozen=True)
class EvidenceQuote:
    field: str
    quote: str
    verified: bool = False


@dataclass(frozen=True)
class CandidateProfile:
    candidate_id: str
    content_hash: str
    extractor_version: str
    years_of_experience: Optional[float]
    has_led_team: Optional[bool]
    max_team_size: Optional[int]
    seniority: Optional[SeniorityLevel]
    core_skills: Tuple[str, ...]
    evidence: Tuple[EvidenceQuote, ...]
    degraded: bool = False
    unverified_skills: Tuple[str, ...] = ()   # LLM 宣稱但證據驗證失敗之技能 → 比對為 UNKNOWN


@dataclass(frozen=True)
class CandidateEvaluation:
    candidate_id: str
    candidate_name: str
    semantic_score: float
    statuses: Mapping[str, MatchStatus]
    profile: CandidateProfile
    must_ids: Tuple[str, ...] = ()
    nice_ids: Tuple[str, ...] = ()

    @property
    def fully_qualified(self) -> bool:
        return all(self.statuses.get(rid) == MatchStatus.MET for rid in self.must_ids)

    def count(self, ids: Tuple[str, ...], status: MatchStatus) -> int:
        return sum(1 for rid in ids if self.statuses.get(rid) == status)


@dataclass(frozen=True)
class RequirementEvidence:
    requirement_id: Optional[str]
    field: str
    quote: str
    verified: bool = True


@dataclass(frozen=True)
class ShortlistEntry:
    rank: int
    candidate_id: str
    candidate_name: str
    fully_qualified: bool
    semantic_score: float
    met: Tuple[str, ...]
    unmet: Tuple[str, ...]
    unknown: Tuple[str, ...]
    evidence: Tuple[RequirementEvidence, ...] = ()


@dataclass(frozen=True)
class RelaxationItem:
    requirement_id: str
    label: str
    qualified_if_relaxed: int
    delta: int
    unknown_count: int
    met_count: int = 0


@dataclass(frozen=True)
class RelaxationReport:
    pool_size: int
    baseline_qualified: int
    requested_k: int
    items: Tuple[RelaxationItem, ...]
    bottleneck_requirement_ids: Tuple[str, ...]
    scope_note: str = "僅統計語意檢索候選池 Top-N"
    strictest_requirement_ids: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ReferenceResolution:
    kind: ReferenceKind
    rank: Optional[int] = None
    candidate_id: Optional[str] = None
    shortlist_size: int = 0


@dataclass(frozen=True)
class ChatMessage:
    role: str  # "user" | "assistant"
    content: str


@dataclass
class ChatSessionState:
    """與編排框架狀態互轉之領域表示"""
    session_id: str
    turn_count: int = 0
    jd_requirements: Optional[JdRequirements] = None
    shortlist: Tuple[ShortlistEntry, ...] = ()
    pool_evaluations: Tuple[CandidateEvaluation, ...] = ()
    relaxation: Optional[RelaxationReport] = None
    last_referenced_candidate_id: Optional[str] = None
    history: Tuple[ChatMessage, ...] = ()

    def find_evaluation(self, candidate_id: str) -> Optional[CandidateEvaluation]:
        for ev in self.pool_evaluations:
            if ev.candidate_id == candidate_id:
                return ev
        return None

    def find_shortlist_entry(self, candidate_id: str) -> Optional[ShortlistEntry]:
        for entry in self.shortlist:
            if entry.candidate_id == candidate_id:
                return entry
        return None


# ---------------------------------------------------------------------------
# 送往 LLM 之事實包（Facts）：僅含代稱、已驗證證據與確定性數字，不含姓名與聯絡方式
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CandidateFact:
    alias: str
    fully_qualified: bool
    met_labels: Tuple[str, ...]
    unmet_labels: Tuple[str, ...]
    unknown_labels: Tuple[str, ...]
    evidence_quotes: Tuple[str, ...]


@dataclass(frozen=True)
class MatchNarrationFacts:
    jd_title: str
    requested_k: int
    pool_size: int
    must_labels: Tuple[str, ...]
    nice_labels: Tuple[str, ...]
    candidates: Tuple[CandidateFact, ...]
    relaxation: Optional[RelaxationReport]


@dataclass(frozen=True)
class FollowupFacts:
    alias: str
    question: str
    profile_summary: Mapping[str, str]
    evidence_quotes: Tuple[str, ...]
    met_labels: Tuple[str, ...]
    unmet_labels: Tuple[str, ...]
    unknown_labels: Tuple[str, ...]
    resume_excerpt: str


@dataclass(frozen=True)
class FollowupNarration:
    answer_status: AnswerStatus
    answer_text: str
    quotes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class WeaknessFact:
    requirement_id: str
    label: str
    status: str


@dataclass(frozen=True)
class InterviewFacts:
    alias: str
    weaknesses: Tuple[WeaknessFact, ...]
    strengths: Tuple[str, ...]
    jd_title: str


@dataclass(frozen=True)
class InterviewQuestion:
    no: int
    question: str
    target_requirement_id: str
    rationale: str


@dataclass(frozen=True)
class GeneralQaFacts:
    question: str
    jd_title: Optional[str]
    must_labels: Tuple[str, ...]
    nice_labels: Tuple[str, ...]
    shortlist_aliases: Tuple[str, ...]
    history: Tuple[ChatMessage, ...]


@dataclass(frozen=True)
class FollowupAnswer:
    candidate_rank: Optional[int]
    candidate_id: str
    answer_status: AnswerStatus
    evidence: Tuple[str, ...]


@dataclass
class TurnUsage:
    llm_calls: int = 0
    profile_cache_hits: int = 0
    profile_cache_misses: int = 0
    jd_cache_hit: bool = False
    profile_negative_hits: int = 0


@dataclass
class ChatTurnOutcome:
    session_id: str
    intents: List[ChatIntent]
    reply_markdown: str
    shortlist: Tuple[ShortlistEntry, ...]
    relaxation: Optional[RelaxationReport]
    followup: Optional[FollowupAnswer]
    interview_questions: List[InterviewQuestion]
    warnings: List[str]
    degraded: bool
    usage: TurnUsage
    node_ms: Dict[str, float] = field(default_factory=dict)
