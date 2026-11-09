"""
RecruitmentChatUseCase 白箱單元測試：輸入驗證 400/413、session_id 產生、輪數上限 422、熔斷 429、trace_id 傳遞、日誌零原文。
"""
import unittest
from unittest.mock import MagicMock

from src.application.dto import ChatTurnCommand
from src.application.recruitment_chat_use_case import RecruitmentChatUseCase, validate_session_id
from src.domain.exceptions import LlmQuotaExhaustedError, RecruitmentInputError, SessionTurnLimitError
from src.domain.recruitment import ChatIntent, ChatSessionState, ChatTurnOutcome, TurnUsage
from src.domain.recruitment_services import CircuitBreaker
from tests.unit.recruitment_fakes import make_settings


def outcome(session_id="sess_abcdefgh"):
    return ChatTurnOutcome(session_id=session_id, intents=[ChatIntent.GENERAL_QA], reply_markdown="ok",
                           shortlist=(), relaxation=None, followup=None, interview_questions=[], warnings=[],
                           degraded=False, usage=TurnUsage(llm_calls=1))


class TestRecruitmentChatUseCase(unittest.TestCase):
    def setUp(self):
        self.orchestrator = MagicMock()
        self.orchestrator.get_state.return_value = None
        self.orchestrator.run_turn.return_value = outcome()
        self.ids = iter(["generatedsession01", "trace0001"])
        self.use_case = RecruitmentChatUseCase(self.orchestrator, make_settings(max_message_chars=50,
                                                                                session_max_turns=2),
                                               id_factory=lambda: next(self.ids))

    def test_execute_without_session_should_generate_id_and_pass_trace(self):
        dto = self.use_case.execute(ChatTurnCommand(message="  你好  "))
        self.assertEqual(dto.session_id, "generatedsession01")
        self.assertEqual(dto.trace_id, "trace0001")
        self.orchestrator.run_turn.assert_called_once_with("generatedsession01", "你好", "trace0001")
        self.assertEqual(dto.intents, ["GENERAL_QA"])
        self.assertEqual(dto.usage.llm_calls, 1)

    def test_empty_message_should_raise_invalid_input(self):
        with self.assertRaises(RecruitmentInputError) as ctx:
            self.use_case.execute(ChatTurnCommand(message="   "))
        self.assertEqual(ctx.exception.error_code, "INVALID_INPUT")
        self.orchestrator.run_turn.assert_not_called()

    def test_too_long_message_should_raise_message_too_long(self):
        with self.assertRaises(RecruitmentInputError) as ctx:
            self.use_case.execute(ChatTurnCommand(message="字" * 51))
        self.assertEqual(ctx.exception.error_code, "MESSAGE_TOO_LONG")

    def test_illegal_session_id_should_raise_invalid_input(self):
        for sid in ("../x", "short", "a" * 65, "bad id!!"):
            with self.subTest(sid=sid), self.assertRaises(RecruitmentInputError):
                self.use_case.execute(ChatTurnCommand(message="hi", session_id=sid))
        self.assertEqual(validate_session_id("valid_session-01"), "valid_session-01")

    def test_turn_limit_should_raise_session_turn_limit(self):
        self.orchestrator.get_state.return_value = ChatSessionState(session_id="sess_abcdefgh", turn_count=2)
        with self.assertRaises(SessionTurnLimitError):
            self.use_case.execute(ChatTurnCommand(message="hi", session_id="sess_abcdefgh"))
        self.orchestrator.run_turn.assert_not_called()

    def test_open_circuit_should_reject_without_calling_orchestrator(self):
        breaker = CircuitBreaker(60, clock=lambda: 0.0)
        breaker.record_quota_exhausted()
        use_case = RecruitmentChatUseCase(self.orchestrator, make_settings(), circuit_breaker=breaker)
        with self.assertRaises(LlmQuotaExhaustedError) as ctx:
            use_case.execute(ChatTurnCommand(message="hi"))
        self.assertEqual(ctx.exception.retry_after_seconds, 60)
        self.orchestrator.run_turn.assert_not_called()

    def test_log_should_not_contain_message_text(self):
        with self.assertLogs("src.application.recruitment_chat_use_case", level="INFO") as logs:
            self.use_case.execute(ChatTurnCommand(message="秘密職缺內容王小明"))
        joined = "\n".join(logs.output)
        self.assertIn("trace0001", joined)  # AC-33
        self.assertNotIn("秘密職缺內容", joined)  # AC-12
        self.assertNotIn("generatedsession01", joined)

    def test_get_and_reset_session_should_validate_id(self):
        self.use_case.reset_session("sess_abcdefgh")
        self.orchestrator.reset.assert_called_once_with("sess_abcdefgh")
        with self.assertRaises(RecruitmentInputError):
            self.use_case.get_session("../etc")

    def test_close_should_invoke_hook(self):
        hook = MagicMock()
        RecruitmentChatUseCase(self.orchestrator, make_settings(), on_close=hook).close()
        hook.assert_called_once()


if __name__ == "__main__":
    unittest.main()
