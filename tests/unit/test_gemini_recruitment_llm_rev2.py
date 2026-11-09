"""
GeminiRecruitmentLlm Rev2 白箱單元測試 (Mock chat_model，零網路)：
RV2-D1 JD OR 技能展開與抽取器版本拆分、RV2-D2 敘述專用輸出上限 / thinking_budget / include_raw 截斷偵測。
"""
import importlib.util
import unittest
from unittest.mock import MagicMock, patch

from src.domain.exceptions import LlmOutputTruncatedError, RecruitmentLlmError
from src.domain.recruitment import FollowupFacts, GeneralQaFacts, InterviewFacts, MatchNarrationFacts, WeaknessFact
from src.domain.recruitment_services import CircuitBreaker

HAS_LC = importlib.util.find_spec("langchain_core") is not None and importlib.util.find_spec("pydantic") is not None

if HAS_LC:
    from langchain_core.messages import AIMessage

    from src.infrastructure.llm.gemini_recruitment_llm import (
        FollowupSchema,
        GeminiJdExtractorAdapter,
        GeminiProfileExtractorAdapter,
        GeminiRecruitmentLlm,
        IntentSchema,
        JdSchema,
        NarrationSchema,
        QuestionsSchema,
        ProfileSchema,
    )


def make_loader(overrides=None):
    overrides = overrides or {}

    def loader(name):
        base = f"[{name}] {{{{message}}}}{{{{job_description}}}}{{{{resume_content}}}}{{{{facts_json}}}}"
        return overrides.get(name, base)

    return loader


def raw_message(finish_reason=None, output_tokens=100, reasoning=60):
    meta = {} if finish_reason is None else {"finish_reason": finish_reason}
    return AIMessage(content="", response_metadata=meta,
                     usage_metadata={"input_tokens": 10, "output_tokens": output_tokens, "total_tokens": 110,
                                     "output_token_details": {"reasoning": reasoning}})


def structured(parsed, finish_reason="STOP", parsing_error=None):
    return {"raw": raw_message(finish_reason), "parsed": parsed, "parsing_error": parsing_error}


@unittest.skipUnless(HAS_LC, "langchain-core 未安裝")
class TestJdOrSkillMapping(unittest.TestCase):
    def setUp(self):
        self.chat = MagicMock()
        self.runnable = MagicMock()
        self.chat.with_structured_output.return_value = self.runnable
        self.llm = GeminiRecruitmentLlm(
            api_key="unused", model_name="m", temperature=0.2, max_output_tokens=256, timeout_seconds=5,
            circuit_breaker=CircuitBreaker(60), max_retries=1, retry_delay=0.0, chat_model=self.chat,
            prompt_loader=make_loader(), skill_aliases={"CI/CD": "cicd"})

    def _extract(self, must):
        self.runnable.invoke.return_value = JdSchema.model_validate({"title": "t", "must": must})
        return GeminiJdExtractorAdapter(self.llm).extract("JD", 12).must

    def test_skills_array_should_map_to_single_or_requirement(self):
        reqs = self._extract([{"category": "SKILL", "label": "精通 Python 或 Go", "skills": ["Python", "Go"]}])
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0].skills, ("python", "go"))
        self.assertEqual(reqs[0].skill, "python")  # 相容欄位 = skills[0]

    def test_slash_string_in_skill_should_expand(self):
        reqs = self._extract([{"category": "SKILL", "label": "資料庫", "skill": "PostgreSQL/MySQL"}])
        self.assertEqual(reqs[0].skills, ("postgresql", "mysql"))

    def test_merge_skills_and_skill_without_duplicates(self):
        reqs = self._extract([{"category": "SKILL", "label": "x", "skills": ["python"], "skill": "Python or Go"}])
        self.assertEqual(reqs[0].skills, ("python", "go"))

    def test_alias_key_should_not_be_split(self):
        reqs = self._extract([{"category": "SKILL", "label": "x", "skill": "CI/CD"}])
        self.assertEqual(reqs[0].skills, ("ci/cd",))

    def test_non_skill_requirement_without_skill_should_have_empty_skills(self):
        reqs = self._extract([{"category": "YEARS", "label": "5 年", "min_value": 5}])
        self.assertEqual(reqs[0].skills, ())
        self.assertIsNone(reqs[0].skill)


