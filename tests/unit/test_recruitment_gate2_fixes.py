"""
Gate 2 第 2 輪修正之回歸測試 (G2-01 ~ G2-08, G2-10)
姓名零落入對話歷史、受保護欄位表格/英文遮蔽、日期不誤判為電話、指代邊界、技能證據失敗 → UNKNOWN、
抽取逾時降級、負快取計數分離、Session 鎖回收、前端面試題清空。
"""
import importlib.util
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from src.application.candidate_profile_service import CandidateProfileService, TurnBudget
from src.application.recruitment_tools import RecruitmentTools
from src.domain.models import CandidateSummary
from src.domain.recruitment import (
    CandidateProfile,
    ChatSessionState,
    EvidenceQuote,
    JobRequirement,
    MatchStatus,
    ReferenceKind,
    RequirementCategory,
    RequirementPriority,
    ShortlistEntry,
)
from src.domain.recruitment_codec import profile_from_dict, profile_to_dict
from src.domain.recruitment_services import (
    EvidenceVerifier,
    OrdinalReferenceResolver,
    ProtectedAttributeGuard,
    RequirementMatcher,
    mask_contact_info,
)
from tests.unit.recruitment_fakes import (
    JD_TEXT,
    PROTECTED_TERMS,
    RESUMES,
    FakeNarrator,
    FakeProfileExtractor,
    FakeSearch,
    InMemoryProfileCache,
    build_handlers,
)

NAMES = [r["name"] for r in RESUMES.values()]
HAS_LANGGRAPH = importlib.util.find_spec("langgraph") is not None
ROOT = Path(__file__).resolve().parents[2]


def pool(*cids):
    return [CandidateSummary(cid, RESUMES[cid]["name"], RESUMES[cid]["score"], all_skills=RESUMES[cid]["skills"])
            for cid in cids]


class TestG201NamesNeverInHistory(unittest.TestCase):
    def test_history_should_store_alias_reply_while_response_has_names(self):
        narrator = FakeNarrator()
        handlers = build_handlers(narrator=narrator)
        turn = handlers.new_turn(JD_TEXT, "t1")
        state = handlers.run_all(ChatSessionState(session_id="sess_g201_0001"), turn)
        assistant = [m.content for m in state.history if m.role == "assistant"]
        self.assertTrue(assistant)
        self.assertFalse(any(name in text for text in assistant for name in NAMES))
        self.assertIn("候選人 #1（王小明）", turn.final_reply)
        self.assertEqual(state.shortlist[0].candidate_name, "王小明")  # GET /api/chat 還原仍有姓名

    def test_new_jd_should_not_leak_previous_names_to_llm(self):
        narrator = FakeNarrator()
        handlers = build_handlers(narrator=narrator)
        state = handlers.run_all(ChatSessionState(session_id="sess_g201_0002"), handlers.new_turn(JD_TEXT, "t1"))
        other = FakeSearch({"cand_b": RESUMES["cand_b"]})
        handlers2 = build_handlers(narrator=narrator, search=other)
        state = handlers2.run_all(state, handlers2.new_turn(JD_TEXT + "（更新版）", "t2"))
        handlers2.run_all(state, handlers2.new_turn("剛剛聊了什麼", "t3"))
        facts = narrator.general_facts[-1]
        self.assertFalse(any(name in repr(facts) for name in NAMES))


class TestG202ProtectedRedaction(unittest.TestCase):
    def setUp(self):
        self.guard = ProtectedAttributeGuard(list(PROTECTED_TERMS) + ["gender", "age", "birth", "marital"])

    def test_markdown_table_columns_should_be_redacted_by_header(self):
        text = "| 姓名 | 性別 | 年齡 | 技能 |\n| --- | --- | --- | --- |\n| 王小明 | 女 | 30 | Python |"
        out = self.guard.redact_resume(text)
        rows = out.splitlines()
        self.assertIn("| --- |", rows[1])
        self.assertNotIn("| 女 |", out)
        self.assertNotIn("| 30 |", out)
        self.assertIn("Python", out)
        self.assertIn("王小明", out)

    def test_english_key_value_should_be_redacted_case_insensitive(self):
        out = self.guard.redact_resume("Gender: F\nDATE OF BIRTH: 1990\nMarital status: single\nSkills: Python")
        self.assertNotIn(": F", out)
        self.assertNotIn("1990", out)
        self.assertNotIn("single", out)
        self.assertIn("Skills: Python", out)

    def test_english_terms_should_respect_word_boundaries(self):
        self.assertEqual(self.guard.scan_text("Manage a team; page language usage"), [])
        self.assertEqual(self.guard.scan_text("Age: 30"), ["age"])

    def test_default_config_terms_should_include_english(self):
        from src.infrastructure.config import DEFAULT_PROTECTED_ATTR_TERMS

        for term in ("gender", "sex", "age", "birth", "dob", "birthday", "marital", "married", "religion",
                     "nationality", "photo"):
            self.assertIn(term, DEFAULT_PROTECTED_ATTR_TERMS.split(","))
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("nationality", example)


