"""
LangGraph 編排器單元測試：InMemorySaver 實跑圖 + Fake LLM。
跨輪保存 shortlist、TTL 過期（注入時鐘）、LRU 淘汰、Session 鎖 409、Redis 鎖、未安裝 redis checkpointer 降級。
"""
import importlib.util
import threading
import unittest
from unittest.mock import MagicMock, patch

from src.domain.exceptions import ChatUnavailableError, SessionBusyError
from src.domain.recruitment import ChatIntent
from tests.unit.recruitment_fakes import JD_TEXT, build_handlers

HAS_LANGGRAPH = importlib.util.find_spec("langgraph") is not None

if HAS_LANGGRAPH:
    from src.infrastructure.orchestration.checkpointer_factory import (
        MemorySessionLock,
        RedisSessionLock,
        TtlLruSessionRegistry,
        build_checkpointer,
        build_memory_checkpointer,
        build_redis_checkpointer,
    )
    from src.infrastructure.orchestration.langgraph_recruitment_graph import LangGraphRecruitmentOrchestrator

SID = "sess_graph_0001"


@unittest.skipUnless(HAS_LANGGRAPH, "langgraph 未安裝")
class TestLangGraphRecruitmentOrchestrator(unittest.TestCase):
    def setUp(self):
        self.now = [1000.0]
        self.bundle = build_memory_checkpointer(session_ttl_seconds=60, max_sessions=2, clock=lambda: self.now[0])
        self.handlers = build_handlers()
        self.orch = LangGraphRecruitmentOrchestrator(self.handlers, self.bundle, max_intents_per_turn=2)

    def test_state_should_persist_across_turns(self):
        first = self.orch.run_turn(SID, JD_TEXT, "t1")
        self.assertEqual(first.intents, [ChatIntent.JD_MATCH])
        self.assertEqual(len(first.shortlist), 3)
        second = self.orch.run_turn(SID, "第 2 位看起來不錯，他有帶過人嗎？幫他出 3 題面試題", "t2")
        self.assertEqual(second.intents, [ChatIntent.CANDIDATE_FOLLOWUP, ChatIntent.INTERVIEW_QUESTIONS])
        self.assertEqual(second.followup.candidate_id, "cand_b")
        self.assertEqual(second.shortlist, first.shortlist)
        state = self.orch.get_state(SID)
        self.assertEqual(state.turn_count, 2)
        self.assertEqual(state.last_referenced_candidate_id, "cand_b")
        self.assertIn("route", second.node_ms)

    def test_ttl_expired_session_should_restart_with_warning(self):
        self.orch.run_turn(SID, JD_TEXT, "t1")
        self.now[0] += 61
        self.assertIsNone(self.orch.get_state(SID))  # AC-24
        out = self.orch.run_turn(SID, "第 1 位有帶過人嗎？", "t2")
        self.assertTrue(any("逾時" in w for w in out.warnings))
        self.assertIn("請先貼上職缺 JD", out.reply_markdown)
        self.assertEqual(self.orch.get_state(SID).turn_count, 1)

    def test_lru_eviction_should_delete_oldest_thread(self):
        self.orch.run_turn("sess_lru_00001", JD_TEXT, "a")
        self.orch.run_turn("sess_lru_00002", "你好", "b")
        self.orch.run_turn("sess_lru_00003", "你好", "c")
        self.assertIsNone(self.orch.get_state("sess_lru_00001"))
        self.assertIsNotNone(self.orch.get_state("sess_lru_00003"))

    def test_reset_should_clear_state_idempotently(self):
        self.orch.run_turn(SID, JD_TEXT, "t1")
        self.orch.reset(SID)
        self.orch.reset(SID)
        self.assertIsNone(self.orch.get_state(SID))

    def test_concurrent_turn_on_same_session_should_raise_busy(self):
        gate = threading.Event()
        release = threading.Event()
        original = self.handlers.route

        def slow_route(state, turn):
            gate.set()
            release.wait(2)
            return original(state, turn)

        self.handlers.route = slow_route
        worker = threading.Thread(target=self.orch.run_turn, args=(SID, "你好", "t1"))
        worker.start()
        gate.wait(2)
        try:
            with self.assertRaises(SessionBusyError):  # AC-27
                self.orch.run_turn(SID, "你好", "t2")
        finally:
            release.set()
            worker.join(5)
        self.assertEqual(self.orch.get_state(SID).turn_count, 1)

    def test_node_exception_should_propagate_and_keep_previous_state(self):
        self.orch.run_turn(SID, JD_TEXT, "t1")
        self.handlers.general_qa = MagicMock(side_effect=RuntimeError("boom"))
        with self.assertRaises(RuntimeError):
            self.orch.run_turn(SID, "你好", "t2")
        out = self.orch.run_turn(SID, "第 1 位有帶過人嗎？", "t3")
        self.assertEqual(len(out.shortlist), 3)


