"""
灰箱 QA 實測：招募助手 LangSmith 遮蔽式追蹤 (Spec-0020 §3.8 QA 矩陣 TC-1 ~ TC-10)

真實元件：LangGraph 編排器、RecruitmentNodeHandlers、CandidateProfileService（真實執行緒池）、
LangChain chat model 呼叫鏈（以 BaseChatModel 子類模擬 Gemini，產生真實 LLM run 與 usage_metadata）、
真實 langsmith Client（production 同組遮蔽參數，含 auto-batch 背景上傳）。
上傳端點以「攔截式 HTTP Session」取代：記錄 SDK 實際送出之 HTTP 位元組，不連任何外網。

所有姓名/訊息皆為記憶體動態建構之虛構樣本；嚴禁讀取 data/、resume/。
"""
import json
import logging
import os
import socket
import sys
import time
import unittest
from pathlib import Path
from typing import Any, List, Optional
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import requests  # noqa: E402
from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402

from src.infrastructure.config import AppConfig  # noqa: E402
from src.infrastructure.observability import langsmith_tracing as lt  # noqa: E402
from src.infrastructure.orchestration.checkpointer_factory import build_memory_checkpointer  # noqa: E402
from src.infrastructure.orchestration.langgraph_recruitment_graph import LangGraphRecruitmentOrchestrator  # noqa: E402
from tests.unit.recruitment_fakes import (  # noqa: E402
    JD_TEXT,
    RESUMES,
    FakeNarrator,
    FakeProfileExtractor,
    build_handlers,
)

FAKE_KEY = "lsv2_qa0020_fake_key_do_not_upload"
SESSION_ID = "qa0020-raw-session-id-7f3c"
MSG_MARKER = "qa0020-msg-marker@example.com"
OUTPUT_MARKER = "qa0020-llm-output-marker"
ERROR_MARKER = "qa0020-error-marker"
CANDIDATE_NAMES = [r["name"] for r in RESUMES.values()]
RUNTIME_ALLOWED_KEYS = {"library", "library_version", "platform", "runtime", "runtime_version",
                        "sdk", "sdk_version", "py_implementation", "langchain_version", "langchain_core_version"}
FORBIDDEN = [FAKE_KEY, SESSION_ID, MSG_MARKER, OUTPUT_MARKER, ERROR_MARKER] + CANDIDATE_NAMES


class FakeGeminiChatModel(BaseChatModel):
    """模擬 Gemini：回覆含標記文字並附 usage_metadata；fail 為真時拋出含個資標記之例外"""

    fail: bool = False

    @property
    def _llm_type(self) -> str:
        return "fake-gemini"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        if self.fail:
            raise ValueError(f"{ERROR_MARKER} {CANDIDATE_NAMES[0]} 履歷片段")
        msg = AIMessage(content=f"{OUTPUT_MARKER} {messages[-1].content[:40]}",
                        usage_metadata={"input_tokens": 120, "output_tokens": 30, "total_tokens": 150})
        return ChatResult(generations=[ChatGeneration(message=msg)])


def _llm_call(text: str, fail: bool = False) -> None:
    FakeGeminiChatModel(fail=fail).invoke([HumanMessage(content=text)])


class LcProfileExtractor(FakeProfileExtractor):
    """經 LangChain 呼叫鏈（在執行緒池內）送出含履歷原文之 prompt，再回傳確定性 Profile"""

    def __init__(self, fail_for=()):
        super().__init__()
        self._lc_fail_for = set(fail_for)

    def extract(self, candidate_id, resume_text, content_hash):
        _llm_call(f"<resume_content>{resume_text}</resume_content>", fail=candidate_id in self._lc_fail_for)
        return super().extract(candidate_id, resume_text, content_hash)


class LcNarrator(FakeNarrator):
    def narrate_match(self, facts):
        _llm_call(f"facts: {facts!r}")
        return super().narrate_match(facts)


