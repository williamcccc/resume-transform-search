"""
招募助手 Rev2 技能比對白箱單元測試 (ADR-0019 Rev2：RV2-D1 / RV2-D3 之 Domain 部分)
canonical_skill / skill_variants / split_skill_options / find_skill_mention 參數化表、
RequirementMatcher §2.3 七條規則、次級瓶頸診斷、codec 相容、引文驗證括號與括號成對檢查。
全部為記憶體虛構資料，零網路、零 data/ 與 resume/ 讀取。
"""
import unittest

from src.domain.recruitment import (
    CandidateProfile,
    EvidenceQuote,
    JdRequirements,
    JobRequirement,
    MatchStatus,
    RequirementCategory,
    RequirementPriority,
)
from src.domain.recruitment_codec import (
    jd_from_dict,
    jd_to_dict,
    relaxation_from_dict,
    relaxation_to_dict,
    requirement_from_dict,
    requirement_to_dict,
)
from src.domain.recruitment_services import (
    ConstraintRelaxationAnalyzer,
    EvidenceVerifier,
    RequirementMatcher,
    canonical_skill,
    collect_requirement_evidence,
    find_skill_mention,
    has_unbalanced_brackets,
    normalize_alias_map,
    sanitize_reply_quotes,
    skill_variants,
    split_skill_options,
)

RAW_ALIASES = {
    "golang": "go", "k8s": "kubernetes", "js": "javascript", "node.js": "nodejs", "node": "nodejs",
    "postgres": "postgresql", "ci/cd": "cicd",
}
ALIASES = normalize_alias_map(RAW_ALIASES)
EXEMPT = frozenset({"web3", "b2b", "s3x"})


def skill_req(rid="R1", skill=None, skills=(), priority=RequirementPriority.MUST):
    return JobRequirement(rid, RequirementCategory.SKILL, priority, f"技能{rid}", skill=skill, skills=tuple(skills))


def profile(core=(), unverified=(), cid="cand_a"):
    return CandidateProfile(cid, "h", "v", None, None, None, None, tuple(core), (), False, tuple(unverified))


class TestCanonicalSkill(unittest.TestCase):
    CASES = [
        ("Python 3.11", "python"), ("Python3", "python"), ("python", "python"), ("PostgreSQL 12", "postgresql"),
        ("postgres12", "postgresql"), ("Golang", "go"), ("Go 1.21", "go"), ("k8s", "kubernetes"),
        ("Kubernetes (EKS)", "kubernetes"), ("Kubernetes（EKS）", "kubernetes"), ("Node.js", "nodejs"),
        ("ＰＹＴＨＯＮ３", "python"), ("web3", "web3"), ("s3", "s3"), ("ec2", "ec2"), ("C++", "c++"),
        ("C#", "c#"), ("Vue 3", "vue"), ("CI/CD", "cicd"), ("python-3.12", "python"), ("python3.x", "python"),
    ]

    def test_canonical_skill_table(self):
        for raw, expected in self.CASES:
            with self.subTest(raw=raw):
                self.assertEqual(canonical_skill(raw, ALIASES, EXEMPT), expected)

    def test_exempt_word_should_keep_version_like_tail(self):
        self.assertEqual(canonical_skill("s3x", ALIASES, EXEMPT), "s3x")
        self.assertEqual(canonical_skill("web3", ALIASES, {"web3"}), "web3")
        self.assertEqual(canonical_skill("web3", ALIASES, ()), "web")  # 未豁免時才去尾碼（對照組）

    def test_short_stem_should_not_be_stripped(self):
        self.assertEqual(canonical_skill("s3", ALIASES, ()), "s3")
        self.assertEqual(canonical_skill("ec2", ALIASES, ()), "ec2")

    def test_empty_input_should_return_empty(self):
        self.assertEqual(canonical_skill("", ALIASES, EXEMPT), "")
        self.assertEqual(canonical_skill(None, ALIASES, EXEMPT), "")


