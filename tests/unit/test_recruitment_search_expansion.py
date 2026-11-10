"""
候選人不足時自動擴大檢索單元測試 (ADR-0021 / Spec-0021)

100% 離線：記憶體 Fake 向量檢索（依 min_score / top_k / pool_size 真實篩選）+ Fake LLM；
所有履歷與姓名皆為虛構、於記憶體動態建構，不讀取 data/ 或 resume/。
"""
import importlib.util
import os
import threading
import unittest
from pathlib import Path
from typing import Dict, List
from unittest.mock import patch

from src.application.candidate_profile_service import TurnBudget
from src.application.recruitment_nodes import NodeUpdate, RecruitmentNodeHandlers
from src.domain.exceptions import LlmQuotaExhaustedError
from src.domain.models import SearchResultItem
from src.domain.recruitment import (
    CandidateProfile,
    ChatIntent,
    ChatSessionState,
    EvidenceQuote,
    SearchExpansionLimits,
    SearchRoundParams,
    SearchRoundRecord,
    SearchStopReason,
)
from src.domain.recruitment_services import SearchExpansionPolicy
from tests.unit.recruitment_fakes import (
    JD_TEXT,
    FakeClassifier,
    FakeNarrator,
    InMemoryProfileCache,
    build_handlers,
    make_settings,
)

HAS_LANGGRAPH = importlib.util.find_spec("langgraph") is not None
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BODY_MARKER = "此段為不會成為證據之履歷內文標記"


# ----------------------------------------------------------------------
# 虛構候選人庫與 Fake
# ----------------------------------------------------------------------
def make_resume(idx: int, score: float, qualified: bool) -> Dict:
    """qualified=True：Python + 7 年 + 帶過團隊（符合 make_jd 三項必要條件）；否則僅 2 年經驗"""
    years = 7 if qualified else 2
    lead = f"帶領 4 人團隊{idx:02d}"
    text = (f"# 張小強{idx:02d}\n- 工作經歷：{years}年工作經驗\n## 經歷\n{lead}開發 Python 服務。\n{BODY_MARKER}")
    return {"name": f"張小強{idx:02d}", "score": score, "skills": ["python"], "text": text,
            "years": float(years), "years_quote": f"{years}年工作經驗", "lead_quote": lead,
            "skill_quote": "Python 服務"}


def make_library(spec: List[tuple]) -> Dict[str, Dict]:
    """spec: [(score, qualified), ...]，依序編號 cand_s01..."""
    return {f"cand_s{i + 1:02d}": make_resume(i + 1, score, q) for i, (score, q) in enumerate(spec)}


class ThresholdSearch:
    """每位候選人一個切片：依 min_score 篩選、依 top_k 截斷（模擬真實向量檢索之範圍語意）"""

    def __init__(self, resumes: Dict[str, Dict], fail_on_call: int = 0, fail_exc: Exception = None):
        self.resumes = resumes
        self.queries = []
        self.fail_on_call = fail_on_call
        self.fail_exc = fail_exc or RuntimeError("redis down")

    def execute_grouped_by_candidate(self, query):
        self.queries.append(query)
        if self.fail_on_call and len(self.queries) == self.fail_on_call:
            raise self.fail_exc
        rows = []
        for cid, r in self.resumes.items():
            if r["score"] < query.min_score:
                continue
            chunk = SearchResultItem(candidate_id=cid, candidate_name=r["name"], chunk_type="experience",
                                     section_title="經歷", content=r["text"], score=r["score"], skills=r["skills"])
            rows.append({"candidate_id": cid, "candidate_name": r["name"], "max_score": r["score"],
                         "matched_chunks": [chunk], "all_skills": list(r["skills"]), "file_path": None})
        rows.sort(key=lambda x: x["max_score"], reverse=True)
        return rows[: query.top_k]

    def get_resume_markdown(self, candidate_id):
        r = self.resumes.get(candidate_id)
        return r["text"] if r else None


