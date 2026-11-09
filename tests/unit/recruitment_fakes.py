"""
招募助手單元測試共用 Fake 樁件 (100% 記憶體、零網路、零 Redis、零 API Key)

所有履歷、姓名與公司皆為虛構範例，於記憶體動態建構，嚴禁讀取 data/ 或 resume/。
"""
import threading
from dataclasses import replace
from typing import Dict, List, Optional

from src.application.candidate_profile_service import CandidateProfileService
from src.application.recruitment_nodes import RecruitmentNodeHandlers
from src.application.recruitment_settings import RecruitmentSettings
from src.application.recruitment_tools import RecruitmentTools
from src.domain.models import SearchResultItem
from src.domain.recruitment import (
    AnswerStatus,
    CandidateProfile,
    ChatIntent,
    EvidenceQuote,
    FollowupNarration,
    InterviewQuestion,
    JdRequirements,
    JobRequirement,
    RequirementCategory,
    RequirementPriority,
)
from src.domain.recruitment_services import EvidenceVerifier, ProtectedAttributeGuard

PROTECTED_TERMS = ("年齡", "歲", "出生", "性別", "男性", "女性", "婚姻", "已婚", "未婚", "照片")

JD_TEXT = (
    "【職缺】資深後端工程師 JD\n"
    "工作內容：負責高併發交易系統之後端服務設計與開發，與產品團隊協作規劃架構演進。\n"
    "必要條件：精通 Python、具 5 年以上後端開發經驗、具帶領團隊經驗。\n"
    "加分條件：熟悉 Kubernetes 容器化部署。\n"
    "請幫我從資料庫挑 3 個最適合的人，告訴我為什麼推薦；人選不夠就告訴我哪個條件太嚴格。"
    + "補充說明：本職缺重視系統設計能力與跨部門溝通，" * 4
)

RESUMES: Dict[str, Dict] = {
    "cand_a": {
        "name": "王小明",
        "score": 0.91,
        "skills": ["python", "redis"],
        "text": "# 王小明\n- Email：sample_a@example.com\n- 性別：男\n- 工作經歷：8年工作經驗\n"
                "## 經歷\n擔任技術主管，帶領 6 人後端團隊完成交易系統重構。\n主要使用 Python 與 Redis 開發微服務。",
        "profile": dict(years=8.0, years_quote="8年工作經驗", led=True, led_quote="帶領 6 人後端團隊",
                        team=6, skills={"python": "Python 與 Redis"}),
    },
    "cand_b": {
        "name": "李小華",
        "score": 0.88,
        "skills": ["python", "kubernetes"],
        "text": "# 李小華\n- 工作經歷：6年工作經驗\n## 經歷\n負責 Python 後端 API 開發與 Kubernetes 部署維運。",
        "profile": dict(years=6.0, years_quote="6年工作經驗", led=None, led_quote=None, team=None,
                        skills={"python": "Python 後端 API 開發", "kubernetes": "Kubernetes 部署維運"}),
    },
    "cand_c": {
        "name": "陳大文",
        "score": 0.85,
        "skills": ["python"],
        "text": "# 陳大文\n- 工作經歷：3年工作經驗\n## 經歷\n帶領 3 人小組開發 Python 數據服務。",
        "profile": dict(years=3.0, years_quote="3年工作經驗", led=True, led_quote="帶領 3 人小組", team=3,
                        skills={"python": "Python 數據服務"}),
    },
    "cand_d": {
        "name": "林美玲",
        "score": 0.80,
        "skills": ["java"],
        "text": "# 林美玲\n- 工作經歷：10年工作經驗\n## 經歷\n擔任部門經理，帶領 12 人 Java 團隊。",
        "profile": dict(years=10.0, years_quote="10年工作經驗", led=True, led_quote="帶領 12 人 Java 團隊",
                        team=12, skills={"java": "Java 團隊"}),
    },
}


