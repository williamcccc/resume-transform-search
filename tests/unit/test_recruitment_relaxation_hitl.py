"""
放寬條件之人工決策單元測試 (ADR-0022 / Spec-0022)

100% 離線：記憶體 Fake 檢索 / LLM + LangGraph InMemorySaver；所有履歷與姓名皆為虛構、於記憶體動態建構。
預設 Fake 庫（recruitment_fakes.RESUMES）對 make_jd 之三項必要條件只有 cand_a 完全符合，必然觸發放寬報告。
"""
import importlib.util
import logging
import os
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.application.dto import ChatTurnCommand
from src.application.recruitment_chat_use_case import RecruitmentChatUseCase
from src.domain.exceptions import RelaxationDecisionError
from src.domain.recruitment import (
    CandidateEvaluation,
    CandidateProfile,
    ChatIntent,
    ChatSessionState,
    MatchStatus,
    RelaxationItem,
    RelaxationReport,
)
from src.domain.recruitment_codec import (
    relaxation_prompt_from_dict,
    relaxation_prompt_to_dict,
    session_from_dict,
    session_to_dict,
)
from src.domain.recruitment_services import (
    CandidateRanker,
    apply_requirement_relaxation,
    build_relaxation_prompt,
    renumber_requirements,
    validate_relaxation_decision,
)
from tests.unit.recruitment_fakes import (
    JD_TEXT,
    FakeClassifier,
    FakeNarrator,
    FakeProfileExtractor,
    build_handlers,
    make_jd,
    make_settings,
)

HAS_LANGGRAPH = importlib.util.find_spec("langgraph") is not None
PROJECT_ROOT = Path(__file__).resolve().parents[2]
GUIDE_FRAGMENT = "勾選要放寬的條件"


def settings(**kw):
    kw.setdefault("search_expansion_max_rounds", 0)  # 本檔聚焦人工放寬，排除自動擴大之干擾
    return make_settings(**kw)


def jd3():
    jd, _ = renumber_requirements(make_jd(), 12)
    return jd


def report(items, bottleneck=(), strictest=(), k=3, baseline=1):
    return RelaxationReport(pool_size=4, baseline_qualified=baseline, requested_k=k, items=tuple(items),
                            bottleneck_requirement_ids=tuple(bottleneck), strictest_requirement_ids=tuple(strictest))


def item(rid, q=2, delta=1, unknown=0):
    return RelaxationItem(requirement_id=rid, label=f"條件{rid}", qualified_if_relaxed=q, delta=delta,
                          unknown_count=unknown, met_count=1)


def evaluation(cid, statuses, must=("R1", "R2", "R3"), nice=("R4",), score=0.5):
    profile = CandidateProfile(candidate_id=cid, content_hash="h", extractor_version="v", years_of_experience=None,
                               has_led_team=None, max_team_size=None, seniority=None, core_skills=(), evidence=())
    return CandidateEvaluation(candidate_id=cid, candidate_name=f"虛構{cid}", semantic_score=score,
                               statuses={k: MatchStatus(v) for k, v in statuses.items()}, profile=profile,
                               must_ids=tuple(must), nice_ids=tuple(nice))


