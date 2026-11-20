"""
缺陷 0029 回歸測試：Web 儀表板 CORS 不得對任意來源放行（只允許同源）

儀表板前端一律以相對路徑同源呼叫 API，不需任何跨來源許可標頭。
修正前 FastAPI 引擎以 allow_origins=["*"] + allow_credentials=True 將任意 Origin 原樣回寫，
內建引擎則對所有 JSON 回應寫死 Access-Control-Allow-Origin: *，
使本機使用者瀏覽之任意網頁可跨站讀取履歷全文、檢索結果與招募助手對話。
"""
import io
import unittest
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from src.application.dto import DashboardResultDTO
from src.domain.models import DashboardSummary
from src.interfaces.web.fastapi_server import create_app
from src.interfaces.web.server import make_dashboard_handler

EVIL_ORIGIN = "https://evil.example"
ACAO = "access-control-allow-origin"
ACAC = "access-control-allow-credentials"


def build_dashboard_use_case() -> MagicMock:
    use_case = MagicMock()
    use_case.execute.return_value = DashboardResultDTO(
        summary=DashboardSummary(
            total_files=1, success_count=1, quarantined_count=0, error_count=0,
            success_rate=100.0, avg_score=95.0, avg_judge_score=90.0,
        ),
        audit_records=[], total_audit_records=0, recent_logs=[], total_log_records=0,
    )
    return use_case


class TestFastApiCorsSameOrigin(unittest.TestCase):
    def setUp(self):
        self.chat = MagicMock()
        self.client = TestClient(create_app(build_dashboard_use_case(), None, self.chat))

    def test_cross_origin_get_should_not_be_allowed(self):
        # Arrange / Act
        res = self.client.get("/api/stats", headers={"Origin": EVIL_ORIGIN})

        # Assert：瀏覽器端因缺少 ACAO 而拒絕將回應交給外站腳本
        self.assertNotIn(ACAO, res.headers)
        self.assertNotIn(ACAC, res.headers)

    def test_cross_origin_get_with_cookie_should_not_echo_origin(self):
        res = self.client.get("/api/stats", headers={"Origin": EVIL_ORIGIN, "Cookie": "sid=abc"})

        self.assertNotIn(ACAO, res.headers)
        self.assertNotIn(ACAC, res.headers)

    def test_cross_origin_preflight_for_chat_should_not_be_allowed(self):
        res = self.client.options("/api/chat", headers={
            "Origin": EVIL_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })

        self.assertNotIn(ACAO, res.headers)
        self.assertNotIn("access-control-allow-methods", res.headers)
        self.chat.execute.assert_not_called()

    def test_same_origin_request_should_still_work(self):
        # 同源請求不帶 Origin 標頭，行為不得改變
        res = self.client.get("/api/stats")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["total_files"], 1)


class TestBuiltinEngineCorsSameOrigin(unittest.TestCase):
    def _make_handler(self):
        handler_cls = make_dashboard_handler(build_dashboard_use_case(), None)
        handler = handler_cls.__new__(handler_cls)
        handler.wfile = io.BytesIO()
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        return handler

    def test_json_response_should_not_send_acao_header(self):
        handler = self._make_handler()

        handler.send_json_response(200, {"ok": True})

        sent = [call.args[0].lower() for call in handler.send_header.call_args_list]
        self.assertNotIn(ACAO, sent)
        self.assertIn("content-type", sent)
        self.assertEqual(handler.wfile.getvalue(), b'{"ok": true}')

    def test_error_response_should_not_send_acao_header(self):
        handler = self._make_handler()

        handler.send_error_response(404, "not found")

        sent = [call.args[0].lower() for call in handler.send_header.call_args_list]
        self.assertNotIn(ACAO, sent)
        handler.send_response.assert_called_with(404)


if __name__ == "__main__":
    unittest.main()
