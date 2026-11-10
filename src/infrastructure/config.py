import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


def _safe_int(val: Optional[str], default: int) -> int:
    if not val or not str(val).strip():
        return default
    try:
        return int(str(val).strip())
    except ValueError:
        return default


def _safe_float(val: Optional[str], default: float) -> float:
    if not val or not str(val).strip():
        return default
    try:
        return float(str(val).strip())
    except ValueError:
        return default


def _clamp_unit(val: float) -> float:
    """限制於 [0, 1]；NaN 視為 1.0（全取樣）"""
    if val != val:
        return 1.0
    return min(max(val, 0.0), 1.0)


def _clamp(val: float, lo: float, hi: float) -> float:
    """限制於 [lo, hi]；NaN 視為 lo"""
    if val != val:
        return lo
    return min(max(val, lo), max(lo, hi))


def _search_expansion_fields(base: Dict[str, object]) -> Dict[str, object]:
    """候選人不足時自動擴大檢索設定 (ADR-0021)；越界值夾回合法範圍，部分上下限相依於基準檢索設定"""
    pool_size = int(base["recruit_candidate_pool_size"])
    top_k = int(base["recruit_retrieval_top_k_chunks"])
    min_score = float(base["recruit_retrieval_min_score"])
    timeout = float(base["recruit_turn_timeout_seconds"])
    env = os.environ.get
    return dict(
        recruit_search_expansion_max_rounds=int(_clamp(
            _safe_int(env("RECRUIT_SEARCH_EXPANSION_MAX_ROUNDS"), 2), 0, 5)),
        recruit_search_expansion_pool_step=int(_clamp(
            _safe_int(env("RECRUIT_SEARCH_EXPANSION_POOL_STEP"), 10), 1, 50)),
        recruit_search_expansion_pool_max=int(_clamp(
            _safe_int(env("RECRUIT_SEARCH_EXPANSION_POOL_MAX"), 40), pool_size, 100)),
        recruit_search_expansion_top_k_chunks_max=int(_clamp(
            _safe_int(env("RECRUIT_SEARCH_EXPANSION_TOP_K_CHUNKS_MAX"), 200), top_k, 1000)),
        recruit_search_expansion_min_score_step=_clamp(
            _safe_float(env("RECRUIT_SEARCH_EXPANSION_MIN_SCORE_STEP"), 0.05), 0.001, 0.5),
        recruit_search_expansion_min_score_floor=_clamp(
            _safe_float(env("RECRUIT_SEARCH_EXPANSION_MIN_SCORE_FLOOR"), 0.4), 0.0, min_score),
        recruit_search_expansion_llm_reserve=int(_clamp(
            _safe_int(env("RECRUIT_SEARCH_EXPANSION_LLM_RESERVE"), 2), 0, 10)),
        recruit_search_expansion_min_remaining_seconds=_clamp(
            _safe_float(env("RECRUIT_SEARCH_EXPANSION_MIN_REMAINING_SECONDS"), 30.0), 0.0, max(timeout, 0.0)),
    )


def _safe_optional_int(val: Optional[str]) -> Optional[int]:
    """空值或非法值 -> None（沿用模型預設）；0 與正整數保留"""
    if not val or not str(val).strip():
        return None
    try:
        parsed = int(str(val).strip())
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _safe_list(val: Optional[str]) -> List[str]:
    if not val or not str(val).strip():
        return []
    return [item.strip() for item in str(val).split(",") if item.strip()]


def _safe_bool(val: Optional[str], default: bool) -> bool:
    if val is None or not str(val).strip():
        return default
    return str(val).strip().lower() in ("1", "true", "yes", "on")


def _safe_mapping(val: Optional[str]) -> Dict[str, str]:
    """解析 "a:b,c:d" 形式之對照表"""
    result: Dict[str, str] = {}
    for item in _safe_list(val):
        if ":" in item:
            key, _, value = item.partition(":")
            if key.strip() and value.strip():
                result[key.strip().lower()] = value.strip().lower()
    return result


