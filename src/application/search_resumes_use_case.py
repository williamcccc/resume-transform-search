import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.application.dto import WebSearchRequestDTO, WebSearchResponseDTO
from src.domain.interfaces import IEmbeddingService, IVectorStore, IExperienceParser
from src.domain.models import SearchQuery, SearchResultItem, CandidateSummary

logger = logging.getLogger(__name__)


class SearchResumesUseCase:
    """
    履歷自然語言語意檢索核心使用案例
    """

    def __init__(
        self,
        embedding_service: IEmbeddingService,
        vector_store: IVectorStore,
        markdown_base_dir: Optional[Path] = None,
        experience_parser: Optional[IExperienceParser] = None,
    ):
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.markdown_base_dir = markdown_base_dir or Path("data/markdown_out")
        self.experience_parser = experience_parser

    def execute(self, query: SearchQuery) -> List[SearchResultItem]:
        if not query.query_text or not query.query_text.strip():
            return []

        # 1. 取得自然語言查詢之 768 維 Embedding
        query_vector = self.embedding_service.embed_query(query.query_text.strip())

        # 2. 執行 RediSearch KNN + Tag 混合檢索
        results = self.vector_store.search(query_vector=query_vector, query=query)
        return results

    def execute_grouped_by_candidate(self, query: SearchQuery) -> List[Dict[str, Any]]:
        """
        將檢索結果依候選人歸併，便於 HR 綜合評估候選人整體符合度
        """
        chunk_results = self.execute(query)
        grouped: Dict[str, Dict[str, Any]] = {}

        for item in chunk_results:
            cid = item.candidate_id
            if cid not in grouped:
                grouped[cid] = {
                    "candidate_id": cid,
                    "candidate_name": item.candidate_name,
                    "max_score": item.score,
                    "matched_chunks": [],
                    "all_skills": set(),
                    "file_path": item.file_path,
                }
            grouped[cid]["max_score"] = max(grouped[cid]["max_score"], item.score)
            grouped[cid]["matched_chunks"].append(item)
            for s in item.skills:
                grouped[cid]["all_skills"].add(s)

        aggregated = []
        for g in grouped.values():
            g["all_skills"] = sorted(list(g["all_skills"]))
            aggregated.append(g)

        aggregated.sort(key=lambda x: x["max_score"], reverse=True)
        return aggregated

    def execute_web_search(self, dto: WebSearchRequestDTO) -> WebSearchResponseDTO:
        """
        Web 端複合查詢：結合自然語言語意搜尋與制式年資/標籤過濾
        """
        query = SearchQuery(
            query_text=dto.query_text,
            top_k=dto.top_k,
            chunk_type=dto.chunk_type if dto.chunk_type and dto.chunk_type != "ALL" else None,
            skills_filter=dto.skills,
            min_score=dto.min_score,
            min_years=dto.min_years,
        )

        chunk_results = self.execute(query)

        if not dto.group_by_candidate:
            unique_cand_ids = set(c.candidate_id for c in chunk_results)
            return WebSearchResponseDTO(
                total_candidates=len(unique_cand_ids),
                total_chunks=len(chunk_results),
                query_text=dto.query_text,
                candidates=[],
                raw_chunks=chunk_results,
            )

        # 候選人整合分組
        grouped_chunks: Dict[str, List[SearchResultItem]] = {}
        for item in chunk_results:
            grouped_chunks.setdefault(item.candidate_id, []).append(item)

        candidate_summaries: List[CandidateSummary] = []
        for cid, chunks in grouped_chunks.items():
            first_chunk = chunks[0]
            cand_name = first_chunk.candidate_name
            file_path_str = first_chunk.file_path

            # 嘗試讀取履歷全文以精確解析年資
            resume_text = self._read_candidate_text(cid, file_path_str)
            if not resume_text:
                # 回退：從命中的切片組合文字中解析
                resume_text = "\n".join(c.content for c in chunks)

            years_val, raw_exp = None, None
            if self.experience_parser:
                years_val, raw_exp = self.experience_parser.parse(resume_text)

            # 制式條件過濾：最低工作年資 (min_years)
            if dto.min_years is not None and dto.min_years > 0:
                if years_val is None or years_val < dto.min_years:
                    continue

            # 整合技術標籤與最高分
            max_score = max(c.score for c in chunks)
            all_skills = sorted(list({s for c in chunks for s in c.skills if s}))

            candidate_summaries.append(
                CandidateSummary(
                    candidate_id=cid,
                    candidate_name=cand_name,
                    max_score=round(max_score, 4),
                    years_of_experience=years_val,
                    experience_raw=raw_exp,
                    all_skills=all_skills,
                    matched_chunks=chunks,
                    file_path=file_path_str,
                )
            )

        # 依最高相似度降序排序
        candidate_summaries.sort(key=lambda x: x.max_score, reverse=True)

        return WebSearchResponseDTO(
            total_candidates=len(candidate_summaries),
            total_chunks=len(chunk_results),
            query_text=dto.query_text,
            candidates=candidate_summaries,
            raw_chunks=chunk_results,
        )

    def get_resume_markdown(self, candidate_id: str) -> Optional[str]:
        """
        安全讀取候選人原始 Markdown 檔案，防止路徑遍歷越權
        """
        if not candidate_id or ".." in candidate_id or "/" in candidate_id or "\\" in candidate_id:
            return None

        # 尋找候選人檔案
        candidate_file = self._find_candidate_file(candidate_id)
        if candidate_file and candidate_file.exists():
            try:
                with open(candidate_file, "r", encoding="utf-8", errors="replace") as f:
                    return f.read()
            except Exception as err:
                logger.warning(f"讀取候選人履歷檔案 [{candidate_file}] 異常: {err}")
                return None
        return None

    def _read_candidate_text(self, candidate_id: str, file_path_str: Optional[str]) -> Optional[str]:
        """安全讀取候選人文字內容"""
        if file_path_str:
            p = Path(file_path_str)
            if p.exists() and p.is_file():
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as f:
                        return f.read()
                except Exception as err:
                    logger.warning(f"依 file_path 讀取履歷異常 [{p}]: {err}")

        # 透過 candidate_id 尋找
        cf = self._find_candidate_file(candidate_id)
        if cf and cf.exists():
            try:
                with open(cf, "r", encoding="utf-8", errors="replace") as f:
                    return f.read()
            except Exception as err:
                logger.warning(f"依 candidate_id 讀取履歷異常 [{cf}]: {err}")
        return None

    def _find_candidate_file(self, candidate_id: str) -> Optional[Path]:
        """在 markdown 目錄中遞迴尋找指定候選人檔案"""
        search_dirs = [self.markdown_base_dir, Path("data/markdown_out"), Path("resume/markdown_out")]
        for base in search_dirs:
            if not base.exists():
                continue
            # 優先找精確檔名 <candidate_id>.md
            exact = base / f"{candidate_id}.md"
            if exact.exists():
                return exact
            # 遞迴搜尋
            for f in base.rglob(f"*{candidate_id}*.md"):
                if f.is_file():
                    return f
        return None
