"""
招募助手確定性領域服務白箱單元測試 (ADR-0019)
Matcher 三態、Ranker 排序與補位、leave-one-out 手算對照、序號指代、證據驗證、受保護屬性、熔斷、編解碼。
"""
import unittest

from src.domain.recruitment import (
    CandidateEvaluation,
    CandidateProfile,
    ChatIntent,
    ChatMessage,
    ChatSessionState,
    EvidenceQuote,
    JobRequirement,
    MatchStatus,
    ReferenceKind,
    RequirementCategory as Cat,
    RequirementPriority as Pri,
    SeniorityLevel,
    ShortlistEntry,
)
from src.domain.recruitment_codec import session_from_dict, session_to_dict
from src.domain.recruitment_services import (
    CandidateRanker,
    CircuitBreaker,
    ConstraintRelaxationAnalyzer,
    EvidenceVerifier,
    OrdinalReferenceResolver,
    ProtectedAttributeGuard,
    RequirementMatcher,
    collect_requirement_evidence,
    mask_contact_info,
    normalize_intents,
    parse_number_token,
    parse_question_count,
    parse_requested_count,
    renumber_requirements,
    sanitize_reply_quotes,
    trim_history,
)
from tests.unit.recruitment_fakes import make_jd

M, U, K = MatchStatus.MET, MatchStatus.UNMET, MatchStatus.UNKNOWN


def profile(cid="c", years=None, led=None, team=None, seniority=None, skills=(), evidence=()):
    return CandidateProfile(cid, "h", "v", years, led, team, seniority, tuple(skills), tuple(evidence))


def evaluation(cid, statuses, must=("R1", "R2", "R3"), nice=(), score=0.5, name=None):
    return CandidateEvaluation(cid, name or cid, score, dict(statuses), profile(cid), tuple(must), tuple(nice))


def entries(n):
    return tuple(ShortlistEntry(i, f"cand_{i}", f"name{i}", True, 0.9, (), (), ()) for i in range(1, n + 1))


class TestRequirementMatcher(unittest.TestCase):
    def setUp(self):
        self.matcher = RequirementMatcher({"k8s": "kubernetes", "Golang": "go"})

    def test_skill_with_alias_and_whitespace_should_match(self):
        req = JobRequirement("R1", Cat.SKILL, Pri.MUST, "K8s", skill="K 8s")
        self.assertEqual(self.matcher.evaluate(req, profile(skills=["Kubernetes"])), M)

    def test_skill_from_chunk_tags_should_match(self):
        req = JobRequirement("R1", Cat.SKILL, Pri.MUST, "Go", skill="golang")
        self.assertEqual(self.matcher.evaluate(req, profile(), chunk_skills=["go"]), M)

    def test_skill_absent_should_be_unmet_and_no_sources_unknown(self):
        req = JobRequirement("R1", Cat.SKILL, Pri.MUST, "Rust", skill="rust")
        self.assertEqual(self.matcher.evaluate(req, profile(skills=["python"])), U)
        self.assertEqual(self.matcher.evaluate(req, profile()), K)

    def test_years_three_states(self):
        req = JobRequirement("R2", Cat.YEARS, Pri.MUST, "5 年", min_value=5)
        self.assertEqual(self.matcher.evaluate(req, profile(years=5.0)), M)
        self.assertEqual(self.matcher.evaluate(req, profile(years=4.9)), U)
        self.assertEqual(self.matcher.evaluate(req, profile(years=None)), K)

    def test_team_size_leadership_and_seniority(self):
        team = JobRequirement("R3", Cat.TEAM_SIZE, Pri.MUST, "5 人", min_value=5)
        lead = JobRequirement("R4", Cat.LEADERSHIP, Pri.MUST, "帶人")
        sen = JobRequirement("R5", Cat.SENIORITY, Pri.MUST, "資深", min_level=SeniorityLevel.SENIOR)
        self.assertEqual(self.matcher.evaluate(team, profile(team=6)), M)
        self.assertEqual(self.matcher.evaluate(team, profile(team=3)), U)
        self.assertEqual(self.matcher.evaluate(team, profile()), K)
        self.assertEqual(self.matcher.evaluate(lead, profile(led=True)), M)
        self.assertEqual(self.matcher.evaluate(lead, profile(led=False)), U)
        self.assertEqual(self.matcher.evaluate(lead, profile()), K)
        self.assertEqual(self.matcher.evaluate(sen, profile(seniority=SeniorityLevel.LEAD)), M)
        self.assertEqual(self.matcher.evaluate(sen, profile(seniority=SeniorityLevel.MID)), U)
        self.assertEqual(self.matcher.evaluate(sen, profile()), K)


