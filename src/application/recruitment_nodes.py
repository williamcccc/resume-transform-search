"""
招募助手固定節點處理器 (ADR-0019)

純 Python、零編排框架依賴；每個節點簽章 (state: ChatSessionState, turn: TurnContext) -> NodeUpdate。
編排器（如 LangGraph）僅負責依意圖佇列呼叫節點與保存狀態，所有業務規則皆在此與領域服務中。
排序、條件瓶頸與指代解析皆為確定性計算；LLM 只負責分類、抽取與敘述，失敗時平滑降級為模板。
"""
import logging
import re
import time
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from src.application.candidate_profile_service import CandidateProfileService, TurnBudget
from src.application.recruitment_settings import RecruitmentSettings
from src.application.recruitment_tools import RecruitmentTools
from src.domain.exceptions import LlmOutputTruncatedError, LlmQuotaExhaustedError, TurnTimeoutError
from src.domain.interfaces import (
    ICandidateProfileCache,
    IIntentClassifier,
    IJdRequirementExtractor,
    IRecruitmentNarrator,
)
from src.domain.models import CandidateSummary
from src.domain.recruitment import (
    AnswerStatus,
    CandidateEvaluation,
    CandidateFact,
    ChatIntent,
    ChatMessage,
    ChatSessionState,
    FollowupAnswer,
    FollowupFacts,
    FollowupNarration,
    GeneralQaFacts,
    InterviewFacts,
    InterviewQuestion,
    JdRequirements,
    MatchNarrationFacts,
    MatchStatus,
    ReferenceKind,
    ReferenceResolution,
    RelaxationReport,
    RequirementCategory,
    RequirementEvidence,
    SearchExpansionLimits,
    SearchRoundParams,
    SearchRoundRecord,
    SearchStopReason,
    ShortlistEntry,
    TurnUsage,
    WeaknessFact,
)
from src.domain.recruitment_services import (
    CandidateRanker,
    ConstraintRelaxationAnalyzer,
    EvidenceVerifier,
    OrdinalReferenceResolver,
    ProtectedAttributeGuard,
    RequirementMatcher,
    SearchExpansionPolicy,
    collect_requirement_evidence,
    compute_content_hash,
    mask_contact_info,
    normalize_intents,
    parse_question_count,
    parse_requested_count,
    renumber_requirements,
    sanitize_reply_quotes,
    trim_history,
)

logger = logging.getLogger(__name__)

_JD_KEYWORDS = re.compile(r"職缺|JD|職務|工作內容|職責|資格|條件|要求|招募|徵才|hiring|requirements", re.IGNORECASE)
_INTERVIEW_KEYWORDS = re.compile(r"面試題|考題|面試問題|題目|interview", re.IGNORECASE)
_QUESTION_PATTERN = re.compile(r"[?？]|嗎|是否|有沒有|有无|如何|怎麼|怎样|多少|哪些|什麼|為什麼")
_LEADERSHIP_KEYWORDS = re.compile(r"帶人|帶過人|帶領|帶隊|管理|主管|團隊|leader|lead", re.IGNORECASE)

_SECTION_SEPARATOR = "\n\n---\n\n"
_REMOVED_QUOTE_PLACEHOLDER = "（引文未通過原文驗證，已移除）"
_STATUS_LABELS = {MatchStatus.MET: "符合", MatchStatus.UNMET: "明確不符", MatchStatus.UNKNOWN: "履歷未提及"}
_STOP_REASON_TEXT = {
    SearchStopReason.SATISFIED: "完全符合必要條件之人數已達需求",
    SearchStopReason.MAX_ROUNDS: "已達擴大檢索輪數上限",
    SearchStopReason.POOL_CAP: "已達單輪評估人數上限",
    SearchStopReason.EXHAUSTED: "相似度門檻已降至下限或無法再取得新人選",
    SearchStopReason.BUDGET: "本輪 LLM 呼叫預算僅剩保留額度",
    SearchStopReason.DEADLINE: "本輪剩餘處理時間不足",
    SearchStopReason.DISABLED: "自動擴大檢索已停用",
}


@dataclass(frozen=True)
class ReplySection:
    """回覆段落：llm_generated=True 者於 compose 逐字驗證引文；模板段落（系統產出）不驗證。

    join 為 None 時獨立成區塊（以分隔線相連）；否則以該字串接續上一段（同一區塊內）。
    """
    text: str
    llm_generated: bool = False
    join: Optional[str] = None


class _BudgetExhausted(Exception):
    """單輪 LLM 預算用罄（內部控制流程，必轉為模板降級）"""


@dataclass
class JdSearchProgress:
    """jd_match 子步驟之單輪暫態資料（ADR-0021）：含履歷文字，僅存於 TurnContext，絕不寫入 checkpoint"""
    jd: JdRequirements
    requested_k: int
    params: SearchRoundParams  # 下一輪要執行之參數
    warning_index: int = 0     # 「候選池僅 N 人」警告之插入位置（維持與拆分前相同之警告順序）
    history: List[SearchRoundRecord] = field(default_factory=list)
    candidates: Dict[str, CandidateSummary] = field(default_factory=dict)  # 依首次出現順序
    evals: Dict[str, CandidateEvaluation] = field(default_factory=dict)
    llm_texts: Dict[str, str] = field(default_factory=dict)
    match_texts: Dict[str, str] = field(default_factory=dict)
    stop_reason: Optional[SearchStopReason] = None


