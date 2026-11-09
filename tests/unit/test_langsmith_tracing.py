"""
Spec-0020 LangSmith 遮蔽式追蹤單元測試（100% 離線：langsmith Client 一律以 Mock 取代，不發送任何 HTTP）。
涵蓋：遮蔽政策純函式、組裝失效安全、invoke config、編排器注入與隔離、執行緒池 contextvars 傳遞、AppConfig。
"""
import contextvars
import importlib.util
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from src.application.recruitment_chat_use_case import session_hash
from src.infrastructure.config import AppConfig, _clamp_unit
from src.infrastructure.observability import langsmith_tracing as lt
from tests.unit.recruitment_fakes import JD_TEXT, FakeProfileExtractor, build_handlers

HAS_LANGGRAPH = importlib.util.find_spec("langgraph") is not None
HAS_LANGSMITH = importlib.util.find_spec("langsmith") is not None
TRACING_ENV = ("RECRUIT_TRACING_ENABLED", "LANGSMITH_API_KEY", "LANGSMITH_ENDPOINT", "LANGSMITH_PROJECT",
               "RECRUIT_TRACING_SAMPLING_RATE", "RECRUIT_TRACING_FLUSH_TIMEOUT_SECONDS","LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2")
FAKE_KEY = "lsv2_fake_unit_test_key"


def _config(**overrides):
    base = dict(recruit_tracing_enabled=True, langsmith_api_key=FAKE_KEY, langsmith_endpoint="",
                langsmith_project="unit-proj", recruit_tracing_sampling_rate=0.5,
                recruit_tracing_flush_timeout_seconds=2.0)
    base.update(overrides)
    cfg = MagicMock()
    for key, value in base.items():
        setattr(cfg, key, value)
    return cfg


class TestScrubPolicy(unittest.TestCase):
    def test_scrub_metadata_should_keep_allowlist_and_drop_session_keys(self):
        # Arrange
        meta = {"trace_id": "t1", "session_hash": "abc", "langgraph_node": "jd_match", "langgraph_step": 2,
                "ls_model_name": "gemini-x", "thread_id": "raw-session-id", "checkpoint_ns": "jd_match:1",
                "candidate_name": "王小明", "langgraph_path": ["__pregel_pull", "jd_match"]}
        # Act
        result = lt.scrub_metadata(meta)
        # Assert
        self.assertEqual(result, {"trace_id": "t1", "session_hash": "abc", "langgraph_node": "jd_match",
                                  "langgraph_step": 2, "ls_model_name": "gemini-x"})

    def test_scrub_metadata_allowlisted_key_with_nested_value_should_be_dropped(self):
        result = lt.scrub_metadata({"trace_id": {"nested": "王小明"}, "ls_provider": ["x"]})
        self.assertEqual(result, {})

    def test_scrub_metadata_usage_should_keep_numeric_leaves_only(self):
        usage = {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14,
                 "input_token_details": {"cache_read": 3, "note": "王小明"}, "model": "x", "flag": True}
        result = lt.scrub_metadata({"usage_metadata": usage})
        self.assertEqual(result, {"usage_metadata": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14,
                                                     "input_token_details": {"cache_read": 3}}})

    def test_scrub_metadata_usage_without_numbers_should_be_omitted(self):
        self.assertEqual(lt.scrub_metadata({"usage_metadata": {"a": "b"}}), {})
        self.assertEqual(lt.scrub_metadata(None), {})

    def test_scrub_error_should_keep_only_exception_type(self):
        err = "ValueError('王小明 test@example.com 履歷內容')\n\nTraceback (most recent call last):\n  File x"
        self.assertEqual(lt.scrub_error(err), "ValueError")

    def test_scrub_error_dotted_and_colon_forms(self):
        self.assertEqual(lt.scrub_error("langchain_core.exceptions.OutputParserException: 王小明"),
                         "langchain_core.exceptions.OutputParserException")
        self.assertEqual(lt.scrub_error("TimeoutError()"), "TimeoutError")
        self.assertEqual(lt.scrub_error("KeyboardInterrupt"), "KeyboardInterrupt")

    def test_scrub_error_unrecognized_or_empty_should_return_generic(self):
        self.assertEqual(lt.scrub_error("王小明 crashed"), lt.UNKNOWN_ERROR_TYPE)
        self.assertEqual(lt.scrub_error(""), lt.UNKNOWN_ERROR_TYPE)
        self.assertEqual(lt.scrub_error(None), lt.UNKNOWN_ERROR_TYPE)
        self.assertEqual(lt.scrub_error({"x": 1}), lt.UNKNOWN_ERROR_TYPE)

    def test_trace_anonymizer_should_route_error_and_metadata(self):
        self.assertEqual(lt.trace_anonymizer({"error": "RuntimeError('王小明')"}), {"error": "RuntimeError"})
        self.assertEqual(lt.trace_anonymizer({"thread_id": "s", "trace_id": "t"}), {"trace_id": "t"})
        self.assertEqual(lt.trace_anonymizer("not-a-dict"), {})

    def test_global_tracing_enabled_detection(self):
        self.assertTrue(lt.global_tracing_enabled({"LANGSMITH_TRACING": "true"}))
        self.assertTrue(lt.global_tracing_enabled({"LANGCHAIN_TRACING_V2": "1"}))
        self.assertFalse(lt.global_tracing_enabled({"LANGSMITH_TRACING": "false"}))
        self.assertFalse(lt.global_tracing_enabled({}))


