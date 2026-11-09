"""
招募助手 Rev2 節點層白箱單元測試 (Fake LLM、純 Python run_all)
AC-36/37/43（SKILL 詞面回退、次級瓶頸、真實寫法技能）、AC-40（截斷降級）、AC-41/42（引文驗證範圍限縮）。
履歷與姓名皆為記憶體虛構資料。
"""
import unittest
from dataclasses import replace

from src.application.candidate_profile_service import TurnBudget
from src.application.recruitment_nodes import ReplySection
from src.domain.exceptions import LlmOutputTruncatedError
from src.domain.recruitment import (
    AnswerStatus,
    CandidateProfile,
    ChatSessionState,
    EvidenceQuote,
    FollowupNarration,
    InterviewQuestion,
    JdRequirements,
    JobRequirement,
    MatchStatus,
    RequirementCategory,
    RequirementPriority,
)
from tests.unit.recruitment_fakes import (
    JD_TEXT,
    RESUMES,
    FakeJdExtractor,
    FakeNarrator,
    FakeSearch,
    InMemoryProfileCache,
    build_handlers,
    make_settings,
)

REMOVED = "（引文未通過原文驗證，已移除）"


def run_turn(handlers, state, message):
    turn = handlers.new_turn(message, "trace")
    return handlers.run_all(state, turn), turn


def skill(rid, label, *skills, priority=RequirementPriority.MUST):
    return JobRequirement(rid, RequirementCategory.SKILL, priority, label, skill=skills[0], skills=tuple(skills))


class SpecProfileExtractor:
    """依 specs 回傳 Profile：core_skills 僅含明列者（其餘技能只存在於履歷內文）"""

    def __init__(self, specs, version="v-rev2"):
        self._specs = specs
        self._version = version
        self.calls = []

    @property
    def extractor_version(self):
        return self._version

    def extract(self, candidate_id, resume_text, content_hash):
        self.calls.append(candidate_id)
        spec = self._specs[candidate_id]
        evidence = [EvidenceQuote(f"skill:{name}", quote) for name, quote in spec.items()]
        return CandidateProfile(candidate_id, content_hash, self._version, None, None, None, None,
                                tuple(spec.keys()), tuple(evidence))


AC43_RESUMES = {
    "cand_a": {"name": "王小明", "score": 0.95, "skills": [],
               "text": "# 王小明\n## 技能\n使用 Python3 開發後端服務並以 k8s 部署\n維運 PostgreSQL 12 資料庫"},
    "cand_b": {"name": "李小華", "score": 0.90, "skills": [],
               "text": "# 李小華\n## 經歷\n使用 Golang 撰寫微服務並部署於 Kubernetes (EKS)\n資料層採用 postgres 14"},
    "cand_c": {"name": "陳大文", "score": 0.85, "skills": [],
               "text": "# 陳大文\n## 經歷\n以 Python 3.11 開發資料服務，資料庫為 PostgreSQL"},
    "cand_d": {"name": "林美玲", "score": 0.80, "skills": [],
               "text": "# 林美玲\n## 經歷\n擔任部門經理，帶領 12 人 Java 團隊"},
}
AC43_PROFILES = {
    "cand_a": {"python3": "Python3 開發後端服務", "k8s": "k8s 部署"},
    "cand_b": {},
    "cand_c": {"python": "Python 3.11 開發資料服務"},
    "cand_d": {},
}
AC43_JD = JdRequirements(
    jd_hash="", title="資深後端工程師",
    must=(skill("x1", "精通 Python 或 Go", "python", "go"), skill("x2", "熟悉 PostgreSQL", "postgresql"),
          skill("x3", "熟悉 Kubernetes", "kubernetes")),
    nice=(), retrieval_query="後端 Python Go PostgreSQL Kubernetes")


AC43_ALIASES = {"k8s": "kubernetes", "golang": "go", "postgres": "postgresql"}


def build_ac43(narrator=None, resumes=None, profiles=None, jd=None):
    resumes = resumes or AC43_RESUMES
    extractor = SpecProfileExtractor(profiles or AC43_PROFILES)
    handlers = build_handlers(
        settings=make_settings(skill_aliases=AC43_ALIASES), search=FakeSearch(resumes), profile_extractor=extractor, cache=InMemoryProfileCache(),
        jd_extractor=FakeJdExtractor(jd or AC43_JD), narrator=narrator or self_narrator())
    return handlers