class TestSkillVariantsAndOptions(unittest.TestCase):
    def test_variants_should_split_separators_and_brackets(self):
        self.assertEqual(skill_variants("Kubernetes (EKS)", ALIASES, EXEMPT), frozenset({"kubernetes", "eks"}))
        self.assertEqual(skill_variants("Python/Go", ALIASES, EXEMPT), frozenset({"python/go", "python", "go"}))
        self.assertIn("postgresql", skill_variants("PostgreSQL、MySQL", ALIASES, EXEMPT))
        self.assertIn("mysql", skill_variants("PostgreSQL、MySQL", ALIASES, EXEMPT))
        self.assertEqual(skill_variants("", ALIASES, EXEMPT), frozenset())

    def test_split_options_or_separators(self):
        self.assertEqual(split_skill_options("PostgreSQL / MySQL", ALIASES, EXEMPT), ("postgresql", "mysql"))
        self.assertEqual(split_skill_options("Python or Go", ALIASES, EXEMPT), ("python", "go"))
        self.assertEqual(split_skill_options("python 或 go", ALIASES, EXEMPT), ("python", "go"))
        self.assertEqual(split_skill_options("a|b|a", ALIASES, EXEMPT), ("a", "b"))
        self.assertEqual(split_skill_options("", ALIASES, EXEMPT), ())

    def test_split_options_should_not_split_alias_key(self):
        self.assertEqual(split_skill_options("CI/CD", ALIASES, EXEMPT), ("ci/cd",))
        self.assertEqual(split_skill_options("ci / cd", ALIASES, EXEMPT), ("ci / cd",))

    def test_split_options_word_or_should_require_spaces(self):
        self.assertEqual(split_skill_options("sqlalchemy orm", ALIASES, EXEMPT), ("sqlalchemy orm",))


class TestFindSkillMention(unittest.TestCase):
    TEXT = "# 王小明\n使用 Python3 與 Golang 開發服務\n另熟 C++ 與 PostgreSQL 12\nUsing Go for tooling\n部署於 kubernetes(eks)"

    def find(self, options, min_chars=3, snippet=80, text=None):
        return find_skill_mention(self.TEXT if text is None else text, options, ALIASES, EXEMPT, min_chars, snippet)

    def test_version_suffix_and_alias_hit(self):
        self.assertEqual(self.find(["python"]).term, "python")
        self.assertEqual(self.find(["postgresql"]).snippet, "另熟 C++ 與 PostgreSQL 12")
        self.assertEqual(self.find(["kubernetes"]).term, "kubernetes")

    def test_alias_reverse_lookup_should_find_golang_for_go(self):
        mention = self.find(["go"], text="我用 Golang 寫過服務")
        self.assertEqual(mention.term, "golang")
        self.assertFalse(mention.ambiguous)

    def test_short_term_should_be_ambiguous(self):
        mention = self.find(["go"], text="Using Go for tooling")
        self.assertTrue(mention.ambiguous)
        self.assertFalse(self.find(["go"], min_chars=2, text="Using Go for tooling").ambiguous)

    def test_c_should_not_hit_cpp_or_csharp(self):
        self.assertIsNone(self.find(["c"], text="熟悉 C++ 與 C#"))
        self.assertEqual(self.find(["c++"], text="熟悉 C++ 與 C#").term, "c++")

    def test_java_should_not_hit_javascript(self):
        self.assertIsNone(self.find(["java"], text="只寫 JavaScript"))

    def test_absent_and_empty_inputs(self):
        self.assertIsNone(self.find(["rust"]))
        self.assertIsNone(self.find(["python"], text=""))
        self.assertIsNone(self.find([], text="python"))

    def test_snippet_should_be_truncated(self):
        mention = self.find(["python"], snippet=6, text="Python " + "x" * 100)
        self.assertEqual(len(mention.snippet), 6)

    def test_non_ambiguous_hit_should_win_over_ambiguous(self):
        mention = self.find(["go"], text="Go 與 Golang")
        self.assertEqual(mention.term, "golang")

    def test_multiword_option_should_match_with_spaces(self):
        mention = self.find(["machine learning"], text="專長 Machine  Learning 與統計")
        self.assertIsNotNone(mention)