def make_settings(**overrides) -> RecruitmentSettings:
    base = RecruitmentSettings(
        jd_intent_min_chars=100,
        protected_attr_terms=PROTECTED_TERMS,
        skill_aliases={"k8s": "kubernetes"},
        profile_max_concurrency=2,
    )
    return replace(base, **overrides)


def make_jd(extra_must: List[JobRequirement] = ()) -> JdRequirements:
    must = [
        JobRequirement("x1", RequirementCategory.SKILL, RequirementPriority.MUST, "精通 Python", skill="python"),
        JobRequirement("x2", RequirementCategory.YEARS, RequirementPriority.MUST, "5 年以上後端經驗", min_value=5),
        JobRequirement("x3", RequirementCategory.LEADERSHIP, RequirementPriority.MUST, "具帶領團隊經驗"),
        *extra_must,
    ]
    nice = [JobRequirement("x4", RequirementCategory.SKILL, RequirementPriority.NICE, "熟悉 Kubernetes",
                           skill="k8s")]
    return JdRequirements(jd_hash="", title="資深後端工程師", must=tuple(must), nice=tuple(nice),
                          retrieval_query="資深 Python 後端工程師 帶領團隊")


class FakeSearch:
    """模擬 SearchResumesUseCase 之 execute_grouped_by_candidate / get_resume_markdown"""

    def __init__(self, resumes: Optional[Dict[str, Dict]] = None):
        self.resumes = {k: dict(v) for k, v in (resumes if resumes is not None else RESUMES).items()}
        self.queries = []

    def execute_grouped_by_candidate(self, query):
        self.queries.append(query)
        rows = []
        for cid, r in self.resumes.items():
            chunk = SearchResultItem(candidate_id=cid, candidate_name=r["name"], chunk_type="experience",
                                     section_title="經歷", content=r["text"], score=r["score"], skills=r["skills"])
            rows.append({"candidate_id": cid, "candidate_name": r["name"], "max_score": r["score"],
                         "matched_chunks": [chunk], "all_skills": sorted(r["skills"]), "file_path": None})
        rows.sort(key=lambda x: x["max_score"], reverse=True)
        return rows

    def get_resume_markdown(self, candidate_id):
        r = self.resumes.get(candidate_id)
        return r["text"] if r else None


class FakeProfileExtractor:
    def __init__(self, version: str = "v-test", fail_for=(), raise_exc: Optional[Exception] = None):
        self._version = version
        self.fail_for = set(fail_for)
        self.raise_exc = raise_exc
        self.calls: List[str] = []
        self.texts: Dict[str, str] = {}
        self._lock = threading.Lock()

    @property
    def extractor_version(self) -> str:
        return self._version

    def extract(self, candidate_id: str, resume_text: str, content_hash: str) -> CandidateProfile:
        with self._lock:
            self.calls.append(candidate_id)
            self.texts[candidate_id] = resume_text
        if self.raise_exc is not None:
            raise self.raise_exc
        if candidate_id in self.fail_for:
            raise RuntimeError("simulated extraction failure")
        spec = RESUMES[candidate_id]["profile"]
        evidence = [EvidenceQuote("years", spec["years_quote"])]
        if spec["led_quote"]:
            evidence.append(EvidenceQuote("has_led_team", spec["led_quote"]))
            evidence.append(EvidenceQuote("team_size", spec["led_quote"]))
        for skill, quote in spec["skills"].items():
            evidence.append(EvidenceQuote(f"skill:{skill}", quote))
        return CandidateProfile(
            candidate_id=candidate_id, content_hash=content_hash, extractor_version=self._version,
            years_of_experience=spec["years"], has_led_team=spec["led"], max_team_size=spec["team"],
            seniority=None, core_skills=tuple(spec["skills"].keys()), evidence=tuple(evidence),
        )


