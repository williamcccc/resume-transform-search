"""
E2E / 灰箱 QA 實測：候選人不足時自動擴大檢索 (ADR-0021，Spec-0021 §3.7 QA 矩陣)

分軌：
- FAKE 軌：真實 FastAPI 路由 + 真實 LangGraph 編排器（InMemorySaver）+ 真實節點/Profile 服務；
  向量檢索為依 min_score / top_k 真實篩選之記憶體 Fake，LLM 為確定性 Fake（無 API Key、無 Redis 亦可執行）。
- REDIS 軌：真實 RediSearch KNN（RedisVectorStore + IndexResumesUseCase + SearchResumesUseCase）
  + 可控餘弦相似度之確定性 Fake Embedding（離線、零 Token），驗證真實索引下「降低門檻 / 放大 top_k」確實召回池外人選。
  Redis 8 之 RediSearch 僅允許 db0 建索引，故使用 REDIS_URL + 專屬前綴 qa0021* 隔離，結束後清除，不觸碰正式索引。

所有履歷與姓名皆為記憶體動態建構之虛構樣本，寫入 tempfile 隔離目錄；嚴禁讀取 data/、resume/。
"""
import logging
import math
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Dict, List
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.application.recruitment_chat_use_case import RecruitmentChatUseCase  # noqa: E402
from src.domain.recruitment import ChatIntent  # noqa: E402
from src.infrastructure.config import AppConfig  # noqa: E402
from src.interfaces.web.fastapi_server import create_app  # noqa: E402
from tests.unit.recruitment_fakes import (  # noqa: E402
    JD_TEXT,
    FakeClassifier,
    FakeNarrator,
    InMemoryProfileCache,
    build_handlers,
    make_settings,
)
from tests.unit.test_recruitment_search_expansion import (  # noqa: E402
    BODY_MARKER,
    LibraryExtractor,
    ThresholdSearch,
    make_library,
)

try:
    import langgraph  # noqa: F401

    from src.infrastructure.orchestration.checkpointer_factory import build_memory_checkpointer
    from src.infrastructure.orchestration.langgraph_recruitment_graph import LangGraphRecruitmentOrchestrator

    LANGGRAPH_OK = True
except ImportError:  # pragma: no cover
    LANGGRAPH_OK = False

REDIS_SEARCH_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
QA_PREFIX = "qa0021:"
QA_INDEX = "idx:qa0021:v1"
NARRATION = "推薦理由由敘述模型產生。"


def no_hit_pool(n: int, top: float = 0.95, step: float = 0.005) -> List[tuple]:
    return [(round(top - i * step, 4), False) for i in range(n)]


def base_pool(qualified: int, size: int = 15) -> List[tuple]:
    return [(round(0.9 - i * 0.01, 3), i < qualified) for i in range(size)]


class _Harness:
    """真實 LangGraph + FastAPI，Fake 檢索 / LLM"""

    def __init__(self, spec, search=None, classifier=None, **settings_overrides):
        self.library = make_library(spec)
        self.search = search or ThresholdSearch(self.library)
        self.extractor = LibraryExtractor(self.library)
        self.narrator = FakeNarrator()
        self.narrator.match_text = NARRATION
        self.settings = make_settings(**settings_overrides)
        handlers = build_handlers(settings=self.settings, search=self.search, profile_extractor=self.extractor,
                                  cache=InMemoryProfileCache(), narrator=self.narrator, classifier=classifier)
        self.bundle = build_memory_checkpointer(3600, 200)
        self.orchestrator = LangGraphRecruitmentOrchestrator(handlers, self.bundle,
                                                             self.settings.max_intents_per_turn)
        self.use_case = RecruitmentChatUseCase(self.orchestrator, self.settings, None,
                                               on_close=self.orchestrator.close)
        self.client = TestClient(create_app(use_case=MagicMock(), search_use_case=None,
                                            chat_use_case=self.use_case))

    def chat(self, message=JD_TEXT, session_id=None):
        body = {"message": message}
        if session_id:
            body["session_id"] = session_id
        r = self.client.post("/api/chat", json=body)
        assert r.status_code == 200, r.text[:300]
        return r.json()

    def close(self):
        self.use_case.close()