# ----------------------------------------------------------------------
# Domain
# ----------------------------------------------------------------------
class TestRelaxationDomain(unittest.TestCase):
    def setUp(self):
        self.jd = jd3()
        self.rep = report([item("R1"), item("R2", delta=2), item("R3")], bottleneck=("R2",))

    def test_build_prompt_should_list_must_items_with_recommendation(self):
        prompt = build_relaxation_prompt(self.jd, self.rep, rounds_used=0, max_rounds=2)
        self.assertEqual([o.requirement_id for o in prompt.options], ["R1", "R2", "R3"])
        self.assertEqual([o.recommended for o in prompt.options], [False, True, False])
        self.assertEqual((prompt.round, prompt.max_rounds, prompt.max_select), (1, 2, 2))

    def test_build_prompt_should_fall_back_to_strictest_when_no_bottleneck(self):
        rep = report([item("R1", delta=0), item("R2", delta=0)], strictest=("R1",))
        prompt = build_relaxation_prompt(self.jd, rep, 0, 2)
        self.assertEqual([o.recommended for o in prompt.options], [True, False])

    def test_build_prompt_should_return_none_when_not_applicable(self):
        one_must = replace(self.jd, must=self.jd.must[:1])
        self.assertIsNone(build_relaxation_prompt(None, self.rep, 0, 2))
        self.assertIsNone(build_relaxation_prompt(self.jd, None, 0, 2))
        self.assertIsNone(build_relaxation_prompt(self.jd, self.rep, 2, 2))
        self.assertIsNone(build_relaxation_prompt(one_must, self.rep, 0, 2))

    def test_validate_should_accept_and_normalize(self):
        prompt = build_relaxation_prompt(self.jd, self.rep, 0, 2)
        self.assertEqual(validate_relaxation_decision(prompt, [" r2 ", "R3"]), ("R2", "R3"))

    def test_validate_should_reject_invalid_decisions(self):
        prompt = build_relaxation_prompt(self.jd, self.rep, 0, 2)
        for ids in ([], ["R2", "R2"], ["R9"], ["R4"], ["R1", "R2", "R3"]):
            with self.subTest(ids=ids), self.assertRaises(RelaxationDecisionError) as ctx:
                validate_relaxation_decision(prompt, ids)
            self.assertEqual(ctx.exception.error_code, "INVALID_RELAXATION_DECISION")
        with self.assertRaises(RelaxationDecisionError) as ctx:
            validate_relaxation_decision(prompt, ["R9"])
        self.assertIn("R1、R2、R3", str(ctx.exception))

    def test_apply_relaxation_should_demote_to_nice_and_keep_statuses(self):
        evals = (evaluation("a", {"R1": "MET", "R2": "MET", "R3": "UNKNOWN", "R4": "MET"}),
                 evaluation("b", {"R1": "MET", "R2": "UNMET", "R3": "MET", "R4": "UNMET"}))
        new_jd, new_evals = apply_requirement_relaxation(self.jd, evals, ("R3",))
        self.assertEqual([r.requirement_id for r in new_jd.must], ["R1", "R2"])
        self.assertEqual([r.requirement_id for r in new_jd.nice], ["R4", "R3"])
        self.assertEqual(new_jd.nice[-1].priority.value, "NICE")
        self.assertEqual(new_evals[0].must_ids, ("R1", "R2"))
        self.assertEqual(new_evals[0].nice_ids, ("R4", "R3"))
        self.assertEqual(new_evals[0].statuses, evals[0].statuses)
        self.assertEqual([e.fully_qualified for e in new_evals], [True, False])
        self.assertEqual([e.fully_qualified for e in evals], [False, False])

    def test_prompt_and_session_codec_roundtrip_and_legacy_data(self):
        prompt = build_relaxation_prompt(self.jd, self.rep, 1, 3)
        self.assertEqual(relaxation_prompt_from_dict(relaxation_prompt_to_dict(prompt)), prompt)
        state = ChatSessionState(session_id="s", relaxed_requirement_ids=("R2",), relaxation_rounds=1)
        self.assertEqual(session_from_dict(session_to_dict(state), "s"), state)
        legacy = session_to_dict(ChatSessionState(session_id="s"))
        legacy.pop("relaxed_requirement_ids")
        legacy.pop("relaxation_rounds")
        restored = session_from_dict(legacy, "s")
        self.assertEqual((restored.relaxed_requirement_ids, restored.relaxation_rounds), ((), 0))