@unittest.skipUnless(HAS_LANGSMITH, "langsmith 未安裝")
class TestBuildLangSmithTracing(unittest.TestCase):
    def setUp(self):
        self._env = patch.dict(os.environ, {}, clear=False)
        self._env.start()
        for key in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"):
            os.environ.pop(key, None)

    def tearDown(self):
        self._env.stop()

    def test_disabled_should_return_none_without_creating_client(self):
        with patch("langsmith.Client") as client_cls:
            self.assertIsNone(lt.build_langsmith_tracing(_config(recruit_tracing_enabled=False)))
        client_cls.assert_not_called()

    def test_enabled_without_key_should_warn_and_return_none(self):
        with patch("langsmith.Client") as client_cls, self.assertLogs(lt.logger, "WARNING") as logs:
            result = lt.build_langsmith_tracing(_config(langsmith_api_key=""))
        self.assertIsNone(result)
        client_cls.assert_not_called()
        self.assertIn("LANGSMITH_API_KEY", "\n".join(logs.output))

    def test_client_failure_should_warn_with_type_only_and_return_none(self):
        with patch("langsmith.Client", side_effect=RuntimeError(f"bad key {FAKE_KEY}")), \
                self.assertLogs(lt.logger, "WARNING") as logs:
            result = lt.build_langsmith_tracing(_config())
        self.assertIsNone(result)
        joined = "\n".join(logs.output)
        self.assertIn("RuntimeError", joined)
        self.assertNotIn(FAKE_KEY, joined)

    def test_missing_package_should_warn_and_return_none(self):
        with patch.dict(sys.modules, {"langsmith": None}), self.assertLogs(lt.logger, "WARNING") as logs:
            result = lt.build_langsmith_tracing(_config())
        self.assertIsNone(result)
        self.assertRegex("\n".join(logs.output), r"err_type=(ImportError|ModuleNotFoundError)")

    def test_global_flag_should_warn(self):
        os.environ["LANGSMITH_TRACING"] = "true"
        with patch("langsmith.Client"), self.assertLogs(lt.logger, "WARNING") as logs:
            lt.build_langsmith_tracing(_config())
        self.assertIn("LANGSMITH_TRACING", "\n".join(logs.output))

    def test_success_should_configure_client_with_masking_policy(self):
        with patch("langsmith.Client") as client_cls:
            result = lt.build_langsmith_tracing(_config(langsmith_endpoint="https://eu.example.invalid"))
        self.assertIsInstance(result, lt.LangSmithTurnTracing)
        kwargs = client_cls.call_args.kwargs
        self.assertIs(kwargs["hide_inputs"], True)
        self.assertIs(kwargs["hide_outputs"], True)
        self.assertIs(kwargs["anonymizer"], lt.trace_anonymizer)
        self.assertIs(kwargs["omit_traced_runtime_info"], True)
        self.assertEqual(kwargs["tracing_sampling_rate"], 0.5)
        self.assertEqual(kwargs["api_url"], "https://eu.example.invalid")
        self.assertEqual(kwargs["api_key"], FAKE_KEY)

    def test_empty_endpoint_should_pass_none_for_sdk_default(self):
        with patch("langsmith.Client") as client_cls:
            lt.build_langsmith_tracing(_config())
        self.assertIsNone(client_cls.call_args.kwargs["api_url"])


