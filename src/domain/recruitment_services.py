"""
招募助手確定性領域服務 (ADR-0019)

全部為純函式 / 無 I/O 之類別：比對、排序、leave-one-out 條件瓶頸、序號指代、
證據逐字驗證、受保護屬性防護、熔斷冷卻、意圖正規化與歷史裁切。
排序、瓶頸與指代皆與 LLM 輸出無關，確保 Prompt Injection 無法影響結果（AC-03、AC-10、AC-18）。
"""
import hashlib
import re
import threading
import time
import unicodedata
from dataclasses import replace
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from src.domain.recruitment import (
    CandidateEvaluation,
    CandidateProfile,
    ChatIntent,
    ChatMessage,
    JdRequirements,
    JobRequirement,
    MatchStatus,
    ReferenceKind,
    ReferenceResolution,
    RelaxationItem,
    RelaxationReport,
    RequirementCategory,
    RequirementEvidence,
    RequirementPriority,
    ShortlistEntry,
)

# 意圖固定優先序（數字越小越先執行）
INTENT_PRIORITY: Dict[ChatIntent, int] = {
    ChatIntent.JD_MATCH: 0,
    ChatIntent.CANDIDATE_FOLLOWUP: 1,
    ChatIntent.INTERVIEW_QUESTIONS: 2,
    ChatIntent.GENERAL_QA: 3,
}

_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_NUM_TOKEN = r"[0-9０-９]+|[零〇一二兩两三四五六七八九十]+"


def compute_content_hash(text: str) -> str:
    """NFKC 正規化後之 SHA-256 內容指紋"""
    normalized = unicodedata.normalize("NFKC", text or "")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def parse_number_token(token: str) -> Optional[int]:
    """解析阿拉伯數字或中文數字（一 ~ 九十九）"""
    if not token:
        return None
    token = unicodedata.normalize("NFKC", token.strip())
    if token.isdigit():
        return int(token)
    if any(ch not in _CN_DIGITS and ch != "十" for ch in token):
        return None
    if "十" not in token:
        if len(token) != 1:
            return None
        return _CN_DIGITS[token]
    head, _, tail = token.partition("十")
    if len(head) > 1 or len(tail) > 1 or "十" in tail:
        return None
    tens = _CN_DIGITS[head] if head else 1
    ones = _CN_DIGITS[tail] if tail else 0
    return tens * 10 + ones


def parse_requested_count(text: str, default: int, maximum: int) -> Tuple[int, bool]:
    """解析「挑 5 個 / 前五名 / 推薦 3 位」；回傳 (人數, 是否超過上限而截斷)"""
    pattern = rf"(?:挑|選|找|推薦|列出|給我|前)\s*({_NUM_TOKEN})\s*(?:個|位|名|人)"
    match = re.search(pattern, text or "")
    value = parse_number_token(match.group(1)) if match else None
    if value is None or value <= 0:
        return default, False
    if value > maximum:
        return maximum, True
    return value, False


def parse_question_count(text: str, default: int, maximum: int) -> Tuple[int, bool]:
    """解析「出 3 題 / 五道題」；回傳 (題數, 是否截斷)"""
    match = re.search(rf"({_NUM_TOKEN})\s*(?:題|道)", text or "")
    value = parse_number_token(match.group(1)) if match else None
    if value is None or value <= 0:
        return default, False
    if value > maximum:
        return maximum, True
    return value, False


def normalize_skill(skill: str, aliases: Mapping[str, str]) -> str:
    """技能正規化：NFKC、小寫、去空白，再套用別名表"""
    key = re.sub(r"\s+", "", unicodedata.normalize("NFKC", skill or "").lower())
    return aliases.get(key, key)


