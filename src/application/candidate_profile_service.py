"""
候選人 Profile 查詢期延遲抽取服務 (ADR-0019)

內容 Hash + extractor_version 雙鍵快取（未變更履歷 0 Token，AC-13~15）、
逐欄逐字證據驗證（AC-09）、抽取失敗降級（AC-16）與單輪 LLM 預算熔斷（AC-17）。
"""
import contextvars
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field, replace
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from src.domain.exceptions import LlmQuotaExhaustedError
from src.domain.interfaces import ICandidateProfileCache, ICandidateProfileExtractor
from src.domain.models import CandidateSummary
from src.domain.recruitment import CandidateProfile, EvidenceQuote
from src.domain.recruitment_services import (
    EvidenceVerifier,
    ProtectedAttributeGuard,
    compute_content_hash,
    mask_contact_info,
)
from src.application.recruitment_tools import RecruitmentTools

logger = logging.getLogger(__name__)


class TurnBudget:
    """單輪 LLM 呼叫預算（執行緒安全）"""

    def __init__(self, limit: int):
        self._limit = max(int(limit), 0)
        self._used = 0
        self._lock = threading.Lock()

    def try_consume(self) -> bool:
        with self._lock:
            if self._used >= self._limit:
                return False
            self._used += 1
            return True

    @property
    def used(self) -> int:
        with self._lock:
            return self._used

    @property
    def exhausted(self) -> bool:
        with self._lock:
            return self._used >= self._limit


@dataclass
class ProfileBatchResult:
    profiles: Dict[str, CandidateProfile] = field(default_factory=dict)
    llm_texts: Dict[str, str] = field(default_factory=dict)
    match_texts: Dict[str, str] = field(default_factory=dict)  # 遮蔽後、未截斷全文（詞面比對用；載入失敗為 ""）
    warnings: List[str] = field(default_factory=list)
    cache_hits: int = 0
    cache_misses: int = 0
    negative_hits: int = 0