DEFAULT_PROTECTED_ATTR_TERMS = (
    "年齡,歲,出生,生日,出生日期,生辰,性別,男性,女性,婚姻,已婚,未婚,婚育,懷孕,照片,大頭照,宗教,國籍,籍貫,身高,體重,血型,"
    "gender,sex,age,birth,dob,birthday,marital,married,religion,nationality,photo"
)
DEFAULT_SKILL_ALIASES = (
    "golang:go,k8s:kubernetes,js:javascript,ts:typescript,node.js:nodejs,node:nodejs,"
    "postgres:postgresql,reactjs:react,react.js:react,vue.js:vue,vuejs:vue,ci/cd:cicd,"
    "pl/sql:plsql,tcp/ip:tcpip,a/b testing:abtesting"
)
DEFAULT_SKILL_VERSION_STRIP_EXEMPT = "web3,b2b,b2c,e2e,p2p,base64,utf8,utf-8,sha256,arm64"
DEFAULT_SKILL_LEXICAL_ALIAS_DENYLIST = "node"


@dataclass
class AppConfig:
    gemini_api_key: str
    gemini_model: str
    gemini_review: bool
    gemini_judge: bool = False
    gemini_temperature: float = 0.2
    gemini_max_output_tokens: int = 8192
    redis_url: str = "redis://localhost:6379/0"
    redis_test_url: str = "redis://localhost:6379/15"
    redis_index_name: str = "idx:resumes:v1"
    redis_prefix: str = "resume:v1:chunk:"
    redis_hash_prefix: str = "resume:v1:hash:"
    redis_hnsw_m: int = 16
    redis_hnsw_ef_construction: int = 200
    redis_hnsw_initial_cap: int = 1000
    redis_distance_metric: str = "COSINE"
    embedding_model: str = "gemini-embedding-001"
    embedding_batch_size: int = 20
    embedding_dim: int = 768
    min_chunk_size: int = 80
    max_chunk_size: int = 1500
    quality_threshold: int = 65
    quality_min_retention_ratio: float = 0.35
    quality_max_retention_ratio: float = 3.5
    max_file_size_mb: int = 25
    max_pdf_pages: int = 30
    max_docx_expansion_ratio: float = 10.0
    max_docx_uncompressed_mb: int = 100
    api_max_retries: int = 3
    api_retry_delay: float = 2.0
    pdf_render_dpi: int = 150
    pdf_ocr_dpi: int = 200
    pdf_text_first_min_chars: int = 50
    pdf_scanned_min_chars: int = 30
    pdf_obfuscated_ufffd_threshold: int = 10
    pdf_obfuscated_strikethrough_threshold: int = 30
    vision_review_max_pages: int = 5
    search_default_top_k: int = 5
    search_min_score: float = 0.0
    extra_skill_patterns: List[str] = field(default_factory=list)
    default_output_dir: Optional[str] = None
    default_quarantine_dir: Optional[str] = None
    default_audit_report: Optional[str] = None
    default_scorecard_dir: Optional[str] = None
    log_level: str = "INFO"
    log_file: Optional[str] = "logs/app.log"
    log_max_bytes: int = 10 * 1024 * 1024
    log_backup_count: int = 5
    web_host: str = "127.0.0.1"
    web_port: int = 8080
    web_engine: str = "auto"
    # ---- 招募助手 (ADR-0019) ----
    recruit_chat_enabled: bool = True
    recruit_llm_model: str = ""
    recruit_llm_temperature: float = 0.2
    recruit_llm_max_output_tokens: int = 2048
    recruit_llm_timeout_seconds: float = 45.0
    recruit_profile_max_output_tokens: int = 1024
    recruit_narrative_max_output_tokens: int = 8192
    recruit_llm_thinking_budget: Optional[int] = None
    recruit_skill_lexical_min_chars: int = 3
    recruit_skill_mention_snippet_chars: int = 80
    recruit_skill_version_strip_exempt: List[str] = field(
        default_factory=lambda: _safe_list(DEFAULT_SKILL_VERSION_STRIP_EXEMPT))
    recruit_skill_lexical_alias_denylist: List[str] = field(
        default_factory=lambda: _safe_list(DEFAULT_SKILL_LEXICAL_ALIAS_DENYLIST))
    recruit_retrieval_top_k_chunks: int = 60
    recruit_retrieval_min_score: float = 0.5
    recruit_candidate_pool_size: int = 15
    recruit_candidate_pool_max: int = 30
    recruit_shortlist_size: int = 3
    recruit_shortlist_max: int = 10
    recruit_max_must_requirements: int = 12
    recruit_max_intents_per_turn: int = 2
    recruit_jd_intent_min_chars: int = 200
    recruit_profile_max_resume_chars: int = 12000
    recruit_profile_max_concurrency: int = 8
    recruit_profile_negative_cache_ttl_seconds: int = 600
    recruit_profile_cache_prefix: str = "recruit:v1:profile:"
    recruit_jd_cache_prefix: str = "recruit:v1:jd:"
    recruit_profile_cache_ttl_seconds: int = 2592000
    recruit_evidence_min_chars: int = 4
    recruit_default_interview_questions: int = 3
    recruit_max_interview_questions: int = 10
    recruit_max_message_chars: int = 12000
    recruit_max_llm_calls_per_turn: int = 25
    recruit_turn_timeout_seconds: float = 150.0
    recruit_circuit_breaker_cooldown_seconds: float = 60.0
    # 候選人不足時自動擴大檢索 (ADR-0021)
    recruit_search_expansion_max_rounds: int = 2
    recruit_search_expansion_pool_step: int = 10
    recruit_search_expansion_pool_max: int = 40
    recruit_search_expansion_top_k_chunks_max: int = 200
    recruit_search_expansion_min_score_step: float = 0.05
    recruit_search_expansion_min_score_floor: float = 0.4
    recruit_search_expansion_llm_reserve: int = 2
    recruit_search_expansion_min_remaining_seconds: float = 30.0
    recruit_protected_attr_terms: List[str] = field(default_factory=lambda: _safe_list(DEFAULT_PROTECTED_ATTR_TERMS))
    recruit_skill_aliases: Dict[str, str] = field(default_factory=lambda: _safe_mapping(DEFAULT_SKILL_ALIASES))
    chat_checkpointer_backend: str = "memory"
    chat_checkpoint_redis_url: str = ""
    chat_session_ttl_seconds: int = 3600
    chat_history_max_turns: int = 10
    chat_history_max_chars: int = 24000
    chat_session_max_turns: int = 50
    chat_memory_max_sessions: int = 200
    chat_session_lock_ttl_buffer_seconds: int = 30
    # 招募助手 LangSmith 遮蔽式效能追蹤 (ADR-0020)；預設關閉
    recruit_tracing_enabled: bool = False
    langsmith_api_key: str = field(default="", repr=False)
    langsmith_endpoint: str = ""
    langsmith_project: str = "recruitment-assistant"
    recruit_tracing_sampling_rate: float = 1.0
    recruit_tracing_flush_timeout_seconds: float = 5.0

    @classmethod
    def load(
        cls,
        override_api_key: Optional[str] = None,
        override_model: Optional[str] = None,
        override_review: Optional[bool] = None,
        override_judge: Optional[bool] = None,
        override_gemini_temperature: Optional[float] = None,
        override_gemini_max_output_tokens: Optional[int] = None,
        override_redis_url: Optional[str] = None,
        override_redis_test_url: Optional[str] = None,
        override_redis_index_name: Optional[str] = None,
        override_redis_prefix: Optional[str] = None,
        override_redis_hash_prefix: Optional[str] = None,
        override_redis_hnsw_m: Optional[int] = None,
        override_redis_hnsw_ef_construction: Optional[int] = None,
        override_redis_hnsw_initial_cap: Optional[int] = None,
        override_redis_distance_metric: Optional[str] = None,
        override_embedding_model: Optional[str] = None,
        override_embedding_batch_size: Optional[int] = None,
        override_embedding_dim: Optional[int] = None,
        override_min_chunk_size: Optional[int] = None,
        override_max_chunk_size: Optional[int] = None,
        override_quality_threshold: Optional[int] = None,
        override_quality_min_retention_ratio: Optional[float] = None,
        override_quality_max_retention_ratio: Optional[float] = None,
        override_max_file_size_mb: Optional[int] = None,
        override_max_pdf_pages: Optional[int] = None,
        override_max_docx_expansion_ratio: Optional[float] = None,
        override_max_docx_uncompressed_mb: Optional[int] = None,
        override_api_max_retries: Optional[int] = None,
        override_api_retry_delay: Optional[float] = None,
        override_pdf_render_dpi: Optional[int] = None,
        override_pdf_ocr_dpi: Optional[int] = None,
        override_pdf_text_first_min_chars: Optional[int] = None,
        override_pdf_scanned_min_chars: Optional[int] = None,
        override_pdf_obfuscated_ufffd_threshold: Optional[int] = None,
        override_pdf_obfuscated_strikethrough_threshold: Optional[int] = None,
        override_vision_review_max_pages: Optional[int] = None,
        override_search_default_top_k: Optional[int] = None,
        override_search_min_score: Optional[float] = None,
        override_extra_skill_patterns: Optional[List[str]] = None,
        override_output_dir: Optional[str] = None,
        override_quarantine_dir: Optional[str] = None,
        override_audit_report: Optional[str] = None,
        override_scorecard_dir: Optional[str] = None,
        override_log_level: Optional[str] = None,
        override_log_file: Optional[str] = None,
        override_log_max_bytes: Optional[int] = None,
        override_log_backup_count: Optional[int] = None,
        override_web_host: Optional[str] = None,
        override_web_port: Optional[int] = None,
        override_web_engine: Optional[str] = None,
    ) -> "AppConfig":
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            # 若未安裝 python-dotenv，跳過並由系統環境變數讀取
            pass

        api_key = override_api_key or os.environ.get("GEMINI_API_KEY", "")
        model = override_model or os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
        
        env_review = os.environ.get("GEMINI_REVIEW", "").strip().lower() in ("1", "true", "yes")
        review = override_review if override_review is not None else env_review

        env_judge = os.environ.get("GEMINI_JUDGE", "").strip().lower() in ("1", "true", "yes")
        judge = override_judge if override_judge is not None else env_judge

        gemini_temperature = (
            override_gemini_temperature
            if override_gemini_temperature is not None
            else _safe_float(os.environ.get("GEMINI_TEMPERATURE"), 0.2)
        )
        gemini_max_output_tokens = (
            override_gemini_max_output_tokens
            if override_gemini_max_output_tokens is not None
            else _safe_int(os.environ.get("GEMINI_MAX_OUTPUT_TOKENS"), 8192)
        )

        redis_url = override_redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        redis_test_url = override_redis_test_url or os.environ.get("REDIS_TEST_URL", "redis://localhost:6379/15")
        redis_index_name = override_redis_index_name or os.environ.get("REDIS_INDEX_NAME", "idx:resumes:v1")
        redis_prefix = override_redis_prefix or os.environ.get("REDIS_PREFIX", "resume:v1:chunk:")
        redis_hash_prefix = override_redis_hash_prefix or os.environ.get("REDIS_HASH_PREFIX", "resume:v1:hash:")
        
        redis_hnsw_m = (
            override_redis_hnsw_m
            if override_redis_hnsw_m is not None
            else _safe_int(os.environ.get("REDIS_HNSW_M"), 16)
        )
        redis_hnsw_ef_construction = (
            override_redis_hnsw_ef_construction
            if override_redis_hnsw_ef_construction is not None
            else _safe_int(os.environ.get("REDIS_HNSW_EF_CONSTRUCTION"), 200)
        )
        redis_hnsw_initial_cap = (
            override_redis_hnsw_initial_cap
            if override_redis_hnsw_initial_cap is not None
            else _safe_int(os.environ.get("REDIS_HNSW_INITIAL_CAP"), 1000)
        )
        redis_distance_metric = override_redis_distance_metric or os.environ.get("REDIS_DISTANCE_METRIC", "COSINE")

        embedding_model = override_embedding_model or os.environ.get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
        
        embedding_batch_size = (
            override_embedding_batch_size
            if override_embedding_batch_size is not None
            else _safe_int(os.environ.get("EMBEDDING_BATCH_SIZE"), 20)
        )
        embedding_dim = (
            override_embedding_dim
            if override_embedding_dim is not None
            else _safe_int(os.environ.get("EMBEDDING_DIM"), 768)
        )

        min_chunk_size = (
            override_min_chunk_size
            if override_min_chunk_size is not None
            else _safe_int(os.environ.get("MIN_CHUNK_SIZE"), 80)
        )
        max_chunk_size = (
            override_max_chunk_size
            if override_max_chunk_size is not None
            else _safe_int(os.environ.get("MAX_CHUNK_SIZE"), 1500)
        )

        quality_threshold = (
            override_quality_threshold
            if override_quality_threshold is not None
            else _safe_int(os.environ.get("QUALITY_THRESHOLD"), 65)
        )
        quality_min_retention_ratio = (
            override_quality_min_retention_ratio
            if override_quality_min_retention_ratio is not None
            else _safe_float(os.environ.get("QUALITY_MIN_RETENTION_RATIO"), 0.35)
        )
        quality_max_retention_ratio = (
            override_quality_max_retention_ratio
            if override_quality_max_retention_ratio is not None
            else _safe_float(os.environ.get("QUALITY_MAX_RETENTION_RATIO"), 3.5)
        )

        max_file_size_mb = (
            override_max_file_size_mb
            if override_max_file_size_mb is not None
            else _safe_int(os.environ.get("MAX_FILE_SIZE_MB"), 25)
        )
        max_pdf_pages = (
            override_max_pdf_pages
            if override_max_pdf_pages is not None
            else _safe_int(os.environ.get("MAX_PDF_PAGES"), 30)
        )
        max_docx_expansion_ratio = (
            override_max_docx_expansion_ratio
            if override_max_docx_expansion_ratio is not None
            else _safe_float(os.environ.get("MAX_DOCX_EXPANSION_RATIO"), 10.0)
        )
        max_docx_uncompressed_mb = (
            override_max_docx_uncompressed_mb
            if override_max_docx_uncompressed_mb is not None
            else _safe_int(os.environ.get("MAX_DOCX_UNCOMPRESSED_MB"), 100)
        )

        api_max_retries = (
            override_api_max_retries
            if override_api_max_retries is not None
            else _safe_int(os.environ.get("API_MAX_RETRIES"), 3)
        )
        api_retry_delay = (
            override_api_retry_delay
            if override_api_retry_delay is not None
            else _safe_float(os.environ.get("API_RETRY_DELAY"), 2.0)
        )

        pdf_render_dpi = (
            override_pdf_render_dpi
            if override_pdf_render_dpi is not None
            else _safe_int(os.environ.get("PDF_RENDER_DPI"), 150)
        )
        pdf_ocr_dpi = (
            override_pdf_ocr_dpi
            if override_pdf_ocr_dpi is not None
            else _safe_int(os.environ.get("PDF_OCR_DPI"), 200)
        )
        pdf_text_first_min_chars = (
            override_pdf_text_first_min_chars
            if override_pdf_text_first_min_chars is not None
            else _safe_int(os.environ.get("PDF_TEXT_FIRST_MIN_CHARS"), 50)
        )
        pdf_scanned_min_chars = (
            override_pdf_scanned_min_chars
            if override_pdf_scanned_min_chars is not None
            else _safe_int(os.environ.get("PDF_SCANNED_MIN_CHARS"), 30)
        )
        pdf_obfuscated_ufffd_threshold = (
            override_pdf_obfuscated_ufffd_threshold
            if override_pdf_obfuscated_ufffd_threshold is not None
            else _safe_int(os.environ.get("PDF_OBFUSCATED_UFFFD_THRESHOLD"), 10)
        )
        pdf_obfuscated_strikethrough_threshold = (
            override_pdf_obfuscated_strikethrough_threshold
            if override_pdf_obfuscated_strikethrough_threshold is not None
            else _safe_int(os.environ.get("PDF_OBFUSCATED_STRIKETHROUGH_THRESHOLD"), 30)
        )
        vision_review_max_pages = (
            override_vision_review_max_pages
            if override_vision_review_max_pages is not None
            else _safe_int(os.environ.get("VISION_REVIEW_MAX_PAGES"), 5)
        )

        search_default_top_k = (
            override_search_default_top_k
            if override_search_default_top_k is not None
            else _safe_int(os.environ.get("SEARCH_DEFAULT_TOP_K"), 5)
        )
        search_min_score = (
            override_search_min_score
            if override_search_min_score is not None
            else _safe_float(os.environ.get("SEARCH_MIN_SCORE"), 0.0)
        )

        extra_skill_patterns = (
            override_extra_skill_patterns
            if override_extra_skill_patterns is not None
            else _safe_list(os.environ.get("EXTRA_SKILL_PATTERNS"))
        )

        default_output = override_output_dir or os.environ.get("DEFAULT_OUTPUT_DIR")
        default_quarantine = override_quarantine_dir or os.environ.get("DEFAULT_QUARANTINE_DIR")
        default_audit = override_audit_report or os.environ.get("DEFAULT_AUDIT_REPORT")
        default_scorecard = override_scorecard_dir or os.environ.get("DEFAULT_SCORECARD_DIR")

        log_level = override_log_level or os.environ.get("LOG_LEVEL", "INFO").strip().upper()
        log_file = override_log_file if override_log_file is not None else os.environ.get("LOG_FILE", "logs/app.log")
        log_max_bytes = (
            override_log_max_bytes
            if override_log_max_bytes is not None
            else _safe_int(os.environ.get("LOG_MAX_BYTES"), 10 * 1024 * 1024)
        )
        log_backup_count = (
            override_log_backup_count
            if override_log_backup_count is not None
            else _safe_int(os.environ.get("LOG_BACKUP_COUNT"), 5)
        )

        web_host = override_web_host or os.environ.get("WEB_HOST", "127.0.0.1")
        web_port = (
            override_web_port
            if override_web_port is not None
            else _safe_int(os.environ.get("WEB_PORT"), 8080)
        )
        web_engine = override_web_engine or os.environ.get("WEB_ENGINE", "auto").strip().lower()

        recruit_fields = dict(
            recruit_chat_enabled=_safe_bool(os.environ.get("RECRUIT_CHAT_ENABLED"), True),
            recruit_llm_model=(os.environ.get("RECRUIT_LLM_MODEL") or "").strip() or model,
            recruit_llm_temperature=_safe_float(os.environ.get("RECRUIT_LLM_TEMPERATURE"), 0.2),
            recruit_llm_max_output_tokens=_safe_int(os.environ.get("RECRUIT_LLM_MAX_OUTPUT_TOKENS"), 2048),
            recruit_llm_timeout_seconds=_safe_float(os.environ.get("RECRUIT_LLM_TIMEOUT_SECONDS"), 45.0),
            recruit_profile_max_output_tokens=_safe_int(os.environ.get("RECRUIT_PROFILE_MAX_OUTPUT_TOKENS"), 1024),
            recruit_narrative_max_output_tokens=_safe_int(os.environ.get("RECRUIT_NARRATIVE_MAX_OUTPUT_TOKENS"), 8192),
            recruit_llm_thinking_budget=_safe_optional_int(os.environ.get("RECRUIT_LLM_THINKING_BUDGET")),
            recruit_skill_lexical_min_chars=_safe_int(os.environ.get("RECRUIT_SKILL_LEXICAL_MIN_CHARS"), 3),
            recruit_skill_mention_snippet_chars=_safe_int(os.environ.get("RECRUIT_SKILL_MENTION_SNIPPET_CHARS"), 80),
            recruit_skill_version_strip_exempt=_safe_list(
                os.environ.get("RECRUIT_SKILL_VERSION_STRIP_EXEMPT") or DEFAULT_SKILL_VERSION_STRIP_EXEMPT),
            recruit_skill_lexical_alias_denylist=_safe_list(
                os.environ.get("RECRUIT_SKILL_LEXICAL_ALIAS_DENYLIST") or DEFAULT_SKILL_LEXICAL_ALIAS_DENYLIST),
            recruit_retrieval_top_k_chunks=_safe_int(os.environ.get("RECRUIT_RETRIEVAL_TOP_K_CHUNKS"), 60),
            recruit_retrieval_min_score=_safe_float(os.environ.get("RECRUIT_RETRIEVAL_MIN_SCORE"), 0.5),
            recruit_candidate_pool_size=_safe_int(os.environ.get("RECRUIT_CANDIDATE_POOL_SIZE"), 15),
            recruit_candidate_pool_max=_safe_int(os.environ.get("RECRUIT_CANDIDATE_POOL_MAX"), 30),
            recruit_shortlist_size=_safe_int(os.environ.get("RECRUIT_SHORTLIST_SIZE"), 3),
            recruit_shortlist_max=_safe_int(os.environ.get("RECRUIT_SHORTLIST_MAX"), 10),
            recruit_max_must_requirements=_safe_int(os.environ.get("RECRUIT_MAX_MUST_REQUIREMENTS"), 12),
            recruit_max_intents_per_turn=_safe_int(os.environ.get("RECRUIT_MAX_INTENTS_PER_TURN"), 2),
            recruit_jd_intent_min_chars=_safe_int(os.environ.get("RECRUIT_JD_INTENT_MIN_CHARS"), 200),
            recruit_profile_max_resume_chars=_safe_int(os.environ.get("RECRUIT_PROFILE_MAX_RESUME_CHARS"), 12000),
            recruit_profile_max_concurrency=_safe_int(os.environ.get("RECRUIT_PROFILE_MAX_CONCURRENCY"), 8),
            recruit_profile_negative_cache_ttl_seconds=_safe_int(
                os.environ.get("RECRUIT_PROFILE_NEGATIVE_CACHE_TTL_SECONDS"), 600),
            recruit_profile_cache_prefix=(os.environ.get("RECRUIT_PROFILE_CACHE_PREFIX") or "").strip() or "recruit:v1:profile:",
            recruit_jd_cache_prefix=(os.environ.get("RECRUIT_JD_CACHE_PREFIX") or "").strip() or "recruit:v1:jd:",
            recruit_profile_cache_ttl_seconds=_safe_int(os.environ.get("RECRUIT_PROFILE_CACHE_TTL_SECONDS"), 2592000),
            recruit_evidence_min_chars=_safe_int(os.environ.get("RECRUIT_EVIDENCE_MIN_CHARS"), 4),
            recruit_default_interview_questions=_safe_int(os.environ.get("RECRUIT_DEFAULT_INTERVIEW_QUESTIONS"), 3),
            recruit_max_interview_questions=_safe_int(os.environ.get("RECRUIT_MAX_INTERVIEW_QUESTIONS"), 10),
            recruit_max_message_chars=_safe_int(os.environ.get("RECRUIT_MAX_MESSAGE_CHARS"), 12000),
            recruit_max_llm_calls_per_turn=_safe_int(os.environ.get("RECRUIT_MAX_LLM_CALLS_PER_TURN"), 25),
            recruit_turn_timeout_seconds=_safe_float(os.environ.get("RECRUIT_TURN_TIMEOUT_SECONDS"), 150.0),
            recruit_circuit_breaker_cooldown_seconds=_safe_float(os.environ.get("RECRUIT_CIRCUIT_BREAKER_COOLDOWN_SECONDS"), 60.0),
            recruit_protected_attr_terms=_safe_list(os.environ.get("RECRUIT_PROTECTED_ATTR_TERMS") or DEFAULT_PROTECTED_ATTR_TERMS),
            recruit_skill_aliases=_safe_mapping(os.environ.get("RECRUIT_SKILL_ALIASES") or DEFAULT_SKILL_ALIASES),
            chat_checkpointer_backend=(os.environ.get("CHAT_CHECKPOINTER_BACKEND") or "memory").strip().lower(),
            chat_checkpoint_redis_url=(os.environ.get("CHAT_CHECKPOINT_REDIS_URL") or "").strip() or redis_url,
            chat_session_ttl_seconds=_safe_int(os.environ.get("CHAT_SESSION_TTL_SECONDS"), 3600),
            chat_history_max_turns=_safe_int(os.environ.get("CHAT_HISTORY_MAX_TURNS"), 10),
            chat_history_max_chars=_safe_int(os.environ.get("CHAT_HISTORY_MAX_CHARS"), 24000),
            chat_session_max_turns=_safe_int(os.environ.get("CHAT_SESSION_MAX_TURNS"), 50),
            chat_memory_max_sessions=_safe_int(os.environ.get("CHAT_MEMORY_MAX_SESSIONS"), 200),
            chat_session_lock_ttl_buffer_seconds=_safe_int(os.environ.get("CHAT_SESSION_LOCK_TTL_BUFFER_SECONDS"), 30),
            recruit_tracing_enabled=_safe_bool(os.environ.get("RECRUIT_TRACING_ENABLED"), False),
            langsmith_api_key=(os.environ.get("LANGSMITH_API_KEY") or "").strip(),
            langsmith_endpoint=(os.environ.get("LANGSMITH_ENDPOINT") or "").strip(),
            langsmith_project=(os.environ.get("LANGSMITH_PROJECT") or "").strip() or "recruitment-assistant",
            recruit_tracing_sampling_rate=_clamp_unit(
                _safe_float(os.environ.get("RECRUIT_TRACING_SAMPLING_RATE"), 1.0)),
            recruit_tracing_flush_timeout_seconds=max(
                _safe_float(os.environ.get("RECRUIT_TRACING_FLUSH_TIMEOUT_SECONDS"), 5.0), 0.0),
        )

        return cls(
            gemini_api_key=api_key,
            gemini_model=model,
            gemini_review=review,
            gemini_judge=judge,
            gemini_temperature=gemini_temperature,
            gemini_max_output_tokens=gemini_max_output_tokens,
            redis_url=redis_url,
            redis_test_url=redis_test_url,
            redis_index_name=redis_index_name,
            redis_prefix=redis_prefix,
            redis_hash_prefix=redis_hash_prefix,
            redis_hnsw_m=redis_hnsw_m,
            redis_hnsw_ef_construction=redis_hnsw_ef_construction,
            redis_hnsw_initial_cap=redis_hnsw_initial_cap,
            redis_distance_metric=redis_distance_metric,
            embedding_model=embedding_model,
            embedding_batch_size=embedding_batch_size,
            embedding_dim=embedding_dim,
            min_chunk_size=min_chunk_size,
            max_chunk_size=max_chunk_size,
            quality_threshold=quality_threshold,
            quality_min_retention_ratio=quality_min_retention_ratio,
            quality_max_retention_ratio=quality_max_retention_ratio,
            max_file_size_mb=max_file_size_mb,
            max_pdf_pages=max_pdf_pages,
            max_docx_expansion_ratio=max_docx_expansion_ratio,
            max_docx_uncompressed_mb=max_docx_uncompressed_mb,
            api_max_retries=api_max_retries,
            api_retry_delay=api_retry_delay,
            pdf_render_dpi=pdf_render_dpi,
            pdf_ocr_dpi=pdf_ocr_dpi,
            pdf_text_first_min_chars=pdf_text_first_min_chars,
            pdf_scanned_min_chars=pdf_scanned_min_chars,
            pdf_obfuscated_ufffd_threshold=pdf_obfuscated_ufffd_threshold,
            pdf_obfuscated_strikethrough_threshold=pdf_obfuscated_strikethrough_threshold,
            vision_review_max_pages=vision_review_max_pages,
            search_default_top_k=search_default_top_k,
            search_min_score=search_min_score,
            extra_skill_patterns=extra_skill_patterns,
            default_output_dir=default_output,
            default_quarantine_dir=default_quarantine,
            default_audit_report=default_audit,
            default_scorecard_dir=default_scorecard,
            log_level=log_level,
            log_file=log_file,
            log_max_bytes=log_max_bytes,
            log_backup_count=log_backup_count,
            web_host=web_host,
            web_port=web_port,
            web_engine=web_engine,
            **recruit_fields,
            **_search_expansion_fields(recruit_fields),
        )