def self_narrator():
    narrator = FakeNarrator()
    narrator.match_text = "整體而言多位人選技術背景相近。"
    return narrator


class TestAc43RealWorldSkills(unittest.TestCase):
    """AC-43 / TC-31（FAKE 軌）：真實寫法技能 E2E"""

    def setUp(self):
        self.handlers = build_ac43()
        self.state, self.turn = run_turn(self.handlers, ChatSessionState(session_id="sess_rev2_01"), JD_TEXT)

    def test_baseline_qualified_should_be_positive_and_or_requirement_met(self):
        evals = {e.candidate_id: e for e in self.state.pool_evaluations}
        self.assertEqual(sum(1 for e in evals.values() if e.fully_qualified), 2)
        self.assertEqual(evals["cand_a"].statuses["R1"], MatchStatus.MET)  # Python3（結構化命中）
        self.assertEqual(evals["cand_b"].statuses["R1"], MatchStatus.MET)  # 僅 Golang 且只在內文（OR 其一 + 詞面回退）
        self.assertEqual(evals["cand_b"].statuses["R3"], MatchStatus.MET)  # Kubernetes (EKS) 詞面
        self.assertEqual(evals["cand_a"].statuses["R2"], MatchStatus.MET)  # PostgreSQL 12 只在內文
        self.assertEqual(evals["cand_b"].statuses["R2"], MatchStatus.MET)  # postgres 14 → 別名反查
        self.assertEqual(evals["cand_d"].statuses["R1"], MatchStatus.UNMET)  # 全文零命中 → UNMET 非 UNKNOWN

    def test_designed_bottleneck_should_have_positive_delta(self):
        rep = self.state.relaxation
        self.assertEqual(rep.baseline_qualified, 2)
        self.assertEqual(rep.bottleneck_requirement_ids, ("R3",))
        self.assertEqual({i.requirement_id: i.delta for i in rep.items}, {"R1": 0, "R2": 0, "R3": 1})
        self.assertEqual(rep.strictest_requirement_ids, ())

    def test_lexical_met_should_carry_verified_evidence_in_shortlist(self):
        entry_b = self.state.find_shortlist_entry("cand_b")
        lexical = [e for e in entry_b.evidence if e.requirement_id == "R1"]
        self.assertEqual(len(lexical), 1)
        self.assertTrue(lexical[0].verified)
        self.assertIn("Golang", lexical[0].quote)
        self.assertEqual(lexical[0].field, "skill:golang")
        self.assertIn("Golang", self.turn.final_reply)  # 證據顯示於名單
        self.assertNotIn(REMOVED, self.turn.final_reply)

    def test_structured_hit_should_not_add_lexical_evidence_duplicate(self):
        entry_a = self.state.find_shortlist_entry("cand_a")
        r1 = [e for e in entry_a.evidence if e.requirement_id == "R1"]
        self.assertEqual([e.field for e in r1], ["skill:python3"])  # 僅抽取期證據，掛回條件編號

    def test_no_warning_about_removed_quotes_from_templates(self):
        self.assertFalse([w for w in self.turn.warnings if "引文未通過" in w])


class TestStrictestDiagnosisReply(unittest.TestCase):
    """AC-37：每人皆缺 ≥2 項必要條件時，回覆數字與 relaxation 一致且模板註記保留"""

    def setUp(self):
        resumes = {
            "cand_a": {"name": "王小明", "score": 0.9, "skills": [], "text": "# 王小明\n使用 Python 開發服務"},
            "cand_b": {"name": "李小華", "score": 0.8, "skills": [], "text": "# 李小華\n專長 Python 資料處理"},
            "cand_c": {"name": "陳大文", "score": 0.7, "skills": [], "text": "# 陳大文\n維運 PostgreSQL 叢集"},
            "cand_d": {"name": "林美玲", "score": 0.6, "skills": [], "text": "# 林美玲\n負責專案管理"},
        }
        handlers = build_ac43(resumes=resumes, profiles={k: {} for k in resumes})
        self.state, self.turn = run_turn(handlers, ChatSessionState(session_id="sess_rev2_02"), JD_TEXT)

    def test_strictest_requirement_and_reply_numbers_should_match(self):
        rep = self.state.relaxation
        self.assertEqual(rep.baseline_qualified, 0)
        self.assertTrue(all(i.delta == 0 for i in rep.items))
        self.assertEqual({i.requirement_id: i.met_count for i in rep.items}, {"R1": 2, "R2": 1, "R3": 0})
        self.assertEqual(rep.strictest_requirement_ids, ("R3",))
        self.assertIn("通過率最低之條件為 R3 熟悉 Kubernetes（0/4 位符合），建議優先檢討", self.turn.final_reply)
        self.assertIn("| R3 熟悉 Kubernetes | 0 | 0 | 0 | 0 |", self.turn.final_reply)

    def test_template_note_with_unknown_label_should_survive_compose(self):
        self.assertIn("註：「履歷未提及」視為未滿足", self.turn.final_reply)  # AC-41
        self.assertNotIn(REMOVED, self.turn.final_reply)
        self.assertEqual([w for w in self.turn.warnings if "引文未通過" in w], [])