class LibraryExtractor:
    def __init__(self, resumes: Dict[str, Dict]):
        self.resumes = resumes
        self.calls: List[str] = []
        self._lock = threading.Lock()

    @property
    def extractor_version(self) -> str:
        return "v-test"

    def extract(self, candidate_id, resume_text, content_hash):
        with self._lock:
            self.calls.append(candidate_id)
        r = self.resumes[candidate_id]
        led = r["years"] >= 5
        evidence = [EvidenceQuote("years", r["years_quote"]), EvidenceQuote("skill:python", r["skill_quote"])]
        if led:
            evidence.append(EvidenceQuote("has_led_team", r["lead_quote"]))
        return CandidateProfile(candidate_id=candidate_id, content_hash=content_hash, extractor_version="v-test",
                                years_of_experience=r["years"], has_led_team=True if led else None,
                                max_team_size=None, seniority=None, core_skills=("python",),
                                evidence=tuple(evidence))


def build(spec, clock=None, cache=None, search_kwargs=None, classifier=None, **settings_overrides):
    library = make_library(spec)
    search = ThresholdSearch(library, **(search_kwargs or {}))
    extractor = LibraryExtractor(library)
    narrator = FakeNarrator()
    handlers = build_handlers(settings=make_settings(**settings_overrides), search=search,
                              profile_extractor=extractor, cache=cache, narrator=narrator, clock=clock,
                              classifier=classifier)
    return handlers, search, extractor, narrator


def run(handlers, message=JD_TEXT):
    turn = handlers.new_turn(message, "trace-x")
    state = handlers.run_all(ChatSessionState(session_id="sess-x"), turn)
    return state, turn


def base_pool(qualified_count: int, size: int = 15, top: float = 0.9) -> List[tuple]:
    """前 size 名（分數 >= 0.6）中前 qualified_count 位合格"""
    return [(round(top - i * 0.01, 3), i < qualified_count) for i in range(size)]


# ----------------------------------------------------------------------
# Domain：SearchExpansionPolicy
# ----------------------------------------------------------------------
LIMITS = SearchExpansionLimits(max_rounds=2, pool_step=10, pool_max=40, top_k_max=200,
                               min_score_step=0.05, min_score_floor=0.4)


def rec(round_no, target, top_k, min_score, returned, new, qualified):
    return SearchRoundRecord(SearchRoundParams(round_no, target, top_k, min_score), returned, new, qualified)