@unittest.skipUnless(LANGGRAPH_OK, "未安裝 langgraph，略過 FAKE 軌")
class TestSearchExpansionFakeE2E(unittest.TestCase):
    def harness(self, spec, **kwargs) -> _Harness:
        h = _Harness(spec, **kwargs)
        self.addCleanup(h.close)
        return h

    # TC-1 / AC-1, AC-9
    def test_tc01_baseline_satisfied_is_byte_identical_to_disabled(self):
        on = self.harness(base_pool(3))
        off = self.harness(base_pool(3), search_expansion_max_rounds=0)
        d_on, d_off = on.chat(), off.chat()
        self.assertEqual(d_on["reply_markdown"], d_off["reply_markdown"])
        self.assertEqual(d_on["shortlist"], d_off["shortlist"])
        self.assertEqual(d_on["warnings"], d_off["warnings"])
        self.assertEqual(len(on.search.queries), 1)
        self.assertEqual((d_on["usage"]["search_rounds"], d_on["usage"]["search_stop_reason"]), (0, "SATISFIED"))

    # TC-2 / AC-2, AC-8
    def test_tc02_first_round_fills_shortlist_and_only_new_candidates_extracted(self):
        h = self.harness(base_pool(1) + [(0.7, True), (0.69, False), (0.68, True)], max_llm_calls_per_turn=100)
        d = h.chat()
        ids = [x["candidate_id"] for x in d["shortlist"]]
        self.assertEqual(sorted(ids), ["cand_s01", "cand_s16", "cand_s18"])
        self.assertTrue(all(x["fully_qualified"] for x in d["shortlist"]))
        self.assertIsNone(d["relaxation"])
        self.assertEqual(sorted(h.extractor.calls), sorted(set(h.extractor.calls)))
        self.assertEqual(len(h.extractor.calls), 18)
        self.assertIn("| 第 1 輪 | 0.50 | 25 | 18 | 3 | 3 |", d["reply_markdown"])
        self.assertIn(NARRATION, d["reply_markdown"])
        # 同一 Session 再送同一 JD：快取命中，0 次抽取
        before = len(h.extractor.calls)
        h.chat(session_id=d["session_id"])
        self.assertEqual(len(h.extractor.calls), before)

    # TC-3 / AC-3
    def test_tc03_saturation_lowers_threshold_never_below_floor(self):
        spec = [(round(0.8 - i * 0.01, 3), False) for i in range(5)] + [(0.47, True), (0.43, True), (0.41, True)]
        h = self.harness(spec, search_expansion_max_rounds=5, max_llm_calls_per_turn=100)
        d = h.chat()
        self.assertEqual([q.min_score for q in h.search.queries], [0.5, 0.45, 0.4])
        self.assertTrue(all(q.min_score >= 0.4 for q in h.search.queries))
        self.assertEqual(d["usage"]["search_stop_reason"], "SATISFIED")
        self.assertIn("| 第 2 輪 | 0.40 |", d["reply_markdown"])

    def test_tc03b_exhausted_at_floor(self):
        spec = [(round(0.8 - i * 0.01, 3), False) for i in range(5)]
        h = self.harness(spec, search_expansion_max_rounds=5)
        d = h.chat()
        self.assertEqual([q.min_score for q in h.search.queries], [0.5, 0.45, 0.4])
        self.assertEqual(d["usage"]["search_stop_reason"], "EXHAUSTED")
        self.assertIn("相似度門檻已降至下限", d["reply_markdown"])

    # TC-4 / AC-4, AC-5
    def test_tc04_max_rounds_relaxation_scope_and_pool_cap(self):
        h = self.harness(no_hit_pool(80), max_llm_calls_per_turn=100)
        d = h.chat()
        self.assertEqual(len(h.search.queries), 3)
        self.assertEqual(d["usage"]["search_stop_reason"], "MAX_ROUNDS")
        rel = d["relaxation"]
        self.assertEqual(rel["pool_size"], 35)
        self.assertEqual(rel["pool_size"], d["usage"]["pool_evaluated"])
        self.assertIn("已自動擴大檢索 2 輪", rel["scope_note"])
        self.assertIn("候選池共 35 人", d["reply_markdown"])
        capped = self.harness(no_hit_pool(80), search_expansion_max_rounds=5, search_expansion_pool_max=30,
                              max_llm_calls_per_turn=100)
        d2 = capped.chat()
        self.assertEqual((d2["usage"]["pool_evaluated"], d2["usage"]["search_stop_reason"]), (30, "POOL_CAP"))
        self.assertEqual(len(capped.extractor.calls), 30)

    # TC-5 / AC-6, AC-7
    def test_tc05_budget_reserve_keeps_llm_narration_and_deadline_stops(self):
        h = self.harness(no_hit_pool(60))  # 預設預算 25、保留 2
        d = h.chat()
        self.assertEqual(d["usage"]["search_stop_reason"], "BUDGET")
        self.assertIn(NARRATION, d["reply_markdown"])
        self.assertFalse(d["degraded"])
        self.assertLessEqual(d["usage"]["llm_calls"], 25)
        late = self.harness(base_pool(1), search_expansion_min_remaining_seconds=1000.0)
        d2 = late.chat()
        self.assertEqual(d2["usage"]["search_stop_reason"], "DEADLINE")
        self.assertEqual(len(late.search.queries), 1)

    # TC-6 / AC-10
    def test_tc06_topology_and_two_intents_at_max_config(self):
        classifier = FakeClassifier(intents=[ChatIntent.JD_MATCH, ChatIntent.GENERAL_QA])
        h = self.harness(no_hit_pool(150), classifier=classifier, search_expansion_max_rounds=5,
                         search_expansion_pool_max=100, max_llm_calls_per_turn=200)
        mermaid = h.orchestrator._graph.get_graph().draw_mermaid()
        self.assertIn("jd_search_round -.-> jd_search_round", mermaid)
        d = h.chat("幫我找人")
        self.assertEqual(d["intents"], ["JD_MATCH", "GENERAL_QA"])
        self.assertEqual(d["usage"]["search_rounds"], 5)
        self.assertEqual(len(h.narrator.general_facts), 1)

    # TC-7 / AC-11
    def test_tc07_checkpoint_has_no_resume_body_and_log_has_new_fields(self):
        h = self.harness(base_pool(1) + [(0.7, True), (0.68, True)])
        with self.assertLogs("src.application.recruitment_chat_use_case", level=logging.INFO) as logs:
            d = h.chat()
        line = next(m for m in logs.output if "chat_turn" in m)
        self.assertRegex(line, r"search_rounds=1 search_stop_reason=SATISFIED pool_evaluated=\d+")
        self.assertNotIn("張小強", line)
        config = {"configurable": {"thread_id": d["session_id"]}}
        snapshots = list(h.orchestrator._graph.get_state_history(config))
        self.assertGreater(len(snapshots), 0)
        for snap in snapshots:
            self.assertNotIn(BODY_MARKER, repr(snap.values))
            self.assertLessEqual(set(snap.values), {"session", "queue", "goto"})
        self.assertIsNone(h.orchestrator._graph.get_state(config).values.get("goto"))

    # TC-8 / AC-12
    def test_tc08_empty_pool_no_llm_beyond_jd(self):
        h = self.harness([(0.3, True), (0.25, True)])
        d = h.chat()
        self.assertEqual([q.min_score for q in h.search.queries], [0.5, 0.45, 0.4])
        self.assertIn("資料庫中無相關人選", d["reply_markdown"])
        self.assertEqual(d["shortlist"], [])
        self.assertEqual(h.extractor.calls, [])
        self.assertEqual(h.narrator.match_facts, [])
        self.assertEqual(d["usage"]["llm_calls"], 1)  # 只有 JD 抽取

    # 對抗：擴大輪檢索中斷 → 以已評估者收尾，不 500
    def test_tc12_expansion_retrieval_outage_degrades_gracefully(self):
        library = make_library(base_pool(1) + [(0.7, True)])
        search = ThresholdSearch(library, fail_on_call=2, fail_exc=ConnectionError("redis reset"))
        h = self.harness(base_pool(1) + [(0.7, True)], search=search)
        d = h.chat()
        self.assertEqual(d["usage"]["search_stop_reason"], "EXHAUSTED")
        self.assertTrue(any("擴大檢索失敗" in w for w in d["warnings"]))
        self.assertIsNotNone(d["relaxation"])

    # 對抗：同一 Session 連續兩輪 JD（第二輪條件已足夠）→ 每輪獨立重算，不殘留上一輪擴大狀態
    def test_tc13_consecutive_turns_do_not_leak_loop_state(self):
        h = self.harness(base_pool(1) + [(0.7, True), (0.68, True)], max_llm_calls_per_turn=100)
        d1 = h.chat()
        d2 = h.chat(session_id=d1["session_id"])
        self.assertEqual(d1["usage"]["search_rounds"], d2["usage"]["search_rounds"])
        self.assertEqual(d1["shortlist"], d2["shortlist"])
        self.assertEqual(d1["reply_markdown"], d2["reply_markdown"])


