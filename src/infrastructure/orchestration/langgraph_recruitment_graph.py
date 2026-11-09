"""
LangGraph 招募助手編排器 (ADR-0019)，實作 IChatOrchestrator

圖：START → route → (依 intents 佇列條件邊) → jd_match | candidate_followup | interview_questions
     | general_qa | out_of_scope → … → compose → END
節點僅為轉接層：反序列化領域狀態 → 委派 RecruitmentNodeHandlers → 序列化回寫。
持久化狀態僅含 JSON 相容之 session dict 與意圖佇列；單輪暫態（預算、逾時、回覆段落）經 Runtime context 傳遞，不落盤。
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from src.application.recruitment_nodes import RecruitmentNodeHandlers, TurnContext
from src.domain.recruitment import ChatIntent, ChatSessionState, ChatTurnOutcome
from src.domain.recruitment_codec import session_from_dict, session_to_dict
from src.infrastructure.orchestration.checkpointer_factory import CheckpointerBundle

logger = logging.getLogger(__name__)


class RecruitmentGraphState(TypedDict, total=False):
    session: Dict[str, Any]
    queue: List[str]


@dataclass
class TurnRuntimeContext:
    turn: TurnContext


class LangGraphRecruitmentOrchestrator:
    def __init__(self, handlers: RecruitmentNodeHandlers, bundle: CheckpointerBundle, max_intents_per_turn: int):
        self._handlers = handlers
        self._bundle = bundle
        # route + 最多 N 個意圖節點 + compose，另留緩衝防無限迴圈
        self._recursion_limit = max(int(max_intents_per_turn), 1) + 4
        self._graph = self._build_graph()

    # ------------------------------------------------------------------
    def _build_graph(self):
        handlers = self._handlers
        intent_nodes = handlers.INTENT_NODES
        graph = StateGraph(RecruitmentGraphState, context_schema=TurnRuntimeContext)

        def make_node(name: str):
            def node(state: RecruitmentGraphState, runtime: Runtime[TurnRuntimeContext]) -> Dict[str, Any]:
                raw = state.get("session") or {}
                session = session_from_dict(raw, str(raw.get("session_id", "")))
                turn = runtime.context.turn
                update = handlers.execute_node(name, session, turn)
                out: Dict[str, Any] = {"session": session_to_dict(update.session)}
                if name == handlers.NODE_ROUTE:
                    out["queue"] = [intent.value for intent in turn.intents]
                elif name != handlers.NODE_COMPOSE:
                    out["queue"] = list(state.get("queue") or [])[1:]
                return out

            return node

        for name in handlers.node_names():
            graph.add_node(name, make_node(name))

        def next_step(state: RecruitmentGraphState) -> str:
            queue = state.get("queue") or []
            if not queue:
                return handlers.NODE_COMPOSE
            return intent_nodes[ChatIntent(queue[0])]

        destinations = [*intent_nodes.values(), handlers.NODE_COMPOSE]
        graph.add_edge(START, handlers.NODE_ROUTE)
        graph.add_conditional_edges(handlers.NODE_ROUTE, next_step, destinations)
        for node_name in intent_nodes.values():
            graph.add_conditional_edges(node_name, next_step, destinations)
        graph.add_edge(handlers.NODE_COMPOSE, END)
        return graph.compile(checkpointer=self._bundle.saver)

    def _config(self, session_id: str) -> Dict[str, Any]:
        return {"configurable": {"thread_id": session_id}, "recursion_limit": self._recursion_limit}

    def _load(self, session_id: str) -> Optional[ChatSessionState]:
        snapshot = self._graph.get_state(self._config(session_id))
        raw = (snapshot.values or {}).get("session") if snapshot else None
        if not raw:
            return None
        return session_from_dict(raw, session_id)

    # ------------------------------------------------------------------
    # IChatOrchestrator
    # ------------------------------------------------------------------
    def run_turn(self, session_id: str, message: str, trace_id: str) -> ChatTurnOutcome:
        with self._bundle.lock.hold(session_id):
            expired_notice = self._touch(session_id)
            turn = self._handlers.new_turn(message, trace_id)
            if expired_notice:
                turn.warn("先前對話已逾時失效，已建立新對話")
            prior = self._load(session_id) or ChatSessionState(session_id=session_id)
            self._graph.invoke(
                {"session": session_to_dict(prior), "queue": []},
                self._config(session_id),
                context=TurnRuntimeContext(turn=turn),
            )
            final = self._load(session_id) or prior
            return ChatTurnOutcome(
                session_id=session_id,
                intents=list(turn.intents),
                reply_markdown=turn.final_reply,
                shortlist=tuple(final.shortlist),
                relaxation=final.relaxation,
                followup=turn.followup,
                interview_questions=list(turn.interview_questions),
                warnings=list(turn.warnings),
                degraded=turn.degraded,
                usage=turn.usage,
                node_ms=dict(turn.node_ms),
            )

    def get_state(self, session_id: str) -> Optional[ChatSessionState]:
        registry = self._bundle.registry
        if registry is not None and registry.is_expired(session_id):
            return None
        return self._load(session_id)

    def reset(self, session_id: str) -> None:
        self._delete_thread(session_id)
        if self._bundle.registry is not None:
            self._bundle.registry.remove(session_id)
        self._release_lock_entry(session_id)

    def close(self) -> None:
        self._bundle.close()

    # ------------------------------------------------------------------
    def _touch(self, session_id: str) -> bool:
        registry = self._bundle.registry
        if registry is None:
            return False
        expired, evicted = registry.touch(session_id)
        for old_sid in evicted:
            self._delete_thread(old_sid)
            self._release_lock_entry(old_sid)
        if expired:
            self._delete_thread(session_id)
        return expired

    def _release_lock_entry(self, session_id: str) -> None:
        remover = getattr(self._bundle.lock, "remove", None)
        if callable(remover):
            remover(session_id)

    def _delete_thread(self, session_id: str) -> None:
        try:
            self._bundle.saver.delete_thread(session_id)
        except Exception as err:
            logger.warning("刪除 Session 檢查點失敗 (err_type=%s)", type(err).__name__)