# ----------------------------------------------------------------------
# Application：節點（純 Python 路徑）
# ----------------------------------------------------------------------
class TestRelaxationNodes(unittest.TestCase):
    def run_jd(self, **kw):
        extractor = kw.pop("profile_extractor", None) or FakeProfileExtractor()
        narrator = kw.pop("narrator", None) or FakeNarrator()
        handlers = build_handlers(settings=settings(**kw), profile_extractor=extractor, narrator=narrator)
        turn = handlers.new_turn(JD_TEXT, "t1")
        state = handlers.run_all(ChatSessionState(session_id="s1"), turn)
        return handlers, state, turn, extractor, narrator

    def test_jd_turn_should_offer_decision_with_guide(self):
        _, state, turn, _, _ = self.run_jd()
        self.assertIsNotNone(turn.pending_decision)
        self.assertEqual([o.requirement_id for o in turn.pending_decision.options], ["R1", "R2", "R3"])
        self.assertIn(GUIDE_FRAGMENT, turn.final_reply)
        self.assertEqual((state.relaxed_requirement_ids, state.relaxation_rounds), ((), 0))
        # 「」保留給可逐字回溯之引文（Spec-0019 AC-08）：操作提示段落不得含「」（QA-0022 D1 回歸）
        guide = next(p for p in turn.final_reply.split("\n\n") if GUIDE_FRAGMENT in p)
        self.assertNotIn("「", guide)

    def test_disabled_should_not_offer_nor_show_guide(self):
        _, state, turn, _, _ = self.run_jd(relaxation_hitl_enabled=False)
        self.assertIsNone(turn.pending_decision)
        self.assertNotIn(GUIDE_FRAGMENT, turn.final_reply)
        self.assertIsNotNone(state.relaxation)

    def test_resume_should_rerank_deterministically_without_extraction(self):
        handlers, state, _, extractor, narrator = self.run_jd()
        calls_before, narr_before = len(extractor.calls), len(narrator.match_facts)
        expected_jd, expected_evals = apply_requirement_relaxation(state.jd_requirements, state.pool_evaluations,
                                                                   ("R3",))
        expected_ids = [e.candidate_id for e in CandidateRanker().rank(expected_evals, 3)]
        turn2 = handlers.new_turn("放寬 R3", "t2")
        state2 = handlers.resume_relaxation(state, turn2, ["R3"])
        self.assertEqual(len(extractor.calls), calls_before)
        self.assertEqual(len(narrator.match_facts), narr_before + 1)
        self.assertLessEqual(turn2.budget.used, 1)
        self.assertEqual([e.candidate_id for e in state2.shortlist], expected_ids)
        self.assertEqual(state2.jd_requirements, expected_jd)
        self.assertEqual(state2.relaxed_requirement_ids, ("R3",))
        self.assertEqual(state2.relaxation_rounds, 1)
        self.assertEqual(turn2.intents, [ChatIntent.RELAX_CONSTRAINTS])
        audit = turn2.relaxation_audit
        self.assertEqual((audit.requirement_ids, audit.qualified_before, audit.qualified_after, audit.round),
                         (("R3",), 1, 2, 1))
        self.assertIn("### 已依您的決定放寬條件", turn2.final_reply)
        self.assertIn("完全符合必要條件人數：1 → 2 位", turn2.final_reply)
        self.assertIn("已人工放寬 R3", state2.relaxation.scope_note)
        self.assertEqual(state2.history[-2].content, "放寬 R3")

    def test_second_round_should_exclude_relaxed_and_stop_at_max(self):
        handlers, state, _, _, _ = self.run_jd(relaxation_max_rounds=2)
        turn2 = handlers.new_turn("放寬 R3", "t2")
        state2 = handlers.resume_relaxation(state, turn2, ["R3"])
        self.assertEqual(turn2.pending_decision.round, 2)
        self.assertEqual([o.requirement_id for o in turn2.pending_decision.options], ["R1", "R2"])
        self.assertEqual(turn2.pending_decision.max_select, 1)
        turn3 = handlers.new_turn("放寬 R2", "t3")
        state3 = handlers.resume_relaxation(state2, turn3, ["R2"])
        self.assertIsNone(turn3.pending_decision)
        self.assertEqual(state3.relaxed_requirement_ids, ("R3", "R2"))
        self.assertIn("已人工放寬 R3、R2", state3.relaxation.scope_note if state3.relaxation else "已人工放寬 R3、R2")

    def test_new_jd_should_reset_relaxation_memory(self):
        handlers, state, _, _, _ = self.run_jd()
        state2 = handlers.resume_relaxation(state, handlers.new_turn("放寬 R3", "t2"), ["R3"])
        turn3 = handlers.new_turn(JD_TEXT, "t3")
        state3 = handlers.run_all(state2, turn3)
        self.assertEqual((state3.relaxed_requirement_ids, state3.relaxation_rounds), ((), 0))
        self.assertEqual(len(state3.jd_requirements.must), 3)
        self.assertEqual(turn3.pending_decision.round, 1)

    def test_resume_with_invalid_or_missing_decision_should_raise(self):
        handlers, state, _, _, _ = self.run_jd()
        with self.assertRaises(RelaxationDecisionError):
            handlers.resume_relaxation(state, handlers.new_turn("x", "t2"), ["R9"])
        with self.assertRaises(RelaxationDecisionError) as ctx:
            handlers.resume_relaxation(ChatSessionState(session_id="empty"), handlers.new_turn("x", "t3"), ["R1"])
        self.assertEqual(ctx.exception.error_code, "NO_PENDING_DECISION")

    def test_narration_failure_should_degrade_to_template(self):
        narrator = FakeNarrator()
        handlers, state, _, _, _ = self.run_jd(narrator=narrator)
        narrator.raise_on.add("match")
        turn2 = handlers.new_turn("放寬 R3", "t2")
        handlers.resume_relaxation(state, turn2, ["R3"])
        self.assertTrue(turn2.degraded)
        self.assertIn("### 推薦理由", turn2.final_reply)

    def test_resume_text_reload_failure_should_not_raise(self):
        handlers, state, _, _, _ = self.run_jd()
        handlers._tools._search.get_resume_markdown = MagicMock(side_effect=OSError("disk"))
        turn2 = handlers.new_turn("放寬 R3", "t2")
        state2 = handlers.resume_relaxation(state, turn2, ["R3"])
        self.assertEqual(len(state2.shortlist), 3)

    def test_classifier_cannot_emit_relax_intent(self):
        classifier = FakeClassifier(intents=[ChatIntent.RELAX_CONSTRAINTS])
        handlers = build_handlers(settings=settings(), classifier=classifier)
        turn = handlers.new_turn("嗨", "t")
        handlers.run_all(ChatSessionState(session_id="s"), turn)
        self.assertEqual(turn.intents, [ChatIntent.GENERAL_QA])


