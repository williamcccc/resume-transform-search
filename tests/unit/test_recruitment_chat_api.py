"""
招募助手 Chat API 單元測試 (FastAPI TestClient + Mock Use Case)
200 結構、各錯誤碼映射、chat_use_case=None → 503、既有 /api/search 不受影響、內建引擎 501、build_chat_use_case 降級。
"""
import unittest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dto import ChatTurnResultDTO
from src.domain.exceptions import (
    ChatUnavailableError,
    LlmQuotaExhaustedError,
    RecruitmentInputError,
    SessionBusyError,
    SessionTurnLimitError,
    TurnTimeoutError,
)
from src.domain.recruitment import (
    AnswerStatus,
    ChatSessionState,
    FollowupAnswer,
    InterviewQuestion,
    RelaxationItem,
    RelaxationReport,
    RequirementEvidence,
    ShortlistEntry,
    TurnUsage,
)
from src.infrastructure.config import AppConfig
from src.interfaces.web.fastapi_server import create_app
from src.interfaces.web.server import build_chat_use_case

SID = "sess_api_000001"


def sample_dto():
    entry = ShortlistEntry(1, "cand_a", "王小明", True, 0.91, ("R1",), (), ("R2",),
                           (RequirementEvidence("R1", "skill:python", "Python 開發"),))
    rep = RelaxationReport(5, 1, 3, (RelaxationItem("R1", "Python", 2, 1, 0),), ("R1",))
    return ChatTurnResultDTO(
        session_id=SID, trace_id="trace01", intents=["JD_MATCH"], reply_markdown="<script>alert(1)</script>",
        shortlist=[entry], relaxation=rep,
        followup=FollowupAnswer(1, "cand_a", AnswerStatus.SUPPORTED, ("帶領 6 人",)),
        interview_questions=[InterviewQuestion(1, "Q", "R2", "r")], warnings=["w"], degraded=False,
        usage=TurnUsage(llm_calls=2, profile_cache_hits=1, profile_cache_misses=0, jd_cache_hit=True),
    )