# TC-9 / AC-13
class TestSearchExpansionConfigE2E(unittest.TestCase):
    def test_tc09_env_parsing_end_to_end(self):
        env = {"RECRUIT_SEARCH_EXPANSION_MAX_ROUNDS": "-4", "RECRUIT_SEARCH_EXPANSION_POOL_MAX": "1e9",
               "RECRUIT_SEARCH_EXPANSION_MIN_SCORE_FLOOR": "0.45", "RECRUIT_RETRIEVAL_MIN_SCORE": "0.3",
               "RECRUIT_SEARCH_EXPANSION_MIN_REMAINING_SECONDS": "inf"}
        with patch.dict(os.environ, env, clear=True):
            cfg = AppConfig.load(override_api_key="mock_key")
        self.assertEqual(cfg.recruit_search_expansion_max_rounds, 0)
        self.assertEqual(cfg.recruit_search_expansion_pool_max, 40)            # 非整數 → 預設
        self.assertEqual(cfg.recruit_search_expansion_min_score_floor, 0.3)    # 夾至基準門檻
        self.assertEqual(cfg.recruit_search_expansion_min_remaining_seconds, 150.0)
        text = (ROOT_DIR / ".env.example").read_text(encoding="utf-8")
        self.assertEqual(len(re.findall(r"^RECRUIT_SEARCH_EXPANSION_\w+=", text, flags=re.M)), 8)