# ----------------------------------------------------------------------
# Infrastructure：LangGraph interrupt / resume
# ----------------------------------------------------------------------
@unittest.skipUnless(HAS_LANGGRAPH, "langgraph 未安裝")
class TestRelaxationGraph(unittest.TestCase):
    def setUp(self):
        from src.infrastructure.orchestration.checkpointer_factory import build_memory_checkpointer
        from src.infrastructure.orchestration.langgraph_recruitment_graph import LangGraphRecruitmentOrchestrator
        self.extractor = FakeProfileExtractor()
        self.narrator = FakeNarrator()
        self.handlers = build_handlers(settings=settings(), profile_extractor=self.extractor, narrator=self.narrator)
        self.orch = LangGraphRecruitmentOrchestrator(self.handlers, build_memory_checkpointer(600, 20), 2)

    def config(self, sid):
        return {"configurable": {"thread_id": sid}}

    def test_graph_edges_should_form_hitl_loop(self):
        edges = {(e.source, e.target) for e in self.orch._graph.get_graph().edges}
        for edge in (("compose", "await_relaxation"), ("await_relaxation", "apply_relaxation"),
                     ("apply_relaxation", "compose")):
            self.assertIn(edge, edges)

    def test_jd_turn_should_pause_at_await_with_pii_free_payload(self):
        out = self.orch.run_turn("g1", JD_TEXT, "t1")
        self.assertEqual(self.orch._graph.get_state(self.config("g1")).next, ("await_relaxation",))
        self.assertEqual(out.pending_decision.round, 1)
        snapshot = self.orch._graph.get_state(self.config("g1"))
        payload = repr([i.value for t in snapshot.tasks for i in t.interrupts])
        for marker in ("王小明", "李小華", "sample_a@example.com", "cand_a"):
            self.assertNotIn(marker, payload)
        self.assertEqual(self.orch.get_pending_decision("g1"), out.pending_decision)

    def test_structured_resume_should_apply_and_offer_next_round(self):
        self.orch.run_turn("g2", JD_TEXT, "t1")
        calls = len(self.extractor.calls)
        out = self.orch.run_turn("g2", "放寬 R3", "t2", relax_requirement_ids=["r3"])
        self.assertEqual(out.intents, [ChatIntent.RELAX_CONSTRAINTS])
        self.assertEqual(out.relaxed_requirement_ids, ("R3",))
        self.assertEqual(out.relaxation_audit.qualified_after, 2)
        self.assertEqual(len(self.extractor.calls), calls)
        self.assertIn("apply_relaxation", out.node_ms)
        self.assertNotIn("route", out.node_ms)  # 新的單輪 context：恢復不重跑 route
        self.assertEqual(out.pending_decision.round, 2)
        self.assertEqual(self.orch.get_state("g2").turn_count, 2)

    def test_invalid_decision_should_raise_and_keep_checkpoint(self):
        self.orch.run_turn("g3", JD_TEXT, "t1")
        before = self.orch._graph.get_state(self.config("g3"))
        for ids in (["R9"], ["R1", "R2", "R3"]):
            with self.assertRaises(RelaxationDecisionError):
                self.orch.run_turn("g3", "x", "t2", relax_requirement_ids=ids)
        after = self.orch._graph.get_state(self.config("g3"))
        self.assertEqual(after.values, before.values)
        self.assertEqual(after.next, ("await_relaxation",))
        ok = self.orch.run_turn("g3", "放寬 R1", "t3", relax_requirement_ids=["R1"])
        self.assertEqual(ok.relaxed_requirement_ids, ("R1",))

    def test_text_message_while_pending_should_abandon(self):
        self.orch.run_turn("g4", JD_TEXT, "t1")
        out = self.orch.run_turn("g4", "放寬 R3", "t2")  # 文字不觸發放寬（Gate 1 決定：只接受 UI 勾選）
        self.assertNotIn(ChatIntent.RELAX_CONSTRAINTS, out.intents)
        self.assertIsNone(out.pending_decision)
        self.assertEqual(out.relaxed_requirement_ids, ())
        self.assertEqual(len(self.orch.get_state("g4").jd_requirements.must), 3)

    def test_decision_without_pending_should_raise_no_pending(self):
        with self.assertRaises(RelaxationDecisionError) as ctx:
            self.orch.run_turn("g5", "放寬 R1", "t1", relax_requirement_ids=["R1"])
        self.assertEqual(ctx.exception.error_code, "NO_PENDING_DECISION")

    def test_settings_change_while_pending_should_report_no_pending(self):
        # Gate 2 P3：待決定期間關閉 HITL（如重啟後設定變更）→ 不得恢復成無動作之空回覆
        self.orch.run_turn("g7", JD_TEXT, "t1")
        self.handlers._settings = replace(self.handlers._settings, relaxation_hitl_enabled=False)
        with self.assertRaises(RelaxationDecisionError) as ctx:
            self.orch.run_turn("g7", "放寬 R3", "t2", relax_requirement_ids=["R3"])
        self.assertEqual(ctx.exception.error_code, "NO_PENDING_DECISION")
        self.assertEqual(self.orch.get_state("g7").turn_count, 1)

    def test_followup_after_relaxation_should_use_relaxed_jd(self):
        self.orch.run_turn("g6", JD_TEXT, "t1")
        self.orch.run_turn("g6", "放寬 R3", "t2", relax_requirement_ids=["R3"])
        out = self.orch.run_turn("g6", "第 2 位有帶過人嗎？幫他出 2 題面試題", "t3")
        self.assertEqual(out.intents, [ChatIntent.CANDIDATE_FOLLOWUP, ChatIntent.INTERVIEW_QUESTIONS])
        state = self.orch.get_state("g6")
        self.assertEqual([r.requirement_id for r in state.jd_requirements.must], ["R1", "R2"])
        self.assertIn("R3", [r.requirement_id for r in state.jd_requirements.nice])
        # 追問對象為放寬後名單之第 2 位，且面試題弱點只來自放寬後之條件集合
        self.assertEqual(self.narrator.followup_facts[-1].alias, "候選人 #2")
        weak_ids = {w.requirement_id for w in self.narrator.interview_facts[-1].weaknesses}
        self.assertTrue(weak_ids <= {r.requirement_id for r in state.jd_requirements.all_requirements})
        self.assertEqual(state.relaxed_requirement_ids, ("R3",))