class TestG203PhoneMasking(unittest.TestCase):
    def test_date_ranges_should_not_be_masked(self):
        for text in ("2015/03 - 2020/06 backend", "2018.01-2020.12 工程師", "2019-03 ~ 2021-07", "2016/09~2018/08"):
            with self.subTest(text=text):
                self.assertEqual(mask_contact_info(text, [], "#1"), text)

    def test_phone_numbers_should_still_be_masked(self):
        mobile = "09" + "12" + "345678"
        mobile_dash = "09" + "12-345" + "-678"
        landline = "(0" + "2)2345-" + "6789"
        intl = "+886-9" + "12-345-" + "678"
        for phone in (mobile, mobile_dash, landline, intl):
            with self.subTest(phone=phone):
                out = mask_contact_info(f"電話：{phone}", [], "#1")
                self.assertIn("[已遮蔽電話]", out)
                self.assertNotIn(phone, out)


class TestG204ReferenceBoundaries(unittest.TestCase):
    def setUp(self):
        self.resolver = OrdinalReferenceResolver()
        self.shortlist = tuple(ShortlistEntry(i, f"c{i}", f"n{i}", True, 0.9, (), (), ()) for i in (1, 2, 3))

    def test_date_hao_pronoun_other_and_csharp_should_not_resolve(self):
        for text in ("我們 3月5號 討論", "3月15號再說", "其他人呢", "其它的呢", "熟悉 C# 10 的人"):
            with self.subTest(text=text):
                self.assertEqual(self.resolver.resolve(text, self.shortlist, "c1").kind, ReferenceKind.NONE)

    def test_valid_forms_still_resolve(self):
        self.assertEqual(self.resolver.resolve("3月5號面試第 2 位", self.shortlist, None).rank, 2)
        self.assertEqual(self.resolver.resolve("2號呢", self.shortlist, None).rank, 2)
        self.assertEqual(self.resolver.resolve("看 #3", self.shortlist, None).rank, 3)


class TestG205UnverifiedSkill(unittest.TestCase):
    def test_matcher_should_return_unknown_for_unverified_skill(self):
        prof = CandidateProfile("c", "h", "v", 5.0, None, None, None, ("python",), (),
                                unverified_skills=("kubernetes",))
        req = JobRequirement("R1", RequirementCategory.SKILL, RequirementPriority.MUST, "K8s", skill="k8s")
        self.assertEqual(RequirementMatcher({"k8s": "kubernetes"}).evaluate(req, prof), MatchStatus.UNKNOWN)
        self.assertEqual(profile_from_dict(profile_to_dict(prof)).unverified_skills, ("kubernetes",))

    def test_profile_service_should_record_unverified_skills(self):
        class FabricatedSkill(FakeProfileExtractor):
            def extract(self, candidate_id, resume_text, content_hash):
                return CandidateProfile(candidate_id, content_hash, self.extractor_version, None, None, None, None,
                                        ("python", "golang"),
                                        (EvidenceQuote("skill:python", "Python 後端 API 開發"),
                                         EvidenceQuote("skill:golang", "Golang 高併發架構")))

        tools = RecruitmentTools(FakeSearch(), None)
        service = CandidateProfileService(FabricatedSkill(), InMemoryProfileCache(), tools,
                                          ProtectedAttributeGuard(PROTECTED_TERMS), EvidenceVerifier(4), 12000, 2)
        prof = service.get_profiles(pool("cand_b"), TurnBudget(5)).profiles["cand_b"]
        self.assertEqual(prof.core_skills, ("python",))
        self.assertEqual(prof.unverified_skills, ("golang",))