class CandidateProfileService:
    def __init__(
        self,
        extractor: ICandidateProfileExtractor,
        cache: ICandidateProfileCache,
        tools: RecruitmentTools,
        guard: ProtectedAttributeGuard,
        verifier: EvidenceVerifier,
        max_resume_chars: int,
        max_concurrency: int,
        negative_cache_ttl_seconds: float = 0.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._extractor = extractor
        self._cache = cache
        self._tools = tools
        self._guard = guard
        self._verifier = verifier
        self._max_chars = max(int(max_resume_chars), 1)
        self._max_concurrency = max(int(max_concurrency), 1)
        # 抽取失敗之短期負快取（行程內）：(candidate_id, content_hash, extractor_version) -> 到期時間
        self._negative_ttl = max(float(negative_cache_ttl_seconds), 0.0)
        self._clock = clock
        self._negative: Dict[Tuple[str, str, str], float] = {}
        self._negative_lock = threading.Lock()

    def prepare_match_text(self, resume_text: str, names: Sequence[str], alias: str) -> str:
        """受保護欄位行遮蔽 → 姓名/聯絡方式遮蔽（不截斷，僅供伺服器端確定性比對，不送 LLM）"""
        redacted = self._guard.redact_resume(resume_text)
        return mask_contact_info(redacted, names, alias)

    def prepare_llm_text(self, resume_text: str, names: Sequence[str], alias: str) -> str:
        """受保護欄位行遮蔽 → 姓名/聯絡方式遮蔽 → 截斷"""
        return self.prepare_match_text(resume_text, names, alias)[: self._max_chars]

    def get_profiles(
        self,
        pool: Sequence[CandidateSummary],
        budget: TurnBudget,
        check_deadline: Optional[Callable[[], None]] = None,
        remaining_seconds: Optional[Callable[[], float]] = None,
    ) -> ProfileBatchResult:
        result = ProfileBatchResult()
        version = self._extractor.extractor_version
        pending: List[Tuple[CandidateSummary, str, str]] = []
        negative_hits = 0

        # 1~2. 讀取全文 → 內容 Hash → 快取查詢
        for cand in pool:
            raw_text = self._tools.load_resume_text(cand)
            content_hash = compute_content_hash(raw_text)
            match_text = self.prepare_match_text(raw_text, [cand.candidate_name], "候選人")
            llm_text = match_text[: self._max_chars]
            result.match_texts[cand.candidate_id] = match_text
            result.llm_texts[cand.candidate_id] = llm_text
            cached = self._safe_cache_get(cand.candidate_id, content_hash, version)
            if cached is not None:
                result.cache_hits += 1
                result.profiles[cand.candidate_id] = cached
            elif self._negative_hit(cand.candidate_id, content_hash, version):
                negative_hits += 1
                result.profiles[cand.candidate_id] = self._degraded_profile(cand, content_hash, llm_text, version)
            else:
                result.cache_misses += 1
                pending.append((cand, content_hash, llm_text))

        result.negative_hits = negative_hits
        if negative_hits:
            result.warnings.append(
                f"{negative_hits} 位人選近期結構化抽取失敗，暫以年資正則與技能標籤回退資料（負快取冷卻中）")
        if not pending:
            return result

        # 3. 預算檢查：超出者降級
        to_extract: List[Tuple[CandidateSummary, str, str]] = []
        budget_exceeded = 0
        for cand, content_hash, llm_text in pending:
            if check_deadline:
                check_deadline()
            if budget.try_consume():
                to_extract.append((cand, content_hash, llm_text))
            else:
                budget_exceeded += 1
                result.profiles[cand.candidate_id] = self._degraded_profile(cand, content_hash, llm_text, version)
        if budget_exceeded:
            result.warnings.append(f"單輪 LLM 呼叫預算已用罄，{budget_exceeded} 位人選改用正則與標籤回退資料")

        # 4. 有界執行緒池並行抽取
        failures = 0
        downgraded = 0
        timed_out = 0
        quota_error: Optional[LlmQuotaExhaustedError] = None
        if to_extract:
            # 不使用 with：逾時時須 shutdown(wait=False) 立即返回，不等待仍在執行之抽取（由 finally 保證釋放）
            executor = ThreadPoolExecutor(max_workers=min(self._max_concurrency, len(to_extract)))
            try:
                # 每個 Future 各自複製呼叫端 contextvars（含追蹤脈絡，ADR-0020）；同一 Context 不可併發進入
                futures = [
                    (cand, content_hash, llm_text,
                     executor.submit(contextvars.copy_context().run, self._extractor.extract,
                                     cand.candidate_id, llm_text, content_hash))
                    for cand, content_hash, llm_text in to_extract
                ]
                for cand, content_hash, llm_text, future in futures:
                    try:
                        timeout = max(remaining_seconds(), 0.0) if remaining_seconds else None
                        raw_profile = future.result(timeout=timeout)
                    except FutureTimeoutError:
                        timed_out += 1
                        future.cancel()
                        result.profiles[cand.candidate_id] = self._degraded_profile(cand, content_hash, llm_text, version)
                        continue
                    except LlmQuotaExhaustedError as err:
                        quota_error = quota_error or err
                        continue
                    except Exception as err:
                        failures += 1
                        logger.warning("候選人 Profile 抽取失敗，改用降級資料 (err_type=%s)", type(err).__name__)
                        result.profiles[cand.candidate_id] = self._degraded_profile(cand, content_hash, llm_text, version)
                        self._remember_failure(cand.candidate_id, content_hash, version)
                        continue
                    verified, had_downgrade = self._verify_profile(raw_profile, cand, content_hash, llm_text, version)
                    downgraded += 1 if had_downgrade else 0
                    result.profiles[cand.candidate_id] = verified
                    self._forget_failure(cand.candidate_id, content_hash, version)
                    self._safe_cache_set(verified)
            finally:
                executor.shutdown(wait=False, cancel_futures=True)
        if quota_error is not None:
            raise quota_error
        if timed_out:
            result.warnings.append(f"{timed_out} 位人選結構化抽取逾時，已改用年資正則與技能標籤回退")
        if failures:
            result.warnings.append(f"{failures} 位人選結構化抽取失敗，已改用年資正則與技能標籤回退")
        if downgraded:
            result.warnings.append(f"{downgraded} 位人選部分欄位證據驗證失敗，已降為「履歷未提及」")
        return result

    # ------------------------------------------------------------------
    def _verify_profile(self, profile: CandidateProfile, cand: CandidateSummary, content_hash: str,
                        llm_text: str, version: str) -> Tuple[CandidateProfile, bool]:
        """逐欄證據驗證：無證據或驗證失敗之欄位一律設為 None (UNKNOWN)"""
        verified_ev: List[EvidenceQuote] = []
        verified_fields = set()
        for ev in profile.evidence:
            if self._verifier.verify(ev.quote, llm_text):
                verified_ev.append(EvidenceQuote(field=ev.field, quote=ev.quote, verified=True))
                verified_fields.add(ev.field)

        downgraded = False

        def keep(field_name: str, value):
            nonlocal downgraded
            if value is None:
                return None
            if field_name in verified_fields:
                return value
            downgraded = True
            return None

        skills, unverified_skills = [], []
        for skill in profile.core_skills:
            if f"skill:{skill}" in verified_fields:
                skills.append(skill)
            else:
                unverified_skills.append(skill)
                downgraded = True
        return CandidateProfile(
            candidate_id=cand.candidate_id,
            content_hash=content_hash,
            extractor_version=version,
            years_of_experience=keep("years", profile.years_of_experience),
            has_led_team=keep("has_led_team", profile.has_led_team),
            max_team_size=keep("team_size", profile.max_team_size),
            seniority=keep("seniority", profile.seniority),
            core_skills=tuple(skills),
            evidence=tuple(verified_ev),
            degraded=False,
            unverified_skills=tuple(unverified_skills),
        ), downgraded

    def _degraded_profile(self, cand: CandidateSummary, content_hash: str, llm_text: str,
                          version: str) -> CandidateProfile:
        years, raw = self._tools.parse_years(llm_text)
        evidence: Tuple[EvidenceQuote, ...] = ()
        if years is not None and raw and self._verifier.verify(raw, llm_text):
            evidence = (EvidenceQuote(field="years", quote=raw, verified=True),)
        return CandidateProfile(
            candidate_id=cand.candidate_id,
            content_hash=content_hash,
            extractor_version=version,
            years_of_experience=years,
            has_led_team=None,
            max_team_size=None,
            seniority=None,
            core_skills=tuple(cand.all_skills),
            evidence=evidence,
            degraded=True,
        )

    def _negative_hit(self, cid: str, content_hash: str, version: str) -> bool:
        if self._negative_ttl <= 0:
            return False
        key = (cid, content_hash, version)
        with self._negative_lock:
            expires = self._negative.get(key)
            if expires is None:
                return False
            if self._clock() >= expires:
                del self._negative[key]
                return False
            return True

    def _remember_failure(self, cid: str, content_hash: str, version: str) -> None:
        if self._negative_ttl <= 0:
            return
        now = self._clock()
        with self._negative_lock:
            # 惰性清除過期項，避免長時間執行之字典無界成長
            for key in [k for k, exp in self._negative.items() if now >= exp]:
                del self._negative[key]
            self._negative[(cid, content_hash, version)] = now + self._negative_ttl

    def _forget_failure(self, cid: str, content_hash: str, version: str) -> None:
        with self._negative_lock:
            self._negative.pop((cid, content_hash, version), None)

    def _safe_cache_get(self, cid: str, content_hash: str, version: str) -> Optional[CandidateProfile]:
        try:
            cached = self._cache.get_profile(cid, content_hash, version)
        except Exception as err:
            logger.warning("Profile 快取讀取失敗，視為未命中 (err_type=%s)", type(err).__name__)
            return None
        if cached is None or cached.content_hash != content_hash or cached.extractor_version != version:
            return None
        return replace(cached, candidate_id=cid)

    def _safe_cache_set(self, profile: CandidateProfile) -> None:
        if profile.degraded:
            return
        try:
            self._cache.set_profile(profile)
        except Exception as err:
            logger.warning("Profile 快取寫入失敗 (err_type=%s)", type(err).__name__)