class TestComposeSectionScope(unittest.TestCase):
    """AC-41 / AC-42：僅 LLM 段落驗證引文；模板段落零誤刪"""

    def setUp(self):
        self.narrator = FakeNarrator()
        self.handlers = build_handlers(narrator=self.narrator)
        self.state = ChatSessionState(session_id="sess_rev2_03")

    def test_llm_fabricated_quotes_should_be_removed_but_system_vocabulary_kept(self):
        self.narrator.match_text = "虛構「根本不存在的句子」與『另一段杜撰內容』；狀態為「履歷未提及」，職缺「資深後端工程師」。"
        state, turn = run_turn(self.handlers, self.state, JD_TEXT)
        reply = turn.final_reply
        self.assertNotIn("根本不存在的句子", reply)
        self.assertNotIn("另一段杜撰內容", reply)
        self.assertEqual(reply.count(REMOVED), 2)
        self.assertIn("狀態為「履歷未提及」", reply)
        self.assertIn("職缺「資深後端工程師」", reply)
        self.assertTrue(any("2 段引文未通過原文驗證" in w for w in turn.warnings))

    def test_verified_evidence_quote_in_llm_text_should_be_kept(self):
        state, turn = run_turn(self.handlers, self.state, JD_TEXT)  # 預設敘述引述「帶領 6 人後端團隊」(已驗證證據)
        self.assertIn("符合「帶領 6 人後端團隊」", turn.final_reply)
        self.assertNotIn(REMOVED, turn.final_reply)

    def test_template_general_with_title_should_not_be_stripped(self):
        state, _ = run_turn(self.handlers, self.state, JD_TEXT)
        self.narrator.raise_on = {"general"}
        state2, turn2 = run_turn(self.handlers, state, "目前職缺條件是什麼")
        self.assertIn("目前職缺「資深後端工程師」之條件如下", turn2.final_reply)
        self.assertNotIn(REMOVED, turn2.final_reply)

    def test_template_interview_questions_should_keep_label_and_status_quotes(self):
        state, _ = run_turn(self.handlers, self.state, JD_TEXT)
        self.narrator.raise_on = {"interview"}
        state2, turn2 = run_turn(self.handlers, state, "請針對第 2 位出 2 題面試題")
        reply = turn2.final_reply
        self.assertIn("請具體說明您在「具帶領團隊經驗」方面的實際經驗", reply)
        self.assertIn("該條件目前判定為「履歷未提及」", reply)
        self.assertNotIn(REMOVED, reply)
        self.assertEqual([w for w in turn2.warnings if "引文未通過" in w], [])

    def test_llm_interview_questions_fabricated_quote_should_be_removed(self):
        state, _ = run_turn(self.handlers, self.state, JD_TEXT)
        self.narrator.question_batches = [[InterviewQuestion(1, "請說明您引用的「杜撰詞彙」經驗", "R3", "驗證")]]
        state2, turn2 = run_turn(self.handlers, state, "請針對第 2 位出 1 題面試題")
        self.assertNotIn("杜撰詞彙", turn2.final_reply)
        self.assertIn(REMOVED, turn2.final_reply)
        self.assertIn("（對應：R3 具帶領團隊經驗）", turn2.final_reply)  # 系統產出部分完整保留
        self.assertTrue(any("引文未通過" in w for w in turn2.warnings))

    def test_followup_quotes_lines_are_template_while_answer_text_is_validated(self):
        state, _ = run_turn(self.handlers, self.state, JD_TEXT)
        self.narrator.followup_result = FollowupNarration(
            AnswerStatus.SUPPORTED, "有帶人：「帶領 3 人小組」；另稱「虛構的管理經歷」", ("帶領 3 人小組",))
        state2, turn2 = run_turn(self.handlers, state, "第 3 位有沒有帶過人？")
        reply = turn2.final_reply
        self.assertIn("有帶人：「帶領 3 人小組」", reply)
        self.assertNotIn("虛構的管理經歷", reply)
        self.assertIn("- 引用：「帶領 3 人小組」", reply)

    def test_template_followup_text_is_not_validated(self):
        state, _ = run_turn(self.handlers, self.state, JD_TEXT)
        self.narrator.raise_on = {"followup"}
        state2, turn2 = run_turn(self.handlers, state, "第 2 位有沒有帶過人？")
        self.assertIn("履歷未提及是否有帶人經驗", turn2.final_reply)
        self.assertNotIn(REMOVED, turn2.final_reply)

    def test_duplicate_blocks_are_deduplicated_with_their_continuations(self):
        turn = self.handlers.new_turn("x", "t")
        turn.add_template("A 區塊")
        turn.add_template("續一", join="\n")
        turn.add_template("A 區塊")
        turn.add_template("續一", join="\n")
        turn.add_template("B 區塊")
        _, turn = turn, self.handlers.compose(ChatSessionState(session_id="sess_rev2_04"), turn)
        self.assertEqual(_.final_reply, "A 區塊\n續一\n\n---\n\nB 區塊")

    def test_repeated_continuation_text_within_one_block_is_preserved(self):
        turn = self.handlers.new_turn("x", "t")
        turn.add_template("標題")
        turn.add_template("項目", join="\n")
        turn.add_template("項目", join="\n")
        self.handlers.compose(ChatSessionState(session_id="sess_rev2_05"), turn)
        self.assertEqual(turn.final_reply, "標題\n項目\n項目")

    def test_empty_sections_fall_back_to_default_message(self):
        turn = self.handlers.new_turn("x", "t")
        turn.sections.append(ReplySection(""))
        self.handlers.compose(ChatSessionState(session_id="sess_rev2_06"), turn)
        self.assertIn("目前無法處理此請求", turn.final_reply)

    def test_section_helpers(self):
        turn = self.handlers.new_turn("x", "t")
        turn.add_template("t1")
        turn.add_llm("l1", join="\n")
        self.assertEqual(turn.sections, [ReplySection("t1", False, None), ReplySection("l1", True, "\n")])
        self.assertTrue(turn.has_text("t1"))
        self.assertFalse(turn.has_text("nope"))