class InMemoryProfileCache:
    def __init__(self):
        self.profiles: Dict[str, CandidateProfile] = {}
        self.jds: Dict[str, JdRequirements] = {}
        self.set_calls = 0

    def get_profile(self, candidate_id, content_hash, extractor_version):
        p = self.profiles.get(f"{extractor_version}:{candidate_id}")
        return p if p and p.content_hash == content_hash else None

    def set_profile(self, profile):
        self.set_calls += 1
        self.profiles[f"{profile.extractor_version}:{profile.candidate_id}"] = profile

    def get_jd(self, jd_hash, extractor_version):
        return self.jds.get(f"{extractor_version}:{jd_hash}")

    def set_jd(self, jd, extractor_version):
        self.jds[f"{extractor_version}:{jd.jd_hash}"] = jd


class FakeJdExtractor:
    def __init__(self, jd: Optional[JdRequirements] = None, version: str = "v-test", raise_exc=None):
        self.jd = jd or make_jd()
        self._version = version
        self.calls = 0
        self.raise_exc = raise_exc

    @property
    def extractor_version(self):
        return self._version

    def extract(self, jd_text, max_must):
        self.calls += 1
        if self.raise_exc is not None:
            raise self.raise_exc
        return self.jd


class FakeClassifier:
    def __init__(self, intents=None, raise_exc=None):
        self.intents = intents or [ChatIntent.GENERAL_QA]
        self.calls: List[str] = []
        self.raise_exc = raise_exc

    def classify(self, message, has_shortlist):
        self.calls.append(message)
        if self.raise_exc is not None:
            raise self.raise_exc
        return list(self.intents)


class FakeNarrator:
    def __init__(self):
        self.match_facts = []
        self.followup_facts = []
        self.interview_facts = []
        self.general_facts = []
        self.match_text = "候選人 #1 符合「帶領 6 人後端團隊」。"
        self.followup_result: Optional[FollowupNarration] = None
        self.question_batches: List[List[InterviewQuestion]] = []
        self.raise_on = set()
        self.raise_exc: Exception = RuntimeError("narrator down")

    def _maybe_raise(self, name):
        if name in self.raise_on:
            raise self.raise_exc

    def narrate_match(self, facts):
        self.match_facts.append(facts)
        self._maybe_raise("match")
        return self.match_text

    def answer_followup(self, facts):
        self.followup_facts.append(facts)
        self._maybe_raise("followup")
        return self.followup_result or FollowupNarration(AnswerStatus.NOT_MENTIONED, "履歷未提及。", ())

    def generate_interview_questions(self, facts, count):
        self.interview_facts.append(facts)
        self._maybe_raise("interview")
        if self.question_batches:
            return self.question_batches.pop(0)
        return [InterviewQuestion(i + 1, f"請說明您在{w.label}的經驗？", w.requirement_id, "驗證弱點")
                for i, w in enumerate(facts.weaknesses[:count])]

    def answer_general(self, facts):
        self.general_facts.append(facts)
        self._maybe_raise("general")
        return "目前必要條件為：" + "、".join(facts.must_labels)


def build_handlers(settings=None, search=None, profile_extractor=None, cache=None, jd_extractor=None,
                   classifier=None, narrator=None, clock=None):
    settings = settings or make_settings()
    search = search or FakeSearch()
    tools = RecruitmentTools(search, experience_parser=None)
    guard = ProtectedAttributeGuard(settings.protected_attr_terms)
    cache = cache if cache is not None else InMemoryProfileCache()
    profile_extractor = profile_extractor or FakeProfileExtractor()
    service = CandidateProfileService(profile_extractor, cache, tools, guard,
                                      EvidenceVerifier(settings.evidence_min_chars),
                                      settings.profile_max_resume_chars, settings.profile_max_concurrency)
    kwargs = {}
    if clock is not None:
        kwargs["clock"] = clock
    handlers = RecruitmentNodeHandlers(
        classifier=classifier or FakeClassifier(),
        jd_extractor=jd_extractor or FakeJdExtractor(),
        narrator=narrator or FakeNarrator(),
        profile_service=service,
        tools=tools,
        guard=guard,
        settings=settings,
        jd_cache=cache,
        **kwargs,
    )
    return handlers
