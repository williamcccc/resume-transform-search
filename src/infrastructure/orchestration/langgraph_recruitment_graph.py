"""
LangGraph 招募助手編排器 (ADR-0019)，實作 IChatOrchestrator

圖：START → route → (依 intents 佇列條件邊) → jd_match | candidate_followup | interview_questions
     | general_qa | out_of_scope → … → compose → END
jd_match 子步驟 (ADR-0021)：jd_match → jd_search_round ⟲（自循環）→ jd_finalize，由節點回傳之 goto 驅動條件邊；
子步驟中間資料（含履歷文字）只存在 Runtime context 之 TurnContext，graph state 僅多一個節點名稱 goto。
節點僅為轉接層：反序列化領域狀態 → 委派 RecruitmentNodeHandlers → 序列化回寫。
持久化狀態僅含 JSON 相容之 session dict 與意圖佇列；單輪暫態（預算、逾時、回覆段落）經 Runtime context 傳遞，不落盤。
"""
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from src.application.recruitment_nodes import RecruitmentNodeHandlers, TurnContext
from src.domain.recruitment import ChatIntent, ChatSessionState, ChatTurnOutcome
from src.domain.recruitment_codec import session_from_dict, session_to_dict
from src.infrastructure.orchestration.checkpointer_factory import CheckpointerBundle

if TYPE_CHECKING:
    from src.infrastructure.observability.langsmith_tracing import LangSmithTurnTracing

logger = logging.getLogger(__name__)


class RecruitmentGraphState(TypedDict, total=False):
    session: Dict[str, Any]
    queue: List[str]
    goto: Optional[str]  # 子步驟節點名稱（ADR-0021）；None 時依意圖佇列前進


@dataclass
class TurnRuntimeContext:
    turn: TurnContext


class LangGraphRecruitmentOrchestrator:
    def __init__(self, handlers: RecruitmentNodeHandlers, bundle: CheckpointerBundle, max_intents_per_turn: int,
                 tracing: Optional["LangSmithTurnTracing"] = None):
        self._handlers = handlers
        self._bundle = bundle
        # 選用之遮蔽式效能追蹤 (ADR-0020)；None 時行為與未整合前完全一致
        self._tracing = tracing
        # route + 最多 N 個意圖節點（各含子步驟：檢索輪 1+擴大輪數、收尾 1）+ compose，另留緩衝防無限迴圈
        substeps = max(int(getattr(handlers, "max_substeps_per_intent", 0)), 0)
        self._recursion_limit = max(int(max_intents_per_turn), 1) * (substeps + 1) + 4
        self._graph = self._build_graph()

    # ------------------------------------------------------------------
    def _build_graph(self):
        handlers = self._handlers
        intent_nodes = handlers.INTENT_NODES
        substep_nodes = tuple(handlers.SUBSTEP_NODES)
        graph = StateGraph(RecruitmentGraphState, context_schema=TurnRuntimeContext)

        def make_node(name: str):
            def node(state: RecruitmentGraphState, runtime: Runtime[TurnRuntimeContext]) -> Dict[str, Any]:
                raw = state.get("session") or {}
                session = session_from_dict(raw, str(raw.get("session_id", "")))
                turn = runtime.context.turn
                update = handlers.execute_node(name, session, turn)
                out: Dict[str, Any] = {"goto": update.goto}
                is_edge_node = name in (handlers.NODE_ROUTE, handlers.NODE_COMPOSE)
                # session 內容未變更時不輸出通道，避免子步驟循環每輪重複寫入相同快照
                # （比較序列化內容而非物件身分，就地修改 session 之節點也不會遺失變更）
                serialized = session_to_dict(update.session)
                if is_edge_node or serialized != raw:
                    out["session"] = serialized
                if name == handlers.NODE_ROUTE:
                    out["queue"] = [intent.value for intent in turn.intents]
                elif not is_edge_node and update.goto is None:  # 意圖（含其子步驟）處理完畢才彈出佇列
                    out["queue"] = list(state.get("queue") or [])[1:]
                return out

            return node

        for name in handlers.node_names():
            graph.add_node(name, make_node(name))

        def next_step(state: RecruitmentGraphState) -> str:
            goto = state.get("goto")
            if goto is not None:
                if goto not in substep_nodes:
                    raise ValueError(f"未知子步驟節點：{goto}")
                return goto
            queue = state.get("queue") or []
            if not queue:
                return handlers.NODE_COMPOSE
            return intent_nodes[ChatIntent(queue[0])]

        destinations = [*intent_nodes.values(), *substep_nodes, handlers.NODE_COMPOSE]
        graph.add_edge(START, handlers.NODE_ROUTE)
        graph.add_conditional_edges(handlers.NODE_ROUTE, next_step, destinations)
        for node_name in (*intent_nodes.values(), *substep_nodes):
            graph.add_conditional_edges(node_name, next_step, destinations)
        graph.add_edge(handlers.NODE_COMPOSE, END)
        return graph.compile(checkpointer=self._bundle.saver)

    def _config(self, session_id: str) -> Dict[str, Any]:
        return {"configurable": {"thread_id": session_id}, "recursion_limit": self._recursion_limit}

    def _invoke_config(self, session_id: str, trace_id: str) -> Dict[str, Any]:
        config = self._config(session_id)
        if self._tracing is None:
            return config
        try:
            extra = self._tracing.invoke_config(trace_id, session_id)
        except Exception as err:  # 追蹤為旁路，失敗時本輪改走不追蹤路徑
            logger.warning("LangSmith 追蹤設定失敗，本輪不追蹤 (err_type=%s)", type(err).__name__)
            return config
        return {**config, **extra}

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
                {"session": session_to_dict(prior), "queue": [], "goto": None},
                self._invoke_config(session_id, trace_id),
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
        try:
            if self._tracing is not None:
                self._tracing.close()
        finally:
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
