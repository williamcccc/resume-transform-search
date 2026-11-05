import logging
import re
import time
from typing import List, Optional, Any
import numpy as np
import redis
from redis.commands.search.field import TextField, TagField, VectorField
from redis.commands.search.index_definition import IndexDefinition, IndexType
from redis.commands.search.query import Query

from src.domain.enums import ChunkType
from src.domain.interfaces import IVectorStore
from src.domain.models import ResumeChunk, SearchQuery, SearchResultItem

logger = logging.getLogger(__name__)


def _escape_redis_tag(tag: str) -> str:
    """跳脫 RediSearch Tag 欄位保留符號"""
    return re.sub(r"([,.<>{}\[\]\"'\\:;!@#$%^&*()\-+=~|/ ])", r"\\\1", tag.strip())


def _safe_str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    return str(val)


class RedisVectorStore(IVectorStore):
    """
    基於 RediSearch 與 Redis HASH + HNSW 向量索引的履歷切片儲存與檢索實作
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        index_name: str = "idx:resumes:v1",
        prefix: str = "resume:v1:chunk:",
        hash_prefix: str = "resume:v1:hash:",
        hnsw_m: int = 16,
        hnsw_ef_construction: int = 200,
        hnsw_initial_cap: int = 1000,
        distance_metric: str = "COSINE",
    ):
        self.redis_url = redis_url
        self.index_name = index_name
        self.prefix = prefix
        self.hash_prefix = hash_prefix
        self.hnsw_m = hnsw_m
        self.hnsw_ef_construction = hnsw_ef_construction
        self.hnsw_initial_cap = hnsw_initial_cap
        self.distance_metric = distance_metric
        self._client: Optional[redis.Redis] = None

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(self.redis_url, decode_responses=False)
        return self._client

    def ensure_index(self, dim: int = 768, recreate: bool = False) -> None:
        """確保 RediSearch HNSW 向量索引已建立"""
        ft = self.client.ft(self.index_name)

        if recreate:
            try:
                ft.dropindex(delete_documents=False)
            except (redis.exceptions.RedisError, Exception) as err:
                logger.debug(f"刪除舊索引時忽略預期異常 (可能索引不存在): {err}")

        try:
            ft.info()
            # 索引已存在且無需重建
            return
        except (redis.exceptions.RedisError, Exception) as err:
            # 索引不存在，進行建立
            logger.debug(f"RediSearch 索引不存在，準備建立新索引: {err}")

        schema = (
            TagField("candidate_id"),
            TextField("candidate_name"),
            TagField("chunk_type"),
            TextField("section_title"),
            TextField("company"),
            TextField("job_title"),
            TagField("skills", separator=","),
            TextField("content"),
            TextField("file_path"),
            VectorField(
                "content_vector",
                "HNSW",
                {
                    "TYPE": "FLOAT32",
                    "DIM": dim,
                    "DISTANCE_METRIC": self.distance_metric,
                    "INITIAL_CAP": self.hnsw_initial_cap,
                    "M": self.hnsw_m,
                    "EF_CONSTRUCTION": self.hnsw_ef_construction,
                },
            ),
        )

        ft.create_index(
            schema,
            definition=IndexDefinition(
                prefix=[self.prefix],
                index_type=IndexType.HASH,
            ),
        )

    def upsert_chunks(self, chunks: List[ResumeChunk]) -> int:
        """批次將 ResumeChunk 寫入 Redis HASH"""
        if not chunks:
            return 0

        pipe = self.client.pipeline(transaction=False)
        count = 0

        for chunk in chunks:
            key = f"{self.prefix}{chunk.chunk_id}"
            vec_bytes = (
                np.array(chunk.vector, dtype=np.float32).tobytes()
                if chunk.vector is not None
                else b""
            )

            c_type_val = (
                chunk.chunk_type.value
                if isinstance(chunk.chunk_type, ChunkType)
                else str(chunk.chunk_type)
            )

            mapping = {
                "chunk_id": chunk.chunk_id,
                "candidate_id": chunk.candidate_id,
                "candidate_name": chunk.candidate_name,
                "chunk_type": c_type_val,
                "section_title": chunk.section_title or "",
                "company": chunk.company or "",
                "job_title": chunk.job_title or "",
                "skills": ",".join(chunk.skills) if chunk.skills else "",
                "content": chunk.content or "",
                "file_path": chunk.file_path or "",
                "content_hash": chunk.content_hash or "",
                "content_vector": vec_bytes,
            }
            pipe.hset(key, mapping=mapping)
            count += 1

        start_time = time.perf_counter()
        pipe.execute()
        elapsed = time.perf_counter() - start_time
        logger.info(
            "Redis 向量切片批次寫入成功 - 寫入筆數: %d, 耗時: %.3f 秒",
            count,
            elapsed,
        )
        return count

    def search(self, query_vector: List[float], query: SearchQuery) -> List[SearchResultItem]:
        """
        以 Cosine 相似度進行 KNN 向量檢索，並支援 Tag 混合過濾
        """
        filters: List[str] = []

        if query.chunk_type:
            c_type = query.chunk_type.strip().lower()
            escaped_type = _escape_redis_tag(c_type)
            filters.append(f"@chunk_type:{{{escaped_type}}}")

        if query.skills_filter:
            for skill in query.skills_filter:
                cleaned_skill = skill.strip().lower()
                if cleaned_skill:
                    escaped_skill = _escape_redis_tag(cleaned_skill)
                    filters.append(f"@skills:{{{escaped_skill}}}")

        filter_expr = " ".join(filters) if filters else "*"
        search_query_str = f"({filter_expr})=>[KNN {query.top_k} @content_vector $vec AS score]"

        q = (
            Query(search_query_str)
            .sort_by("score")
            .return_fields(
                "candidate_id",
                "candidate_name",
                "chunk_type",
                "section_title",
                "content",
                "company",
                "job_title",
                "skills",
                "file_path",
                "score",
            )
            .paging(0, query.top_k)
            .dialect(2)
        )

        query_bytes = np.array(query_vector, dtype=np.float32).tobytes()
        ft = self.client.ft(self.index_name)
        start_time = time.perf_counter()
        res = ft.search(q, query_params={"vec": query_bytes})
        elapsed = time.perf_counter() - start_time
        total_hits = getattr(res, "total", len(res.docs))
        logger.info(
            "Redis KNN 向量檢索成功 - 命中切片總數: %d, 請求 Top_K: %d, 檢索耗時: %.3f 秒",
            total_hits,
            query.top_k,
            elapsed,
        )

        results: List[SearchResultItem] = []
        for doc in res.docs:
            # RediSearch Cosine 距離: 0.0 (最相似) ~ 2.0 (最不相似)
            # 轉換為 Cosine 相似度 (1 - distance)
            distance = float(getattr(doc, "score", 1.0))
            similarity = max(0.0, min(1.0, 1.0 - distance))

            if query.min_score > 0.0 and similarity < query.min_score:
                continue

            skills_raw = _safe_str(getattr(doc, "skills", ""))
            skills_list = [s.strip() for s in skills_raw.split(",") if s.strip()]

            results.append(
                SearchResultItem(
                    candidate_id=_safe_str(getattr(doc, "candidate_id", "")),
                    candidate_name=_safe_str(getattr(doc, "candidate_name", "")),
                    chunk_type=_safe_str(getattr(doc, "chunk_type", "")),
                    section_title=_safe_str(getattr(doc, "section_title", "")),
                    content=_safe_str(getattr(doc, "content", "")),
                    score=round(similarity, 4),
                    company=_safe_str(getattr(doc, "company", None)) or None,
                    job_title=_safe_str(getattr(doc, "job_title", None)) or None,
                    skills=skills_list,
                    file_path=_safe_str(getattr(doc, "file_path", None)) or None,
                )
            )

        return results

    def delete_by_candidate(self, candidate_id: str) -> int:
        """刪除指定候選人的所有切片"""
        pattern = f"{self.prefix}{candidate_id}:*"
        keys = list(self.client.scan_iter(match=pattern, count=100))
        if not keys:
            return 0

        pipe = self.client.pipeline(transaction=False)
        for k in keys:
            pipe.delete(k)
        pipe.execute()
        self.client.delete(f"{self.hash_prefix}{candidate_id}")
        return len(keys)

    def get_candidate_hash(self, candidate_id: str) -> Optional[str]:
        """取得指定候選人的內容 Hash 指紋"""
        val = self.client.get(f"{self.hash_prefix}{candidate_id}")
        if val is None:
            return None
        if isinstance(val, bytes):
            return val.decode("utf-8", errors="replace")
        return str(val)

    def set_candidate_hash(self, candidate_id: str, content_hash: str) -> None:
        """設定指定候選人的內容 Hash 指紋"""
        self.client.set(f"{self.hash_prefix}{candidate_id}", content_hash)