class TestLangSmithTurnTracing(unittest.TestCase):
    def test_invoke_config_should_create_fresh_tracer_and_hashed_metadata(self):
        # Arrange
        client = MagicMock()
        factory = MagicMock(side_effect=lambda **kw: object())
        tracing = lt.LangSmithTurnTracing(client, "proj", factory)
        # Act
        first = tracing.invoke_config("trace-1", "raw-session-id")
        second = tracing.invoke_config("trace-2", "raw-session-id")
        # Assert
        factory.assert_called_with(client=client, project_name="proj")
        self.assertIsNot(first["callbacks"][0], second["callbacks"][0])
        self.assertEqual(first["run_name"], lt.TURN_RUN_NAME)
        self.assertEqual(first["tags"], list(lt.TURN_TAGS))
        self.assertEqual(first["metadata"], {"trace_id": "trace-1", "session_hash": session_hash("raw-session-id")})
        self.assertNotIn("raw-session-id", repr(first["metadata"]))

    def test_close_should_flush_and_swallow_errors_with_warning(self):
        client = MagicMock()
        client.flush.side_effect = ConnectionError("unreachable")
        tracing = lt.LangSmithTurnTracing(client, "proj", MagicMock())
        with self.assertLogs(lt.logger, "WARNING") as logs:
            tracing.close()
        client.flush.assert_called_once()
        self.assertIn("ConnectionError", "\n".join(logs.output))

    def test_close_should_return_within_timeout_when_flush_hangs(self):
        # Arrange
        import threading
        import time

        release = threading.Event()
        client = MagicMock()
        client.flush.side_effect = lambda: release.wait(10)
        tracing = lt.LangSmithTurnTracing(client, "proj", MagicMock(), flush_timeout_seconds=0.2)
        # Act
        start = time.monotonic()
        with self.assertLogs(lt.logger, "WARNING") as logs:
            tracing.close()
        elapsed = time.monotonic() - start
        release.set()
        # Assert
        self.assertLess(elapsed, 2.0)
        self.assertIn("逾時", "\n".join(logs.output))

    def test_close_success_should_not_warn(self):
        client = MagicMock()
        tracing = lt.LangSmithTurnTracing(client, "proj", MagicMock(), flush_timeout_seconds=2.0)
        with patch.object(lt.logger, "warning") as warn:
            tracing.close()
        client.flush.assert_called_once()
        warn.assert_not_called()


@unittest.skipUnless(HAS_LANGGRAPH, "langgraph 未安裝")
class TestOrchestratorTracingInjection(unittest.TestCase):
    def setUp(self):
        from langchain_core.callbacks import BaseCallbackHandler

        from src.infrastructure.orchestration.checkpointer_factory import build_memory_checkpointer
        from src.infrastructure.orchestration.langgraph_recruitment_graph import LangGraphRecruitmentOrchestrator

        class Recorder(BaseCallbackHandler):
            def __init__(self):
                self.chains = []

            def on_chain_start(self, serialized, inputs, **kwargs):
                self.chains.append((kwargs.get("name"), kwargs.get("metadata") or {}))

        self.Recorder = Recorder
        self.Orch = LangGraphRecruitmentOrchestrator
        self.bundle = build_memory_checkpointer(session_ttl_seconds=60, max_sessions=4)

    def test_without_tracing_config_should_have_no_callbacks(self):
        orch = self.Orch(build_handlers(), self.bundle, 2)
        config = orch._invoke_config("s1", "t1")
        self.assertNotIn("callbacks", config)
        self.assertEqual(config["configurable"], {"thread_id": "s1"})

    def test_with_tracing_should_pass_callbacks_and_metadata_into_graph(self):
        # Arrange
        recorder = self.Recorder()
        tracing = MagicMock()
        tracing.invoke_config.return_value = {"callbacks": [recorder], "run_name": "turn",
                                               "metadata": {"trace_id": "t-77"}}
        orch = self.Orch(build_handlers(), self.bundle, 2, tracing=tracing)
        # Act
        outcome = orch.run_turn("s2", JD_TEXT, "t-77")
        # Assert
        tracing.invoke_config.assert_called_once_with("t-77", "s2")
        self.assertEqual(len(outcome.shortlist), 3)
        names = [name for name, _ in recorder.chains]
        self.assertIn("turn", names)
        self.assertIn("jd_match", names)
        root_meta = next(meta for name, meta in recorder.chains if name == "turn")
        self.assertEqual(root_meta.get("trace_id"), "t-77")

    def test_tracing_config_failure_should_not_break_turn(self):
        tracing = MagicMock()
        tracing.invoke_config.side_effect = RuntimeError("boom")
        orch = self.Orch(build_handlers(), self.bundle, 2, tracing=tracing)
        from src.infrastructure.orchestration import langgraph_recruitment_graph as g
        with self.assertLogs(g.logger, "WARNING") as logs:
            outcome = orch.run_turn("s3", JD_TEXT, "t3")
        self.assertEqual(len(outcome.shortlist), 3)
        self.assertIn("RuntimeError", "\n".join(logs.output))

    def test_close_should_close_tracing_then_bundle_even_if_tracing_fails(self):
        bundle = MagicMock()
        bundle.saver = self.bundle.saver
        tracing = MagicMock()
        tracing.close.side_effect = RuntimeError("flush failed")
        orch = self.Orch(build_handlers(), bundle, 2, tracing=tracing)
        with self.assertRaises(RuntimeError):
            orch.close()
        tracing.close.assert_called_once()
        bundle.close.assert_called_once()