class TestSearchExpansionPolicy(unittest.TestCase):
    def setUp(self):
        self.policy = SearchExpansionPolicy(LIMITS)
        self.base = rec(0, 15, 60, 0.5, 15, 15, 1)

    def decide(self, history, k=3, evaluated=15, affordable=10, seconds=100.0, min_seconds=30.0, policy=None):
        return (policy or self.policy).decide(history, k, evaluated, affordable, seconds, min_seconds)

    def test_initial_should_clamp_to_positive(self):
        p = SearchExpansionPolicy.initial(0, 0, 0.5)
        self.assertEqual((p.round_no, p.pool_target, p.top_k_chunks, p.min_score), (0, 1, 1, 0.5))

    def test_decide_when_qualified_enough_should_stop_satisfied_before_any_other_reason(self):
        history = [self.base, rec(1, 25, 100, 0.5, 25, 10, 3), rec(2, 35, 140, 0.5, 35, 10, 3)]
        nxt, reason = self.decide(history, affordable=0, seconds=0.0)
        self.assertIsNone(nxt)
        self.assertEqual(reason, SearchStopReason.SATISFIED)

    def test_decide_when_disabled_should_stop_disabled(self):
        policy = SearchExpansionPolicy(SearchExpansionLimits(0, 10, 40, 200, 0.05, 0.4))
        self.assertEqual(self.decide([self.base], policy=policy), (None, SearchStopReason.DISABLED))

    def test_decide_after_max_rounds_should_stop(self):
        history = [self.base, rec(1, 25, 100, 0.5, 25, 10, 1), rec(2, 35, 140, 0.5, 35, 10, 1)]
        self.assertEqual(self.decide(history, evaluated=35), (None, SearchStopReason.MAX_ROUNDS))

    def test_decide_when_time_short_should_stop_deadline(self):
        self.assertEqual(self.decide([self.base], seconds=29.9), (None, SearchStopReason.DEADLINE))

    def test_decide_when_no_affordable_calls_should_stop_budget(self):
        self.assertEqual(self.decide([self.base], affordable=0), (None, SearchStopReason.BUDGET))

    def test_decide_when_saturated_at_floor_should_stop_exhausted(self):
        history = [rec(0, 15, 60, 0.4, 8, 8, 0)]
        self.assertEqual(self.decide(history, evaluated=8), (None, SearchStopReason.EXHAUSTED))

    def test_decide_when_saturated_should_lower_min_score_but_never_below_floor(self):
        history = [rec(0, 15, 60, 0.42, 8, 8, 0)]
        nxt, reason = self.decide(history, evaluated=8)
        self.assertIsNone(reason)
        self.assertAlmostEqual(nxt.min_score, 0.4)
        self.assertEqual(nxt.round_no, 1)

    def test_decide_when_not_saturated_should_keep_threshold_and_scale_pool_and_top_k(self):
        nxt, reason = self.decide([self.base])
        self.assertIsNone(reason)
        self.assertEqual(nxt, SearchRoundParams(round_no=1, pool_target=25, top_k_chunks=100, min_score=0.5))

    def test_decide_top_k_should_be_capped(self):
        policy = SearchExpansionPolicy(SearchExpansionLimits(2, 10, 40, 80, 0.05, 0.4))
        nxt, _ = self.decide([self.base], policy=policy)
        self.assertEqual(nxt.top_k_chunks, 80)

    def test_decide_target_should_be_limited_by_affordable_calls(self):
        nxt, _ = self.decide([self.base], affordable=3)
        self.assertEqual(nxt.pool_target, 18)

    def test_decide_when_pool_max_reached_should_stop_pool_cap(self):
        history = [self.base, rec(1, 40, 160, 0.5, 40, 25, 1)]
        policy = SearchExpansionPolicy(SearchExpansionLimits(3, 10, 40, 200, 0.05, 0.4))
        self.assertEqual(self.decide(history, evaluated=40, policy=policy), (None, SearchStopReason.POOL_CAP))

    def test_decide_with_empty_history_should_raise(self):
        with self.assertRaises(ValueError):
            self.decide([])


# ----------------------------------------------------------------------
# Application：TurnBudget 保留額度
# ----------------------------------------------------------------------
class TestTurnBudgetReserve(unittest.TestCase):
    def test_reserved_view_should_never_consume_reserved_calls(self):
        budget = TurnBudget(5)
        view = budget.reserved_view(2)
        results = [view.try_consume() for _ in range(5)]
        self.assertEqual(results, [True, True, True, False, False])
        self.assertEqual(budget.remaining, 2)
        self.assertTrue(budget.try_consume())  # 保留額度仍可由一般呼叫使用

    def test_reserved_view_should_be_thread_safe(self):
        budget = TurnBudget(100)
        view = budget.reserved_view(10)
        granted = []
        lock = threading.Lock()

        def worker():
            for _ in range(20):
                ok = view.try_consume()
                with lock:
                    granted.append(ok)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(sum(granted), 90)
        self.assertEqual(budget.remaining, 10)