class CapturingSession(requests.Session):
    """攔截 langsmith SDK 之所有 HTTP 請求，保存送出之原始位元組；回應 200 空 JSON"""

    def __init__(self):
        super().__init__()
        self.bodies: List[bytes] = []
        self.urls: List[str] = []

    def request(self, method, url, *args, **kwargs):  # noqa: D401
        data = kwargs.get("data")
        if data is None and kwargs.get("json") is not None:
            data = json.dumps(kwargs["json"]).encode("utf-8")
        if hasattr(data, "read"):
            data = data.read()
        if isinstance(data, str):
            data = data.encode("utf-8")
        if isinstance(data, (bytes, bytearray)):
            self.bodies.append(bytes(data))
        self.urls.append(url)
        resp = requests.Response()
        resp.status_code = 200
        resp._content = b"{}"
        resp.headers["Content-Type"] = "application/json"
        resp.url = url
        return resp


def _tracing_config(**overrides):
    with patch("dotenv.load_dotenv"), patch.dict(os.environ, {
        "RECRUIT_TRACING_ENABLED": "true", "LANGSMITH_API_KEY": FAKE_KEY,
        "LANGSMITH_ENDPOINT": "http://qa0020.invalid", "LANGSMITH_PROJECT": "qa0020",
        "RECRUIT_TRACING_SAMPLING_RATE": "1.0", "RECRUIT_TRACING_FLUSH_TIMEOUT_SECONDS": "3",
        "LANGSMITH_TRACING": "", "LANGCHAIN_TRACING_V2": "",
    }):
        cfg = AppConfig.load(override_api_key="x")
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def _build_tracing(session: Optional[requests.Session] = None, **cfg_overrides):
    """以 production 之 build_langsmith_tracing 組裝，僅將 HTTP Session 換成攔截式"""
    import langsmith

    real_client = langsmith.Client

    def client_with_session(*args, **kwargs):
        if session is not None:
            kwargs["session"] = session
        return real_client(*args, **kwargs)

    with patch("langsmith.Client", side_effect=client_with_session):
        return lt.build_langsmith_tracing(_tracing_config(**cfg_overrides))


class _RunCollector:
    """
    於 SDK 序列化層攔截已遮蔽之 run payload（langsmith.client 內之 serialize_run_dict 綁定名），
    供結構驗證（父子關係、metadata 鍵）；位元組層之個資檢查另由 CapturingSession 負責。
    """

    def __init__(self):
        import langsmith.client as ls_client

        self.runs: List[dict] = []
        orig = ls_client.serialize_run_dict
        collector = self

        def spy(operation=None, payload=None, **kwargs):
            op = operation if operation is not None else kwargs.get("operation")
            data = payload if payload is not None else kwargs.get("payload")
            collector.runs.append(json.loads(json.dumps(data, default=str)))
            return orig(op, data)

        self._patch = patch.object(ls_client, "serialize_run_dict", spy)

    def __enter__(self):
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()


