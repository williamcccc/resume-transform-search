"""
E2E / 灰箱 QA 實測：放寬條件之人工決策 (ADR-0022，Spec-0022 §3.7 QA 矩陣)

分軌：
- FAKE 軌：真實 FastAPI 路由 + 真實 LangGraph（interrupt / Command(resume)）+ 真實節點，Fake 檢索 / LLM。
  情境 1 自動擴大檢索維持預設開啟，以驗證「先自動擴大 → 仍不足 → 交由人工決定」的整合流程。
- REDIS 軌：RedisSaver Checkpointer 跨 App 實例恢復待決定（Redis 不可連線或未安裝 redis checkpointer 則 skip）；
  Session ID 含 qa0022 專屬標記，結束後只清除含該標記之鍵。

所有履歷與姓名皆為記憶體動態建構之虛構樣本；嚴禁讀取 data/、resume/。
"""
import logging
import os
import re
import sys
import threading
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.domain.recruitment_services import CandidateRanker, apply_requirement_relaxation  # noqa: E402
from src.domain.recruitment_codec import session_from_dict  # noqa: E402
from tests.e2e.test_recruitment_chat_e2e import (  # noqa: E402
    LANGGRAPH_OK,
    REDIS_SEARCH_URL,
    _delete_keys,
    _FakeAppHarness,
    _redis_available,
    _SlowNarrator,
)
from tests.unit.recruitment_fakes import JD_TEXT, make_settings  # noqa: E402

GUIDE = "勾選要放寬的條件"


def post(h, **body):
    return h.client.post("/api/chat", json=body)


