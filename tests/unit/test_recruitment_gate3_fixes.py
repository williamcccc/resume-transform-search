"""
Gate 2 複審後第 3 輪 P2 修正之回歸測試 (G3-02 生日詞彙、G3-03 追問改用已驗證抽取證據、G3-04 「月 號」含空白)
"""
import unittest
from pathlib import Path

from src.domain.recruitment import (
    AnswerStatus,
    ChatSessionState,
    FollowupNarration,
    ReferenceKind,
    ShortlistEntry,
)
from src.domain.recruitment_services import OrdinalReferenceResolver, ProtectedAttributeGuard
from src.infrastructure.config import DEFAULT_PROTECTED_ATTR_TERMS
from tests.unit.recruitment_fakes import JD_TEXT, FakeNarrator, build_handlers

ROOT = Path(__file__).resolve().parents[2]


class TestG302BirthdayTerms(unittest.TestCase):
    def setUp(self):
        self.guard = ProtectedAttributeGuard(DEFAULT_PROTECTED_ATTR_TERMS.split(","))

    def test_default_terms_and_env_example_should_include_birthday_terms(self):
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        for term in ("生日", "出生日期", "生辰"):
            self.assertIn(term, DEFAULT_PROTECTED_ATTR_TERMS.split(","))
            self.assertIn(term, example)

    def test_birthday_key_value_and_tables_should_be_redacted(self):
        text = ("生日：1990/01/01\n"
                "| 項目 | 生日 | 技能 |\n| --- | --- | --- |\n| A | 1991/02/03 | Python |\n"
                "<tr><td>生辰</td><td>1992/04/05</td></tr>\n"
                "專長：Go")
        out = self.guard.redact_resume(text)
        for value in ("1990/01/01", "1991/02/03", "1992/04/05"):
            self.assertNotIn(value, out)
        self.assertIn("Python", out)
        self.assertIn("專長：Go", out)


class TestG303FollowupFallbackToVerifiedProfileEvidence(unittest.TestCase):
    def setUp(self):
        self.narrator = FakeNarrator()
        self.handlers = build_handlers(narrator=self.narrator)
        turn = self.handlers.new_turn(JD_TEXT, "t1")
        self.state = self.handlers.run_all(ChatSessionState(session_id="sess_g303_0001"), turn)

    def _ask(self, message):
        turn = self.handlers.new_turn(message, "t2")
        self.handlers.run_all(self.state, turn)
        return turn

    def test_non_verbatim_llm_quote_with_profile_evidence_should_stay_supported(self):
        self.narrator.followup_result = FollowupNarration(AnswerStatus.SUPPORTED, "有帶人經驗。", ("曾經管理六位工程師",))
        turn = self._ask("第 1 位有帶過人嗎？")
        self.assertEqual(turn.followup.answer_status, AnswerStatus.SUPPORTED)
        self.assertTrue(turn.followup.evidence)
        verified = {e.quote for e in self.state.shortlist[0].evidence}
        self.assertTrue(set(turn.followup.evidence) <= verified)
        self.assertNotIn("曾經管理六位工程師", turn.final_reply)
        self.assertTrue(any("抽取證據" in w for w in turn.warnings))

    def test_without_profile_evidence_should_still_downgrade_to_not_mentioned(self):
        self.narrator.followup_result = FollowupNarration(AnswerStatus.SUPPORTED, "有帶人經驗。", ("帶領 30 人事業群",))
        turn = self._ask("第 2 位有帶過人嗎？")
        self.assertEqual(turn.followup.answer_status, AnswerStatus.NOT_MENTIONED)
        self.assertEqual(turn.followup.evidence, ())
        self.assertIn("履歷未提及", turn.final_reply)


class TestG304MonthDaySpacing(unittest.TestCase):
    def test_month_day_with_spaces_should_not_resolve(self):
        resolver = OrdinalReferenceResolver()
        shortlist = tuple(ShortlistEntry(i, f"c{i}", f"n{i}", True, 0.9, (), (), ()) for i in (1, 2, 3))
        for text in ("5 月 3 號討論", "5月 3 號討論", "5 月3號討論", "5月　3號討論"):
            with self.subTest(text=text):
                self.assertEqual(resolver.resolve(text, shortlist, "c1").kind, ReferenceKind.NONE)
        self.assertEqual(resolver.resolve("5 月 3 號面試 2 號", shortlist, None).rank, 2)


if __name__ == "__main__":
    unittest.main()