class TestRecruitmentTracingE2E(unittest.TestCase):
    def _orchestrator(self, tracing, profile_extractor=None):
        handlers = build_handlers(profile_extractor=profile_extractor or LcProfileExtractor(), narrator=LcNarrator())
        bundle = build_memory_checkpointer(session_ttl_seconds=600, max_sessions=10)
        return LangGraphRecruitmentOrchestrator(handlers, bundle, 2, tracing=tracing)

    def _run_traced_turn(self, profile_extractor=None):
        session = CapturingSession()
        tracing = _build_tracing(session)
        self.assertIsNotNone(tracing)
        orch = self._orchestrator(tracing, profile_extractor)
        with _RunCollector() as collector:
            outcome = orch.run_turn(SESSION_ID, f"{JD_TEXT}\n聯絡窗口 {MSG_MARKER}", "qa0020-trace-1")
            orch.close()  # flush：強制背景佇列送出
        return outcome, session, collector.runs

    # TC-1 / AC-1
    def test_tc1_default_disabled_should_not_build_tracing(self):
        with patch("dotenv.load_dotenv"), patch.dict(os.environ, {
                "RECRUIT_TRACING_ENABLED": "", "LANGSMITH_API_KEY": "", "LANGSMITH_TRACING": ""}):
            cfg = AppConfig.load(override_api_key="x")
        with patch("langsmith.Client") as client_cls:
            tracing = lt.build_langsmith_tracing(cfg)
        self.assertIsNone(tracing)
        client_cls.assert_not_called()
        orch = self._orchestrator(None)
        self.assertNotIn("callbacks", orch._invoke_config("s", "t"))

    # TC-2 / AC-2：追蹤樹完整（含執行緒池內 Profile 抽取）
    def test_tc2_trace_tree_should_include_pool_llm_runs_with_parents(self):
        outcome, _session, runs = self._run_traced_turn()
        posts = {r["id"]: r for r in runs if r.get("name")}
        llm_runs = [r for r in posts.values() if r.get("run_type") == "llm"]
        # 4 位候選人抽取（執行緒池）+ 1 次敘述
        self.assertGreaterEqual(len(llm_runs), len(RESUMES) + 1)
        self.assertTrue(all(r.get("parent_run_id") for r in llm_runs))
        roots = [r for r in posts.values() if not r.get("parent_run_id")]
        self.assertEqual(len(roots), 1)
        self.assertEqual(roots[0]["name"], lt.TURN_RUN_NAME)
        node_names = {r["name"] for r in posts.values()}
        self.assertTrue({"route", "jd_match", "compose"} <= node_names)
        self.assertEqual(len(outcome.shortlist), 3)

    # TC-3 / AC-3：零內容上傳（HTTP 位元組層 + run payload 層雙重檢查）
    def test_tc3_uploaded_bytes_should_contain_no_content_or_pii(self):
        _outcome, session, runs = self._run_traced_turn()
        self.assertTrue(session.bodies, "SDK 應實際送出上傳請求")
        raw = b"\n".join(session.bodies)
        for marker in FORBIDDEN:
            self.assertNotIn(marker.encode("utf-8"), raw, f"上傳位元組含禁止內容：{marker!r}")
        for run in runs:
            for field in ("inputs", "outputs"):
                if field in run and run[field] is not None:
                    self.assertEqual(run[field], {}, f"{run.get('name')}.{field} 未隱藏")
        blob = json.dumps(runs, ensure_ascii=False)
        for marker in FORBIDDEN:
            self.assertNotIn(marker, blob)
        self.assertNotIn("<resume_content>", blob)

    # TC-4 / AC-4：metadata 白名單，且保留 token 用量
    def test_tc4_metadata_should_be_allowlisted_and_keep_usage(self):
        _outcome, _session, runs = self._run_traced_turn()
        usage_seen = False
        for run in runs:
            meta = (run.get("extra") or {}).get("metadata") or {}
            self.assertTrue(set(meta) <= lt.ALLOWED_METADATA_KEYS, f"非白名單鍵：{set(meta) - lt.ALLOWED_METADATA_KEYS}")
            # DV-1：langchain-core tracer 固定附帶之執行環境僅允許函式庫/平台版本字串（無個資、無內容）
            runtime = (run.get("extra") or {}).get("runtime") or {}
            self.assertTrue(set(runtime) <= RUNTIME_ALLOWED_KEYS, f"非預期 runtime 鍵：{set(runtime)}")
            self.assertTrue(set(run.get("extra") or {}) <= {"metadata", "runtime", "invocation_params",
                                                            "batch_size", "options"}, run.get("extra"))
            if "usage_metadata" in meta:
                usage_seen = True
                self.assertEqual(meta["usage_metadata"]["total_tokens"], 150)
        self.assertTrue(usage_seen, "LLM run 應保留 usage_metadata")

    # TC-5 / AC-5：錯誤脫敏（執行緒池內 LLM 失敗 → 降級，錯誤僅留類別名）
    def test_tc5_error_should_be_reduced_to_type_name(self):
        first = next(iter(RESUMES))
        outcome, session, runs = self._run_traced_turn(LcProfileExtractor(fail_for={first}))
        names = {r["id"]: r.get("name") for r in runs if r.get("name")}
        # ADR-0022：人數不足時圖暫停於 await_relaxation，LangGraph 以 GraphInterrupt 標記該節點 run；
        # 屬控制流程訊號（同樣只有類別名），只允許出現在 await_relaxation，不計入錯誤脫敏檢核
        interrupts = [r for r in runs if r.get("error") == "GraphInterrupt"]
        self.assertTrue(all((r.get("name") or names.get(r["id"])) == "await_relaxation" for r in interrupts),
                        [(r.get("name") or names.get(r["id"])) for r in interrupts])
        errors = [r["error"] for r in runs if r.get("error") and r.get("error") != "GraphInterrupt"]
        self.assertTrue(errors, "應有失敗之 LLM run")
        self.assertTrue(all(e in ("ValueError", lt.UNKNOWN_ERROR_TYPE) for e in errors), errors)
        self.assertIn("ValueError", errors)
        self.assertNotIn(ERROR_MARKER.encode("utf-8"), b"\n".join(session.bodies))
        self.assertTrue(outcome.warnings)

    # TC-6 / AC-6：端點無法連線，對話結果與未追蹤一致，收尾不無限懸掛
    def test_tc6_unreachable_endpoint_should_not_affect_chat(self):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        baseline = self._orchestrator(None).run_turn("qa0020-base", JD_TEXT, "t-base")
        tracing = _build_tracing(None, langsmith_endpoint=f"http://127.0.0.1:{port}")
        self.assertIsNotNone(tracing)
        orch = self._orchestrator(tracing)
        logging.getLogger("langsmith").setLevel(logging.CRITICAL)
        start = time.monotonic()
        outcome = orch.run_turn("qa0020-unreach", JD_TEXT, "t-unreach")
        turn_seconds = time.monotonic() - start
        close_start = time.monotonic()
        orch.close()
        close_seconds = time.monotonic() - close_start
        self.assertEqual([e.candidate_id for e in outcome.shortlist], [e.candidate_id for e in baseline.shortlist])
        self.assertEqual(outcome.reply_markdown, baseline.reply_markdown)
        self.assertLess(turn_seconds, 10.0, "追蹤上傳不得阻塞對話回合")
        print(f"\n[TC-6] turn={turn_seconds:.2f}s close(flush)={close_seconds:.2f}s")
        self.assertLess(close_seconds, 3.0 + 2.0, "收尾 flush 須受 RECRUIT_TRACING_FLUSH_TIMEOUT_SECONDS 約束")

    # TC-7 / AC-7：根 run metadata 與日誌 trace_id / session_hash 一致
    def test_tc7_root_metadata_should_match_log_identifiers(self):
        from src.application.recruitment_chat_use_case import session_hash

        _outcome, _session, runs = self._run_traced_turn()
        root = next(r for r in runs if r.get("name") == lt.TURN_RUN_NAME and r.get("extra"))
        meta = root["extra"]["metadata"]
        self.assertEqual(meta["trace_id"], "qa0020-trace-1")
        self.assertEqual(meta["session_hash"], session_hash(SESSION_ID))

    # TC-8 / AC-8：全域追蹤旗標警告
    def test_tc8_global_tracing_flag_should_warn(self):
        with patch.dict(os.environ, {"LANGSMITH_TRACING": "true"}), self.assertLogs(lt.logger, "WARNING") as logs:
            with patch("langsmith.Client"):
                lt.build_langsmith_tracing(_tracing_config())
        self.assertIn("LANGSMITH_TRACING", "\n".join(logs.output))

    # TC-9 / AC-9：設定治理（.env.example 同步、金鑰不入日誌）
    def test_tc9_env_example_and_no_key_in_logs(self):
        example = (ROOT_DIR / ".env.example").read_text(encoding="utf-8")
        for key in ("RECRUIT_TRACING_ENABLED", "LANGSMITH_API_KEY", "LANGSMITH_ENDPOINT", "LANGSMITH_PROJECT",
                    "RECRUIT_TRACING_SAMPLING_RATE", "RECRUIT_TRACING_FLUSH_TIMEOUT_SECONDS"):
            self.assertRegex(example, rf"(?m)^{key}=")
        self.assertRegex(example, r"(?m)^LANGSMITH_API_KEY=\s*$")
        root_logger = logging.getLogger()
        records: List[str] = []

        class Sink(logging.Handler):
            def emit(self, record):
                records.append(self.format(record))

        sink = Sink(level=logging.DEBUG)
        root_logger.addHandler(sink)
        old_level = root_logger.level
        root_logger.setLevel(logging.DEBUG)
        try:
            self._run_traced_turn()
        finally:
            root_logger.removeHandler(sink)
            root_logger.setLevel(old_level)
        joined = "\n".join(records)
        self.assertNotIn(FAKE_KEY, joined)
        for name in CANDIDATE_NAMES:
            self.assertNotIn(name, joined)


if __name__ == "__main__":
    unittest.main()