@unittest.skipUnless(LANGGRAPH_OK, "未安裝 langgraph，略過 FAKE 軌")
class TestRelaxationHitlFakeE2E(unittest.TestCase):
    def harness(self, **kwargs) -> _FakeAppHarness:
        h = _FakeAppHarness(**kwargs)
        self.addCleanup(h.close)
        return h

    def start(self, h):
        r = post(h, message=JD_TEXT)
        self.assertEqual(r.status_code, 200, r.text[:200])
        return r.json()

    # TC-1 / AC-1, AC-2：自動擴大仍不足 → 暫停 → 勾選 R3 → 0 次抽取之確定性重排
    def test_tc01_offer_then_structured_resume(self):
        h = self.harness()
        d1 = self.start(h)
        self.assertEqual(d1["usage"]["search_stop_reason"], "MAX_ROUNDS")  # 情境 1 先自動擴大
        pending = d1["pending_decision"]
        self.assertEqual(pending["kind"], "RELAXATION")
        self.assertEqual((pending["round"], pending["max_rounds"], pending["max_select"]), (1, 2, 2))
        self.assertEqual([o["requirement_id"] for o in pending["options"]], ["R1", "R2", "R3"])
        self.assertTrue(any(o["recommended"] for o in pending["options"]))
        self.assertIn(GUIDE, d1["reply_markdown"])
        sid = d1["session_id"]
        state_before = h.use_case.get_session(sid)
        exp_jd, exp_evals = apply_requirement_relaxation(state_before.jd_requirements,
                                                         state_before.pool_evaluations, ("R3",))
        expected = [e.candidate_id for e in CandidateRanker().rank(exp_evals, 3)]
        extract_before = len(h.extractor.calls)
        d2 = post(h, session_id=sid, relax_requirement_ids=["R3"]).json()
        self.assertEqual(d2["intents"], ["RELAX_CONSTRAINTS"])
        self.assertEqual([x["candidate_id"] for x in d2["shortlist"]], expected)
        self.assertEqual(len(h.extractor.calls), extract_before)
        self.assertLessEqual(d2["usage"]["llm_calls"], 1)
        self.assertEqual(d2["relaxed_requirement_ids"], ["R3"])
        self.assertIn("完全符合必要條件人數：1 → 2 位", d2["reply_markdown"])
        self.assertIn("已人工放寬 R3", d2["relaxation"]["scope_note"])
        self.assertIn("已自動擴大檢索 2 輪", d2["relaxation"]["scope_note"])  # 情境 1 揭露保留
        self.assertEqual(h.use_case.get_session(sid).jd_requirements, exp_jd)

    # TC-2 / AC-3
    def test_tc02_text_command_does_not_relax(self):
        h = self.harness()
        sid = self.start(h)["session_id"]
        d2 = post(h, session_id=sid, message="放寬 R3").json()
        self.assertNotIn("RELAX_CONSTRAINTS", d2["intents"])
        self.assertIsNone(d2["pending_decision"])
        self.assertEqual(d2["relaxed_requirement_ids"], [])
        self.assertEqual(len(h.use_case.get_session(sid).jd_requirements.must), 3)

    # TC-3 / AC-4
    def test_tc03_invalid_decisions_are_rejected_and_recoverable(self):
        h = self.harness()
        sid = self.start(h)["session_id"]
        cases = [(["R9"], "INVALID_RELAXATION_DECISION"), (["R1", "R2", "R3"], "INVALID_RELAXATION_DECISION"),
                 (["R2", "R2"], "INVALID_RELAXATION_DECISION"), (["<script>"], "INVALID_RELAXATION_DECISION"),
                 ([], "INVALID_RELAXATION_DECISION")]
        for ids, code in cases:
            with self.subTest(ids=ids):
                r = post(h, session_id=sid, relax_requirement_ids=ids)
                self.assertEqual((r.status_code, r.json()["error_code"]), (422, code))
                self.assertNotIn("Traceback", r.text)
        self.assertIsNotNone(h.client.get(f"/api/chat/{sid}").json()["pending_decision"])
        self.assertEqual(h.use_case.get_session(sid).turn_count, 1)
        ok = post(h, session_id=sid, relax_requirement_ids=["R1"])
        self.assertEqual(ok.status_code, 200)
        none = post(h, relax_requirement_ids=["R1"])
        self.assertEqual((none.status_code, none.json()["error_code"]), (422, "NO_PENDING_DECISION"))

    # TC-4 / AC-5
    def test_tc04_followup_while_pending_abandons_decision(self):
        h = self.harness()
        sid = self.start(h)["session_id"]
        d2 = post(h, session_id=sid, message="第 1 位有帶過人嗎？").json()
        self.assertEqual(d2["intents"], ["CANDIDATE_FOLLOWUP"])
        self.assertIsNone(d2["pending_decision"])
        late = post(h, session_id=sid, relax_requirement_ids=["R3"])
        self.assertEqual((late.status_code, late.json()["error_code"]), (422, "NO_PENDING_DECISION"))

    # TC-5 / AC-6, AC-7
    def test_tc05_multi_round_cap_and_reset_on_new_jd(self):
        h = self.harness()
        sid = self.start(h)["session_id"]
        d2 = post(h, session_id=sid, relax_requirement_ids=["R3"]).json()
        self.assertEqual(d2["pending_decision"]["round"], 2)
        self.assertEqual([o["requirement_id"] for o in d2["pending_decision"]["options"]], ["R1", "R2"])
        d3 = post(h, session_id=sid, relax_requirement_ids=["R2"]).json()
        self.assertEqual(d3["relaxed_requirement_ids"], ["R3", "R2"])
        self.assertIsNone(d3["pending_decision"])  # 達 MAX_ROUNDS=2
        d4 = post(h, session_id=sid, message=JD_TEXT).json()
        self.assertEqual(d4["relaxed_requirement_ids"], [])
        self.assertEqual(d4["pending_decision"]["round"], 1)

    # TC-6 / AC-8
    def test_tc06_disabled_matches_pre_feature_behavior(self):
        off = self.harness(settings=make_settings(relaxation_hitl_enabled=False))
        on = self.harness()
        d_off, d_on = self.start(off), self.start(on)
        self.assertIsNone(d_off["pending_decision"])
        self.assertNotIn(GUIDE, d_off["reply_markdown"])
        # 開關只差一行操作提示，其餘回覆逐字相同
        self.assertEqual(d_off["reply_markdown"], "\n\n".join(
            p for p in d_on["reply_markdown"].split("\n\n") if GUIDE not in p))
        self.assertEqual(d_off["shortlist"], d_on["shortlist"])

    # TC-8 / AC-10
    def test_tc08_concurrent_decisions_one_wins(self):
        h = self.harness(narrator=_SlowNarrator(0.6))
        sid = self.start(h)["session_id"]
        results = []
        barrier = threading.Barrier(2)

        def worker():
            barrier.wait()
            results.append(post(h, session_id=sid, relax_requirement_ids=["R3"]).status_code)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        self.assertEqual(sorted(results), [200, 409])
        state = h.use_case.get_session(sid)
        self.assertEqual((state.relaxed_requirement_ids, state.relaxation_rounds, state.turn_count), (("R3",), 1, 2))

    # TC-9 / AC-11
    def test_tc09_audit_log_and_checkpoint_are_pii_free(self):
        h = self.harness()
        sid = self.start(h)["session_id"]
        with self.assertLogs("src.application.recruitment_chat_use_case", level=logging.INFO) as logs:
            post(h, session_id=sid, relax_requirement_ids=["R3"])
        line = next(m for m in logs.output if "relaxation_decision" in m)
        self.assertRegex(line, r"round=1 relaxed=R3 qualified_before=1 qualified_after=2")
        for marker in ("王小明", "李小華", sid):
            self.assertNotIn(marker, line)
        snapshot = h.orchestrator._graph.get_state({"configurable": {"thread_id": sid}})
        payload = repr([i.value for t in snapshot.tasks for i in t.interrupts])
        self.assertIn("RELAXATION", payload)
        for marker in ("王小明", "李小華", "陳大文", "sample_a@example.com", "cand_"):
            self.assertNotIn(marker, payload)

    # TC-10 / AC-12
    def test_tc10_get_restores_pending_and_ui_has_decision_form(self):
        h = self.harness()
        d1 = self.start(h)
        g = h.client.get(f"/api/chat/{d1['session_id']}").json()
        self.assertEqual(g["pending_decision"], d1["pending_decision"])
        html = h.client.get("/").text
        for needle in ("renderRelaxationDecision", "relax_requirement_ids", "放寬並重新比對",
                       "data.error_code === 'SESSION_TURN_LIMIT'"):
            self.assertIn(needle, html)

    # TC-11 / AC-13
    def test_tc11_interview_questions_after_relaxation(self):
        h = self.harness()
        sid = self.start(h)["session_id"]
        post(h, session_id=sid, relax_requirement_ids=["R3"])
        d3 = post(h, session_id=sid, message="第 2 位幫我出 2 題面試題").json()
        self.assertIn("INTERVIEW_QUESTIONS", d3["intents"])
        state = h.use_case.get_session(sid)
        valid = {r.requirement_id for r in state.jd_requirements.all_requirements}
        self.assertTrue(all(q["target_requirement_id"] in valid for q in d3["interview_questions"]))
        self.assertEqual([r.requirement_id for r in state.jd_requirements.must], ["R1", "R2"])