# ----------------------------------------------------------------------
# Use Case / API / Config
# ----------------------------------------------------------------------
@unittest.skipUnless(HAS_LANGGRAPH, "langgraph 未安裝")
class TestRelaxationUseCaseAndApi(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        from src.infrastructure.orchestration.checkpointer_factory import build_memory_checkpointer
        from src.infrastructure.orchestration.langgraph_recruitment_graph import LangGraphRecruitmentOrchestrator
        from src.interfaces.web.fastapi_server import create_app
        s = settings()
        self.orch = LangGraphRecruitmentOrchestrator(build_handlers(settings=s), build_memory_checkpointer(600, 20),
                                                     2)
        self.use_case = RecruitmentChatUseCase(self.orch, s)
        self.client = TestClient(create_app(use_case=MagicMock(), search_use_case=None,
                                            chat_use_case=self.use_case))

    def test_empty_message_with_ids_should_synthesize_history_and_log_audit(self):
        first = self.use_case.execute(ChatTurnCommand(message=JD_TEXT))
        self.assertIsNotNone(first.pending_decision)
        with self.assertLogs("src.application.recruitment_chat_use_case", level=logging.INFO) as logs:
            dto = self.use_case.execute(ChatTurnCommand(message="", session_id=first.session_id,
                                                        relax_requirement_ids=["R3"]))
        self.assertEqual(dto.relaxed_requirement_ids, ["R3"])
        self.assertEqual(self.orch.get_state(first.session_id).history[-2].content, "放寬 R3")
        line = next(m for m in logs.output if "relaxation_decision" in m)
        self.assertIn("relaxed=R3 qualified_before=1 qualified_after=2", line)
        self.assertNotIn("王小明", line)
        self.assertNotIn(first.session_id, line)

    def test_id_format_and_count_should_be_validated(self):
        for ids in (["DROP TABLE"], ["R1234"], [f"R{i}" for i in range(13)], []):
            with self.subTest(ids=ids), self.assertRaises(RelaxationDecisionError):
                self.use_case.execute(ChatTurnCommand(message="x", relax_requirement_ids=ids))

    def test_api_should_expose_pending_and_map_errors_to_422(self):
        r1 = self.client.post("/api/chat", json={"message": JD_TEXT})
        d1 = r1.json()
        self.assertEqual(d1["pending_decision"]["kind"], "RELAXATION")
        self.assertEqual([o["requirement_id"] for o in d1["pending_decision"]["options"]], ["R1", "R2", "R3"])
        sid = d1["session_id"]
        g = self.client.get(f"/api/chat/{sid}").json()
        self.assertEqual(g["pending_decision"], d1["pending_decision"])
        self.assertEqual(g["relaxed_requirement_ids"], [])
        bad = self.client.post("/api/chat", json={"session_id": sid, "relax_requirement_ids": ["R9"]})
        self.assertEqual((bad.status_code, bad.json()["error_code"]), (422, "INVALID_RELAXATION_DECISION"))
        none = self.client.post("/api/chat", json={"relax_requirement_ids": ["R1"]})
        self.assertEqual((none.status_code, none.json()["error_code"]), (422, "NO_PENDING_DECISION"))
        ok = self.client.post("/api/chat", json={"session_id": sid, "relax_requirement_ids": ["R3"]}).json()
        self.assertEqual(ok["intents"], ["RELAX_CONSTRAINTS"])
        self.assertEqual(ok["relaxed_requirement_ids"], ["R3"])
        self.assertEqual(ok["pending_decision"]["round"], 2)


class TestRelaxationConfig(unittest.TestCase):
    def load(self, env):
        from src.infrastructure.config import AppConfig
        with patch.dict(os.environ, env, clear=True):
            return AppConfig.load(override_api_key="mock_key")

    def test_defaults_clamp_and_mapping(self):
        from src.interfaces.web.server import build_recruitment_settings
        cfg = self.load({})
        self.assertEqual((cfg.recruit_relaxation_hitl_enabled, cfg.recruit_relaxation_max_rounds), (True, 2))
        cfg = self.load({"RECRUIT_RELAXATION_HITL_ENABLED": "false", "RECRUIT_RELAXATION_MAX_ROUNDS": "99"})
        self.assertEqual((cfg.recruit_relaxation_hitl_enabled, cfg.recruit_relaxation_max_rounds), (False, 5))
        self.assertEqual(self.load({"RECRUIT_RELAXATION_MAX_ROUNDS": "0"}).recruit_relaxation_max_rounds, 1)
        mapped = build_recruitment_settings(cfg)
        self.assertEqual((mapped.relaxation_hitl_enabled, mapped.relaxation_max_rounds), (False, 5))

    def test_env_example_documents_keys(self):
        text = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
        for key in ("RECRUIT_RELAXATION_HITL_ENABLED=", "RECRUIT_RELAXATION_MAX_ROUNDS="):
            self.assertIn(key, text)


if __name__ == "__main__":
    unittest.main()