class RequirementMatcher:
    """單一條件 × 單一候選人之三態比對 (MET / UNMET / UNKNOWN)"""

    def __init__(self, skill_aliases: Optional[Mapping[str, str]] = None):
        self._aliases = {
            normalize_skill(k, {}): normalize_skill(v, {}) for k, v in (skill_aliases or {}).items()
        }

    def evaluate(self, req: JobRequirement, profile: CandidateProfile,
                 chunk_skills: Iterable[str] = ()) -> MatchStatus:
        cat = req.category
        if cat == RequirementCategory.SKILL:
            skills = {normalize_skill(s, self._aliases) for s in tuple(profile.core_skills) + tuple(chunk_skills) if s}
            if not req.skill:
                return MatchStatus.UNKNOWN
            target = normalize_skill(req.skill, self._aliases)
            if target in skills:
                return MatchStatus.MET
            unverified = {normalize_skill(s, self._aliases) for s in profile.unverified_skills if s}
            if target in unverified or not skills:
                return MatchStatus.UNKNOWN
            return MatchStatus.UNMET
        if cat == RequirementCategory.YEARS:
            return self._compare(profile.years_of_experience, req.min_value)
        if cat == RequirementCategory.TEAM_SIZE:
            return self._compare(profile.max_team_size, req.min_value)
        if cat == RequirementCategory.LEADERSHIP:
            if profile.has_led_team is None:
                return MatchStatus.UNKNOWN
            return MatchStatus.MET if profile.has_led_team else MatchStatus.UNMET
        if cat == RequirementCategory.SENIORITY:
            if profile.seniority is None:
                return MatchStatus.UNKNOWN
            threshold = int(req.min_level) if req.min_level is not None else 0
            return MatchStatus.MET if int(profile.seniority) >= threshold else MatchStatus.UNMET
        return MatchStatus.UNKNOWN

    @staticmethod
    def _compare(value: Optional[float], minimum: Optional[float]) -> MatchStatus:
        if value is None:
            return MatchStatus.UNKNOWN
        return MatchStatus.MET if float(value) >= float(minimum or 0) else MatchStatus.UNMET

    def evaluate_candidate(self, jd: JdRequirements, candidate_id: str, candidate_name: str,
                           semantic_score: float, profile: CandidateProfile,
                           chunk_skills: Iterable[str] = ()) -> CandidateEvaluation:
        chunk_skills = tuple(chunk_skills)
        statuses = {r.requirement_id: self.evaluate(r, profile, chunk_skills) for r in jd.all_requirements}
        return CandidateEvaluation(
            candidate_id=candidate_id,
            candidate_name=candidate_name,
            semantic_score=float(semantic_score),
            statuses=statuses,
            profile=profile,
            must_ids=tuple(r.requirement_id for r in jd.must),
            nice_ids=tuple(r.requirement_id for r in jd.nice),
        )


class CandidateRanker:
    """確定性排序：(-fully_qualified, -must_met, -nice_met, -semantic_score, candidate_id)"""

    @staticmethod
    def sort_key(ev: CandidateEvaluation):
        return (
            0 if ev.fully_qualified else 1,
            -ev.count(ev.must_ids, MatchStatus.MET),
            -ev.count(ev.nice_ids, MatchStatus.MET),
            -float(ev.semantic_score),
            ev.candidate_id,
        )

    def rank(self, evals: Sequence[CandidateEvaluation], k: int) -> Tuple[ShortlistEntry, ...]:
        ordered = sorted(evals, key=self.sort_key)[: max(k, 0)]
        entries = []
        for idx, ev in enumerate(ordered, start=1):
            ids = tuple(ev.must_ids) + tuple(ev.nice_ids)
            entries.append(
                ShortlistEntry(
                    rank=idx,
                    candidate_id=ev.candidate_id,
                    candidate_name=ev.candidate_name,
                    fully_qualified=ev.fully_qualified,
                    semantic_score=round(float(ev.semantic_score), 4),
                    met=tuple(r for r in ids if ev.statuses.get(r) == MatchStatus.MET),
                    unmet=tuple(r for r in ids if ev.statuses.get(r) == MatchStatus.UNMET),
                    unknown=tuple(r for r in ids if ev.statuses.get(r) == MatchStatus.UNKNOWN),
                )
            )
        return tuple(entries)


class ConstraintRelaxationAnalyzer:
    """逐一放寬必要條件之 leave-one-out 合格人數（UNKNOWN 視為未滿足）"""

    def analyze(self, evals: Sequence[CandidateEvaluation], must: Sequence[JobRequirement],
                k: int) -> RelaxationReport:
        must_ids = [r.requirement_id for r in must]

        def qualified(ev: CandidateEvaluation, skip: Optional[str]) -> bool:
            return all(ev.statuses.get(rid) == MatchStatus.MET for rid in must_ids if rid != skip)

        baseline = sum(1 for ev in evals if qualified(ev, None))
        items = []
        for req in must:
            q_r = sum(1 for ev in evals if qualified(ev, req.requirement_id))
            unknown = sum(1 for ev in evals if ev.statuses.get(req.requirement_id) == MatchStatus.UNKNOWN)
            items.append(RelaxationItem(
                requirement_id=req.requirement_id,
                label=req.label,
                qualified_if_relaxed=q_r,
                delta=q_r - baseline,
                unknown_count=unknown,
            ))
        max_delta = max((i.delta for i in items), default=0)
        bottleneck = tuple(i.requirement_id for i in items if max_delta > 0 and i.delta == max_delta)
        return RelaxationReport(
            pool_size=len(evals),
            baseline_qualified=baseline,
            requested_k=k,
            items=tuple(items),
            bottleneck_requirement_ids=bottleneck,
        )