class TestRelaxationHitlRedisE2E(unittest.TestCase):
    """TC-7 / AC-9：RedisSaver 跨 App 實例恢復待決定"""
    SID = "qa0022redis01"

    def setUp(self):
        if not LANGGRAPH_OK:
            self.skipTest("未安裝 langgraph")
        if not _redis_available(REDIS_SEARCH_URL):
            self.skipTest("Redis 不可連線")
        try:
            import langgraph.checkpoint.redis  # noqa: F401
        except ImportError:
            self.skipTest("未安裝 langgraph-checkpoint-redis")
        assert "qa0022" in self.SID
        _delete_keys(REDIS_SEARCH_URL, [f"*{self.SID}*"])
        self.addCleanup(_delete_keys, REDIS_SEARCH_URL, [f"*{self.SID}*"])

    def test_tc07_resume_on_another_instance(self):
        app1 = _FakeAppHarness(backend="redis")
        try:
            d1 = post(app1, message=JD_TEXT, session_id=self.SID).json()
        finally:
            app1.close()
        self.assertIsNotNone(d1["pending_decision"])
        app2 = _FakeAppHarness(backend="redis")  # 模擬程序重啟：全新 handlers / 連線
        try:
            g = app2.client.get(f"/api/chat/{self.SID}").json()
            self.assertEqual(g["pending_decision"], d1["pending_decision"])
            d2 = post(app2, session_id=self.SID, relax_requirement_ids=["R3"]).json()
            self.assertEqual(d2["intents"], ["RELAX_CONSTRAINTS"])
            self.assertEqual(d2["relaxed_requirement_ids"], ["R3"])
            self.assertEqual(app2.extractor.calls, [])
            self.assertEqual(d2["pending_decision"]["round"], 2)
        finally:
            app2.close()


if __name__ == "__main__":
    unittest.main()