# ----------------------------------------------------------------------
# Application：jd_match 子步驟節點
# ----------------------------------------------------------------------
class TestSearchExpansionNodes(unittest.TestCase):
    def test_baseline_satisfied_should_not_expand_and_match_disabled_output(self):
        # AC-1：基準輪已足夠 → 只檢索 1 次，回覆與停用時逐字相同
        spec = base_pool(qualified_count=3)
        h_on, search_on, _, _ = build(spec)
        h_off, _, _, _ = build(spec, search_expansion_max_rounds=0)
        state_on, turn_on = run(h_on)
        state_off, turn_off = run(h_off)
        self.assertEqual(len(search_on.queries), 1)
        self.assertEqual(turn_on.usage.search_rounds, 0)
        self.assertEqual(turn_on.usage.search_stop_reason, "SATISFIED")
        self.assertEqual(turn_on.final_reply, turn_off.final_reply)
        self.assertEqual(turn_on.warnings, turn_off.warnings)
        self.assertNotIn("檢索擴大紀錄", turn_on.final_reply)
        self.assertIsNone(state_on.relaxation)

    def test_expansion_round_should_find_new_qualified_candidates(self):
        # AC-2 + AC-8：第 16~20 名中有 2 位合格 → 第 1 輪補足
        spec = base_pool(qualified_count=1) + [(0.7, True), (0.69, False), (0.68, True)]
        handlers, search, extractor, _ = build(spec, max_llm_calls_per_turn=100)  # 預算充足：目標人數不受預算截斷
        state, turn = run(handlers)
        self.assertEqual(len(search.queries), 2)
        self.assertEqual(search.queries[1].min_score, 0.5)
        self.assertEqual(search.queries[1].top_k, 100)
        self.assertEqual(turn.usage.search_rounds, 1)
        self.assertEqual(turn.usage.search_stop_reason, "SATISFIED")
        self.assertEqual(turn.usage.pool_evaluated, 18)
        self.assertEqual({e.candidate_id for e in state.shortlist}, {"cand_s01", "cand_s16", "cand_s18"})
        self.assertTrue(all(e.fully_qualified for e in state.shortlist))
        self.assertIsNone(state.relaxation)
        self.assertEqual(len(extractor.calls), 18)
        self.assertEqual(len(set(extractor.calls)), 18)
        self.assertIn("### 檢索擴大紀錄", turn.final_reply)
        self.assertIn("| 第 1 輪 | 0.50 | 25 | 18 | 3 | 3 |", turn.final_reply)
        self.assertIn("停止原因：完全符合必要條件之人數已達需求", turn.final_reply)
        self.assertIn("jd_search_round", turn.node_ms)
        self.assertIsNone(turn.jd_search)  # 暫態資料已釋放

    def test_warm_cache_rerun_should_not_extract_again(self):
        # AC-8：快取命中 0 Token
        spec = base_pool(qualified_count=1) + [(0.7, True), (0.68, True)]
        cache = InMemoryProfileCache()
        handlers, _, extractor, _ = build(spec, cache=cache)
        run(handlers)
        first_calls = len(extractor.calls)
        run(handlers)
        self.assertEqual(len(extractor.calls), first_calls)

    def test_saturated_pool_should_lower_threshold_until_floor(self):
        # AC-3：門檻 0.5 只有 5 人 → 降到 0.45 找到合格者；下限 0.45 時仍飽和 → EXHAUSTED
        spec = [(0.8 - i * 0.01, False) for i in range(5)] + [(0.47, True), (0.46, False)]
        handlers, search, _, _ = build(spec, search_expansion_min_score_floor=0.45)
        state, turn = run(handlers)
        self.assertEqual([q.min_score for q in search.queries], [0.5, 0.45])
        self.assertEqual(turn.usage.search_stop_reason, "EXHAUSTED")
        self.assertTrue(all(q.min_score >= 0.45 for q in search.queries))
        self.assertIn("cand_s06", {e.candidate_id for e in state.shortlist})

    def test_max_rounds_should_stop_and_annotate_relaxation_scope(self):
        # AC-4：沒有任何合格者 → 擴大 2 輪後停止，放寬報告標註擴大輪數
        spec = [(0.95 - i * 0.005, False) for i in range(60)]
        handlers, search, _, _ = build(spec, max_llm_calls_per_turn=100)
        state, turn = run(handlers)
        self.assertEqual(len(search.queries), 3)
        self.assertEqual(turn.usage.search_stop_reason, "MAX_ROUNDS")
        self.assertEqual(state.relaxation.pool_size, 35)
        self.assertIn("已自動擴大檢索 2 輪", state.relaxation.scope_note)
        self.assertIn("已自動擴大檢索 2 輪", turn.final_reply)
        self.assertEqual(len(state.pool_evaluations), 35)

    def test_default_budget_should_limit_expansion_target(self):
        # AC-6：預設預算 25：JD 1 + 基準 15 = 16，扣保留 2 → 第 1 輪目標 15+7=22（切片數等比例 88）
        spec = [(0.95 - i * 0.005, False) for i in range(60)]
        handlers, search, extractor, _ = build(spec)
        _, turn = run(handlers)
        self.assertEqual((search.queries[1].top_k, len(extractor.calls)), (88, 22))
        self.assertEqual(turn.usage.search_stop_reason, "BUDGET")

    def test_pool_max_should_cap_total_evaluated(self):
        # AC-5
        spec = [(0.95 - i * 0.005, False) for i in range(60)]
        handlers, _, extractor, _ = build(spec, search_expansion_pool_max=20, search_expansion_max_rounds=5)
        _, turn = run(handlers)
        self.assertEqual(turn.usage.pool_evaluated, 20)
        self.assertEqual(turn.usage.search_stop_reason, "POOL_CAP")
        self.assertEqual(len(extractor.calls), 20)

    def test_budget_reserve_should_keep_llm_narration(self):
        # AC-6：JD 1 + 基準 15 = 16，上限 21、保留 2 → 擴大輪最多抽 3 人，敘述仍由 LLM 產生
        spec = [(0.95 - i * 0.005, False) for i in range(60)]
        handlers, _, extractor, narrator = build(spec, max_llm_calls_per_turn=21)
        narrator.match_text = "推薦理由由敘述模型產生。"
        _, turn = run(handlers)
        self.assertEqual(len(extractor.calls), 18)
        self.assertEqual(turn.usage.search_stop_reason, "BUDGET")
        self.assertEqual(len(narrator.match_facts), 1)
        self.assertIn(narrator.match_text, turn.final_reply)
        self.assertFalse(turn.degraded)

    def test_deadline_should_stop_without_timeout_error(self):
        # AC-7
        spec = base_pool(qualified_count=1)
        handlers, search, _, _ = build(spec, search_expansion_min_remaining_seconds=1000.0)
        _, turn = run(handlers)
        self.assertEqual(len(search.queries), 1)
        self.assertEqual(turn.usage.search_stop_reason, "DEADLINE")

    def test_disabled_should_keep_original_relaxation_scope(self):
        # AC-9
        spec = base_pool(qualified_count=1)
        handlers, search, _, _ = build(spec, search_expansion_max_rounds=0)
        state, turn = run(handlers)
        self.assertEqual(len(search.queries), 1)
        self.assertEqual(turn.usage.search_stop_reason, "DISABLED")
        self.assertEqual(state.relaxation.scope_note, "僅統計語意檢索候選池 Top-N")
        self.assertNotIn("檢索擴大紀錄", turn.final_reply)

    def test_empty_pool_should_try_lower_threshold_then_report_no_candidates(self):
        # AC-12
        spec = [(0.3, True), (0.2, True)]
        handlers, search, extractor, narrator = build(spec)
        state, turn = run(handlers)
        self.assertEqual([q.min_score for q in search.queries], [0.5, 0.45, 0.4])
        self.assertIn("資料庫中無相關人選", turn.final_reply)
        self.assertEqual(extractor.calls, [])
        self.assertEqual(narrator.match_facts, [])
        self.assertEqual(state.shortlist, ())

    def test_small_pool_should_warn_with_total_count(self):
        spec = [(0.8, True), (0.7, False)]
        handlers, _, _, _ = build(spec)
        _, turn = run(handlers)
        self.assertIn("候選池僅 2 人，少於需求之 3 位", turn.warnings)

    def test_expansion_retrieval_failure_should_finish_with_evaluated_candidates(self):
        spec = base_pool(qualified_count=1) + [(0.7, True)]
        handlers, search, _, _ = build(spec, search_kwargs={"fail_on_call": 2})
        state, turn = run(handlers)
        self.assertEqual(len(search.queries), 2)
        self.assertEqual(turn.usage.search_stop_reason, "EXHAUSTED")
        self.assertTrue(any("擴大檢索失敗" in w for w in turn.warnings))
        self.assertEqual(len(state.pool_evaluations), 15)

    def test_baseline_retrieval_failure_should_propagate(self):
        handlers, _, _, _ = build(base_pool(1), search_kwargs={"fail_on_call": 1})
        with self.assertRaises(RuntimeError):
            run(handlers)

    def test_expansion_quota_error_should_propagate(self):
        handlers, _, _, _ = build(base_pool(1), search_kwargs={
            "fail_on_call": 2, "fail_exc": LlmQuotaExhaustedError("429")})
        with self.assertRaises(LlmQuotaExhaustedError):
            run(handlers)

    def test_substep_without_progress_should_raise(self):
        handlers, _, _, _ = build(base_pool(1))
        turn = handlers.new_turn(JD_TEXT, "t")
        with self.assertRaises(RuntimeError):
            handlers.jd_search_round(ChatSessionState(session_id="s"), turn)

    def test_run_all_with_unknown_goto_should_raise(self):
        handlers, _, _, _ = build(base_pool(1))
        with patch.object(RecruitmentNodeHandlers, "jd_match",
                          lambda self, state, turn: NodeUpdate(session=state, goto="bogus")):
            with self.assertRaises(ValueError):
                run(handlers)


