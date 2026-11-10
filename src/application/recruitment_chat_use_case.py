"""
招募助手多輪對話使用案例 (ADR-0019)

職責：輸入驗證 → Session 識別 → 熔斷檢查 → 輪數上限 → trace_id → 呼叫 IChatOrchestrator → DTO 映射。
本身無狀態；所有對話狀態皆由編排器之 Checkpointer 保存。日誌僅記錄長度、Hash 與 trace_id（AC-12、AC-33）。
"""
import hashlib
import logging
import re
import uuid
from typing import Callable, List, Optional

from src.application.dto import ChatTurnCommand, ChatTurnResultDTO
from src.application.recruitment_settings import RecruitmentSettings
from src.domain.exceptions import (
    LlmQuotaExhaustedError,
    RecruitmentInputError,
    RelaxationDecisionError,
    SessionTurnLimitError,
)
from src.domain.interfaces import IChatOrchestrator
from src.domain.recruitment import ChatSessionState, RelaxationPrompt
from src.domain.recruitment_services import CircuitBreaker

logger = logging.getLogger(__name__)

SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def default_id_factory() -> str:
    return uuid.uuid4().hex


_RELAX_ID_PATTERN = re.compile(r"R\d{1,3}")
_MAX_RELAX_IDS = 12


def session_hash(session_id: str) -> str:
    return hashlib.sha256((session_id or "").encode("utf-8")).hexdigest()[:12]


def validate_session_id(session_id: str) -> str:
    if not session_id or not SESSION_ID_PATTERN.match(session_id):
        raise RecruitmentInputError("session_id 格式不合法", error_code="INVALID_INPUT")
    return session_id


class RecruitmentChatUseCase:
    def __init__(
        self,
        orchestrator: IChatOrchestrator,
        settings: RecruitmentSettings,
        circuit_breaker: Optional[CircuitBreaker] = None,
        id_factory: Callable[[], str] = default_id_factory,
        on_close: Optional[Callable[[], None]] = None,
    ):
        self._orchestrator = orchestrator
        self._settings = settings
        self._breaker = circuit_breaker
        self._id_factory = id_factory
        self._on_close = on_close

    def execute(self, cmd: ChatTurnCommand) -> ChatTurnResultDTO:
        relax_ids = self._normalize_relax_ids(cmd.relax_requirement_ids)
        message = (cmd.message or "").strip()
        if not message and relax_ids:
            message = "放寬 " + "、".join(relax_ids)
        if not message:
            raise RecruitmentInputError("訊息不可為空", error_code="INVALID_INPUT")
        if len(message) > self._settings.max_message_chars:
            raise RecruitmentInputError(
                f"訊息長度超過上限 {self._settings.max_message_chars} 字元", error_code="MESSAGE_TOO_LONG"
            )
        session_id = validate_session_id(cmd.session_id) if cmd.session_id else self._id_factory()

        if self._breaker is not None and self._breaker.is_open():
            raise LlmQuotaExhaustedError("LLM 配額熔斷冷卻中", retry_after_seconds=self._breaker.retry_after_seconds())

        state = self._orchestrator.get_state(session_id)
        if state is not None and state.turn_count >= self._settings.session_max_turns:
            raise SessionTurnLimitError(f"對話已達 {self._settings.session_max_turns} 輪上限，請開新對話")

        trace_id = self._id_factory()
        if relax_ids:
            outcome = self._orchestrator.run_turn(session_id, message, trace_id, relax_requirement_ids=relax_ids)
        else:
            outcome = self._orchestrator.run_turn(session_id, message, trace_id)
        if outcome.relaxation_audit is not None:
            audit = outcome.relaxation_audit
            logger.info(
                "relaxation_decision trace_id=%s session_hash=%s round=%d relaxed=%s qualified_before=%d "
                "qualified_after=%d",
                trace_id, session_hash(session_id), audit.round, ",".join(audit.requirement_ids),
                audit.qualified_before, audit.qualified_after,
            )

        logger.info(
            "chat_turn trace_id=%s session_hash=%s msg_len=%d intents=%s node_ms=%s llm_calls=%d "
            "profile_cache_hits=%d profile_cache_misses=%d jd_cache_hit=%s degraded=%s "
            "search_rounds=%d search_stop_reason=%s pool_evaluated=%d",
            trace_id,
            session_hash(session_id),
            len(message),
            ",".join(i.value for i in outcome.intents),
            outcome.node_ms,
            outcome.usage.llm_calls,
            outcome.usage.profile_cache_hits,
            outcome.usage.profile_cache_misses,
            outcome.usage.jd_cache_hit,
            outcome.degraded,
            outcome.usage.search_rounds,
            outcome.usage.search_stop_reason or "-",
            outcome.usage.pool_evaluated,
        )
        return ChatTurnResultDTO(
            session_id=session_id,
            trace_id=trace_id,
            intents=[i.value for i in outcome.intents],
            reply_markdown=outcome.reply_markdown,
            shortlist=list(outcome.shortlist),
            relaxation=outcome.relaxation,
            followup=outcome.followup,
            interview_questions=list(outcome.interview_questions),
            warnings=list(outcome.warnings),
            degraded=outcome.degraded,
            usage=outcome.usage,
            pending_decision=outcome.pending_decision,
            relaxed_requirement_ids=list(outcome.relaxed_requirement_ids),
        )

    @staticmethod
    def _normalize_relax_ids(ids: Optional[List[str]]) -> List[str]:
        """格式與數量檢查（是否屬於當時選項由編排器對照待決定內容驗證）"""
        if ids is None:
            return []
        if not isinstance(ids, (list, tuple)) or len(ids) > _MAX_RELAX_IDS:
            raise RelaxationDecisionError(f"放寬條件數量不合法（最多 {_MAX_RELAX_IDS} 項）")
        normalized = [str(i).strip().upper() for i in ids]
        if not normalized:
            raise RelaxationDecisionError("請至少選擇 1 個要放寬的條件")
        if any(not _RELAX_ID_PATTERN.fullmatch(i) for i in normalized):
            raise RelaxationDecisionError("放寬條件代號格式不合法（應為 R1、R2…）")
        return normalized

    def get_pending_decision(self, session_id: str) -> Optional[RelaxationPrompt]:
        return self._orchestrator.get_pending_decision(validate_session_id(session_id))

    def get_session(self, session_id: str) -> Optional[ChatSessionState]:
        return self._orchestrator.get_state(validate_session_id(session_id))

    def reset_session(self, session_id: str) -> None:
        self._orchestrator.reset(validate_session_id(session_id))

    def close(self) -> None:
        if self._on_close is not None:
            self._on_close()