class OrdinalReferenceResolver:
    """「第N位 / N號 / #N / 他 / 這位」指代解析（純正則，與 LLM 無關）"""

    _ORDINAL_PATTERNS = (
        re.compile(rf"第\s*({_NUM_TOKEN})\s*(?:位|個|名|號)"),
        # 「C# 10」等英數字後接 # 不視為序號
        re.compile(rf"(?<![A-Za-z0-9])[#＃]\s*({_NUM_TOKEN})"),
        # 「3月5號」日期不視為序號：數字前不得為「月」或其他數字
        # 「月」與數字之間允許至多兩個空白仍排除（5 月 3 號、5月　3號）
        re.compile(rf"(?<![月0-9０-９零〇一二兩两三四五六七八九十])(?<!月\s)(?<!月\s\s)({_NUM_TOKEN})\s*號"),
    )
    # 「其他 / 其它」不視為代名詞
    _PRONOUN_PATTERN = re.compile(r"(?<!其)[他她]|這位|这位|該候選人|该候选人|此人|這個人|這名")

    def find_ordinal(self, text: str) -> Optional[int]:
        for pattern in self._ORDINAL_PATTERNS:
            match = pattern.search(text or "")
            if match:
                value = parse_number_token(match.group(1))
                if value is not None:
                    return value
        return None

    def has_pronoun(self, text: str) -> bool:
        return bool(self._PRONOUN_PATTERN.search(text or ""))

    def resolve(self, text: str, shortlist: Sequence[ShortlistEntry],
                last_ref: Optional[str]) -> ReferenceResolution:
        ordinal = self.find_ordinal(text)
        pronoun = self.has_pronoun(text)
        size = len(shortlist)
        if ordinal is None and not pronoun:
            return ReferenceResolution(kind=ReferenceKind.NONE, shortlist_size=size)
        if size == 0:
            return ReferenceResolution(kind=ReferenceKind.NO_SHORTLIST, rank=ordinal, shortlist_size=0)
        if ordinal is not None:
            for entry in shortlist:
                if entry.rank == ordinal:
                    return ReferenceResolution(ReferenceKind.RESOLVED, ordinal, entry.candidate_id, size)
            return ReferenceResolution(kind=ReferenceKind.OUT_OF_RANGE, rank=ordinal, shortlist_size=size)
        if last_ref:
            rank = next((e.rank for e in shortlist if e.candidate_id == last_ref), None)
            return ReferenceResolution(ReferenceKind.RESOLVED, rank, last_ref, size)
        return ReferenceResolution(kind=ReferenceKind.NONE, shortlist_size=size)


class EvidenceVerifier:
    """引文逐字驗證：雙方 NFKC、去 Markdown 標記、去空白後做子字串比對"""

    _MARKDOWN_CHARS = re.compile(r"[\*_`#>\|~]")
    _WHITESPACE = re.compile(r"\s+")

    def __init__(self, min_chars: int):
        self._min_chars = max(int(min_chars), 1)

    def normalize(self, text: str) -> str:
        text = unicodedata.normalize("NFKC", text or "")
        text = self._MARKDOWN_CHARS.sub("", text)
        return self._WHITESPACE.sub("", text)

    def verify(self, quote: Optional[str], resume_text: Optional[str]) -> bool:
        norm_quote = self.normalize(quote or "")
        if len(norm_quote) < self._min_chars:
            return False
        return norm_quote in self.normalize(resume_text or "")


