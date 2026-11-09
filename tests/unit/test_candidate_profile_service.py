"""
CandidateProfileService 白箱單元測試 (AC-09, AC-13~17)：快取命中 0 呼叫、Hash/版本失效、降級、預算熔斷、證據驗證。
"""
import unittest
from unittest.mock import MagicMock

from src.application.candidate_profile_service import CandidateProfileService, TurnBudget
from src.application.recruitment_tools import RecruitmentTools
from src.domain.exceptions import LlmQuotaExhaustedError
from src.domain.models import CandidateSummary
from src.domain.recruitment import CandidateProfile, EvidenceQuote
from src.domain.recruitment_services import EvidenceVerifier, ProtectedAttributeGuard
from tests.unit.recruitment_fakes import PROTECTED_TERMS, RESUMES, FakeProfileExtractor, FakeSearch, InMemoryProfileCache


def pool(*cids):
    return [CandidateSummary(cid, RESUMES[cid]["name"], RESUMES[cid]["score"], all_skills=RESUMES[cid]["skills"])
            for cid in cids]


class TestCandidateProfileService(unittest.TestCase):
    def setUp(self):
        self.search = FakeSearch()
        self.cache = InMemoryProfileCache()
        self.extractor = FakeProfileExtractor()
        self.parser = MagicMock()
        self.parser.parse.return_value = (6.0, "6年工作經驗")
        self.service = self._service(self.extractor)

    def _service(self, extractor):
        tools = RecruitmentTools(self.search, self.parser)
        return CandidateProfileService(extractor, self.cache, tools, ProtectedAttributeGuard(PROTECTED_TERMS),
                                       EvidenceVerifier(4), max_resume_chars=12000, max_concurrency=2)

    def test_second_query_should_hit_cache_with_zero_llm_calls(self):
        # Arrange
        self.service.get_profiles(pool("cand_a", "cand_b"), TurnBudget(10))
        self.extractor.calls.clear()
        # Act
        result = self.service.get_profiles(pool("cand_a", "cand_b"), TurnBudget(10))
        # Assert (AC-13)
        self.assertEqual(self.extractor.calls, [])
        self.assertEqual((result.cache_hits, result.cache_misses), (2, 0))

    def test_content_hash_change_should_reextract_only_that_candidate(self):
        self.service.get_profiles(pool("cand_a", "cand_b"), TurnBudget(10))
        self.extractor.calls.clear()
        self.search.resumes["cand_b"]["text"] += "\n新增：Kubernetes 認證。"
        result = self.service.get_profiles(pool("cand_a", "cand_b"), TurnBudget(10))
        self.assertEqual(self.extractor.calls, ["cand_b"])  # AC-14
        self.assertEqual((result.cache_hits, result.cache_misses), (1, 1))

    def test_extractor_version_change_should_invalidate_cache(self):
        self.service.get_profiles(pool("cand_a"), TurnBudget(10))
        new_extractor = FakeProfileExtractor(version="v-new")
        result = self._service(new_extractor).get_profiles(pool("cand_a"), TurnBudget(10))
        self.assertEqual(new_extractor.calls, ["cand_a"])  # AC-15
        self.assertEqual(result.cache_misses, 1)

    def test_extraction_failure_should_degrade_and_not_cache(self):
        extractor = FakeProfileExtractor(fail_for={"cand_a"})
        result = self._service(extractor).get_profiles(pool("cand_a", "cand_b"), TurnBudget(10))
        degraded = result.profiles["cand_a"]
        self.assertTrue(degraded.degraded)
        self.assertEqual(degraded.years_of_experience, 6.0)  # Regex 回退
        self.assertEqual(degraded.core_skills, ("python", "redis"))  # 切片標籤回退
        self.assertIsNone(degraded.has_led_team)
        self.assertNotIn("v-test:cand_a", self.cache.profiles)  # 降級不寫快取
        self.assertIn("v-test:cand_b", self.cache.profiles)
        self.assertTrue(any("抽取失敗" in w for w in result.warnings))  # AC-16

    def test_budget_exhausted_should_stop_new_extractions(self):
        budget = TurnBudget(1)
        result = self.service.get_profiles(pool("cand_a", "cand_b", "cand_c"), budget)
        self.assertEqual(len(self.extractor.calls), 1)  # AC-17
        self.assertEqual(sum(1 for p in result.profiles.values() if p.degraded), 2)
        self.assertTrue(any("預算" in w for w in result.warnings))

    def test_unverified_evidence_should_downgrade_field_to_unknown(self):
        class FabricatingExtractor(FakeProfileExtractor):
            def extract(self, candidate_id, resume_text, content_hash):
                return CandidateProfile(candidate_id, content_hash, self.extractor_version, 20.0, True, 50, None,
                                        ("python",), (EvidenceQuote("years", "20年資深經驗"),
                                                      EvidenceQuote("has_led_team", "帶領 50 人事業部"),
                                                      EvidenceQuote("skill:python", "Python 後端 API 開發")))

        result = self._service(FabricatingExtractor()).get_profiles(pool("cand_b"), TurnBudget(5))
        prof = result.profiles["cand_b"]
        self.assertIsNone(prof.years_of_experience)  # AC-09
        self.assertIsNone(prof.has_led_team)
        self.assertIsNone(prof.max_team_size)
        self.assertEqual(prof.core_skills, ("python",))
        self.assertTrue(all(e.verified for e in prof.evidence))
        self.assertTrue(any("證據驗證失敗" in w for w in result.warnings))

    def test_llm_text_should_redact_protected_lines_and_mask_contacts(self):
        self.service.get_profiles(pool("cand_a"), TurnBudget(5))
        sent = self.extractor.texts["cand_a"]
        self.assertNotIn("性別", sent)  # AC-11
        self.assertNotIn("王小明", sent)  # AC-12
        self.assertNotIn("sample_a@example.com", sent)

    def test_quota_error_should_propagate_with_original_exception(self):
        extractor = FakeProfileExtractor(raise_exc=LlmQuotaExhaustedError("quota", retry_after_seconds=30))
        with self.assertRaises(LlmQuotaExhaustedError) as ctx:
            self._service(extractor).get_profiles(pool("cand_a"), TurnBudget(5))
        self.assertEqual(ctx.exception.retry_after_seconds, 30)

    def test_cache_failure_should_be_treated_as_miss(self):
        broken = MagicMock()
        broken.get_profile.side_effect = ConnectionError("redis down")
        broken.set_profile.side_effect = ConnectionError("redis down")
        tools = RecruitmentTools(self.search, self.parser)
        service = CandidateProfileService(self.extractor, broken, tools, ProtectedAttributeGuard(PROTECTED_TERMS),
                                          EvidenceVerifier(4), 12000, 2)
        result = service.get_profiles(pool("cand_a"), TurnBudget(5))
        self.assertEqual(result.cache_misses, 1)
        self.assertFalse(result.profiles["cand_a"].degraded)

    def test_turn_budget_counts_and_exhaustion(self):
        budget = TurnBudget(2)
        self.assertTrue(budget.try_consume())
        self.assertTrue(budget.try_consume())
        self.assertFalse(budget.try_consume())
        self.assertEqual(budget.used, 2)
        self.assertTrue(budget.exhausted)