class TestG206G207ProfileTimeoutAndCounters(unittest.TestCase):
    def test_extraction_exceeding_deadline_should_degrade_without_waiting(self):
        class SlowExtractor(FakeProfileExtractor):
            def extract(self, candidate_id, resume_text, content_hash):
                time.sleep(1.0)
                return super().extract(candidate_id, resume_text, content_hash)

        tools = RecruitmentTools(FakeSearch(), None)
        service = CandidateProfileService(SlowExtractor(), InMemoryProfileCache(), tools,
                                          ProtectedAttributeGuard(PROTECTED_TERMS), EvidenceVerifier(4), 12000, 2)
        start = time.perf_counter()
        result = service.get_profiles(pool("cand_a"), TurnBudget(5), remaining_seconds=lambda: 0.05)
        self.assertLess(time.perf_counter() - start, 0.6)
        self.assertTrue(result.profiles["cand_a"].degraded)
        self.assertTrue(any("逾時" in w for w in result.warnings))

    def test_negative_hits_should_be_counted_separately(self):
        extractor = FakeProfileExtractor(fail_for={"cand_a"})
        tools = RecruitmentTools(FakeSearch(), None)
        service = CandidateProfileService(extractor, InMemoryProfileCache(), tools,
                                          ProtectedAttributeGuard(PROTECTED_TERMS), EvidenceVerifier(4), 12000, 2,
                                          negative_cache_ttl_seconds=600)
        service.get_profiles(pool("cand_a", "cand_b"), TurnBudget(10))
        result = service.get_profiles(pool("cand_a", "cand_b"), TurnBudget(10))
        self.assertEqual((result.cache_hits, result.negative_hits, result.cache_misses), (1, 1, 0))

    def test_turn_usage_should_expose_negative_hits(self):
        handlers = build_handlers(profile_extractor=FakeProfileExtractor(fail_for={"cand_a"}),
                                  settings=None)
        handlers._profiles._negative_ttl = 600.0
        state = handlers.run_all(ChatSessionState(session_id="sess_g207_0001"), handlers.new_turn(JD_TEXT, "a"))
        turn = handlers.new_turn(JD_TEXT, "b")
        handlers.run_all(state, turn)
        self.assertEqual(turn.usage.profile_negative_hits, 1)
        self.assertEqual(turn.usage.profile_cache_hits, 3)

    def test_lock_ttl_buffer_config_default(self):
        from unittest.mock import patch
        import os
        from src.infrastructure.config import AppConfig

        with patch("dotenv.load_dotenv"), patch.dict(os.environ, {}, clear=True):
            cfg = AppConfig.load(override_api_key="k")
        self.assertEqual(cfg.chat_session_lock_ttl_buffer_seconds, 30)


@unittest.skipUnless(HAS_LANGGRAPH, "langgraph 未安裝")
class TestG208LockCleanup(unittest.TestCase):
    def test_reset_and_eviction_should_remove_session_locks(self):
        from src.infrastructure.orchestration.checkpointer_factory import MemorySessionLock, build_memory_checkpointer
        from src.infrastructure.orchestration.langgraph_recruitment_graph import LangGraphRecruitmentOrchestrator

        lock = MemorySessionLock()
        with lock.hold("s1"):
            lock.remove("s1")  # 持有中不得移除
            self.assertEqual(len(lock), 1)
        lock.remove("s1")
        self.assertEqual(len(lock), 0)

        bundle = build_memory_checkpointer(60, 1)
        orch = LangGraphRecruitmentOrchestrator(build_handlers(), bundle, 2)
        orch.run_turn("sess_lock_0001", "你好", "a")
        orch.run_turn("sess_lock_0002", "你好", "b")  # 淘汰 0001
        self.assertEqual(len(bundle.lock), 1)
        orch.reset("sess_lock_0002")
        self.assertEqual(len(bundle.lock), 0)


class TestG210DashboardQuestions(unittest.TestCase):
    def test_render_questions_should_reset_on_empty(self):
        html = (ROOT / "src/interfaces/web/static/dashboard.html").read_text(encoding="utf-8")
        start = html.index("function renderChatQuestions")
        body = html[start:html.index("function setChatBusy")]
        self.assertIn("尚未產生", body)
        self.assertNotIn("innerHTML", body)


if __name__ == "__main__":
    unittest.main()