class TestTruncationDegradation(unittest.TestCase):
    """AC-40：敘述被截斷 → 模板 + 警告，回覆不含截斷文字"""

    def setUp(self):
        self.narrator = FakeNarrator()
        self.narrator.raise_exc = LlmOutputTruncatedError("truncated [recruit_narrate]")
        self.handlers = build_handlers(narrator=self.narrator)

    def test_truncated_match_narration_falls_back_to_template_with_warning(self):
        self.narrator.raise_on = {"match"}
        state, turn = run_turn(self.handlers, ChatSessionState(session_id="sess_rev2_07"), JD_TEXT)
        self.assertTrue(turn.degraded)
        self.assertIn("敘述輸出超出長度上限，已改用系統摘要", turn.warnings)
        self.assertIn("### 推薦理由\n- 候選人 #1（王小明）：符合", turn.final_reply)
        self.assertEqual(len(self.narrator.match_facts), 1)  # 不重試

    def test_truncated_general_answer_falls_back_to_template(self):
        state, _ = run_turn(self.handlers, ChatSessionState(session_id="sess_rev2_08"), JD_TEXT)
        self.narrator.raise_on = {"general"}
        _, turn = run_turn(self.handlers, state, "目前職缺條件是什麼")
        self.assertIn("目前職缺「資深後端工程師」之條件如下", turn.final_reply)
        self.assertIn("敘述輸出超出長度上限，已改用系統摘要", turn.warnings)
        self.assertEqual(len(self.narrator.general_facts), 1)

    def test_truncated_followup_falls_back_to_template(self):
        state, _ = run_turn(self.handlers, ChatSessionState(session_id="sess_rev2_09"), JD_TEXT)
        self.narrator.raise_on = {"followup"}
        _, turn = run_turn(self.handlers, state, "第 1 位有沒有帶過人？")
        self.assertIn("依履歷證據，候選人 #1（王小明）具備帶領團隊經驗", turn.final_reply)
        self.assertIn("敘述輸出超出長度上限，已改用系統摘要", turn.warnings)