class TestRequirementMatcherRules(unittest.TestCase):
    """規格 §2.3 規則 1~7 逐列驗證"""

    def setUp(self):
        self.m = RequirementMatcher(RAW_ALIASES, version_strip_exempt=["web3"], lexical_min_chars=3, snippet_chars=80)

    def test_rule1_no_options_should_be_unknown(self):
        self.assertEqual(self.m.evaluate(skill_req(), profile(["python"]), resume_text="python"), MatchStatus.UNKNOWN)

    def test_rule2_structured_hit_with_or_options(self):
        req = skill_req(skills=["python", "go"])
        self.assertEqual(self.m.evaluate(req, profile(["golang"])), MatchStatus.MET)  # 僅會其一
        self.assertEqual(self.m.evaluate(req, profile(["Python 3.11"])), MatchStatus.MET)

    def test_rule2_legacy_single_skill_fallback(self):
        self.assertEqual(self.m.evaluate(skill_req(skill="k8s"), profile(["Kubernetes (EKS)"])), MatchStatus.MET)

    def test_rule2_chunk_skills_participate(self):
        self.assertEqual(self.m.evaluate(skill_req(skill="redis"), profile(["python"]), ["Redis 7"]), MatchStatus.MET)

    def test_rule3_lexical_fallback_met_with_evidence(self):
        req = skill_req(skill="postgresql")
        text = "## 經歷\n維運 PostgreSQL 12 叢集"
        self.assertEqual(self.m.evaluate(req, profile(["python"]), resume_text=text), MatchStatus.MET)
        mention = self.m.lexical_mention(req, profile(["python"]), (), text)
        self.assertEqual(mention.snippet, "維運 PostgreSQL 12 叢集")
        self.assertTrue(EvidenceVerifier(4).verify(mention.snippet, text))

    def test_lexical_mention_should_be_none_when_structured_or_non_skill(self):
        req = skill_req(skill="python")
        self.assertIsNone(self.m.lexical_mention(req, profile(["python"]), (), "python"))
        years = JobRequirement("R9", RequirementCategory.YEARS, RequirementPriority.MUST, "年資", min_value=3)
        self.assertIsNone(self.m.lexical_mention(years, profile(), (), "python"))

    def test_rule4_unverified_or_ambiguous_should_be_unknown(self):
        self.assertEqual(self.m.evaluate(skill_req(skill="rust"), profile(["python"], unverified=["Rust"]),
                                         resume_text="沒有相關字樣"), MatchStatus.UNKNOWN)
        self.assertEqual(self.m.evaluate(skill_req(skill="go"), profile(["python"]), resume_text="Using Go daily"),
                         MatchStatus.UNKNOWN)

    def test_rule5_resume_text_none_keeps_rev1_behaviour(self):
        req = skill_req(skill="rust")
        self.assertEqual(self.m.evaluate(req, profile([])), MatchStatus.UNKNOWN)
        self.assertEqual(self.m.evaluate(req, profile(["python"])), MatchStatus.UNMET)

    def test_rule6_empty_text_should_be_unknown(self):
        self.assertEqual(self.m.evaluate(skill_req(skill="rust"), profile(["python"]), resume_text=""),
                         MatchStatus.UNKNOWN)
        self.assertEqual(self.m.evaluate(skill_req(skill="rust"), profile(["python"]), resume_text="  \n"),
                         MatchStatus.UNKNOWN)

    def test_rule7_full_text_without_mention_should_be_unmet(self):
        status = self.m.evaluate(skill_req(skills=["rust", "scala"]), profile(["python"]),
                                 resume_text="只用 Python 與 Redis 開發")
        self.assertEqual(status, MatchStatus.UNMET)  # 不得洗為 UNKNOWN

    def test_exempt_word_not_merged_into_web(self):
        m = RequirementMatcher({}, version_strip_exempt=["web3"])
        self.assertEqual(m.evaluate(skill_req(skill="web"), profile(["web3"])), MatchStatus.UNMET)
        self.assertEqual(m.evaluate(skill_req(skill="web3"), profile(["web3"])), MatchStatus.MET)

    def test_evaluate_candidate_passes_resume_text(self):
        jd = JdRequirements("h", "t", (skill_req("R1", skill="postgresql"),), (), "q")
        ev = self.m.evaluate_candidate(jd, "c1", "王小明", 0.9, profile(["python"]), (), resume_text="用過 PostgreSQL")
        self.assertEqual(ev.statuses["R1"], MatchStatus.MET)
        ev_legacy = self.m.evaluate_candidate(jd, "c1", "王小明", 0.9, profile(["python"]))
        self.assertEqual(ev_legacy.statuses["R1"], MatchStatus.UNMET)


class TestJobRequirementModel(unittest.TestCase):
    def test_skill_options_priority_and_fallback(self):
        self.assertEqual(skill_req(skill="a", skills=["b", "c"]).skill_options, ("b", "c"))
        self.assertEqual(skill_req(skill="a").skill_options, ("a",))
        self.assertEqual(skill_req().skill_options, ())