# ----------------------------------------------------------------------
# Infrastructure：LangGraph 子步驟循環
# ----------------------------------------------------------------------
@unittest.skipUnless(HAS_LANGGRAPH, "langgraph 未安裝")
class TestSearchExpansionGraph(unittest.TestCase):
    def make_orch(self, handlers, max_intents=2):
        from src.infrastructure.orchestration.checkpointer_factory import build_memory_checkpointer
        from src.infrastructure.orchestration.langgraph_recruitment_graph import LangGraphRecruitmentOrchestrator
        bundle = build_memory_checkpointer(session_ttl_seconds=600, max_sessions=10)
        return LangGraphRecruitmentOrchestrator(handlers, bundle, max_intents_per_turn=max_intents)

    def test_graph_should_contain_self_loop_and_finalize_edges(self):
        handlers, _, _, _ = build(base_pool(1))
        edges = {(e.source, e.target) for e in self.make_orch(handlers)._graph.get_graph().edges}
        self.assertIn(("jd_match", "jd_search_round"), edges)
        self.assertIn(("jd_search_round", "jd_search_round"), edges)
        self.assertIn(("jd_search_round", "jd_finalize"), edges)
        self.assertIn(("jd_finalize", "compose"), edges)

    def test_graph_outcome_should_equal_run_all(self):
        spec = base_pool(qualified_count=1) + [(0.7, True), (0.68, True)]
        h_graph, _, _, _ = build(spec)
        h_plain, _, _, _ = build(spec)
        outcome = self.make_orch(h_graph).run_turn("sess-g", JD_TEXT, "t1")
        state, turn = run(h_plain)
        self.assertEqual(outcome.reply_markdown, turn.final_reply)
        self.assertEqual(outcome.shortlist, state.shortlist)
        self.assertEqual(outcome.usage.search_rounds, 1)

    def test_max_config_with_two_intents_should_not_hit_recursion_limit(self):
        # AC-10：MAX_ROUNDS=5 + 2 意圖；第二意圖只執行一次
        spec = [(0.95 - i * 0.005, False) for i in range(120)]
        classifier = FakeClassifier(intents=[ChatIntent.JD_MATCH, ChatIntent.GENERAL_QA])
        handlers, search, _, narrator = build(spec, classifier=classifier, search_expansion_max_rounds=5,
                                              search_expansion_pool_max=100, max_llm_calls_per_turn=200)
        outcome = self.make_orch(handlers).run_turn("sess-r", "幫我找人", "t1")
        self.assertEqual(outcome.intents, [ChatIntent.JD_MATCH, ChatIntent.GENERAL_QA])
        self.assertEqual(outcome.usage.search_rounds, 5)
        self.assertEqual(len(search.queries), 6)
        self.assertEqual(len(narrator.general_facts), 1)

    def test_checkpoint_should_not_contain_resume_body_and_goto_reset(self):
        # AC-11
        spec = base_pool(qualified_count=1) + [(0.7, True), (0.68, True)]
        handlers, _, _, _ = build(spec)
        orch = self.make_orch(handlers)
        orch.run_turn("sess-c", JD_TEXT, "t1")
        config = {"configurable": {"thread_id": "sess-c"}}
        history = list(orch._graph.get_state_history(config))
        self.assertTrue(history)
        for snap in history:
            self.assertNotIn(BODY_MARKER, repr(snap.values))
            self.assertLessEqual(set(snap.values), {"session", "queue", "goto"})
        self.assertIsNone(orch._graph.get_state(config).values.get("goto"))

    def test_substep_nodes_should_not_rewrite_unchanged_session(self):
        from src.domain.recruitment_codec import session_to_dict
        from src.infrastructure.orchestration.langgraph_recruitment_graph import TurnRuntimeContext
        spec = base_pool(qualified_count=1) + [(0.7, True), (0.68, True)]
        handlers, _, _, _ = build(spec)
        orch = self.make_orch(handlers)
        turn = handlers.new_turn(JD_TEXT, "t1")
        updates = list(orch._graph.stream(
            {"session": session_to_dict(ChatSessionState(session_id="sess-u")), "queue": [], "goto": None},
            {"configurable": {"thread_id": "sess-u"}, "recursion_limit": 50},
            context=TurnRuntimeContext(turn=turn), stream_mode="updates"))
        by_node = [(name, out) for upd in updates for name, out in upd.items()]
        rounds = [out for name, out in by_node if name == "jd_search_round"]
        self.assertEqual(len(rounds), 2)
        self.assertTrue(all("session" not in out for out in rounds))
        self.assertTrue(all("queue" not in out for out in rounds))
        finalize = [out for name, out in by_node if name == "jd_finalize"]
        self.assertIn("session", finalize[0])
        self.assertEqual(finalize[0]["queue"], [])

    def test_in_place_session_mutation_should_still_be_persisted(self):
        # Gate 2 P2：節點就地修改 session 並回傳同一物件時，變更不得因「未變更不輸出」最佳化而遺失
        def mutate_in_place(self, state, turn):
            state.last_referenced_candidate_id = "cand_inplace"
            return NodeUpdate(session=state)

        handlers, _, _, _ = build(base_pool(1), classifier=FakeClassifier(intents=[ChatIntent.GENERAL_QA]))
        orch = self.make_orch(handlers)
        with patch.object(RecruitmentNodeHandlers, "general_qa", mutate_in_place):
            orch.run_turn("sess-m", "你好", "t1")
        self.assertEqual(orch.get_state("sess-m").last_referenced_candidate_id, "cand_inplace")

    def test_graph_unknown_goto_should_raise(self):
        handlers, _, _, _ = build(base_pool(1))
        orch = self.make_orch(handlers)
        with patch.object(RecruitmentNodeHandlers, "jd_match",
                          lambda self, state, turn: NodeUpdate(session=state, goto="bogus")):
            with self.assertRaises(ValueError):
                orch.run_turn("sess-b", JD_TEXT, "t1")