class TestCandidateRanker(unittest.TestCase):
    def test_rank_sort_key_order_should_be_deterministic(self):
        # Arrange: 全合格 > 必要 MET 數 > 加分 MET 數 > 語意分數 > candidate_id
        evals = [
            evaluation("e", {"R1": M, "R2": U, "R3": U}, score=0.99),
            evaluation("b", {"R1": M, "R2": M, "R3": K, "N1": M}, nice=("N1",), score=0.1),
            evaluation("c", {"R1": M, "R2": M, "R3": U, "N1": U}, nice=("N1",), score=0.9),
            evaluation("a2", {"R1": M, "R2": M, "R3": M}, score=0.5),
            evaluation("a1", {"R1": M, "R2": M, "R3": M}, score=0.5),
        ]
        # Act
        first = CandidateRanker().rank(evals, 5)
        second = CandidateRanker().rank(list(reversed(evals)), 5)
        # Assert
        self.assertEqual([e.candidate_id for e in first], ["a1", "a2", "b", "c", "e"])
        self.assertEqual(first, second)
        self.assertEqual([e.rank for e in first], [1, 2, 3, 4, 5])
        self.assertTrue(first[0].fully_qualified)
        self.assertEqual(first[2].unknown, ("R3",))

    def test_rank_with_insufficient_qualified_should_backfill_partial(self):
        evals = [evaluation("q", {"R1": M, "R2": M, "R3": M}), evaluation("p", {"R1": M, "R2": U, "R3": M})]
        result = CandidateRanker().rank(evals, 3)
        self.assertEqual(len(result), 2)
        self.assertFalse(result[1].fully_qualified)
        self.assertEqual(result[1].unmet, ("R2",))


class TestConstraintRelaxationAnalyzer(unittest.TestCase):
    def setUp(self):
        self.must = [JobRequirement(f"R{i}", Cat.SKILL, Pri.MUST, f"條件{i}", skill="x") for i in (1, 2, 3)]

    def test_leave_one_out_values_should_match_hand_calculation(self):
        # Arrange: 手算 baseline=1；放寬 R1→2、R2→3、R3→1
        evals = [
            evaluation("a", {"R1": M, "R2": M, "R3": M}),
            evaluation("b", {"R1": U, "R2": M, "R3": M}),
            evaluation("c", {"R1": M, "R2": K, "R3": M}),
            evaluation("d", {"R1": M, "R2": U, "R3": M}),
            evaluation("e", {"R1": U, "R2": U, "R3": K}),
        ]
        # Act
        rep = ConstraintRelaxationAnalyzer().analyze(evals, self.must, 3)
        # Assert
        self.assertEqual(rep.pool_size, 5)
        self.assertEqual(rep.baseline_qualified, 1)
        values = {i.requirement_id: (i.qualified_if_relaxed, i.delta, i.unknown_count) for i in rep.items}
        self.assertEqual(values, {"R1": (2, 1, 0), "R2": (3, 2, 1), "R3": (1, 0, 1)})
        self.assertEqual(rep.bottleneck_requirement_ids, ("R2",))
        self.assertIn("候選池", rep.scope_note)

    def test_tied_bottleneck_should_list_all(self):
        evals = [evaluation("a", {"R1": U, "R2": M, "R3": M}), evaluation("b", {"R1": M, "R2": U, "R3": M})]
        rep = ConstraintRelaxationAnalyzer().analyze(evals, self.must, 3)
        self.assertEqual(rep.bottleneck_requirement_ids, ("R1", "R2"))

    def test_zero_delta_and_zero_qualified_should_have_empty_bottleneck(self):
        evals = [evaluation("a", {"R1": U, "R2": U, "R3": M}), evaluation("b", {"R1": K, "R2": U, "R3": U})]
        rep = ConstraintRelaxationAnalyzer().analyze(evals, self.must, 3)
        self.assertEqual(rep.baseline_qualified, 0)
        self.assertTrue(all(i.delta == 0 for i in rep.items))
        self.assertEqual(rep.bottleneck_requirement_ids, ())

    def test_empty_pool_should_return_zero_report(self):
        rep = ConstraintRelaxationAnalyzer().analyze([], self.must, 3)
        self.assertEqual((rep.pool_size, rep.baseline_qualified), (0, 0))