class TestCodecRev2(unittest.TestCase):
    def test_requirement_round_trip_with_skills(self):
        req = skill_req(skill="python", skills=["python", "go"])
        restored = requirement_from_dict(requirement_to_dict(req))
        self.assertEqual(restored, req)
        self.assertEqual(requirement_to_dict(req)["skills"], ["python", "go"])

    def test_legacy_dict_without_skills_key_should_backfill(self):
        legacy = {"requirement_id": "R1", "category": "SKILL", "priority": "MUST", "label": "x", "skill": "python"}
        self.assertEqual(requirement_from_dict(legacy).skill_options, ("python",))
        legacy_no_skill = dict(legacy, skill=None)
        self.assertEqual(requirement_from_dict(legacy_no_skill).skill_options, ())

    def test_jd_round_trip(self):
        jd = JdRequirements("h", "t", (skill_req("R1", skills=["python", "go"]),), (), "q")
        self.assertEqual(jd_from_dict(jd_to_dict(jd)), jd)

    def test_relaxation_round_trip_and_legacy(self):
        eval_list = [self._ev("a", {"R1": MatchStatus.MET, "R2": MatchStatus.UNMET})]
        rep = ConstraintRelaxationAnalyzer().analyze(eval_list, [skill_req("R1", "x"), skill_req("R2", "y")], 3)
        restored = relaxation_from_dict(relaxation_to_dict(rep))
        self.assertEqual(restored, rep)
        legacy = relaxation_to_dict(rep)
        legacy.pop("strictest_requirement_ids")
        for item in legacy["items"]:
            item.pop("met_count")
        old = relaxation_from_dict(legacy)
        self.assertEqual(old.strictest_requirement_ids, ())
        self.assertTrue(all(i.met_count == 0 for i in old.items))

    @staticmethod
    def _ev(cid, statuses):
        from src.domain.recruitment import CandidateEvaluation

        return CandidateEvaluation(cid, cid, 0.5, statuses, profile(cid=cid), tuple(statuses), ())


class TestStrictestDiagnosis(unittest.TestCase):
    """AC-37：全部 delta=0 時以 met_count 最小者為次級瓶頸"""

    @staticmethod
    def _ev(cid, statuses):
        return TestCodecRev2._ev(cid, statuses)

    def setUp(self):
        self.must = [skill_req("R1", "a"), skill_req("R2", "b"), skill_req("R3", "c")]

    def test_all_delta_zero_should_report_lowest_met_count(self):
        M, U = MatchStatus.MET, MatchStatus.UNMET
        evals = [
            self._ev("c1", {"R1": M, "R2": U, "R3": U}),
            self._ev("c2", {"R1": M, "R2": U, "R3": U}),
            self._ev("c3", {"R1": U, "R2": M, "R3": U}),
            self._ev("c4", {"R1": U, "R2": U, "R3": M}),
        ]
        rep = ConstraintRelaxationAnalyzer().analyze(evals, self.must, 3)
        self.assertEqual(rep.baseline_qualified, 0)
        self.assertTrue(all(i.delta == 0 for i in rep.items))
        self.assertEqual({i.requirement_id: i.met_count for i in rep.items}, {"R1": 2, "R2": 1, "R3": 1})
        self.assertEqual(rep.bottleneck_requirement_ids, ())
        self.assertEqual(rep.strictest_requirement_ids, ("R2", "R3"))  # 並列全列

    def test_positive_delta_should_leave_strictest_empty(self):
        M, U = MatchStatus.MET, MatchStatus.UNMET
        evals = [self._ev("c1", {"R1": M, "R2": M, "R3": U}), self._ev("c2", {"R1": M, "R2": U, "R3": U})]
        rep = ConstraintRelaxationAnalyzer().analyze(evals, self.must, 3)
        self.assertEqual(rep.bottleneck_requirement_ids, ("R3",))
        self.assertEqual(rep.strictest_requirement_ids, ())

    def test_empty_pool_should_not_fail(self):
        rep = ConstraintRelaxationAnalyzer().analyze([], self.must, 3)
        self.assertEqual(rep.strictest_requirement_ids, ("R1", "R2", "R3"))
        self.assertTrue(all(i.met_count == 0 for i in rep.items))


class TestCollectEvidenceMultiOption(unittest.TestCase):
    def test_every_option_should_map_back_to_requirement(self):
        req = skill_req("R1", skill="python", skills=["python", "go"])
        prof = CandidateProfile("c", "h", "v", None, None, None, None, ("golang",),
                                (EvidenceQuote("skill:golang", "使用 Golang 開發", True),
                                 EvidenceQuote("skill:rust", "寫過 Rust 專案", True)), False)
        evidence = collect_requirement_evidence([req], prof, RAW_ALIASES)
        self.assertEqual([(e.field, e.requirement_id) for e in evidence],
                         [("skill:golang", "R1"), ("skill:rust", None)])

    def test_versioned_profile_field_should_map_to_canonical_option(self):
        req = skill_req("R2", skill="python")
        prof = CandidateProfile("c", "h", "v", None, None, None, None, (),
                                (EvidenceQuote("skill:python3", "Python3 開發", True),), False)
        self.assertEqual(collect_requirement_evidence([req], prof, RAW_ALIASES)[0].requirement_id, "R2")