# ----------------------------------------------------------------------
# REDIS 軌：真實 RediSearch KNN + 可控相似度 Fake Embedding
# ----------------------------------------------------------------------
def _redis_available(url: str) -> bool:
    try:
        import redis

        client = redis.Redis.from_url(url, socket_connect_timeout=2)
        try:
            return bool(client.ping())
        finally:
            client.close()
    except Exception:
        return False


class _ControlledEmbedding:
    """查詢向量 = e0；候選人 i 之所有切片向量 = cos·e0 + sin·e_k，使 KNN 餘弦相似度恰為指定分數（零 Token）"""

    dim = 16
    _ID = re.compile(r"(?:張小強|團隊)(\d{2})")

    def __init__(self, scores: Dict[int, float]):
        self.scores = scores
        self.query_calls = 0

    def _vec(self, score: float, k: int) -> List[float]:
        v = [0.0] * self.dim
        v[0] = score
        v[1 + (k % (self.dim - 1))] = math.sqrt(max(1.0 - score * score, 0.0))
        return v

    def embed_texts(self, texts, task_type="retrieval_document"):
        out = []
        for t in texts:
            m = self._ID.search(t)
            idx = int(m.group(1)) if m else 0
            out.append(self._vec(self.scores.get(idx, 0.0), idx))
        return out

    def embed_query(self, query):
        self.query_calls += 1
        return self._vec(1.0, 0)