@unittest.skipUnless(HAS_LC, "langchain-core 未安裝")
class TestExtractorVersionSplit(unittest.TestCase):
    def _llm(self, overrides=None, model="m"):
        return GeminiRecruitmentLlm(
            api_key="unused", model_name=model, temperature=0.2, max_output_tokens=256, timeout_seconds=5,
            circuit_breaker=CircuitBreaker(60), max_retries=1, retry_delay=0.0, chat_model=MagicMock(),
            prompt_loader=make_loader(overrides))

    def test_jd_prompt_change_should_only_change_jd_version(self):
        base, changed = self._llm(), self._llm({"recruit_jd_extract.md": "JD prompt v2"})
        self.assertNotEqual(base.jd_extractor_version, changed.jd_extractor_version)
        self.assertEqual(base.profile_extractor_version, changed.profile_extractor_version)  # AC-38

    def test_profile_prompt_change_should_only_change_profile_version(self):
        base, changed = self._llm(), self._llm({"recruit_profile_extract.md": "profile prompt v2"})
        self.assertEqual(base.jd_extractor_version, changed.jd_extractor_version)
        self.assertNotEqual(base.profile_extractor_version, changed.profile_extractor_version)

    def test_schema_revision_should_participate_in_jd_version(self):
        import src.infrastructure.llm.gemini_recruitment_llm as mod

        before = self._llm().jd_extractor_version
        with patch.object(mod, "JD_SCHEMA_REVISION", "999"):
            after = self._llm().jd_extractor_version
        self.assertNotEqual(before, after)

    def test_model_change_should_change_both_and_adapters_expose_own_version(self):
        a, b = self._llm(), self._llm(model="m2")
        self.assertNotEqual(a.jd_extractor_version, b.jd_extractor_version)
        self.assertNotEqual(a.profile_extractor_version, b.profile_extractor_version)
        self.assertEqual(GeminiJdExtractorAdapter(a).extractor_version, a.jd_extractor_version)
        self.assertEqual(GeminiProfileExtractorAdapter(a).extractor_version, a.profile_extractor_version)
        self.assertEqual(len(a.jd_extractor_version), 12)
        self.assertEqual(a.extractor_version, a.jd_extractor_version)

    def test_extracted_profile_should_carry_profile_version(self):
        llm = self._llm()
        llm._chat.with_structured_output.return_value.invoke.return_value = ProfileSchema()
        prof = GeminiProfileExtractorAdapter(llm).extract("c1", "text", "hash")
        self.assertEqual(prof.extractor_version, llm.profile_extractor_version)


@unittest.skipUnless(HAS_LC, "langchain-core 未安裝")
class TestNarrativeConfiguration(unittest.TestCase):
    def test_narrative_model_should_copy_with_dedicated_limit_and_be_used_only_for_narration(self):
        main, narrative, profile = MagicMock(), MagicMock(), MagicMock()
        main.model_copy.side_effect = lambda update: {1024: profile, 8192: narrative}[update["max_output_tokens"]]
        intent_runnable, narr_runnable, profile_runnable = MagicMock(), MagicMock(), MagicMock()
        main.with_structured_output.return_value = intent_runnable
        narrative.with_structured_output.return_value = narr_runnable
        profile.with_structured_output.return_value = profile_runnable
        intent_runnable.invoke.return_value = IntentSchema(intents=["GENERAL_QA"])
        profile_runnable.invoke.return_value = ProfileSchema()
        narr_runnable.invoke.return_value = structured(NarrationSchema(text="完整敘述"))
        llm = GeminiRecruitmentLlm(
            api_key="unused", model_name="m", temperature=0.2, max_output_tokens=2048, timeout_seconds=5,
            circuit_breaker=CircuitBreaker(60), max_retries=1, retry_delay=0.0, chat_model=main,
            prompt_loader=make_loader(), profile_max_output_tokens=1024, narrative_max_output_tokens=8192)

        llm.classify("x", False)
        llm.extract_profile("c1", "t", "h")
        text = llm.answer_general(GeneralQaFacts("q", None, (), (), (), ()))

        self.assertEqual(text, "完整敘述")
        intent_runnable.invoke.assert_called_once()
        profile_runnable.invoke.assert_called_once()
        narr_runnable.invoke.assert_called_once()
        main.with_structured_output.assert_called_once()  # 僅意圖分類使用主模型
        self.assertEqual({c.kwargs["update"]["max_output_tokens"] for c in main.model_copy.call_args_list},
                         {1024, 8192})  # AC-39 各自上限

    def test_thinking_budget_should_be_passed_when_supported(self):
        with patch("langchain_google_genai.ChatGoogleGenerativeAI") as cls:
            cls.model_fields = {"thinking_budget": object()}
            self._build(thinking_budget=0)
            self.assertEqual(cls.call_args.kwargs["thinking_budget"], 0)  # 0 = 關閉 thinking 須傳入
            self.assertEqual(cls.call_args.kwargs["max_output_tokens"], 256)

    def test_thinking_budget_unset_should_not_be_passed(self):
        with patch("langchain_google_genai.ChatGoogleGenerativeAI") as cls:
            cls.model_fields = {"thinking_budget": object()}
            self._build(thinking_budget=None)
            self.assertNotIn("thinking_budget", cls.call_args.kwargs)

    def test_thinking_budget_unsupported_should_be_ignored_with_info_log(self):
        with patch("langchain_google_genai.ChatGoogleGenerativeAI") as cls:
            cls.model_fields = {}
            with self.assertLogs("src.infrastructure.llm.gemini_recruitment_llm", level="INFO") as logs:
                self._build(thinking_budget=512)
            self.assertNotIn("thinking_budget", cls.call_args.kwargs)
            self.assertTrue(any("thinking_budget" in line for line in logs.output))

    @staticmethod
    def _build(**kwargs):
        return GeminiRecruitmentLlm(
            api_key="unused", model_name="m", temperature=0.2, max_output_tokens=256, timeout_seconds=5,
            circuit_breaker=CircuitBreaker(60), max_retries=1, retry_delay=0.0, prompt_loader=make_loader(), **kwargs)