class ProtectedAttributeGuard:
    """受保護屬性防護：條件過濾、履歷欄位行遮蔽、生成內容後置掃描"""

    REDACTED_LINE = "[已遮蔽受保護欄位]"
    REDACTED_CELL = "[已遮蔽]"
    _TABLE_SEPARATOR = re.compile(r"^:?-{3,}:?$")

    def __init__(self, terms: Sequence[str]):
        self._terms = tuple(dict.fromkeys(t.strip() for t in terms if t and t.strip()))
        self._patterns = tuple((t, self._compile(t)) for t in self._terms)

    @staticmethod
    def _compile(term: str) -> "re.Pattern[str]":
        """英文詞彙大小寫不敏感且需字界（避免 age 命中 manage）；中文詞彙採子字串比對"""
        if term.isascii():
            return re.compile(rf"(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])", re.IGNORECASE)
        return re.compile(re.escape(term))

    @property
    def terms(self) -> Tuple[str, ...]:
        return self._terms

    def scan_text(self, text: str) -> List[str]:
        normalized = unicodedata.normalize("NFKC", text or "")
        return [t for t, pattern in self._patterns if pattern.search(normalized)]

    @staticmethod
    def _split_row(line: str) -> List[str]:
        body = line.strip()
        if body.startswith("|"):
            body = body[1:]
        if body.endswith("|"):
            body = body[:-1]
        return [cell.strip() for cell in body.split("|")]

    def _is_separator(self, line: str) -> bool:
        stripped = line.strip()
        if not stripped.startswith("|"):
            return False
        cells = [c for c in self._split_row(stripped) if c]
        return bool(cells) and all(self._TABLE_SEPARATOR.match(c) for c in cells)

    def filter_requirements(self, reqs: Sequence[JobRequirement]) -> Tuple[Tuple[JobRequirement, ...], Tuple[str, ...]]:
        kept, hits = [], []
        for req in reqs:
            matched = self.scan_text(f"{req.label} {req.skill or ''}")
            if matched:
                hits.extend(matched)
            else:
                kept.append(req)
        return tuple(kept), tuple(dict.fromkeys(hits))

    def redact_resume(self, text: str) -> str:
        """一般行/鍵值行（性別：女、Gender: F）命中即整行遮蔽；Markdown 表格依表頭欄位索引整欄遮蔽"""
        lines = (text or "").splitlines()
        out: List[str] = []
        protected_cols: set = set()
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped.startswith("|"):
                protected_cols = set()
                out.append(self.REDACTED_LINE if self.scan_text(line) else line)
                continue
            if self._is_separator(stripped):
                out.append(line)
                continue
            cells = self._split_row(stripped)
            next_line = lines[idx + 1] if idx + 1 < len(lines) else ""
            if self._is_separator(next_line):
                protected_cols = {i for i, cell in enumerate(cells) if self.scan_text(cell)}
                out.append(line)
                continue
            if protected_cols:
                cells = [self.REDACTED_CELL if i in protected_cols else c for i, c in enumerate(cells)]
                line = "| " + " | ".join(cells) + " |"
            out.append(self.REDACTED_LINE if self.scan_text(line) else line)
        return "\n".join(out)


_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# 電話樣式：國際碼 / 台灣手機 / 市話；前後不得緊鄰數字、斜線、連字號或小數點數字，避免誤判 2015/03 - 2020/06 等年月區間
_PHONE = re.compile(
    r"(?<![0-9A-Za-z/\-])(?<!\d\.)(?:"
    r"\+\d{1,3}[\s\-]?\(?\d{1,4}\)?(?:[\s\-]?\d{2,4}){2,4}"
    r"|09\d{2}[\s\-]?\d{3}[\s\-]?\d{3}"
    r"|\(0\d{1,2}\)\s?\d{3,4}[\s\-]?\d{4}"
    r"|0\d{1,2}[\s\-]\d{3,4}[\s\-]?\d{4}"
    r")(?![0-9/\-])(?!\.\d)"
)
_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)


def mask_contact_info(text: str, names: Sequence[str], alias: str) -> str:
    """送 LLM 前遮蔽姓名（替換為代稱）、Email、電話與網址（AC-12）"""
    masked = text or ""
    for name in names:
        if name and len(name.strip()) >= 2:
            masked = masked.replace(name.strip(), alias)
    masked = _EMAIL.sub("[已遮蔽Email]", masked)
    masked = _URL.sub("[已遮蔽連結]", masked)
    masked = _PHONE.sub("[已遮蔽電話]", masked)
    return masked


class CircuitBreaker:
    """LLM 配額熔斷器：429 用罄後冷卻，冷卻期間直接拒絕（AC-31）"""

    def __init__(self, cooldown_seconds: float, clock: Callable[[], float] = time.monotonic):
        self._cooldown = float(cooldown_seconds)
        self._clock = clock
        self._open_until = 0.0
        self._lock = threading.Lock()

    def record_quota_exhausted(self) -> None:
        with self._lock:
            self._open_until = self._clock() + self._cooldown

    def is_open(self) -> bool:
        with self._lock:
            return self._clock() < self._open_until

    def retry_after_seconds(self) -> int:
        with self._lock:
            remaining = self._open_until - self._clock()
        return max(int(remaining + 0.999), 0)