@unittest.skipUnless(HAS_LANGGRAPH, "langgraph 未安裝")
class TestCheckpointerFactory(unittest.TestCase):
    def test_registry_ttl_and_lru(self):
        now = [0.0]
        reg = TtlLruSessionRegistry(10, 2, clock=lambda: now[0])
        self.assertEqual(reg.touch("a"), (False, []))
        reg.touch("b")
        self.assertEqual(reg.touch("c"), (False, ["a"]))
        now[0] = 11
        self.assertTrue(reg.is_expired("b"))
        self.assertEqual(reg.touch("b"), (True, []))
        reg.remove("b")
        self.assertEqual(len(reg), 1)

    def test_memory_lock_should_be_non_blocking(self):
        lock = MemorySessionLock()
        with lock.hold("s1"):
            with self.assertRaises(SessionBusyError):
                with lock.hold("s1"):
                    pass
            with lock.hold("s2"):
                pass
        with lock.hold("s1"):
            pass

    def test_redis_lock_should_use_set_nx_and_release_by_token(self):
        client = MagicMock()
        client.set.return_value = True
        with RedisSessionLock(client, 90).hold("s1"):
            pass
        args, kwargs = client.set.call_args
        self.assertEqual(args[0], "chat:v1:lock:s1")
        self.assertEqual((kwargs["nx"], kwargs["ex"]), (True, 90))
        self.assertEqual(client.eval.call_args[0][3], args[1])
        client.set.return_value = None
        with self.assertRaises(SessionBusyError):
            with RedisSessionLock(client, 90).hold("s1"):
                pass

    def test_redis_lock_connection_error_should_chain(self):
        client = MagicMock()
        client.set.side_effect = ConnectionError("down")
        with self.assertRaises(ChatUnavailableError) as ctx:
            with RedisSessionLock(client, 90).hold("s1"):
                pass
        self.assertIsInstance(ctx.exception.__cause__, ConnectionError)

    def test_redis_backend_without_package_should_raise_unavailable(self):
        with patch.dict("sys.modules", {"langgraph.checkpoint.redis": None}):
            with self.assertRaises(ChatUnavailableError) as ctx:
                build_redis_checkpointer("redis://unused", 60, 90)
        self.assertIsInstance(ctx.exception.__cause__, ImportError)

    def test_redis_backend_connection_failure_should_raise_unavailable(self):
        fake_redis = MagicMock()
        fake_redis.Redis.from_url.return_value.ping.side_effect = ConnectionError("refused")
        with patch.dict("sys.modules", {"redis": fake_redis}):
            with self.assertRaises(ChatUnavailableError) as ctx:
                build_redis_checkpointer("redis://unused", 60, 90)
        self.assertIsNotNone(ctx.exception.__cause__)

    def test_non_db0_url_should_add_actionable_hint(self):
        from src.infrastructure.orchestration.checkpointer_factory import redis_db_hint

        fake_redis = MagicMock()
        fake_redis.Redis.from_url.return_value.ping.side_effect = ConnectionError("refused")
        with patch.dict("sys.modules", {"redis": fake_redis}):
            with self.assertRaises(ChatUnavailableError) as ctx:
                build_redis_checkpointer("redis://localhost:6379/15", 60, 90)
        self.assertIn("db0", str(ctx.exception))
        self.assertIn("前綴", str(ctx.exception))
        self.assertEqual(redis_db_hint("redis://localhost:6379/0"), "")
        self.assertEqual(redis_db_hint("redis://localhost:6379"), "")
        self.assertIn("db2", redis_db_hint("redis://localhost:6379?db=2"))

    def test_unknown_backend_should_raise(self):
        with self.assertRaises(ChatUnavailableError):
            build_checkpointer("sqlite", "", 60, 10, 90)
        self.assertIsNotNone(build_checkpointer("memory", "", 60, 10, 90).registry)


if __name__ == "__main__":
    unittest.main()
