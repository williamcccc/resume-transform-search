"""
招募助手應用層設定 (ADR-0019)

由 Interfaces 層自 AppConfig 映射組裝；Application 層不 import AppConfig（維持既有 DIP 慣例）。
預設值與 AppConfig / .env.example 一致，僅供單元測試便利建構。
"""
from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class RecruitmentSettings:
    retrieval_top_k_chunks: int = 60
    retrieval_min_score: float = 0.5
    candidate_pool_size: int = 15
    candidate_pool_max: int = 30
    shortlist_size: int = 3
    shortlist_max: int = 10
    max_must_requirements: int = 12
    max_intents_per_turn: int = 2
    jd_intent_min_chars: int = 200
    profile_max_resume_chars: int = 12000
    profile_max_concurrency: int = 8
    profile_negative_cache_ttl_seconds: float = 600.0
    evidence_min_chars: int = 4
    default_interview_questions: int = 3
    max_interview_questions: int = 10
    max_message_chars: int = 12000
    max_llm_calls_per_turn: int = 25
    # 候選人不足時自動擴大檢索 (ADR-0021)；search_expansion_max_rounds=0 即停用
    search_expansion_max_rounds: int = 2
    search_expansion_pool_step: int = 10
    search_expansion_pool_max: int = 40
    search_expansion_top_k_chunks_max: int = 200
    search_expansion_min_score_step: float = 0.05
    search_expansion_min_score_floor: float = 0.4
    search_expansion_llm_reserve: int = 2
    search_expansion_min_remaining_seconds: float = 30.0
    # 放寬條件之人工決策 (ADR-0022)
    relaxation_hitl_enabled: bool = True
    relaxation_max_rounds: int = 2
    turn_timeout_seconds: float = 150.0
    session_max_turns: int = 50
    history_max_turns: int = 10
    history_max_chars: int = 24000
    protected_attr_terms: Tuple[str, ...] = ()
    skill_aliases: Dict[str, str] = field(default_factory=dict)
    skill_lexical_min_chars: int = 3
    skill_mention_snippet_chars: int = 80
    skill_version_strip_exempt: Tuple[str, ...] = ("web3", "b2b", "b2c", "e2e", "p2p", "base64", "utf8", "utf-8",
                                                    "sha256", "arm64")
    skill_lexical_alias_denylist: Tuple[str, ...] = ("node",)
