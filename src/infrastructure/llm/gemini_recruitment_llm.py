"""
招募助手 Gemini LLM 轉接器 (ADR-0019)

以 langchain-google-genai 之 ChatGoogleGenerativeAI + Pydantic 結構化輸出，實作：
IIntentClassifier、IJdRequirementExtractor、ICandidateProfileExtractor、IRecruitmentNarrator。
Pydantic Schema 僅存在於本層，回傳前一律轉為 Domain dataclass。
所有呼叫包 retry_call + CircuitBreaker：429 用罄 → 熔斷冷卻並拋出 LlmQuotaExhaustedError（保留 __cause__）。
"""
import hashlib
import json
import logging
import re
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field

from src.domain.exceptions import LlmQuotaExhaustedError, RecruitmentLlmError
from src.domain.recruitment import (
    AnswerStatus,
    CandidateProfile,
    ChatIntent,
    EvidenceQuote,
    FollowupFacts,
    FollowupNarration,
    GeneralQaFacts,
    InterviewFacts,
    InterviewQuestion,
    JdRequirements,
    JobRequirement,
    MatchNarrationFacts,
    RequirementCategory,
    RequirementPriority,
    SeniorityLevel,
)
from src.domain.recruitment_services import CircuitBreaker
from src.infrastructure.prompts import load_prompt
from src.infrastructure.transformers.utils import retry_call

logger = logging.getLogger(__name__)

PROMPT_FILES = {
    "system": "recruit_system_guardrails.md",
    "intent": "recruit_intent_router.md",
    "jd": "recruit_jd_extract.md",
    "profile": "recruit_profile_extract.md",
    "narrate": "recruit_match_narrate.md",
    "followup": "recruit_followup_answer.md",
    "interview": "recruit_interview_questions.md",
    "general": "recruit_general_qa.md",
}

_FENCE_TAGS = re.compile(r"</?\s*(job_description|resume_content|user_message|facts_json)\s*>", re.IGNORECASE)
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


# ---------------------------------------------------------------------------
# Pydantic 結構化輸出 Schema（僅限 Infrastructure）
# ---------------------------------------------------------------------------
class IntentSchema(BaseModel):
    intents: List[str] = Field(default_factory=list, description="意圖列舉值清單")


class RequirementSchema(BaseModel):
    category: str
    label: str
    skill: Optional[str] = None
    min_value: Optional[float] = None
    min_level: Optional[str] = None


class JdSchema(BaseModel):
    title: str = ""
    must: List[RequirementSchema] = Field(default_factory=list)
    nice: List[RequirementSchema] = Field(default_factory=list)
    retrieval_query: str = ""


class SkillSchema(BaseModel):
    name: str
    quote: Optional[str] = None


class ProfileSchema(BaseModel):
    years_of_experience: Optional[float] = None
    years_quote: Optional[str] = None
    has_led_team: Optional[bool] = None
    leadership_quote: Optional[str] = None
    max_team_size: Optional[int] = None
    team_size_quote: Optional[str] = None
    seniority: Optional[str] = None
    seniority_quote: Optional[str] = None
    core_skills: List[SkillSchema] = Field(default_factory=list)


class NarrationSchema(BaseModel):
    text: str = ""


class FollowupSchema(BaseModel):
    answer_status: str = "NOT_MENTIONED"
    answer_text: str = ""
    quotes: List[str] = Field(default_factory=list)


class QuestionSchema(BaseModel):
    question: str
    target_requirement_id: str
    rationale: str = ""


class QuestionsSchema(BaseModel):
    questions: List[QuestionSchema] = Field(default_factory=list)


def _is_quota_error(err: BaseException) -> bool:
    text = f"{type(err).__name__} {err}".lower()
    return "429" in text or "resource_exhausted" in text or "resourceexhausted" in text or "quota" in text


def _to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj):
        return _to_jsonable(asdict(obj))
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    return obj


def neutralize_fences(text: str) -> str:
    """移除不可信內容中偽造之圍欄標籤，防止跳脫圍欄之注入"""
    return _FENCE_TAGS.sub("[tag]", text or "")


def render_prompt(template: str, values: Dict[str, str]) -> str:
    """單趟替換 {{name}}，替換值內之 {{...}} 不會被再次展開"""
    return _PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), template)