# ----------------------------------------------------------------------
# Config：AppConfig 與 .env.example
# ----------------------------------------------------------------------
class TestSearchExpansionConfig(unittest.TestCase):
    KEYS = (
        "RECRUIT_SEARCH_EXPANSION_MAX_ROUNDS", "RECRUIT_SEARCH_EXPANSION_POOL_STEP",
        "RECRUIT_SEARCH_EXPANSION_POOL_MAX", "RECRUIT_SEARCH_EXPANSION_TOP_K_CHUNKS_MAX",
        "RECRUIT_SEARCH_EXPANSION_MIN_SCORE_STEP", "RECRUIT_SEARCH_EXPANSION_MIN_SCORE_FLOOR",
        "RECRUIT_SEARCH_EXPANSION_LLM_RESERVE", "RECRUIT_SEARCH_EXPANSION_MIN_REMAINING_SECONDS",
    )

    def load(self, env):
        from src.infrastructure.config import AppConfig
        with patch.dict(os.environ, env, clear=True):
            return AppConfig.load(override_api_key="mock_key")

    def test_defaults(self):
        cfg = self.load({})
        self.assertEqual(
            (cfg.recruit_search_expansion_max_rounds, cfg.recruit_search_expansion_pool_step,
             cfg.recruit_search_expansion_pool_max, cfg.recruit_search_expansion_top_k_chunks_max,
             cfg.recruit_search_expansion_min_score_step, cfg.recruit_search_expansion_min_score_floor,
             cfg.recruit_search_expansion_llm_reserve, cfg.recruit_search_expansion_min_remaining_seconds),
            (2, 10, 40, 200, 0.05, 0.4, 2, 30.0))

    def test_out_of_range_values_should_be_clamped(self):
        cfg = self.load({
            "RECRUIT_SEARCH_EXPANSION_MAX_ROUNDS": "99",
            "RECRUIT_SEARCH_EXPANSION_POOL_MAX": "5",            # < CANDIDATE_POOL_SIZE(15)
            "RECRUIT_SEARCH_EXPANSION_TOP_K_CHUNKS_MAX": "10",   # < RETRIEVAL_TOP_K_CHUNKS(60)
            "RECRUIT_SEARCH_EXPANSION_MIN_SCORE_FLOOR": "0.9",   # > RETRIEVAL_MIN_SCORE(0.5)
            "RECRUIT_SEARCH_EXPANSION_MIN_SCORE_STEP": "-1",
            "RECRUIT_SEARCH_EXPANSION_LLM_RESERVE": "-3",
            "RECRUIT_SEARCH_EXPANSION_MIN_REMAINING_SECONDS": "9999",
        })
        self.assertEqual(cfg.recruit_search_expansion_max_rounds, 5)
        self.assertEqual(cfg.recruit_search_expansion_pool_max, 15)
        self.assertEqual(cfg.recruit_search_expansion_top_k_chunks_max, 60)
        self.assertEqual(cfg.recruit_search_expansion_min_score_floor, 0.5)
        self.assertGreater(cfg.recruit_search_expansion_min_score_step, 0.0)
        self.assertEqual(cfg.recruit_search_expansion_llm_reserve, 0)
        self.assertEqual(cfg.recruit_search_expansion_min_remaining_seconds, 150.0)

    def test_non_numeric_and_nan_values_should_fallback(self):
        cfg = self.load({"RECRUIT_SEARCH_EXPANSION_POOL_STEP": "abc",
                         "RECRUIT_SEARCH_EXPANSION_MIN_SCORE_FLOOR": "nan"})
        self.assertEqual(cfg.recruit_search_expansion_pool_step, 10)
        self.assertEqual(cfg.recruit_search_expansion_min_score_floor, 0.0)

    def test_settings_mapping_should_carry_all_fields(self):
        from src.interfaces.web.server import build_recruitment_settings
        cfg = self.load({"RECRUIT_SEARCH_EXPANSION_MAX_ROUNDS": "3", "RECRUIT_SEARCH_EXPANSION_LLM_RESERVE": "4"})
        settings = build_recruitment_settings(cfg)
        self.assertEqual(settings.search_expansion_max_rounds, 3)
        self.assertEqual(settings.search_expansion_llm_reserve, 4)
        self.assertEqual(settings.search_expansion_min_score_floor, 0.4)

    def test_env_example_should_document_all_keys(self):
        text = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
        for key in self.KEYS:
            self.assertIn(f"{key}=", text)


if __name__ == "__main__":
    unittest.main()