def normalize_intents(intents: Iterable[ChatIntent], max_per_turn: int) -> List[ChatIntent]:
    """去重、依固定優先序排序、截斷；OUT_OF_SCOPE 獨佔"""
    unique = list(dict.fromkeys(intents))
    if not unique:
        return [ChatIntent.GENERAL_QA]
    actionable = [i for i in unique if i != ChatIntent.OUT_OF_SCOPE]
    if not actionable:
        return [ChatIntent.OUT_OF_SCOPE]
    actionable.sort(key=lambda i: INTENT_PRIORITY.get(i, 99))
    return actionable[: max(int(max_per_turn), 1)]


def trim_history(history: Sequence[ChatMessage], max_turns: int, max_chars: int) -> Tuple[ChatMessage, ...]:
    """保留最近 max_turns 輪（每輪 user+assistant 兩則）且總字元不超過 max_chars"""
    kept: List[ChatMessage] = []
    total = 0
    for msg in reversed(list(history)[-max(int(max_turns), 0) * 2:] if max_turns > 0 else []):
        if total + len(msg.content) > max_chars:
            break
        kept.append(msg)
        total += len(msg.content)
    return tuple(reversed(kept))


def renumber_requirements(jd: JdRequirements, max_must: int) -> Tuple[JdRequirements, bool]:
    """由程式依序重編 R1..Rn（不採 LLM 給定值），必要條件超過上限截斷"""
    truncated = len(jd.must) > max_must
    must = list(jd.must)[:max_must]
    renumbered_must, renumbered_nice = [], []
    counter = 1
    for req in must:
        renumbered_must.append(replace(req, requirement_id=f"R{counter}", priority=RequirementPriority.MUST))
        counter += 1
    for req in jd.nice:
        renumbered_nice.append(replace(req, requirement_id=f"R{counter}", priority=RequirementPriority.NICE))
        counter += 1
    return replace(jd, must=tuple(renumbered_must), nice=tuple(renumbered_nice)), truncated


def evidence_field_for(req: JobRequirement, aliases: Mapping[str, str]) -> str:
    if req.category == RequirementCategory.YEARS:
        return "years"
    if req.category == RequirementCategory.LEADERSHIP:
        return "has_led_team"
    if req.category == RequirementCategory.TEAM_SIZE:
        return "team_size"
    if req.category == RequirementCategory.SENIORITY:
        return "seniority"
    return f"skill:{normalize_skill(req.skill or '', aliases)}"


def collect_requirement_evidence(requirements: Sequence[JobRequirement], profile: CandidateProfile,
                                 aliases: Optional[Mapping[str, str]] = None) -> Tuple[RequirementEvidence, ...]:
    """將已驗證之 Profile 證據對應至條件編號；未對應條件之證據 requirement_id 為 None"""
    aliases = aliases or {}
    field_to_req: Dict[str, str] = {}
    for req in requirements:
        field_to_req.setdefault(evidence_field_for(req, aliases), req.requirement_id)
    result = []
    for ev in profile.evidence:
        if not ev.verified:
            continue
        key = ev.field
        if key.startswith("skill:"):
            key = f"skill:{normalize_skill(key[len('skill:'):], aliases)}"
        result.append(RequirementEvidence(requirement_id=field_to_req.get(key), field=ev.field,
                                          quote=ev.quote, verified=True))
    return tuple(result)


_BRACKET_QUOTE = re.compile(r"「([^「」]{1,500})」")


def sanitize_reply_quotes(reply: str, sources: Sequence[str], verifier: EvidenceVerifier,
                          placeholder: str) -> Tuple[str, int]:
    """回覆中「」引文須可於來源中逐字找到，否則以佔位文字取代（AC-08）"""
    removed = 0
    joined = "\n".join(s for s in sources if s)

    def _sub(match: "re.Match[str]") -> str:
        nonlocal removed
        quote = match.group(1)
        normalized = verifier.normalize(quote)
        if normalized and normalized in verifier.normalize(joined):
            return match.group(0)
        removed += 1
        return placeholder

    return _BRACKET_QUOTE.sub(_sub, reply or ""), removed