class TestRecruitmentChatApi(unittest.TestCase):
    def setUp(self):
        self.dashboard = MagicMock()
        self.chat = MagicMock()
        self.client = TestClient(create_app(self.dashboard, None, self.chat))

    def test_post_chat_should_return_full_structure(self):
        self.chat.execute.return_value = sample_dto()
        res = self.client.post("/api/chat", json={"session_id": SID, "message": "JD..."})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["session_id"], SID)
        self.assertEqual(body["shortlist"][0]["evidence"][0]["quote"], "Python 開發")
        self.assertEqual(body["relaxation"]["bottleneck_requirement_ids"], ["R1"])
        self.assertEqual(body["followup"]["answer_status"], "SUPPORTED")
        self.assertEqual(body["usage"]["jd_cache_hit"], True)
        self.assertEqual(body["interview_questions"][0]["target_requirement_id"], "R2")
        cmd = self.chat.execute.call_args[0][0]
        self.assertEqual((cmd.message, cmd.session_id), ("JD...", SID))

    def test_exception_mapping_should_return_error_codes(self):
        cases = [
            (RecruitmentInputError("empty"), 400, "INVALID_INPUT"),
            (RecruitmentInputError("long", error_code="MESSAGE_TOO_LONG"), 413, "MESSAGE_TOO_LONG"),
            (SessionBusyError("busy"), 409, "SESSION_BUSY"),
            (SessionTurnLimitError("limit"), 422, "SESSION_TURN_LIMIT"),
            (LlmQuotaExhaustedError("quota", retry_after_seconds=42), 429, "LLM_QUOTA_EXHAUSTED"),
            (ChatUnavailableError("down"), 503, "CHAT_UNAVAILABLE"),
            (TurnTimeoutError("slow"), 504, "TURN_TIMEOUT"),
            (KeyError("secret internals"), 500, "INTERNAL_ERROR"),
        ]
        for exc, status, code in cases:
            with self.subTest(code=code):
                self.chat.execute.side_effect = exc
                res = self.client.post("/api/chat", json={"message": "hi"})
                self.assertEqual(res.status_code, status)
                body = res.json()
                self.assertEqual(body["error_code"], code)
                self.assertIn("trace_id", body)
                self.assertNotIn("Traceback", res.text)
                self.assertNotIn("secret internals", res.text)
        self.chat.execute.side_effect = LlmQuotaExhaustedError("quota", retry_after_seconds=42)
        res = self.client.post("/api/chat", json={"message": "hi"})
        self.assertEqual(res.json()["retry_after_seconds"], 42)
        self.assertEqual(res.headers["Retry-After"], "42")

    def test_get_and_delete_session(self):
        self.chat.get_session.return_value = ChatSessionState(session_id=SID, turn_count=3)
        res = self.client.get(f"/api/chat/{SID}")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["turn_count"], 3)
        self.chat.get_session.return_value = None
        self.assertEqual(self.client.get(f"/api/chat/{SID}").status_code, 404)
        self.chat.get_session.side_effect = RecruitmentInputError("bad")
        self.assertEqual(self.client.get("/api/chat/bad!id").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/chat/{SID}").status_code, 204)
        self.chat.reset_session.assert_called_once_with(SID)

    def test_chat_unavailable_should_return_503_and_keep_search_endpoint(self):
        client = TestClient(create_app(self.dashboard, None, None))
        for method, url in (("post", "/api/chat"), ("get", f"/api/chat/{SID}"), ("delete", f"/api/chat/{SID}")):
            with self.subTest(url=url):
                kwargs = {"json": {"message": "hi"}} if method == "post" else {}
                res = getattr(client, method)(url, **kwargs)
                self.assertEqual(res.status_code, 503)
                self.assertEqual(res.json()["error_code"], "CHAT_UNAVAILABLE")
        self.assertEqual(client.get("/api/search", params={"query": "python"}).status_code, 503)  # 既有行為
        search = MagicMock()
        search.execute_web_search.return_value = MagicMock(total_candidates=0, total_chunks=0, query_text="python",
                                                           candidates=[], raw_chunks=[])
        client = TestClient(create_app(self.dashboard, search, None))
        self.assertEqual(client.get("/api/search", params={"query": "python"}).status_code, 200)

    def test_app_shutdown_should_close_chat_resources(self):
        with TestClient(create_app(self.dashboard, None, self.chat)):
            pass
        self.chat.close.assert_called_once()

    def test_dashboard_html_should_contain_recruit_tab_with_safe_rendering(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        html = res.text
        self.assertIn("recruitTab", html)
        self.assertIn("sessionStorage", html)
        self.assertIn("textContent", html)
        chat_js = html[html.index("CHAT_SESSION_KEY"):html.index("// 初始化")]
        self.assertNotIn("innerHTML", chat_js)  # AC-28 杜絕 XSS


class TestBuildChatUseCase(unittest.TestCase):
    def _config(self, **overrides):
        cfg = AppConfig(gemini_api_key="unused-key", gemini_model="m", gemini_review=False)
        for k, v in overrides.items():
            setattr(cfg, k, v)
        return cfg

    def test_missing_prerequisites_should_degrade_to_none(self):
        uc, err = build_chat_use_case(self._config(gemini_api_key=""), MagicMock())
        self.assertIsNone(uc)
        self.assertIsInstance(err, ChatUnavailableError)
        uc, err = build_chat_use_case(self._config(), None)
        self.assertIsNone(uc)
        uc, err = build_chat_use_case(self._config(recruit_chat_enabled=False), MagicMock())
        self.assertIsNone(uc)

    def test_infrastructure_failure_should_degrade_to_none(self):
        uc, err = build_chat_use_case(self._config(chat_checkpointer_backend="unsupported"), MagicMock())
        self.assertIsNone(uc)
        self.assertIsNotNone(err)


class TestBuiltinEngineChat(unittest.TestCase):
    def test_builtin_handler_should_answer_501(self):
        import io
        from src.interfaces.web.server import make_dashboard_handler

        handler_cls = make_dashboard_handler(MagicMock(), None)
        for method in ("do_GET", "do_POST", "do_DELETE"):
            with self.subTest(method=method):
                handler = handler_cls.__new__(handler_cls)
                handler.path = "/api/chat"
                handler.wfile = io.BytesIO()
                handler.send_response = MagicMock()
                handler.send_header = MagicMock()
                handler.end_headers = MagicMock()
                getattr(handler, method)()
                handler.send_response.assert_called_with(501)


if __name__ == "__main__":
    unittest.main()