@dataclass
class TurnContext:
    """單輪暫態上下文（不持久化）"""
    message: str
    trace_id: str
    budget: TurnBudget
    deadline: float
    clock: Callable[[], float] = time.monotonic
    intents: List[ChatIntent] = field(default_factory=list)
    reference: Optional[ReferenceResolution] = None
    sections: List[ReplySection] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    followup: Optional[FollowupAnswer] = None
    interview_questions: List[InterviewQuestion] = field(default_factory=list)
    usage: TurnUsage = field(default_factory=TurnUsage)
    degraded: bool = False
    referenced_candidate_id: Optional[str] = None
    quote_sources: List[str] = field(default_factory=list)
    node_ms: Dict[str, float] = field(default_factory=dict)
    final_reply: str = ""
    jd_search: Optional[JdSearchProgress] = None

    def remaining(self) -> float:
        return max(self.deadline - self.clock(), 0.0)

    def check_deadline(self) -> None:
        if self.clock() > self.deadline:
            raise TurnTimeoutError("單輪處理逾時")

    def warn(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def add_template(self, text: str, join: Optional[str] = None) -> None:
        self.sections.append(ReplySection(text=text, llm_generated=False, join=join))

    def add_llm(self, text: str, join: Optional[str] = None) -> None:
        self.sections.append(ReplySection(text=text, llm_generated=True, join=join))

    def has_text(self, text: str) -> bool:
        return any(sec.text == text for sec in self.sections)


@dataclass
class NodeUpdate:
    session: ChatSessionState
    goto: Optional[str] = None  # 子步驟路由（ADR-0021）：None 表示本意圖處理完畢，交回意圖佇列


class RecruitmentNodeHandlers:
    NODE_ROUTE = "route"
    NODE_COMPOSE = "compose"
    INTENT_NODES = {
        ChatIntent.JD_MATCH: "jd_match",
        ChatIntent.CANDIDATE_FOLLOWUP: "candidate_followup",
        ChatIntent.INTERVIEW_QUESTIONS: "interview_questions",
        ChatIntent.GENERAL_QA: "general_qa",
        ChatIntent.OUT_OF_SCOPE: "out_of_scope",
    }
    NODE_JD_SEARCH = "jd_search_round"
    NODE_JD_FINALIZE = "jd_finalize"
    SUBSTEP_NODES = (NODE_JD_SEARCH, NODE_JD_FINALIZE)

    def __init__(
        self,
        classifier: IIntentClassifier,
        jd_extractor: IJdRequirementExtractor,
        narrator: IRecruitmentNarrator,
        profile_service: CandidateProfileService,
        tools: RecruitmentTools,
        guard: ProtectedAttributeGuard,
        settings: RecruitmentSettings,
        jd_cache: Optional[ICandidateProfileCache] = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._classifier = classifier
        self._jd_extractor = jd_extractor
        self._narrator = narrator
        self._profiles = profile_service
        self._tools = tools
        self._guard = guard
        self._settings = settings
        self._jd_cache = jd_cache
        self._clock = clock
        self._matcher = RequirementMatcher(
            settings.skill_aliases,
            version_strip_exempt=settings.skill_version_strip_exempt,
            lexical_min_chars=settings.skill_lexical_min_chars,
            snippet_chars=settings.skill_mention_snippet_chars,
            lexical_alias_denylist=settings.skill_lexical_alias_denylist,
        )
        self._ranker = CandidateRanker()
        self._relaxation = ConstraintRelaxationAnalyzer()
        self._expansion = SearchExpansionPolicy(SearchExpansionLimits(
            max_rounds=max(int(settings.search_expansion_max_rounds), 0),
            pool_step=max(int(settings.search_expansion_pool_step), 1),
            pool_max=max(int(settings.search_expansion_pool_max), 1),
            top_k_max=max(int(settings.search_expansion_top_k_chunks_max), 1),
            min_score_step=float(settings.search_expansion_min_score_step),
            min_score_floor=float(settings.search_expansion_min_score_floor),
        ))
        self._resolver = OrdinalReferenceResolver()
        self._verifier = EvidenceVerifier(settings.evidence_min_chars)

    # ------------------------------------------------------------------
    # 編排輔助
    # ------------------------------------------------------------------
    def new_turn(self, message: str, trace_id: str) -> TurnContext:
        return TurnContext(
            message=message,
            trace_id=trace_id,
            budget=TurnBudget(self._settings.max_llm_calls_per_turn),
            deadline=self._clock() + float(self._settings.turn_timeout_seconds),
            clock=self._clock,
        )

    def node_names(self) -> List[str]:
        return [self.NODE_ROUTE, *self.INTENT_NODES.values(), *self.SUBSTEP_NODES, self.NODE_COMPOSE]

    @property
    def max_substeps_per_intent(self) -> int:
        """單一意圖節點之後最多再執行之子步驟數：檢索 (1 + 擴大輪數) + 收尾 1"""
        return self._expansion.limits.max_rounds + 2

    def execute_node(self, name: str, state: ChatSessionState, turn: TurnContext) -> NodeUpdate:
        """依節點名稱執行並記錄耗時（供編排器呼叫）"""
        handler = getattr(self, name)
        start = time.perf_counter()
        try:
            turn.check_deadline()
            return handler(state, turn)
        finally:  # 子步驟可能重複執行，耗時累加
            elapsed = (time.perf_counter() - start) * 1000
            turn.node_ms[name] = round(turn.node_ms.get(name, 0.0) + elapsed, 2)

    def run_all(self, state: ChatSessionState, turn: TurnContext) -> ChatSessionState:
        """純 Python 循序執行（與 LangGraph 圖等價之參考實作，供測試與無框架環境）"""
        state = self.execute_node(self.NODE_ROUTE, state, turn).session
        for intent in list(turn.intents):
            update = self.execute_node(self.INTENT_NODES[intent], state, turn)
            state = update.session
            steps = 0
            while update.goto is not None:
                if update.goto not in self.SUBSTEP_NODES:
                    raise ValueError(f"未知子步驟節點：{update.goto}")
                steps += 1
                if steps > self.max_substeps_per_intent:
                    raise RuntimeError("子步驟數超過上限，疑似無限迴圈")
                update = self.execute_node(update.goto, state, turn)
                state = update.session
        return self.execute_node(self.NODE_COMPOSE, state, turn).session

    def _call_llm(self, turn: TurnContext, fn, *args):
        if not turn.budget.try_consume():
            raise _BudgetExhausted()
        turn.check_deadline()
        return fn(*args)

    # ------------------------------------------------------------------
    # route：雙段式意圖路由（確定性前置規則 → LLM 分類）
    # ------------------------------------------------------------------
    def route(self, state: ChatSessionState, turn: TurnContext) -> NodeUpdate:
        msg = turn.message
        intents: List[ChatIntent] = []
        if len(msg) >= self._settings.jd_intent_min_chars and _JD_KEYWORDS.search(msg):
            intents = [ChatIntent.JD_MATCH]
        else:
            ref = self._resolver.resolve(msg, state.shortlist, state.last_referenced_candidate_id)
            turn.reference = ref
            wants_questions = bool(_INTERVIEW_KEYWORDS.search(msg))
            if ref.kind != ReferenceKind.NONE:
                if wants_questions:
                    intents.append(ChatIntent.INTERVIEW_QUESTIONS)
                if _QUESTION_PATTERN.search(msg) or not wants_questions:
                    intents.append(ChatIntent.CANDIDATE_FOLLOWUP)
            elif wants_questions and state.last_referenced_candidate_id:
                intents.append(ChatIntent.INTERVIEW_QUESTIONS)
        if not intents:
            intents = self._classify(self._deidentify(msg, state), bool(state.shortlist), turn)
        turn.intents = normalize_intents(intents, self._settings.max_intents_per_turn)
        return NodeUpdate(session=state)

    def _classify(self, msg: str, has_shortlist: bool, turn: TurnContext) -> List[ChatIntent]:
        try:
            result = self._call_llm(turn, self._classifier.classify, msg, has_shortlist)
        except (LlmQuotaExhaustedError, TurnTimeoutError):
            raise
        except _BudgetExhausted:
            turn.warn("單輪 LLM 呼叫預算已用罄，意圖改以一般問答處理")
            return [ChatIntent.GENERAL_QA]
        except Exception as err:
            logger.warning("意圖分類失敗，改以一般問答處理 (trace_id=%s, err_type=%s)", turn.trace_id, type(err).__name__)
            return [ChatIntent.GENERAL_QA]
        valid = [i for i in (result or []) if isinstance(i, ChatIntent)]
        return valid or [ChatIntent.GENERAL_QA]

    # ------------------------------------------------------------------
    # jd_match 子步驟 (ADR-0021)：
    #   jd_match（JD → 條件）→ jd_search_round ⟲（檢索 → 新進者延遲抽取 → 確定性比對 → 擴大策略）
    #   → jd_finalize（排序/證據/瓶頸 → 敘述）
    # ------------------------------------------------------------------
    def jd_match(self, state: ChatSessionState, turn: TurnContext) -> NodeUpdate:
        s = self._settings
        requested_k, truncated = parse_requested_count(turn.message, s.shortlist_size, s.shortlist_max)
        if truncated:
            turn.warn(f"推薦人數超過上限，已截斷為 {s.shortlist_max} 位")

        jd = self._load_jd(turn)
        if jd is None:
            turn.degraded = True
            turn.add_template("JD 條件解析暫時失敗，請稍後再試或精簡 JD 內容後重新送出。")
            return NodeUpdate(session=state)

        protected_hits = self._guard.scan_text(turn.message)
        kept_must, ignored_must = self._guard.filter_requirements(jd.must)
        kept_nice, ignored_nice = self._guard.filter_requirements(jd.nice)
        ignored = tuple(dict.fromkeys(tuple(protected_hits) + ignored_must + ignored_nice))
        if ignored:
            turn.warn(f"JD 含受保護屬性相關條件（{'、'.join(ignored)}），已忽略且不納入比對")
        jd = replace(jd, must=kept_must, nice=kept_nice, ignored_protected_terms=ignored)
        jd, must_truncated = renumber_requirements(jd, s.max_must_requirements)
        if must_truncated:
            turn.warn(f"必要條件超過 {s.max_must_requirements} 項，已截斷")

        pool_size = min(s.candidate_pool_size, s.candidate_pool_max)
        turn.jd_search = JdSearchProgress(
            jd=jd,
            requested_k=requested_k,
            params=SearchExpansionPolicy.initial(pool_size, s.retrieval_top_k_chunks, s.retrieval_min_score),
            warning_index=len(turn.warnings),
        )
        return NodeUpdate(session=state, goto=self.NODE_JD_SEARCH)

    def jd_search_round(self, state: ChatSessionState, turn: TurnContext) -> NodeUpdate:
        prog = self._require_progress(turn)
        s = self._settings
        params = prog.params
        limits = self._expansion.limits
        if params.round_no > limits.max_rounds:  # 防禦：Policy 之外的第二道終止保證
            prog.stop_reason = SearchStopReason.MAX_ROUNDS
            return NodeUpdate(session=state, goto=self.NODE_JD_FINALIZE)
        turn.check_deadline()
        jd = prog.jd
        try:
            pool = self._tools.retrieve_candidate_pool(jd.retrieval_query or jd.title, params.top_k_chunks,
                                                       params.pool_target, params.min_score)
        except (LlmQuotaExhaustedError, TurnTimeoutError):
            raise
        except Exception as err:
            if params.round_no == 0:  # 基準輪維持拆分前行為：檢索失敗向上拋出
                raise
            logger.warning("擴大檢索失敗，以已評估之候選人收尾 (trace_id=%s, err_type=%s)",
                           turn.trace_id, type(err).__name__)
            turn.warn("擴大檢索失敗，已以目前評估過之候選人產出結果")
            prog.stop_reason = SearchStopReason.EXHAUSTED
            return NodeUpdate(session=state, goto=self.NODE_JD_FINALIZE)

        # 基準輪不受擴大總人數上限截斷（維持拆分前行為）
        base_target = prog.history[0].params.pool_target if prog.history else params.pool_target
        room = max(max(limits.pool_max, base_target) - len(prog.candidates), 0)
        new = [c for c in pool if c.candidate_id not in prog.candidates][:room]
        if new:
            # 擴大輪之抽取不得吃到保留額度（確保後續敘述仍有 LLM 預算）；基準輪維持原預算語意
            budget = turn.budget.reserved_view(s.search_expansion_llm_reserve) if params.round_no > 0 else turn.budget
            batch = self._profiles.get_profiles(new, budget, turn.check_deadline, turn.remaining)
            turn.usage.profile_cache_hits += batch.cache_hits
            turn.usage.profile_cache_misses += batch.cache_misses
            turn.usage.profile_negative_hits += batch.negative_hits
            for w in batch.warnings:
                turn.warn(w)
            for cand in new:
                cid = cand.candidate_id
                prog.candidates[cid] = cand
                prog.llm_texts[cid] = batch.llm_texts.get(cid, "")
                prog.match_texts[cid] = batch.match_texts.get(cid, "")
                prog.evals[cid] = self._matcher.evaluate_candidate(
                    jd, cid, cand.candidate_name, cand.max_score, batch.profiles[cid], cand.all_skills,
                    resume_text=prog.match_texts[cid])

        qualified = sum(1 for e in prog.evals.values() if e.fully_qualified)
        prog.history.append(SearchRoundRecord(params=params, returned=len(pool), new_candidates=len(new),
                                              qualified_total=qualified))
        nxt, reason = self._expansion.decide(
            prog.history, prog.requested_k, len(prog.candidates),
            affordable_calls=turn.budget.remaining - max(int(s.search_expansion_llm_reserve), 0),
            seconds_left=turn.remaining(),
            min_seconds=float(s.search_expansion_min_remaining_seconds),
        )
        if nxt is not None:
            prog.params = nxt
            return NodeUpdate(session=state, goto=self.NODE_JD_SEARCH)
        prog.stop_reason = reason
        return NodeUpdate(session=state, goto=self.NODE_JD_FINALIZE)

    def jd_finalize(self, state: ChatSessionState, turn: TurnContext) -> NodeUpdate:
        prog = self._require_progress(turn)
        turn.jd_search = None  # 子步驟結束即釋放履歷文字等暫態資料
        jd, requested_k = prog.jd, prog.requested_k
        rounds = max(len(prog.history) - 1, 0)
        turn.usage.search_rounds = rounds
        turn.usage.search_stop_reason = prog.stop_reason.value if prog.stop_reason else ""
        turn.usage.pool_evaluated = len(prog.candidates)

        pool = list(prog.candidates.values())
        if not pool:
            turn.add_template("資料庫中無相關人選，建議調整 JD 描述或放寬條件後再試。")
            new_state = replace(state, jd_requirements=jd, shortlist=(), pool_evaluations=(), relaxation=None,
                                last_referenced_candidate_id=None)
            return NodeUpdate(session=new_state)
        if len(pool) < requested_k:
            message = f"候選池僅 {len(pool)} 人，少於需求之 {requested_k} 位"
            if message not in turn.warnings:
                turn.warnings.insert(min(prog.warning_index, len(turn.warnings)), message)

        evals = list(prog.evals.values())
        ranked = self._ranker.rank(evals, requested_k)
        shortlist = tuple(
            replace(entry, evidence=collect_requirement_evidence(
                jd.all_requirements, prog.evals[entry.candidate_id].profile, self._settings.skill_aliases,
                self._settings.skill_version_strip_exempt) + self._lexical_evidence(
                jd, prog.evals[entry.candidate_id], prog.candidates[entry.candidate_id], prog.match_texts))
            for entry in ranked
        )
        baseline = sum(1 for e in evals if e.fully_qualified)
        relaxation = self._relaxation.analyze(evals, jd.must, requested_k) if baseline < requested_k else None
        if relaxation is not None and rounds:
            relaxation = replace(relaxation, scope_note=f"{relaxation.scope_note}（已自動擴大檢索 {rounds} 輪）")

        for entry in shortlist:
            turn.quote_sources.extend(e.quote for e in entry.evidence)
            turn.quote_sources.append(prog.llm_texts.get(entry.candidate_id, ""))
        turn.quote_sources.extend(r.label for r in jd.all_requirements)

        turn.add_template(self._render_shortlist(jd, shortlist, requested_k))
        if rounds:
            turn.add_template(self._render_expansion(prog), join="\n\n")
        if relaxation is not None:
            turn.add_template(self._render_relaxation(jd, relaxation), join="\n\n")
        facts = self._match_facts(jd, shortlist, requested_k, len(pool), relaxation)
        narration = self._narrate(turn, self._narrator.narrate_match, facts)
        if narration:
            turn.add_llm("### 推薦理由\n" + narration, join="\n\n")
        else:
            turn.add_template("### 推薦理由\n" + self._template_match_reason(shortlist, jd), join="\n\n")

        new_state = replace(state, jd_requirements=jd, shortlist=shortlist, pool_evaluations=tuple(evals),
                            relaxation=relaxation, last_referenced_candidate_id=None)
        return NodeUpdate(session=new_state)

    @staticmethod
    def _require_progress(turn: TurnContext) -> JdSearchProgress:
        if turn.jd_search is None:
            raise RuntimeError("jd_match 子步驟須接續 jd_match 節點執行")
        return turn.jd_search

    @staticmethod
    def _render_expansion(prog: JdSearchProgress) -> str:
        lines = [
            "### 檢索擴大紀錄",
            f"基準檢索之合格人數不足，已自動擴大檢索範圍 {len(prog.history) - 1} 輪"
            "（僅擴大語意檢索範圍，未放寬任何招募條件）。",
            "",
            "| 輪次 | 相似度門檻 | 候選池目標 | 檢索回傳 | 新增評估 | 累計合格 |",
            "| :--- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for rec in prog.history:
            p = rec.params
            label = "基準" if p.round_no == 0 else f"第 {p.round_no} 輪"
            lines.append(f"| {label} | {p.min_score:.2f} | {p.pool_target} | {rec.returned} | {rec.new_candidates} "
                         f"| {rec.qualified_total} |")
        if prog.stop_reason is not None:
            reason_text = _STOP_REASON_TEXT.get(prog.stop_reason, prog.stop_reason.value)
            lines.append(f"\n停止原因：{reason_text}。")
        return "\n".join(lines)

    def _lexical_evidence(self, jd: JdRequirements, ev: CandidateEvaluation, cand,
                          match_texts: Dict[str, str]) -> Tuple[RequirementEvidence, ...]:
        """規則 3（履歷全文詞面回退）判 MET 之技能條件，補入已逐字驗證之原文片段作為證據"""
        text = match_texts.get(ev.candidate_id, "")
        result: List[RequirementEvidence] = []
        for req in jd.all_requirements:
            if req.category != RequirementCategory.SKILL or ev.statuses.get(req.requirement_id) != MatchStatus.MET:
                continue
            mention = self._matcher.lexical_mention(req, ev.profile, cand.all_skills, text)
            if mention is not None and self._verifier.verify(mention.snippet, text):
                result.append(RequirementEvidence(requirement_id=req.requirement_id, field=f"skill:{mention.term}",
                                                  quote=mention.snippet, verified=True))
        return tuple(result)

    def _load_jd(self, turn: TurnContext) -> Optional[JdRequirements]:
        jd_hash = compute_content_hash(turn.message)
        version = self._jd_extractor.extractor_version
        cached = None
        if self._jd_cache is not None:
            try:
                cached = self._jd_cache.get_jd(jd_hash, version)
            except Exception as err:
                logger.warning("JD 快取讀取失敗，視為未命中 (trace_id=%s, err_type=%s)", turn.trace_id, type(err).__name__)
        if cached is not None:
            turn.usage.jd_cache_hit = True
            return replace(cached, jd_hash=jd_hash)
        try:
            extracted = self._call_llm(turn, self._jd_extractor.extract, turn.message,
                                       self._settings.max_must_requirements)
        except (LlmQuotaExhaustedError, TurnTimeoutError):
            raise
        except _BudgetExhausted:
            turn.warn("單輪 LLM 呼叫預算已用罄，無法解析 JD")
            return None
        except Exception as err:
            logger.warning("JD 條件抽取失敗 (trace_id=%s, err_type=%s)", turn.trace_id, type(err).__name__)
            return None
        extracted = replace(extracted, jd_hash=jd_hash)
        if self._jd_cache is not None:
            try:
                self._jd_cache.set_jd(extracted, version)
            except Exception as err:
                logger.warning("JD 快取寫入失敗 (trace_id=%s, err_type=%s)", turn.trace_id, type(err).__name__)
        return extracted

    def _match_facts(self, jd: JdRequirements, shortlist: Sequence[ShortlistEntry], k: int, pool_size: int,
                     relaxation: Optional[RelaxationReport]) -> MatchNarrationFacts:
        def labels(ids):
            return tuple(self._label(jd, rid) for rid in ids)

        candidates = tuple(
            CandidateFact(
                alias=self._alias(entry.rank),
                fully_qualified=entry.fully_qualified,
                met_labels=labels(entry.met),
                unmet_labels=labels(entry.unmet),
                unknown_labels=labels(entry.unknown),
                evidence_quotes=tuple(e.quote for e in entry.evidence),
            )
            for entry in shortlist
        )
        return MatchNarrationFacts(
            jd_title=jd.title,
            requested_k=k,
            pool_size=pool_size,
            must_labels=tuple(r.label for r in jd.must),
            nice_labels=tuple(r.label for r in jd.nice),
            candidates=candidates,
            relaxation=relaxation,
        )

    def _render_shortlist(self, jd: JdRequirements, shortlist: Sequence[ShortlistEntry], k: int) -> str:
        lines = [f"### 推薦名單（{len(shortlist)}/{k} 位）"]
        for entry in shortlist:
            status = "完全符合必要條件" if entry.fully_qualified else "部分符合（補位）"
            lines.append(f"{entry.rank}. **{self._alias(entry.rank)}** — {status}"
                         f"｜語意分數 {entry.semantic_score:.2f}")
            if entry.met:
                lines.append("   - 符合：" + "、".join(self._label(jd, r) for r in entry.met))
            if entry.unmet:
                lines.append("   - 明確不符：" + "、".join(self._label(jd, r) for r in entry.unmet))
            if entry.unknown:
                lines.append("   - 履歷未提及：" + "、".join(self._label(jd, r) for r in entry.unknown))
            for ev in entry.evidence[:2]:
                lines.append(f"   - 證據：「{ev.quote}」")
        return "\n".join(lines)

    def _render_relaxation(self, jd: JdRequirements, rep: RelaxationReport) -> str:
        lines = [
            "### 條件瓶頸診斷",
            f"完全符合必要條件者 {rep.baseline_qualified} 位，少於需求之 {rep.requested_k} 位"
            f"（{rep.scope_note}，候選池共 {rep.pool_size} 人）。",
            "",
            "| 條件 | 單獨放寬後合格人數 | 增加人數 | 履歷未提及人數 | 符合人數 |",
            "| :--- | ---: | ---: | ---: | ---: |",
        ]
        for item in rep.items:
            lines.append(f"| {item.requirement_id} {item.label} | {item.qualified_if_relaxed} | {item.delta} "
                         f"| {item.unknown_count} | {item.met_count} |")
        if rep.bottleneck_requirement_ids:
            names = "、".join(f"{rid} {self._label(jd, rid)}" for rid in rep.bottleneck_requirement_ids)
            lines.append(f"\n最主要瓶頸：{names}。")
        elif rep.strictest_requirement_ids:
            by_id = {i.requirement_id: i for i in rep.items}
            names = "、".join(f"{rid} {self._label(jd, rid)}" for rid in rep.strictest_requirement_ids)
            met = by_id[rep.strictest_requirement_ids[0]].met_count if rep.strictest_requirement_ids[0] in by_id else 0
            lines.append(f"\n單一條件放寬無法增加合格人數；通過率最低之條件為 {names}"
                         f"（{met}/{rep.pool_size} 位符合），建議優先檢討。")
        else:
            lines.append("\n單一條件放寬皆無法增加合格人數，需考慮複合放寬。")
        lines.append("註：「履歷未提及」視為未滿足；建議面試或補件確認，而非直接判定不符。")
        return "\n".join(lines)

    def _template_match_reason(self, shortlist: Sequence[ShortlistEntry], jd: JdRequirements) -> str:
        if not shortlist:
            return "目前無可推薦人選。"
        parts = []
        for entry in shortlist:
            met = "、".join(self._label(jd, r) for r in entry.met) or "無"
            parts.append(f"- {self._alias(entry.rank)}：符合 {met}。")
        return "\n".join(parts)

    # ------------------------------------------------------------------
    # candidate_followup
    # ------------------------------------------------------------------
    def candidate_followup(self, state: ChatSessionState, turn: TurnContext) -> NodeUpdate:
        target, rank, message = self._resolve_target(state, turn)
        if target is None:
            turn.add_template(message)
            return NodeUpdate(session=state)
        alias = self._alias(rank) if rank else "該候選人"
        llm_text = self._load_llm_text(target, alias)
        turn.quote_sources.append(llm_text)
        jd = state.jd_requirements
        facts = FollowupFacts(
            alias=alias,
            question=self._deidentify(turn.message, state),
            profile_summary=self._profile_summary(target),
            evidence_quotes=tuple(e.quote for e in target.profile.evidence if e.verified),
            met_labels=self._labels_by_status(jd, target, MatchStatus.MET),
            unmet_labels=self._labels_by_status(jd, target, MatchStatus.UNMET),
            unknown_labels=self._labels_by_status(jd, target, MatchStatus.UNKNOWN),
            resume_excerpt=llm_text,
        )
        narration = self._narrate(turn, self._narrator.answer_followup, facts)
        text_is_llm = False
        if isinstance(narration, FollowupNarration):
            status, text, quotes = self._verify_followup(narration, llm_text, turn, target, alias)
            text_is_llm = text == (narration.answer_text or "")
        else:
            status, text, quotes = self._template_followup(target, alias, turn.message)
        if status == AnswerStatus.NOT_MENTIONED and "履歷未提及" not in text:
            text = "履歷未提及相關資訊。" + text
        turn.quote_sources.extend(quotes)
        turn.add_template(f"### {alias} 追問回覆")
        if text_is_llm:
            turn.add_llm(text, join="\n")
        else:
            turn.add_template(text, join="\n")
        for q in quotes:
            turn.add_template(f"- 引用：「{q}」", join="\n")
        turn.followup = FollowupAnswer(candidate_rank=rank, candidate_id=target.candidate_id,
                                       answer_status=status, evidence=tuple(quotes))
        turn.referenced_candidate_id = target.candidate_id
        return NodeUpdate(session=state)

    def _verify_followup(self, narration: FollowupNarration, llm_text: str, turn: TurnContext,
                         target: CandidateEvaluation, alias: str) -> Tuple[AnswerStatus, str, List[str]]:
        quotes = [q for q in narration.quotes if self._verifier.verify(q, llm_text)]
        status = narration.answer_status
        text = narration.answer_text or ""
        if status in (AnswerStatus.SUPPORTED, AnswerStatus.CONTRADICTED) and not quotes:
            # LLM 引文非逐字：若對應 Profile 欄位已有抽取期驗證證據，改以確定性模板回答（不放寬驗證器）
            fb_status, fb_text, fb_quotes = self._template_followup(target, alias, turn.message)
            if fb_status != AnswerStatus.NOT_MENTIONED and fb_quotes:
                turn.warn("追問回答之引文未通過原文驗證，已改用抽取證據（抽取期已逐字驗證之履歷原文）回答")
                return fb_status, fb_text, fb_quotes
            turn.warn("追問回答之引文未通過原文驗證，已改判為「履歷未提及」")
            return AnswerStatus.NOT_MENTIONED, "履歷未提及可佐證之內容，建議於面試中確認。", []
        if len(quotes) < len(narration.quotes):
            turn.warn("部分追問引文未通過原文驗證，已移除")
        return status, text, quotes

    def _template_followup(self, target: CandidateEvaluation, alias: str,
                           question: str) -> Tuple[AnswerStatus, str, List[str]]:
        profile = target.profile
        if _LEADERSHIP_KEYWORDS.search(question):
            quotes = [e.quote for e in profile.evidence if e.verified and e.field in ("has_led_team", "team_size")]
            if profile.has_led_team is True and quotes:
                size = f"，最大團隊規模約 {profile.max_team_size} 人" if profile.max_team_size else ""
                return AnswerStatus.SUPPORTED, f"依履歷證據，{alias}具備帶領團隊經驗{size}。", quotes
            if profile.has_led_team is False and quotes:
                return AnswerStatus.CONTRADICTED, f"依履歷證據，{alias}未有帶領團隊之紀錄。", quotes
            return AnswerStatus.NOT_MENTIONED, "履歷未提及是否有帶人經驗，建議於面試中確認。", []
        return AnswerStatus.NOT_MENTIONED, "目前無法即時分析此問題；履歷未提及可直接佐證之資訊，建議於面試中確認。", []

    # ------------------------------------------------------------------
    # interview_questions
    # ------------------------------------------------------------------
    def interview_questions(self, state: ChatSessionState, turn: TurnContext) -> NodeUpdate:
        target, rank, message = self._resolve_target(state, turn)
        if target is None:
            if not turn.has_text(message):
                turn.add_template(message)
            return NodeUpdate(session=state)
        jd = state.jd_requirements
        s = self._settings
        count, truncated = parse_question_count(turn.message, s.default_interview_questions, s.max_interview_questions)
        if truncated:
            turn.warn(f"面試題數超過上限，已截斷為 {s.max_interview_questions} 題")
        alias = self._alias(rank) if rank else "該候選人"
        weaknesses, note = self._weaknesses(jd, target)
        allowed = {w.requirement_id for w in weaknesses}
        facts = InterviewFacts(
            alias=alias,
            weaknesses=weaknesses,
            strengths=self._labels_by_status(jd, target, MatchStatus.MET),
            jd_title=jd.title if jd else "",
        )
        questions = self._generate_questions(turn, facts, count, allowed)
        from_llm = questions is not None
        if questions is None:
            questions = self._template_questions(weaknesses, count)
        if len(questions) < count:
            turn.warn(f"符合規範之面試題僅 {len(questions)} 題（已剔除不合規或未對應弱點之題目）")
        turn.interview_questions = questions
        turn.add_template(f"### {alias} 面試題")
        if note:
            turn.add_template(note, join="\n")
        label_map = {w.requirement_id: w.label for w in weaknesses}
        for q in questions:
            # 題目本文僅在 LLM 產生時驗證引文；「（對應：…）」與模板題之「」皆為系統產出
            turn.add_template(f"{q.no}. ", join="\n")
            self._add_part(turn, q.question, from_llm, join="")
            turn.add_template(f"（對應：{q.target_requirement_id} {label_map.get(q.target_requirement_id, '')}）",
                              join="")
            if q.rationale:
                turn.add_template("   - 設計理由：", join="\n")
                self._add_part(turn, q.rationale, from_llm, join="")
        turn.referenced_candidate_id = target.candidate_id
        return NodeUpdate(session=state)

    @staticmethod
    def _add_part(turn: TurnContext, text: str, llm_generated: bool, join: Optional[str]) -> None:
        if llm_generated:
            turn.add_llm(text, join=join)
        else:
            turn.add_template(text, join=join)

    def _weaknesses(self, jd: Optional[JdRequirements],
                    target: CandidateEvaluation) -> Tuple[Tuple[WeaknessFact, ...], str]:
        if jd is None:
            return (), ""
        weak = tuple(
            WeaknessFact(r.requirement_id, r.label, _STATUS_LABELS[target.statuses.get(r.requirement_id)])
            for r in jd.all_requirements
            if target.statuses.get(r.requirement_id) in (MatchStatus.UNMET, MatchStatus.UNKNOWN)
        )
        if weak:
            return weak, ""
        nice = tuple(WeaknessFact(r.requirement_id, r.label, "加分條件") for r in jd.nice)
        if nice:
            return nice, "該人選必要與加分條件皆已符合，改針對加分條件深入驗證。"
        all_reqs = tuple(WeaknessFact(r.requirement_id, r.label, "深入驗證") for r in jd.must)
        return all_reqs, "該人選無明顯弱點，改針對必要條件深入驗證。"

    def _generate_questions(self, turn: TurnContext, facts: InterviewFacts, count: int,
                            allowed: set) -> Optional[List[InterviewQuestion]]:
        valid: List[InterviewQuestion] = []
        for attempt in range(2):
            raw = self._narrate(turn, self._narrator.generate_interview_questions, facts, count)
            if raw is None:
                return None if not valid else self._renumber(valid, count)
            protected_hit = False
            for q in raw:
                if q.target_requirement_id not in allowed:
                    continue
                if self._guard.scan_text(f"{q.question} {q.rationale}"):
                    protected_hit = True
                    continue
                if all(v.question != q.question for v in valid):
                    valid.append(q)
            if not protected_hit or len(valid) >= count:
                break
            turn.warn("面試題涉及受保護屬性已剔除" + ("，已重新生成一次" if attempt == 0 else ""))
        return self._renumber(valid, count)

    @staticmethod
    def _renumber(questions: Sequence[InterviewQuestion], count: int) -> List[InterviewQuestion]:
        return [replace(q, no=i) for i, q in enumerate(list(questions)[:count], start=1)]

    @staticmethod
    def _template_questions(weaknesses: Sequence[WeaknessFact], count: int) -> List[InterviewQuestion]:
        questions = []
        for i, w in enumerate(list(weaknesses)[:count], start=1):
            questions.append(InterviewQuestion(
                no=i,
                question=f"請具體說明您在「{w.label}」方面的實際經驗、扮演角色與可量化成果。",
                target_requirement_id=w.requirement_id,
                rationale=f"該條件目前判定為「{w.status}」，需於面試中確認。",
            ))
        return questions

    # ------------------------------------------------------------------
    # general_qa / out_of_scope
    # ------------------------------------------------------------------
    def general_qa(self, state: ChatSessionState, turn: TurnContext) -> NodeUpdate:
        jd = state.jd_requirements
        history = trim_history(state.history, self._settings.history_max_turns, self._settings.history_max_chars)
        facts = GeneralQaFacts(
            question=self._deidentify(turn.message, state),
            jd_title=jd.title if jd else None,
            must_labels=tuple(r.label for r in jd.must) if jd else (),
            nice_labels=tuple(r.label for r in jd.nice) if jd else (),
            shortlist_aliases=tuple(f"{self._alias(e.rank)}（{'完全符合' if e.fully_qualified else '部分符合'}）"
                                    for e in state.shortlist),
            history=tuple(ChatMessage(m.role, self._deidentify(m.content, state)) for m in history),
        )
        answer = self._narrate(turn, self._narrator.answer_general, facts)
        if answer:
            turn.add_llm(answer)
        else:
            turn.add_template(self._template_general(jd))
        if jd:
            turn.quote_sources.extend(r.label for r in jd.all_requirements)
        return NodeUpdate(session=state)

    @staticmethod
    def _template_general(jd: Optional[JdRequirements]) -> str:
        if jd is None:
            return "目前尚未提供職缺 JD。請貼上職缺描述，我會從履歷庫挑選合適人選並說明推薦理由。"
        must = "\n".join(f"- {r.requirement_id} {r.label}" for r in jd.must) or "- （無）"
        nice = "\n".join(f"- {r.requirement_id} {r.label}" for r in jd.nice) or "- （無）"
        return f"目前職缺「{jd.title}」之條件如下：\n\n**必要條件**\n{must}\n\n**加分條件**\n{nice}"

    def out_of_scope(self, state: ChatSessionState, turn: TurnContext) -> NodeUpdate:
        turn.add_template("抱歉，我是招募助手，僅能協助職缺媒合、人選追問與面試題設計等招募相關事務。")
        return NodeUpdate(session=state)

    # ------------------------------------------------------------------
    # compose：合併回覆、引文後置驗證、更新狀態與歷史
    # ------------------------------------------------------------------
    def compose(self, state: ChatSessionState, turn: TurnContext) -> NodeUpdate:
        sources = list(turn.quote_sources)
        for entry in state.shortlist:
            sources.extend(e.quote for e in entry.evidence)
        # 系統詞彙白名單：狀態標籤、職缺名稱與條件 label 為系統產出，LLM 合法引述時不得剝除
        sources.extend(_STATUS_LABELS.values())
        if state.jd_requirements:
            sources.append(state.jd_requirements.title)
            sources.extend(r.label for r in state.jd_requirements.all_requirements)
        blocks: List[List[str]] = []
        removed_total = 0
        seen_starters = set()
        skipping = False
        for sec in turn.sections:
            if not sec.text:
                continue
            if sec.join is None:  # 區塊起點：與先前完全相同者整塊去重（含其接續段落）
                skipping = sec in seen_starters
                seen_starters.add(sec)
            if skipping:
                continue
            text = sec.text
            if sec.llm_generated:  # 僅驗證 LLM 產生之段落；模板段落不驗證
                text, removed = sanitize_reply_quotes(text, sources, self._verifier, _REMOVED_QUOTE_PLACEHOLDER)
                removed_total += removed
            if sec.join is not None and blocks:
                blocks[-1].append(sec.join)
                blocks[-1].append(text)
            else:
                blocks.append([text])
        reply = _SECTION_SEPARATOR.join("".join(b) for b in blocks) or "目前無法處理此請求，請換個說法再試一次。"
        if removed_total:
            turn.warn(f"回覆中 {removed_total} 段引文未通過原文驗證，已移除")
        # 各節點僅產出「候選人 #N」代稱版本；歷史只保存代稱版，姓名僅於本輪回應代入（G2-01）
        turn.final_reply = self._substitute_names(reply, state.shortlist)
        turn.usage.llm_calls = turn.budget.used

        history = tuple(state.history) + (
            ChatMessage(role="user", content=turn.message[: self._settings.history_max_chars]),
            ChatMessage(role="assistant", content=self._deidentify(reply, state)[: self._settings.history_max_chars]),
        )
        new_state = replace(
            state,
            turn_count=state.turn_count + 1,
            last_referenced_candidate_id=turn.referenced_candidate_id or state.last_referenced_candidate_id,
            history=trim_history(history, self._settings.history_max_turns, self._settings.history_max_chars),
        )
        return NodeUpdate(session=new_state)

    # ------------------------------------------------------------------
    # 共用輔助
    # ------------------------------------------------------------------
    def _narrate(self, turn: TurnContext, fn, *args):
        """呼叫敘述 LLM；配額/逾時向上拋出，其餘失敗回傳 None 並標記 degraded"""
        try:
            return self._call_llm(turn, fn, *args)
        except (LlmQuotaExhaustedError, TurnTimeoutError):
            raise
        except _BudgetExhausted:
            turn.degraded = True
            turn.warn("單輪 LLM 呼叫預算已用罄，部分回覆改用確定性模板")
            return None
        except LlmOutputTruncatedError:
            turn.degraded = True
            logger.warning("敘述輸出被截斷，改用確定性模板 (trace_id=%s)", turn.trace_id)
            turn.warn("敘述輸出超出長度上限，已改用系統摘要")
            return None
        except Exception as err:
            turn.degraded = True
            logger.warning("敘述 LLM 失敗，改用確定性模板 (trace_id=%s, err_type=%s)", turn.trace_id, type(err).__name__)
            return None

    def _resolve_target(self, state: ChatSessionState,
                        turn: TurnContext) -> Tuple[Optional[CandidateEvaluation], Optional[int], str]:
        ref = turn.reference or self._resolver.resolve(turn.message, state.shortlist,
                                                       state.last_referenced_candidate_id)
        if ref.kind == ReferenceKind.NO_SHORTLIST or not state.shortlist:
            return None, None, "目前尚無候選名單，請先貼上職缺 JD，我會先為您挑選人選。"
        if ref.kind == ReferenceKind.OUT_OF_RANGE:
            n = len(state.shortlist)
            return None, None, f"目前名單僅 {n} 位，請指定第 1 ~ {n} 位人選。"
        cid = ref.candidate_id if ref.kind == ReferenceKind.RESOLVED else state.last_referenced_candidate_id
        if not cid:
            return None, None, "請指明要詢問第幾位人選（例如「第 2 位」）。"
        target = state.find_evaluation(cid)
        if target is None:
            return None, None, "找不到該人選之評估資料，請重新提供 JD 產生名單。"
        entry = state.find_shortlist_entry(cid)
        return target, entry.rank if entry else ref.rank, ""

    def _load_llm_text(self, target: CandidateEvaluation, alias: str) -> str:
        summary = CandidateSummary(candidate_id=target.candidate_id, candidate_name=target.candidate_name,
                                   max_score=target.semantic_score)
        raw = self._tools.load_resume_text(summary)
        return self._profiles.prepare_llm_text(raw, [target.candidate_name], alias)

    @staticmethod
    def _profile_summary(target: CandidateEvaluation) -> Dict[str, str]:
        p = target.profile

        def fmt(value) -> str:
            return "履歷未提及" if value is None else str(value)

        return {
            "years_of_experience": fmt(p.years_of_experience),
            "has_led_team": fmt(p.has_led_team),
            "max_team_size": fmt(p.max_team_size),
            "seniority": fmt(p.seniority.name if p.seniority is not None else None),
            "core_skills": "、".join(p.core_skills) or "履歷未提及",
        }

    def _labels_by_status(self, jd: Optional[JdRequirements], target: CandidateEvaluation,
                          status: MatchStatus) -> Tuple[str, ...]:
        if jd is None:
            return ()
        return tuple(r.label for r in jd.all_requirements if target.statuses.get(r.requirement_id) == status)

    @staticmethod
    def _label(jd: JdRequirements, requirement_id: str) -> str:
        req = jd.find(requirement_id)
        return req.label if req else requirement_id

    @staticmethod
    def _alias(rank: Optional[int]) -> str:
        return f"候選人 #{rank}"

    def _deidentify(self, text: str, state: ChatSessionState) -> str:
        """送 LLM 前將名單/候選池姓名替換為代稱並遮蔽聯絡方式（AC-12）"""
        result = text or ""
        aliases = {e.candidate_name: self._alias(e.rank) for e in state.shortlist if e.candidate_name}
        for ev in state.pool_evaluations:
            if ev.candidate_name and ev.candidate_name not in aliases:
                aliases[ev.candidate_name] = "某候選人"
        for name in sorted(aliases, key=len, reverse=True):
            result = mask_contact_info(result, [name], aliases[name])
        return mask_contact_info(result, [], "")

    @staticmethod
    def _substitute_names(text: str, shortlist: Sequence[ShortlistEntry]) -> str:
        """伺服器端姓名模板代入：LLM 僅見代稱，回覆時補上姓名（AC-12）"""
        names = {e.rank: e.candidate_name for e in shortlist}

        def _sub(match: "re.Match[str]") -> str:
            rank = int(match.group(1))
            name = names.get(rank)
            return f"{match.group(0)}（{name}）" if name else match.group(0)

        return re.sub(r"候選人\s*#(\d+)(?!\d|\s*[（(])", _sub, text or "")