class GeminiRecruitmentLlm:
    def __init__(
        self,
        api_key: str,
        model_name: str,
        temperature: float,
        max_output_tokens: int,
        timeout_seconds: float,
        circuit_breaker: CircuitBreaker,
        max_retries: int,
        retry_delay: float,
        chat_model: Any = None,
        prompt_loader: Callable[[str], str] = load_prompt,
        profile_max_output_tokens: Optional[int] = None,
        profile_chat_model: Any = None,
    ):
        self._model_name = model_name
        self._breaker = circuit_breaker
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._prompts = {key: prompt_loader(fname) for key, fname in PROMPT_FILES.items()}
        if chat_model is None:
            from langchain_google_genai import ChatGoogleGenerativeAI

            chat_model = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=api_key,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
                timeout=timeout_seconds,
                max_retries=0,
            )
        self._chat = chat_model
        # 履歷抽取輸出精簡，以獨立 max_output_tokens 收斂延遲；未指定時共用主模型
        if profile_chat_model is None and profile_max_output_tokens and hasattr(chat_model, "model_copy"):
            profile_chat_model = chat_model.model_copy(update={"max_output_tokens": int(profile_max_output_tokens)})
        self._profile_chat = profile_chat_model or chat_model
        digest_src = "\n".join([self._prompts["system"], self._prompts["jd"], self._prompts["profile"], model_name])
        self._version = hashlib.sha256(digest_src.encode("utf-8")).hexdigest()[:12]

    @property
    def extractor_version(self) -> str:
        return self._version

    # ------------------------------------------------------------------
    def _invoke(self, schema, prompt_key: str, values: Dict[str, str], op_name: str, chat_model: Any = None):
        if self._breaker.is_open():
            raise LlmQuotaExhaustedError("LLM 配額熔斷冷卻中", retry_after_seconds=self._breaker.retry_after_seconds())
        from langchain_core.messages import HumanMessage, SystemMessage

        human = render_prompt(self._prompts[prompt_key], values)
        messages = [SystemMessage(content=self._prompts["system"]), HumanMessage(content=human)]
        runnable = (chat_model or self._chat).with_structured_output(schema)
        try:
            result = retry_call(lambda: runnable.invoke(messages), max_retries=self._max_retries,
                                initial_delay=self._retry_delay, op_name=op_name)
        except Exception as err:
            if _is_quota_error(err):
                self._breaker.record_quota_exhausted()
                raise LlmQuotaExhaustedError(
                    "LLM 配額用罄", retry_after_seconds=self._breaker.retry_after_seconds()
                ) from err
            raise RecruitmentLlmError(f"LLM 呼叫失敗 [{op_name}] ({type(err).__name__})") from err
        if result is None:
            raise RecruitmentLlmError(f"LLM 結構化輸出為空 [{op_name}]")
        if isinstance(result, dict):
            result = schema.model_validate(result)
        return result

    @staticmethod
    def _facts_json(facts: Any) -> str:
        return neutralize_fences(json.dumps(_to_jsonable(facts), ensure_ascii=False))

    # ------------------------------------------------------------------
    # IIntentClassifier
    # ------------------------------------------------------------------
    def classify(self, message: str, has_shortlist: bool) -> List[ChatIntent]:
        res: IntentSchema = self._invoke(IntentSchema, "intent", {
            "message": neutralize_fences(message),
            "has_shortlist": "是" if has_shortlist else "否",
        }, "recruit_intent")
        intents = []
        for raw in res.intents:
            try:
                intents.append(ChatIntent(str(raw).strip().upper()))
            except ValueError:
                continue
        return intents or [ChatIntent.GENERAL_QA]

    # ------------------------------------------------------------------
    # IJdRequirementExtractor
    # ------------------------------------------------------------------
    def extract_jd(self, jd_text: str, max_must: int) -> JdRequirements:
        res: JdSchema = self._invoke(JdSchema, "jd", {
            "job_description": neutralize_fences(jd_text),
            "max_must": str(max_must),
        }, "recruit_jd_extract")
        return JdRequirements(
            jd_hash="",
            title=res.title or "",
            must=tuple(r for r in (self._map_req(x, RequirementPriority.MUST) for x in res.must) if r),
            nice=tuple(r for r in (self._map_req(x, RequirementPriority.NICE) for x in res.nice) if r),
            retrieval_query=res.retrieval_query or res.title or "",
        )

    @staticmethod
    def _map_req(raw: RequirementSchema, priority: RequirementPriority) -> Optional[JobRequirement]:
        try:
            category = RequirementCategory(str(raw.category).strip().upper())
        except ValueError:
            return None
        level = None
        if raw.min_level:
            try:
                level = SeniorityLevel[str(raw.min_level).strip().upper()]
            except KeyError:
                level = None
        return JobRequirement(
            requirement_id="",
            category=category,
            priority=priority,
            label=(raw.label or "").strip()[:120],
            skill=(raw.skill or "").strip().lower() or None,
            min_value=raw.min_value,
            min_level=level,
        )

    # ------------------------------------------------------------------
    # ICandidateProfileExtractor
    # ------------------------------------------------------------------
    def extract_profile(self, candidate_id: str, resume_text: str, content_hash: str) -> CandidateProfile:
        res: ProfileSchema = self._invoke(ProfileSchema, "profile", {
            "resume_content": neutralize_fences(resume_text),
        }, "recruit_profile_extract", chat_model=self._profile_chat)
        evidence: List[EvidenceQuote] = []

        def add(field_name: str, quote: Optional[str]) -> None:
            if quote and quote.strip():
                evidence.append(EvidenceQuote(field=field_name, quote=quote.strip()))

        add("years", res.years_quote)
        add("has_led_team", res.leadership_quote)
        add("team_size", res.team_size_quote)
        add("seniority", res.seniority_quote)
        skills = []
        for skill in res.core_skills:
            name = (skill.name or "").strip().lower()
            if name:
                skills.append(name)
                add(f"skill:{name}", skill.quote)
        seniority = None
        if res.seniority:
            try:
                seniority = SeniorityLevel[str(res.seniority).strip().upper()]
            except KeyError:
                seniority = None
        return CandidateProfile(
            candidate_id=candidate_id,
            content_hash=content_hash,
            extractor_version=self._version,
            years_of_experience=res.years_of_experience,
            has_led_team=res.has_led_team,
            max_team_size=res.max_team_size,
            seniority=seniority,
            core_skills=tuple(dict.fromkeys(skills)),
            evidence=tuple(evidence),
        )

    # ------------------------------------------------------------------
    # IRecruitmentNarrator
    # ------------------------------------------------------------------
    def narrate_match(self, facts: MatchNarrationFacts) -> str:
        res: NarrationSchema = self._invoke(NarrationSchema, "narrate", {"facts_json": self._facts_json(facts)},
                                            "recruit_narrate")
        return (res.text or "").strip()

    def answer_followup(self, facts: FollowupFacts) -> FollowupNarration:
        payload = {k: v for k, v in _to_jsonable(facts).items() if k not in ("resume_excerpt", "question")}
        res: FollowupSchema = self._invoke(FollowupSchema, "followup", {
            "alias": facts.alias,
            "facts_json": neutralize_fences(json.dumps(payload, ensure_ascii=False)),
            "question": neutralize_fences(facts.question),
            "resume_content": neutralize_fences(facts.resume_excerpt),
        }, "recruit_followup")
        try:
            status = AnswerStatus(str(res.answer_status).strip().upper())
        except ValueError:
            status = AnswerStatus.NOT_MENTIONED
        return FollowupNarration(answer_status=status, answer_text=(res.answer_text or "").strip(),
                                 quotes=tuple(q.strip() for q in res.quotes if q and q.strip()))

    def generate_interview_questions(self, facts: InterviewFacts, count: int) -> List[InterviewQuestion]:
        res: QuestionsSchema = self._invoke(QuestionsSchema, "interview", {
            "alias": facts.alias,
            "count": str(count),
            "facts_json": self._facts_json(facts),
        }, "recruit_interview")
        return [
            InterviewQuestion(no=i, question=q.question.strip(), target_requirement_id=q.target_requirement_id.strip(),
                              rationale=(q.rationale or "").strip())
            for i, q in enumerate(res.questions, start=1)
            if q.question and q.question.strip()
        ]

    def answer_general(self, facts: GeneralQaFacts) -> str:
        payload = {k: v for k, v in _to_jsonable(facts).items() if k != "question"}
        res: NarrationSchema = self._invoke(NarrationSchema, "general", {
            "facts_json": neutralize_fences(json.dumps(payload, ensure_ascii=False)),
            "question": neutralize_fences(facts.question),
        }, "recruit_general")
        return (res.text or "").strip()


class GeminiJdExtractorAdapter:
    """IJdRequirementExtractor 轉接（同一 LLM 實例，方法名對齊 Protocol）"""

    def __init__(self, llm: GeminiRecruitmentLlm):
        self._llm = llm

    @property
    def extractor_version(self) -> str:
        return self._llm.extractor_version

    def extract(self, jd_text: str, max_must: int) -> JdRequirements:
        return self._llm.extract_jd(jd_text, max_must)


class GeminiProfileExtractorAdapter:
    """ICandidateProfileExtractor 轉接（同一 LLM 實例，方法名對齊 Protocol）"""

    def __init__(self, llm: GeminiRecruitmentLlm):
        self._llm = llm

    @property
    def extractor_version(self) -> str:
        return self._llm.extractor_version

    def extract(self, candidate_id: str, resume_text: str, content_hash: str) -> CandidateProfile:
        return self._llm.extract_profile(candidate_id, resume_text, content_hash)