@unittest.skipUnless(HAS_LC, "langchain-core 未安裝")
class TestTruncationDetection(unittest.TestCase):
    def setUp(self):
        self.chat = MagicMock()
        self.runnable = MagicMock()
        self.chat.with_structured_output.return_value = self.runnable
        self.llm = GeminiRecruitmentLlm(
            api_key="unused", model_name="m", temperature=0.2, max_output_tokens=256, timeout_seconds=5,
            circuit_breaker=CircuitBreaker(60), max_retries=2, retry_delay=0.0, chat_model=self.chat,
            prompt_loader=make_loader())
        self.match_facts = MatchNarrationFacts("t", 3, 10, (), (), (), None)
        self.general_facts = GeneralQaFacts("q", None, (), (), (), ())

    def test_narration_should_request_include_raw(self):
        self.runnable.invoke.return_value = structured(NarrationSchema(text="完整"))
        self.llm.narrate_match(self.match_facts)
        self.chat.with_structured_output.assert_called_once_with(NarrationSchema, include_raw=True)

    def test_non_narrative_operations_should_not_request_include_raw(self):
        self.runnable.invoke.return_value = IntentSchema(intents=["GENERAL_QA"])
        self.llm.classify("x", False)
        self.chat.with_structured_output.assert_called_once_with(IntentSchema)

    def test_max_tokens_finish_reason_should_raise_truncated_without_retry(self):
        self.runnable.invoke.return_value = structured(NarrationSchema(text="Message Queue ("), "MAX_TOKENS")
        with self.assertRaises(LlmOutputTruncatedError):
            self.llm.narrate_match(self.match_facts)
        self.assertEqual(self.runnable.invoke.call_count, 1)  # 不重試，避免二次燃燒 Token

    def test_truncated_error_is_a_recruitment_llm_error(self):
        self.assertTrue(issubclass(LlmOutputTruncatedError, RecruitmentLlmError))

    def test_parsing_error_should_raise_truncated_with_cause(self):
        cause = ValueError("invalid json")
        self.runnable.invoke.return_value = structured(None, "STOP", parsing_error=cause)
        with self.assertRaises(LlmOutputTruncatedError) as ctx:
            self.llm.answer_general(self.general_facts)
        self.assertIs(ctx.exception.__cause__, cause)

    def test_missing_finish_reason_should_be_treated_as_complete(self):
        self.runnable.invoke.return_value = {"raw": raw_message(None), "parsed": NarrationSchema(text="完整"),
                                             "parsing_error": None}
        self.assertEqual(self.llm.answer_general(self.general_facts), "完整")

    def test_unbalanced_brackets_should_raise_even_when_finish_reason_is_stop(self):
        self.runnable.invoke.return_value = structured(NarrationSchema(text="使用 Message Queue (Kafka"), "STOP")
        with self.assertRaises(LlmOutputTruncatedError):
            self.llm.narrate_match(self.match_facts)

    def test_followup_and_interview_unbalanced_should_raise(self):
        self.runnable.invoke.return_value = structured(FollowupSchema(answer_status="SUPPORTED", answer_text="有（"))
        with self.assertRaises(LlmOutputTruncatedError):
            self.llm.answer_followup(FollowupFacts("候選人 #1", "q", {}, (), (), (), (), "resume"))
        self.runnable.invoke.return_value = structured(QuestionsSchema.model_validate(
            {"questions": [{"question": "請說明「Kafka", "target_requirement_id": "R1"}]}))
        facts = InterviewFacts("候選人 #1", (WeaknessFact("R1", "x", "履歷未提及"),), (), "t")
        with self.assertRaises(LlmOutputTruncatedError):
            self.llm.generate_interview_questions(facts, 1)

    def test_raw_without_metadata_should_not_crash(self):
        self.runnable.invoke.return_value = {"raw": object(), "parsed": NarrationSchema(text="ok"),
                                             "parsing_error": None}
        self.assertEqual(self.llm.answer_general(self.general_facts), "ok")

    def test_log_should_contain_counts_but_not_text(self):
        secret = "這是不應出現在日誌的敘述內容"
        self.runnable.invoke.return_value = structured(NarrationSchema(text=secret), "STOP")
        with self.assertLogs("src.infrastructure.llm.gemini_recruitment_llm", level="INFO") as logs:
            self.llm.answer_general(self.general_facts)
        joined = "\n".join(logs.output)
        self.assertIn("finish_reason=STOP", joined)
        self.assertIn("output_tokens=100", joined)
        self.assertIn("thinking_tokens=60", joined)
        self.assertNotIn(secret, joined)

    def test_plain_schema_result_should_remain_supported(self):
        self.runnable.invoke.return_value = NarrationSchema(text="舊格式")
        self.assertEqual(self.llm.answer_general(self.general_facts), "舊格式")


if __name__ == "__main__":
    unittest.main()