class TestQuoteSanitizeAndBrackets(unittest.TestCase):
    def setUp(self):
        self.v = EvidenceVerifier(2)

    def test_fullwidth_corner_quotes_should_also_be_verified(self):
        reply, removed = sanitize_reply_quotes("引述『虛構的句子』與「真實的句子」", ["真實的句子"], self.v, "[X]")
        self.assertEqual(reply, "引述[X]與「真實的句子」")
        self.assertEqual(removed, 1)

    def test_unbalanced_brackets_detection(self):
        for text in ["Message Queue (", "「未結束", "（a [b）", "x 【y"]:
            with self.subTest(text=text):
                self.assertTrue(has_unbalanced_brackets(text))
        for text in ["", "完整 (a) 「b」 『c』 [d] 【e】 （f）", "1) 條列 2) 條列"]:
            with self.subTest(text=text):
                self.assertFalse(has_unbalanced_brackets(text))


class TestGateTwoRound1Fixes(unittest.TestCase):
    """Gate 2 P1-01 / P1-02 / P2-01 / P2-05 回歸"""

    ALIASES = {"node.js": "nodejs", "node": "nodejs", "pl/sql": "plsql", "tcp/ip": "tcpip",
               "a/b testing": "abtesting"}

    def test_p1_01_generic_alias_term_must_not_cause_false_met(self):
        # Arrange
        m = RequirementMatcher(self.ALIASES, lexical_alias_denylist=["node"])
        text = "管理 worker node 擴縮容"
        # Act / Assert
        self.assertEqual(m.evaluate(skill_req(skill="nodejs"), profile(), resume_text=text), MatchStatus.UNMET)
        self.assertEqual(m.evaluate(skill_req(skill="nodejs"), profile(), resume_text="使用 Node.js 開發"),
                         MatchStatus.MET)

    def test_p1_01_without_denylist_reproduces_original_false_met(self):
        m = RequirementMatcher(self.ALIASES)
        self.assertEqual(m.evaluate(skill_req(skill="nodejs"), profile(), resume_text="worker node"),
                         MatchStatus.MET)

    def test_p1_02_snippet_is_centered_on_match(self):
        # Arrange
        text = "前綴" * 60 + " 使用 Kafka 處理事件 " + "後綴" * 60
        # Act
        hit = find_skill_mention(text, ["kafka"], {}, (), 3, 80)
        # Assert
        self.assertIn("Kafka", hit.snippet)
        self.assertLessEqual(len(hit.snippet), 80)
        self.assertIn(hit.snippet, text)

    def test_p1_02_short_line_snippet_unchanged(self):
        hit = find_skill_mention("  使用 Kafka  ", ["kafka"], {}, (), 3, 80)
        self.assertEqual(hit.snippet, "使用 Kafka")

    def test_p2_01_slash_compound_terms_with_alias_are_not_split(self):
        aliases = {k: v for k, v in self.ALIASES.items()}
        norm = {"pl/sql": "plsql", "tcp/ip": "tcpip", "a/btesting": "abtesting"}
        self.assertEqual(len(split_skill_options("PL/SQL", norm)), 1)
        self.assertEqual(len(split_skill_options("TCP/IP", norm)), 1)
        self.assertEqual(len(split_skill_options("A/B testing", norm)), 1)
        m = RequirementMatcher(aliases)
        self.assertEqual(m.evaluate(skill_req(skills=["PL/SQL"]), profile(["sql"]), resume_text="sql"),
                         MatchStatus.UNMET)

    def test_p2_05_default_exempt_protects_base64_utf8_sha256_arm64(self):
        from src.application.recruitment_settings import RecruitmentSettings
        exempt = RecruitmentSettings().skill_version_strip_exempt
        for term in ("base64", "utf8", "sha256", "arm64"):
            self.assertEqual(canonical_skill(term, {}, exempt), term)
            self.assertNotEqual(canonical_skill(term, {}, ()), term)


if __name__ == "__main__":
    unittest.main()