class TestOrdinalReferenceResolver(unittest.TestCase):
    def setUp(self):
        self.resolver = OrdinalReferenceResolver()

    def test_various_ordinal_forms_should_resolve_rank_two(self):
        for text in ("第 2 位看起來不錯", "第二位如何", "2號有帶人嗎", "#2 的經歷", "＃２呢", "第二名"):
            with self.subTest(text=text):
                res = self.resolver.resolve(text, entries(3), None)
                self.assertEqual(res.kind, ReferenceKind.RESOLVED)
                self.assertEqual((res.rank, res.candidate_id), (2, "cand_2"))

    def test_chinese_numbers_up_to_ninety_nine(self):
        self.assertEqual(parse_number_token("十"), 10)
        self.assertEqual(parse_number_token("十二"), 12)
        self.assertEqual(parse_number_token("二十三"), 23)
        self.assertEqual(parse_number_token("兩"), 2)
        self.assertIsNone(parse_number_token("十十"))
        self.assertIsNone(parse_number_token("abc"))

    def test_out_of_range_should_report_size(self):
        res = self.resolver.resolve("第 9 位呢？", entries(3), None)
        self.assertEqual(res.kind, ReferenceKind.OUT_OF_RANGE)
        self.assertEqual((res.rank, res.shortlist_size), (9, 3))

    def test_no_shortlist_should_be_flagged(self):
        self.assertEqual(self.resolver.resolve("第 1 位有帶人嗎", (), None).kind, ReferenceKind.NO_SHORTLIST)
        self.assertEqual(self.resolver.resolve("他有帶人嗎", (), "x").kind, ReferenceKind.NO_SHORTLIST)

    def test_pronoun_should_follow_last_reference(self):
        res = self.resolver.resolve("這位的 Python 程度？", entries(3), "cand_3")
        self.assertEqual((res.kind, res.candidate_id, res.rank), (ReferenceKind.RESOLVED, "cand_3", 3))
        self.assertEqual(self.resolver.resolve("他呢", entries(3), None).kind, ReferenceKind.NONE)

    def test_plain_text_without_reference_should_be_none(self):
        self.assertEqual(self.resolver.resolve("剛剛的必要條件是什麼", entries(3), "cand_1").kind,
                         ReferenceKind.NONE)


class TestCountParsing(unittest.TestCase):
    def test_requested_count_variants_and_truncation(self):
        self.assertEqual(parse_requested_count("幫我挑 5 個人", 3, 10), (5, False))
        self.assertEqual(parse_requested_count("列出前五名", 3, 10), (5, False))
        self.assertEqual(parse_requested_count("挑 50 個", 3, 10), (10, True))
        self.assertEqual(parse_requested_count("具 5 年以上經驗", 3, 10), (3, False))

    def test_question_count(self):
        self.assertEqual(parse_question_count("出 3 題面試題", 3, 10), (3, False))
        self.assertEqual(parse_question_count("出二十題", 3, 10), (10, True))
        self.assertEqual(parse_question_count("出面試題", 4, 10), (4, False))


class TestEvidenceVerifier(unittest.TestCase):
    def setUp(self):
        self.verifier = EvidenceVerifier(min_chars=4)
        self.resume = "## 經歷\n擔任**技術主管**，帶領　6 人\n後端團隊。"

    def test_whitespace_fullwidth_and_markdown_should_normalize(self):
        self.assertTrue(self.verifier.verify("技術主管，帶領 6 人後端團隊", self.resume))
        self.assertTrue(self.verifier.verify("帶領６人", self.resume))

    def test_fabricated_or_too_short_quote_should_fail(self):
        self.assertFalse(self.verifier.verify("帶領 20 人團隊", self.resume))
        self.assertFalse(self.verifier.verify("主管", self.resume))
        self.assertFalse(self.verifier.verify(None, self.resume))
        self.assertFalse(self.verifier.verify("技術主管", None))

    def test_sanitize_reply_quotes_should_remove_unverified(self):
        reply = "推薦理由：「帶領 6 人後端團隊」，另「曾任執行長十年」。"
        out, removed = sanitize_reply_quotes(reply, [self.resume], self.verifier, "[已移除]")
        self.assertEqual(removed, 1)
        self.assertIn("「帶領 6 人後端團隊」", out)
        self.assertNotIn("執行長", out)


class TestProtectedAttributeGuard(unittest.TestCase):
    def setUp(self):
        self.guard = ProtectedAttributeGuard(["性別", "男性", "歲", "婚姻", "未婚", "出生"])

    def test_filter_requirements_should_drop_protected(self):
        reqs = [
            JobRequirement("R1", Cat.SKILL, Pri.MUST, "精通 Python", skill="python"),
            JobRequirement("R2", Cat.SENIORITY, Pri.MUST, "限男性"),
            JobRequirement("R3", Cat.YEARS, Pri.MUST, "35 歲以下", min_value=0),
        ]
        kept, hits = self.guard.filter_requirements(reqs)
        self.assertEqual([r.requirement_id for r in kept], ["R1"])
        self.assertEqual(set(hits), {"男性", "歲"})

    def test_redact_resume_should_mask_whole_line(self):
        text = "王小明\n性別：男\n出生：1990/01/01\n婚姻：未婚\n技能：Python"
        out = self.guard.redact_resume(text)
        self.assertNotIn("1990", out)
        self.assertNotIn("未婚", out)
        self.assertEqual(out.count(ProtectedAttributeGuard.REDACTED_LINE), 3)
        self.assertIn("技能：Python", out)

    def test_scan_text_should_detect_terms(self):
        self.assertEqual(self.guard.scan_text("請問您的婚姻狀況？"), ["婚姻"])
        self.assertEqual(self.guard.scan_text("請說明您的 Python 經驗"), [])