class TestProfileNegativeCache(unittest.TestCase):
    """D-01：抽取失敗之短期負快取"""

    def setUp(self):
        self.now = [0.0]
        self.search = FakeSearch()
        self.cache = InMemoryProfileCache()
        self.parser = MagicMock()
        self.parser.parse.return_value = (6.0, "6年工作經驗")

    def _service(self, extractor, ttl=600):
        tools = RecruitmentTools(self.search, self.parser)
        return CandidateProfileService(extractor, self.cache, tools, ProtectedAttributeGuard(PROTECTED_TERMS),
                                       EvidenceVerifier(4), 12000, 2, negative_cache_ttl_seconds=ttl,
                                       clock=lambda: self.now[0])

    def test_failed_extraction_should_not_call_llm_again_within_ttl(self):
        # Arrange
        extractor = FakeProfileExtractor(fail_for={"cand_a"})
        service = self._service(extractor)
        service.get_profiles(pool("cand_a", "cand_b"), TurnBudget(10))
        extractor.calls.clear()
        # Act
        result = service.get_profiles(pool("cand_a", "cand_b"), TurnBudget(10))
        # Assert
        self.assertEqual(extractor.calls, [])
        self.assertEqual((result.cache_hits, result.negative_hits, result.cache_misses), (1, 1, 0))
        self.assertTrue(result.profiles["cand_a"].degraded)
        self.assertEqual(result.profiles["cand_a"].years_of_experience, 6.0)
        self.assertTrue(any("負快取" in w for w in result.warnings))
        self.assertNotIn("v-test:cand_a", self.cache.profiles)

    def test_negative_cache_should_expire_after_ttl(self):
        extractor = FakeProfileExtractor(fail_for={"cand_a"})
        service = self._service(extractor, ttl=600)
        service.get_profiles(pool("cand_a"), TurnBudget(10))
        self.now[0] = 601.0
        extractor.fail_for.clear()
        extractor.calls.clear()
        result = service.get_profiles(pool("cand_a"), TurnBudget(10))
        self.assertEqual(extractor.calls, ["cand_a"])
        self.assertFalse(result.profiles["cand_a"].degraded)
        self.assertIn("v-test:cand_a", self.cache.profiles)

    def test_negative_cache_should_not_override_success_or_other_hash(self):
        extractor = FakeProfileExtractor(fail_for={"cand_a"})
        service = self._service(extractor)
        service.get_profiles(pool("cand_a"), TurnBudget(10))
        self.search.resumes["cand_a"]["text"] += "\n更新內容。"
        extractor.fail_for.clear()
        extractor.calls.clear()
        result = service.get_profiles(pool("cand_a"), TurnBudget(10))
        self.assertEqual(extractor.calls, ["cand_a"])
        self.assertFalse(result.profiles["cand_a"].degraded)
        extractor.calls.clear()
        result = service.get_profiles(pool("cand_a"), TurnBudget(10))
        self.assertEqual(extractor.calls, [])
        self.assertFalse(result.profiles["cand_a"].degraded)

    def test_budget_skip_should_not_create_negative_entry(self):
        extractor = FakeProfileExtractor()
        service = self._service(extractor)
        service.get_profiles(pool("cand_a", "cand_b"), TurnBudget(1))
        extractor.calls.clear()
        service.get_profiles(pool("cand_a", "cand_b"), TurnBudget(10))
        self.assertEqual(extractor.calls, ["cand_b"])

    def test_zero_ttl_should_disable_negative_cache(self):
        extractor = FakeProfileExtractor(fail_for={"cand_a"})
        service = self._service(extractor, ttl=0)
        service.get_profiles(pool("cand_a"), TurnBudget(10))
        extractor.calls.clear()
        service.get_profiles(pool("cand_a"), TurnBudget(10))
        self.assertEqual(extractor.calls, ["cand_a"])


if __name__ == "__main__":
    unittest.main()
