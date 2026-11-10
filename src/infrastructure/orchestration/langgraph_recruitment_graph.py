"""
LangGraph 招募助手編排器 (ADR-0019)，實作 IChatOrchestrator

圖：START → route → (依 intents 佇列條件邊) → jd_match | candidate_followup | interview_questions
     | general_qa | out_of_scope → … → compose → END
jd_match 子步驟 (ADR-0021)：jd_match → jd_search_round ⟲（自循環）→ jd_finalize，由節點回傳之 goto 驅動條件邊；
子步驟中間資料（含履歷文字）只存在 Runtime context 之 TurnContext，graph state 僅多一個節點名稱 goto。
放寬條件之人工決策 (ADR-0022)：compose ─(goto)→ await_relaxation（interrupt 暫停）─resume→ apply_relaxation → compose；
interrupt payload 只含條件 ID、標籤與人數。恢復時 await_relaxation 會重新執行，interrupt 之前不得有副作用。
節點僅為轉接層：反序列化領域狀態 → 委派 RecruitmentNodeHandlers → 序列化回寫。
持久化狀態僅含 JSON 相容之 session dict 與意圖佇列；單輪暫態（預算、逾時、回覆段落）經 Runtime context 傳遞，不落盤。
"""
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, interrupt

from src.application.recruitment_nodes import RecruitmentNodeHandlers, TurnContext
from src.domain.exceptions import RelaxationDecisionError
from src.domain.recruitment import ChatIntent, ChatSessionState, ChatTurnOutcome, RelaxationPrompt
from src.domain.recruitment_codec import (
    relaxation_prompt_from_dict,
    relaxation_prompt_to_dict,
    session_from_dict,
    session_to_dict,
)
from src.domain.recruitment_services import validate_relaxation_decision
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
        await_node, apply_node = handlers.NODE_AWAIT_RELAXATION, handlers.NODE_APPLY_RELAXATION
        goto_targets = (*substep_nodes, apply_node, handlers.NODE_COMPOSE)
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

        def await_relaxation(state: RecruitmentGraphState, runtime: Runtime[TurnRuntimeContext]) -> Dict[str, Any]:
            # 恢復時本節點會從頭重新執行：interrupt 之前只做純計算，不得有任何副作用
            raw = state.get("session") or {}
            prompt = handlers.relaxation_prompt(session_from_dict(raw, str(raw.get("session_id", ""))))
            if prompt is None:  # 防禦：條件已不成立
                return {"goto": None}
            decision = interrupt(relaxation_prompt_to_dict(prompt))
            turn = runtime.context.turn
            turn.relaxation_decision = tuple(str(i) for i in (decision or ()))
            turn.intents = [ChatIntent.RELAX_CONSTRAINTS]
            return {"goto": apply_node}

        graph.add_node(await_node, await_relaxation)

        def next_step(state: RecruitmentGraphState) -> str:
            goto = state.get("goto")
            if goto is not None:
                if goto not in goto_targets:
                    raise ValueError(f"未知子步驟節點：{goto}")
                return goto
            queue = state.get("queue") or []
            if not queue:
                return handlers.NODE_COMPOSE
            return intent_nodes[ChatIntent(queue[0])]

        destinations = [*intent_nodes.values(), *substep_nodes, handlers.NODE_COMPOSE]
        graph.add_edge(START, handlers.NODE_ROUTE)
        graph.add_conditional_edges(handlers.NODE_ROUTE, next_step, destinations)
        for node_name in (*intent_nodes.values(), *substep_nodes, apply_node):
            graph.add_conditional_edges(node_name, next_step, destinations)
        graph.add_conditional_edges(handlers.NODE_COMPOSE,
                                    lambda s: await_node if s.get("goto") == await_node else END, [await_node, END])
        graph.add_conditional_edges(await_node, lambda s: apply_node if s.get("goto") == apply_node else END,
                                    [apply_node, END])
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
    def run_turn(self, session_id: str, message: str, trace_id: str,
                 relax_requirement_ids: Optional[Sequence[str]] = None) -> ChatTurnOutcome:
        with self._bundle.lock.hold(session_id):
            expired_notice = self._touch(session_id)
            turn = self._handlers.new_turn(message, trace_id)
            if expired_notice:
                turn.warn("先前對話已逾時失效，已建立新對話")
            prior = self._load(session_id) or ChatSessionState(session_id=session_id)
            pending = None if expired_notice else self._pending(session_id)
            if relax_requirement_ids:
                # 人工放寬決定：先對照當時選項驗證（不合法時拋出，checkpoint 不變），再以 Command(resume) 恢復
                # 以「目前設定 + Session」重算之選項驗證（與恢復後 await_relaxation 之判斷一致），
                # 避免待決定期間設定變更（如關閉 HITL）時恢復後無動作而回傳空回覆
                current = self._handlers.relaxation_prompt(prior) if pending is not None else None
                if current is None:
                    raise RelaxationDecisionError("目前沒有待決定的放寬選項，請先送出 JD 取得條件瓶頸分析",
                                                  error_code="NO_PENDING_DECISION")
                chosen = validate_relaxation_decision(current, relax_requirement_ids)
                turn.intents = [ChatIntent.RELAX_CONSTRAINTS]
                graph_input: Any = Command(resume=list(chosen))
            else:
                # 一般訊息：從 START 重新執行；若有待決定則視為放棄 (ADR-0022 AC-5)
                graph_input = {"session": session_to_dict(prior), "queue": [], "goto": None}
            self._graph.invoke(graph_input, self._invoke_config(session_id, trace_id),
                               context=TurnRuntimeContext(turn=turn))
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
                pending_decision=self._pending(session_id),
                relaxed_requirement_ids=tuple(final.relaxed_requirement_ids),
                relaxation_audit=turn.relaxation_audit,
            )

    def get_state(self, session_id: str) -> Optional[ChatSessionState]:
        registry = self._bundle.registry
        if registry is not None and registry.is_expired(session_id):
            return None
        return self._load(session_id)

    def get_pending_decision(self, session_id: str) -> Optional[RelaxationPrompt]:
        registry = self._bundle.registry
        if registry is not None and registry.is_expired(session_id):
            return None
        return self._pending(session_id)

    def _pending(self, session_id: str) -> Optional[RelaxationPrompt]:
        """讀取 checkpoint 中 await_relaxation 之待決定 payload；讀取失敗視為無待決定"""
        try:
            snapshot = self._graph.get_state(self._config(session_id))
            for task in getattr(snapshot, "tasks", ()) or ():
                for intr in getattr(task, "interrupts", ()) or ():
                    value = getattr(intr, "value", None)
                    if isinstance(value, dict) and value.get("kind") == "RELAXATION":
                        return relaxation_prompt_from_dict(value)
        except Exception as err:
            logger.warning("讀取待決定之放寬選項失敗，視為無待決定 (err_type=%s)", type(err).__name__)
        return None

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