class TestMiscDomainServices(unittest.TestCase):
    def test_mask_contact_info_should_hide_name_email_phone(self):
        fake_phone = "0" + "9" + "12-345" + "-678"  # 動態組裝虛構號碼，避免版控殘留電話樣式
        text = f"王小明 聯絡：sample@example.com {fake_phone} https://example.com/me"
        out = mask_contact_info(text, ["王小明"], "候選人 #1")
        self.assertNotIn("王小明", out)
        self.assertNotIn("sample@example.com", out)
        self.assertNotIn("0912", out)
        self.assertNotIn("https://", out)
        self.assertIn("候選人 #1", out)

    def test_circuit_breaker_should_cool_down_with_injected_clock(self):
        now = [100.0]
        breaker = CircuitBreaker(60, clock=lambda: now[0])
        self.assertFalse(breaker.is_open())
        breaker.record_quota_exhausted()
        self.assertTrue(breaker.is_open())
        self.assertEqual(breaker.retry_after_seconds(), 60)
        now[0] = 161.0
        self.assertFalse(breaker.is_open())
        self.assertEqual(breaker.retry_after_seconds(), 0)

    def test_normalize_intents_priority_dedupe_and_exclusive(self):
        I = ChatIntent
        self.assertEqual(normalize_intents([I.INTERVIEW_QUESTIONS, I.CANDIDATE_FOLLOWUP, I.INTERVIEW_QUESTIONS], 2),
                         [I.CANDIDATE_FOLLOWUP, I.INTERVIEW_QUESTIONS])
        self.assertEqual(normalize_intents([I.GENERAL_QA, I.JD_MATCH, I.INTERVIEW_QUESTIONS], 2),
                         [I.JD_MATCH, I.INTERVIEW_QUESTIONS])
        self.assertEqual(normalize_intents([I.OUT_OF_SCOPE], 2), [I.OUT_OF_SCOPE])
        self.assertEqual(normalize_intents([I.OUT_OF_SCOPE, I.GENERAL_QA], 2), [I.GENERAL_QA])
        self.assertEqual(normalize_intents([], 2), [I.GENERAL_QA])

    def test_trim_history_by_turns_and_chars(self):
        history = [ChatMessage("user" if i % 2 == 0 else "assistant", "x" * 10) for i in range(30)]
        self.assertEqual(len(trim_history(history, 3, 10_000)), 6)
        self.assertEqual(len(trim_history(history, 10, 35)), 3)
        self.assertEqual(trim_history(history, 0, 100), ())

    def test_renumber_requirements_should_ignore_llm_ids_and_truncate(self):
        jd = make_jd()
        renumbered, truncated = renumber_requirements(jd, 2)
        self.assertTrue(truncated)
        self.assertEqual([r.requirement_id for r in renumbered.all_requirements], ["R1", "R2", "R3"])
        self.assertEqual(renumbered.nice[0].priority, Pri.NICE)

    def test_collect_requirement_evidence_maps_fields(self):
        jd, _ = renumber_requirements(make_jd(), 12)
        prof = profile(evidence=[EvidenceQuote("years", "8年工作經驗", True),
                                 EvidenceQuote("skill:K8s", "Kubernetes 部署", True),
                                 EvidenceQuote("has_led_team", "未驗證", False)])
        result = collect_requirement_evidence(jd.all_requirements, prof, {"k8s": "kubernetes"})
        self.assertEqual([(e.requirement_id, e.field) for e in result], [("R2", "years"), ("R4", "skill:K8s")])

    def test_session_codec_round_trip(self):
        jd, _ = renumber_requirements(make_jd(), 12)
        ev = evaluation("a", {"R1": M, "R2": K, "R3": U}, name="王小明")
        state = ChatSessionState(session_id="sess_12345678", turn_count=2, jd_requirements=jd,
                                 shortlist=entries(1), pool_evaluations=(ev,),
                                 last_referenced_candidate_id="cand_1",
                                 history=(ChatMessage("user", "hi"),))
        restored = session_from_dict(session_to_dict(state), "x")
        self.assertEqual(restored.jd_requirements, jd)
        self.assertEqual(restored.shortlist, state.shortlist)
        self.assertEqual(restored.pool_evaluations[0].statuses, ev.statuses)
        self.assertEqual(restored.turn_count, 2)
        self.assertEqual(session_from_dict(None, "new_session").session_id, "new_session")


if __name__ == "__main__":
    unittest.main()