@unittest.skipUnless(LANGGRAPH_OK, "未安裝 langgraph，略過 REDIS 軌")
class TestSearchExpansionRedisE2E(unittest.TestCase):
    """TC-11 / AC-2：真實索引下，基準門檻外之合格者經擴大檢索被召回"""

    SPEC = base_pool(1) + [(0.48, True), (0.47, True), (0.46, True)]

    @classmethod
    def setUpClass(cls):
        if not _redis_available(REDIS_SEARCH_URL):
            raise unittest.SkipTest("Redis 不可連線，略過 REDIS 軌")
        from src.application.dto import IndexCommand
        from src.application.index_resumes_use_case import IndexResumesUseCase
        from src.application.search_resumes_use_case import SearchResumesUseCase
        from src.infrastructure.chunkers.markdown_chunker import MarkdownChunker
        from src.infrastructure.stores.redis_vector_store import RedisVectorStore

        cls.library = make_library(cls.SPEC)
        cls._tmp = tempfile.TemporaryDirectory()
        resume_dir = Path(cls._tmp.name) / "markdown_out"
        resume_dir.mkdir(parents=True)
        for cid, r in cls.library.items():
            (resume_dir / f"{cid}.md").write_text(r["text"], encoding="utf-8")
        scores = {i + 1: s for i, (s, _) in enumerate(cls.SPEC)}
        cls.embedding = _ControlledEmbedding(scores)
        cls.store = RedisVectorStore(redis_url=REDIS_SEARCH_URL, index_name=QA_INDEX,
                                     prefix=f"{QA_PREFIX}chunk:", hash_prefix=f"{QA_PREFIX}hash:")
        try:
            result = IndexResumesUseCase(MarkdownChunker(min_chunk_chars=10, max_chunk_chars=2000),
                                         cls.embedding, cls.store).execute(
                IndexCommand(dir_path=resume_dir, recreate_index=True))
            if result.errors or result.indexed_files != len(cls.library):
                raise AssertionError(f"入庫失敗 indexed={result.indexed_files} errors={len(result.errors)}")
        except Exception:
            cls._cleanup()
            raise
        cls.search_uc = SearchResumesUseCase(embedding_service=cls.embedding, vector_store=cls.store,
                                             markdown_base_dir=resume_dir)

    @classmethod
    def _cleanup(cls):
        try:
            cls.store.client.ft(QA_INDEX).dropindex(delete_documents=True)
        except Exception:
            pass
        try:
            import redis

            client = redis.Redis.from_url(REDIS_SEARCH_URL)
            try:
                keys = list(client.scan_iter(match=f"{QA_PREFIX}*", count=500))
                if keys:
                    client.delete(*keys)
            finally:
                client.close()
        finally:
            cls._tmp.cleanup()

    @classmethod
    def tearDownClass(cls):
        cls._cleanup()

    def test_tc11_real_knn_recalls_qualified_candidates_below_base_threshold(self):
        h = _Harness(self.SPEC, search=self.search_uc, max_llm_calls_per_turn=100)
        self.addCleanup(h.close)
        d = h.chat()
        ids = sorted(x["candidate_id"] for x in d["shortlist"])
        self.assertEqual(ids, ["cand_s01", "cand_s16", "cand_s17"])
        self.assertTrue(all(x["fully_qualified"] for x in d["shortlist"]))
        self.assertEqual(d["usage"]["search_stop_reason"], "SATISFIED")
        self.assertEqual(d["usage"]["search_rounds"], 2)  # 第 1 輪放大池子仍飽和 → 第 2 輪降門檻至 0.45
        self.assertIn("| 第 2 輪 | 0.45 |", d["reply_markdown"])
        self.assertIsNone(d["relaxation"])
        self.assertEqual(self.embedding.query_calls, 3)  # 已知成本：每輪 1 次查詢向量化（Spec-0021 DV-2）


if __name__ == "__main__":
    unittest.main()
