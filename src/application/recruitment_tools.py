"""
招募助手工具層：既有 Use Case 之薄包裝 (ADR-0019)

僅包裝 SearchResumesUseCase 與 IExperienceParser，不擴大既有技術債（風險 R6）。
"""
import logging
from typing import List, Optional, Protocol, Tuple

from src.domain.interfaces import IExperienceParser
from src.domain.models import CandidateSummary, SearchQuery

logger = logging.getLogger(__name__)


class _CandidateSearchPort(Protocol):
    def execute_grouped_by_candidate(self, query: SearchQuery) -> List[dict]:
        ...

    def get_resume_markdown(self, candidate_id: str) -> Optional[str]:
        ...


class RecruitmentTools:
    def __init__(self, search_use_case: _CandidateSearchPort, experience_parser: Optional[IExperienceParser] = None):
        self._search = search_use_case
        self._parser = experience_parser

    def retrieve_candidate_pool(self, retrieval_query: str, top_k_chunks: int, pool_size: int,
                                min_score: float) -> List[CandidateSummary]:
        """包裝 execute_grouped_by_candidate，依候選人最高分取 Top-N"""
        if not retrieval_query or not retrieval_query.strip():
            return []
        query = SearchQuery(query_text=retrieval_query.strip(), top_k=top_k_chunks, min_score=min_score)
        grouped = self._search.execute_grouped_by_candidate(query)
        pool: List[CandidateSummary] = []
        for g in grouped[: max(pool_size, 0)]:
            pool.append(CandidateSummary(
                candidate_id=str(g.get("candidate_id", "")),
                candidate_name=str(g.get("candidate_name", "")),
                max_score=float(g.get("max_score", 0.0)),
                all_skills=list(g.get("all_skills", []) or []),
                matched_chunks=list(g.get("matched_chunks", []) or []),
                file_path=g.get("file_path"),
            ))
        return [c for c in pool if c.candidate_id]

    def load_resume_text(self, candidate: CandidateSummary) -> str:
        """讀取履歷全文；讀取失敗時回退為命中切片內容組合"""
        text: Optional[str] = None
        try:
            text = self._search.get_resume_markdown(candidate.candidate_id)
        except Exception as err:  # 讀檔失敗不阻斷對話，改用切片回退
            logger.warning("履歷全文讀取失敗，改用切片回退 (err_type=%s)", type(err).__name__)
        if text:
            return text
        return "\n".join(getattr(c, "content", "") or "" for c in candidate.matched_chunks)

    def parse_years(self, text: str) -> Tuple[Optional[float], Optional[str]]:
        if not self._parser:
            return None, None
        try:
            return self._parser.parse(text)
        except Exception as err:
            logger.warning("年資正則解析失敗 (err_type=%s)", type(err).__name__)
            return None, None
