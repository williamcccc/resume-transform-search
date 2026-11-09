"""
招募助手 LangSmith 遮蔽式效能追蹤 (ADR-0020 / Spec-0020，方案 A1)

只上傳「結構與數值」：輸入/輸出由 SDK 用戶端整包隱藏；metadata 走白名單（token 用量、模型、節點、
trace_id、session_hash）；錯誤僅留例外類別名；不送執行環境資訊。
追蹤為旁路：任何建立/上傳失敗僅記 WARNING，不影響對話。
langsmith / langchain-core 僅於 build_langsmith_tracing 內延遲匯入。
"""
import logging
import os
import re
import threading
from numbers import Number
from typing import Any, Callable, Dict, Mapping, Optional

from src.application.recruitment_chat_use_case import session_hash

logger = logging.getLogger(__name__)

ALLOWED_METADATA_KEYS = frozenset({
    "trace_id",
    "session_hash",
    "langgraph_node",
    "langgraph_step",
    "ls_provider",
    "ls_model_name",
    "ls_model_type",
    "ls_temperature",
    "ls_max_tokens",
    "usage_metadata",
})
USAGE_METADATA_KEY = "usage_metadata"
GLOBAL_TRACING_ENV_VARS = ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2")
TURN_RUN_NAME = "recruitment_chat_turn"
TURN_TAGS = ("recruitment-chat",)
UNKNOWN_ERROR_TYPE = "Error"

_ERROR_TYPE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*(?:\(|:|$)")
_TRUTHY = ("1", "true", "yes", "on")


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, bool, int, float))


def _numeric_only(value: Any) -> Any:
    """usage_metadata：遞迴僅保留數值葉節點（含 input_token_details 等巢狀計數）"""
    if isinstance(value, Mapping):
        out = {}
        for key, item in value.items():
            kept = _numeric_only(item)
            if kept is not None and kept != {}:
                out[str(key)] = kept
        return out
    if isinstance(value, Number) and not isinstance(value, bool):
        return value
    return None


def scrub_metadata(metadata: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """白名單過濾：非白名單鍵（thread_id、checkpoint_ns 等）一律剔除；非純量值剔除"""
    result: Dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        if key not in ALLOWED_METADATA_KEYS:
            continue
        if key == USAGE_METADATA_KEY:
            usage = _numeric_only(value)
            if isinstance(usage, dict) and usage:
                result[key] = usage
        elif _is_scalar(value):
            result[key] = value
    return result


def scrub_error(error: Any) -> str:
    """錯誤字串（repr(exc) + traceback）僅保留第一行開頭之例外類別名，訊息本文一律丟棄"""
    if not isinstance(error, str) or not error.strip():
        return UNKNOWN_ERROR_TYPE
    first_line = error.strip().splitlines()[0]
    match = _ERROR_TYPE.match(first_line)
    return match.group(1) if match else UNKNOWN_ERROR_TYPE


def trace_anonymizer(payload: Any) -> Any:
    """
    langsmith Client anonymizer：hide_inputs/hide_outputs=True 優先生效，故此處僅會收到
    run metadata 或 {"error": ...}。
    """
    if not isinstance(payload, Mapping):
        return {}
    if set(payload.keys()) == {"error"}:
        return {"error": scrub_error(payload.get("error"))}
    return scrub_metadata(payload)


def global_tracing_enabled(environ: Optional[Mapping[str, str]] = None) -> bool:
    env = os.environ if environ is None else environ
    return any(str(env.get(name, "")).strip().lower() in _TRUTHY for name in GLOBAL_TRACING_ENV_VARS)


class LangSmithTurnTracing:
    """每輪產生獨立 tracer 之 invoke config；client 為已套用遮蔽政策之 langsmith Client"""

    def __init__(self, client: Any, project_name: str, tracer_factory: Callable[..., Any],
                 flush_timeout_seconds: float = 5.0):
        self._client = client
        self._project_name = project_name
        self._tracer_factory = tracer_factory
        self._flush_timeout = max(float(flush_timeout_seconds), 0.0)

    def invoke_config(self, trace_id: str, session_id: str) -> Dict[str, Any]:
        tracer = self._tracer_factory(client=self._client, project_name=self._project_name)
        return {
            "callbacks": [tracer],
            "run_name": TURN_RUN_NAME,
            "tags": list(TURN_TAGS),
            "metadata": {"trace_id": trace_id, "session_hash": session_hash(session_id)},
        }

    def close(self) -> None:
        """有界收尾：flush 於背景執行緒進行，最多等待 flush_timeout 秒（端點不可達時 SDK 退避重試可達數十秒）"""
        done = threading.Event()
        errors: list = []

        def _flush() -> None:
            try:
                self._client.flush()
            except Exception as err:  # 收尾上傳失敗不影響服務關閉
                errors.append(err)
            finally:
                done.set()

        threading.Thread(target=_flush, name="langsmith-trace-flush", daemon=True).start()
        if not done.wait(self._flush_timeout):
            logger.warning("LangSmith 追蹤收尾上傳逾時 (%.1fs)，未送出之追蹤資料將被捨棄", self._flush_timeout)
        elif errors:
            logger.warning("LangSmith 追蹤收尾上傳失敗 (err_type=%s)", type(errors[0]).__name__)


def build_langsmith_tracing(config: Any) -> Optional[LangSmithTurnTracing]:
    """依 AppConfig 組裝；停用、缺金鑰、套件或 Client 失敗一律回傳 None（追蹤停用，對話不受影響）"""
    if not getattr(config, "recruit_tracing_enabled", False):
        return None
    if global_tracing_enabled():
        logger.warning(
            "偵測到全域追蹤旗標 (%s) 已開啟：全域追蹤會繞過遮蔽政策上傳完整內容，請移除該設定",
            "/".join(GLOBAL_TRACING_ENV_VARS),
        )
    if not getattr(config, "langsmith_api_key", ""):
        logger.warning("已啟用 RECRUIT_TRACING_ENABLED 但未設定 LANGSMITH_API_KEY，追蹤停用")
        return None
    try:
        from langchain_core.tracers.langchain import LangChainTracer
        from langsmith import Client

        client = Client(
            api_key=config.langsmith_api_key,
            api_url=config.langsmith_endpoint or None,
            hide_inputs=True,
            hide_outputs=True,
            anonymizer=trace_anonymizer,
            omit_traced_runtime_info=True,
            tracing_sampling_rate=config.recruit_tracing_sampling_rate,
        )
    except Exception as err:
        logger.warning("LangSmith 追蹤初始化失敗，追蹤停用 (err_type=%s)", type(err).__name__)
        return None
    logger.info("LangSmith 遮蔽式追蹤已啟用 (project=%s, sampling_rate=%s)",
                config.langsmith_project, config.recruit_tracing_sampling_rate)
    return LangSmithTurnTracing(client, config.langsmith_project, LangChainTracer,
                                flush_timeout_seconds=config.recruit_tracing_flush_timeout_seconds)