class TestProfilePoolContextPropagation(unittest.TestCase):
    def test_worker_threads_should_see_caller_contextvars(self):
        # Arrange
        marker = contextvars.ContextVar("spec0020_marker", default=None)
        seen = []

        class RecordingExtractor(FakeProfileExtractor):
            def extract(self, candidate_id, resume_text, content_hash):
                seen.append(marker.get())
                return super().extract(candidate_id, resume_text, content_hash)

        handlers = build_handlers(profile_extractor=RecordingExtractor())
        token = marker.set("turn-ctx")
        try:
            # Act
            pool = handlers._tools.retrieve_candidate_pool("python", 10, 5, 0.0)
            from src.application.candidate_profile_service import TurnBudget
            handlers._profiles.get_profiles(pool, TurnBudget(10))
        finally:
            marker.reset(token)
        # Assert
        self.assertTrue(seen)
        self.assertTrue(all(value == "turn-ctx" for value in seen))


@patch("dotenv.load_dotenv")
class TestAppConfigTracingFields(unittest.TestCase):
    def test_defaults_should_be_disabled(self, _mock_dotenv):
        with patch.dict(os.environ, {k: "" for k in TRACING_ENV}):
            cfg = AppConfig.load(override_api_key="x")
        self.assertFalse(cfg.recruit_tracing_enabled)
        self.assertEqual(cfg.langsmith_api_key, "")
        self.assertEqual(cfg.langsmith_endpoint, "")
        self.assertEqual(cfg.langsmith_project, "recruitment-assistant")
        self.assertEqual(cfg.recruit_tracing_sampling_rate, 1.0)
        self.assertEqual(cfg.recruit_tracing_flush_timeout_seconds, 5.0)

    def test_env_values_and_clamping(self, _mock_dotenv):
        env = {"RECRUIT_TRACING_ENABLED": "true", "LANGSMITH_API_KEY": f" {FAKE_KEY} ",
               "LANGSMITH_PROJECT": "p1", "RECRUIT_TRACING_SAMPLING_RATE": "7"}
        with patch.dict(os.environ, env):
            cfg = AppConfig.load(override_api_key="x")
        self.assertTrue(cfg.recruit_tracing_enabled)
        self.assertEqual(cfg.langsmith_api_key, FAKE_KEY)
        self.assertEqual(cfg.langsmith_project, "p1")
        self.assertEqual(cfg.recruit_tracing_sampling_rate, 1.0)
        self.assertNotIn(FAKE_KEY, repr(cfg))

    def test_invalid_sampling_rate_should_fall_back(self, _mock_dotenv):
        with patch.dict(os.environ, {"RECRUIT_TRACING_SAMPLING_RATE": "abc"}):
            self.assertEqual(AppConfig.load(override_api_key="x").recruit_tracing_sampling_rate, 1.0)
        with patch.dict(os.environ, {"RECRUIT_TRACING_SAMPLING_RATE": "-0.3"}):
            self.assertEqual(AppConfig.load(override_api_key="x").recruit_tracing_sampling_rate, 0.0)

    def test_clamp_unit_nan(self, _mock_dotenv):
        self.assertEqual(_clamp_unit(float("nan")), 1.0)
        self.assertEqual(_clamp_unit(0.25), 0.25)


if __name__ == "__main__":
    unittest.main()