class TestMatchTextsPreparation(unittest.TestCase):
    def test_match_text_should_not_be_truncated_but_llm_text_is(self):
        long_body = "技能 Python。" * 100
        resumes = {"cand_a": {"name": "王小明", "score": 0.9, "skills": [],
                              "text": "# 王小明\n- Email：sample_a@example.com\n" + long_body + "\n最後提及 Rust 專案"}}
        settings = make_settings(profile_max_resume_chars=200)
        handlers = build_handlers(settings=settings, search=FakeSearch(resumes),
                                  profile_extractor=SpecProfileExtractor({"cand_a": {}}),
                                  jd_extractor=FakeJdExtractor(AC43_JD))
        service = handlers._profiles
        pool = handlers._tools.retrieve_candidate_pool("q", 10, 5, 0.0)
        batch = service.get_profiles(pool, TurnBudget(5))
        self.assertGreater(len(batch.match_texts["cand_a"]), 200)
        self.assertEqual(len(batch.llm_texts["cand_a"]), 200)
        self.assertIn("最後提及 Rust 專案", batch.match_texts["cand_a"])
        self.assertNotIn("sample_a@example.com", batch.match_texts["cand_a"])  # 聯絡方式仍遮蔽
        self.assertTrue(batch.match_texts["cand_a"].startswith(batch.llm_texts["cand_a"]))

    def test_match_text_from_cache_hit_path_is_also_filled(self):
        handlers = build_ac43()
        pool = handlers._tools.retrieve_candidate_pool("q", 10, 5, 0.0)
        service = handlers._profiles
        service.get_profiles(pool, TurnBudget(10))
        second = service.get_profiles(pool, TurnBudget(10))
        self.assertGreater(second.cache_hits, 0)
        self.assertEqual(second.cache_misses, 0)
        self.assertTrue(all(second.match_texts[c.candidate_id] for c in pool))

    def test_protected_lines_are_redacted_in_match_text(self):
        resumes = {"cand_a": {"name": "王小明", "score": 0.9, "skills": [], "text": "# 王小明\n- 性別：男\n使用 Python"}}
        handlers = build_handlers(search=FakeSearch(resumes), profile_extractor=SpecProfileExtractor({"cand_a": {}}))
        pool = handlers._tools.retrieve_candidate_pool("q", 10, 5, 0.0)
        batch = handlers._profiles.get_profiles(pool, TurnBudget(5))
        self.assertNotIn("性別", batch.match_texts["cand_a"])
        self.assertIn("使用 Python", batch.match_texts["cand_a"])

    def test_empty_resume_text_yields_unknown_not_unmet(self):
        resumes = {"cand_a": {"name": "王小明", "score": 0.9, "skills": [], "text": ""}}
        handlers = build_ac43(resumes=resumes, profiles={"cand_a": {}})
        # FakeSearch 無切片內容時 load_resume_text 回傳空字串 → 規則 6 → UNKNOWN
        state, _ = run_turn(handlers, ChatSessionState(session_id="sess_rev2_10"), JD_TEXT)
        self.assertEqual(state.pool_evaluations[0].statuses["R1"], MatchStatus.UNKNOWN)


class TestSettingsInjection(unittest.TestCase):
    def test_exempt_and_min_chars_settings_reach_matcher(self):
        jd = replace(AC43_JD, must=(skill("x1", "Web", "web"),))
        resumes = {"cand_a": {"name": "王小明", "score": 0.9, "skills": [], "text": "# 王小明\n開發 web3 應用"}}
        profiles = {"cand_a": {"web3": "web3 應用"}}
        with_exempt = build_handlers(settings=make_settings(), search=FakeSearch(resumes),
                                     profile_extractor=SpecProfileExtractor(profiles), jd_extractor=FakeJdExtractor(jd))
        state, _ = run_turn(with_exempt, ChatSessionState(session_id="sess_rev2_11"), JD_TEXT)
        self.assertEqual(state.pool_evaluations[0].statuses["R1"], MatchStatus.UNMET)  # web3 受 exempt 保護，不併為 web
        no_exempt = build_handlers(settings=make_settings(skill_version_strip_exempt=()), search=FakeSearch(resumes),
                                   profile_extractor=SpecProfileExtractor(profiles), jd_extractor=FakeJdExtractor(jd))
        state2, _ = run_turn(no_exempt, ChatSessionState(session_id="sess_rev2_12"), JD_TEXT)
        self.assertEqual(state2.pool_evaluations[0].statuses["R1"], MatchStatus.MET)


if __name__ == "__main__":
    unittest.main()
