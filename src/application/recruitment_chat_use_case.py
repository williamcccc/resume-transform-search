"""
招募助手多輪對話使用案例 (ADR-0019)

職責：輸入驗證 → Session 識別 → 熔斷檢查 → 輪數上限 → trace_id → 呼叫 IChatOrchestrator → DTO 映射。
本身無狀態；所有對話狀態皆由編排器之 Checkpointer 保存。日誌僅記錄長度、Hash 與 trace_id（AC-12、AC-33）。
"""
import hashlib
import logging
import re
import uuid
from typing import Callable, Optional

from src.application.dto import ChatTurnCommand, ChatTurnResultDTO
from src.application.recruitment_settings import RecruitmentSettings
from src.domain.exceptions import LlmQuotaExhaustedError, RecruitmentInputError, SessionTurnLimitError
from src.domain.interfaces import IChatOrchestrator
from src.domain.recruitment import ChatSessionState
from src.domain.recruitment_services import CircuitBreaker

logger = logging.getLogger(__name__)

SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def default_id_factory() -> str:
    return uuid.uuid4().hex


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
        message = (cmd.message or "").strip()
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
        outcome = self._orchestrator.run_turn(session_id, message, trace_id)

        logger.info(
            "chat_turn trace_id=%s session_hash=%s msg_len=%d intents=%s node_ms=%s llm_calls=%d "
            "profile_cache_hits=%d profile_cache_misses=%d jd_cache_hit=%s degraded=%s",
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
        )

    def get_session(self, session_id: str) -> Optional[ChatSessionState]:
        return self._orchestrator.get_state(validate_session_id(session_id))

    def reset_session(self, session_id: str) -> None:
        self._orchestrator.reset(validate_session_id(session_id))

    def close(self) -> None:
        if self._on_close is not None:
            self._on_close()
