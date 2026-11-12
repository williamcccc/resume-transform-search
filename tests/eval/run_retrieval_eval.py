"""
Spec-0024 語意檢索評測（人工觸發，不納入 CI）。

將 tests/eval/data/resumes/ 的合成履歷寫入獨立的評測索引，對每題查詢計算候選人層級的
Recall@K、Precision@K、MRR、nDCG@K。

用法：
    python tests/eval/run_retrieval_eval.py [--k 3 5 10] [--top-chunks 60] [--reindex] [--cleanup]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.eval.eval_support import (  # noqa: E402
    DATA_DIR,
    DATASET_VERSION,
    DIFFICULTY_LEVELS,
    EVAL_CHUNK_PREFIX,
    EVAL_HASH_PREFIX,
    EVAL_INDEX_NAME,
    CountingEmbeddingService,
    RedisNamespace,
    candidate_ranking,
    check_isolation,
    load_jsonl,
    new_results_dir,
    subsets_by,
    write_csv,
    write_json,
)

logger = logging.getLogger("eval.retrieval")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Spec-0024 語意檢索評測")
    parser.add_argument("--k", type=int, nargs="+", default=[3, 5, 10], help="候選人層級的 K 值")
    parser.add_argument("--top-chunks", type=int, default=60, help="每題向量檢索取回的切片數")
    parser.add_argument("--reindex", action="store_true", help="清空並重建評測索引（會重新呼叫 Embedding）")
    parser.add_argument("--cleanup", action="store_true", help="結束後刪除評測索引與 eval: 前綴鍵")
    args = parser.parse_args(argv)
    if any(k <= 0 for k in args.k) or args.top_chunks <= 0:
        parser.error("--k 與 --top-chunks 必須為正整數")
    return args


def _fmt(value) -> str:
    """None（該子集沒有可計分的查詢）顯示為 N/A，不偽裝成 0。"""
    return "N/A" if value is None else f"{value:.3f}"


def _num_docs(store, index_name: str):
    try:
        info = store.client.ft(index_name).info()
        return int(info.get("num_docs", 0))
    except Exception:  # 正式索引不存在時不視為錯誤
        return None


def _cleanup(store, ns: RedisNamespace) -> int:
    deleted = 0
    try:
        store.client.ft(ns.index_name).dropindex(delete_documents=False)
    except Exception:
        logger.info("評測索引不存在或已刪除")
    for prefix in (ns.chunk_prefix, ns.hash_prefix):
        for key in store.client.scan_iter(match=f"{prefix}*", count=500):
            deleted += int(store.client.delete(key))
    return deleted


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    from src.application.dto import IndexCommand
    from src.application.index_resumes_use_case import IndexResumesUseCase
    from src.application.search_resumes_use_case import SearchResumesUseCase
    from src.domain.evaluation_metrics import RetrievalCase, ndcg_at_k, recall_at_k, reciprocal_rank
    from src.domain.evaluation_metrics import summarize_retrieval
    from src.domain.models import SearchQuery
    from src.infrastructure.chunkers.markdown_chunker import MarkdownChunker
    from src.infrastructure.config import AppConfig
    from src.infrastructure.embeddings.gemini_embedding import GeminiEmbeddingService
    from src.infrastructure.stores.redis_vector_store import RedisVectorStore

    prod_cfg = AppConfig.load()
    cfg = AppConfig.load(
        override_redis_index_name=EVAL_INDEX_NAME,
        override_redis_prefix=EVAL_CHUNK_PREFIX,
        override_redis_hash_prefix=EVAL_HASH_PREFIX,
    )
    eval_ns = RedisNamespace(cfg.redis_index_name, cfg.redis_prefix, cfg.redis_hash_prefix)
    prod_ns = RedisNamespace(prod_cfg.redis_index_name, prod_cfg.redis_prefix, prod_cfg.redis_hash_prefix)
    try:
        check_isolation(eval_ns, prod_ns)
    except ValueError as err:
        logger.error("%s", err)
        return 2

    queries = load_jsonl(DATA_DIR / "retrieval_queries.jsonl", ["query_id", "query", "relevant_ids", "difficulty"],
                         "query_id", enum_fields={"difficulty": DIFFICULTY_LEVELS})
    resume_dir = DATA_DIR / "resumes"
    logger.info("資料集 %s：%d 題查詢、%d 份履歷", DATASET_VERSION, len(queries), len(list(resume_dir.glob("*.md"))))

    embedding = CountingEmbeddingService(GeminiEmbeddingService(
        api_key=cfg.gemini_api_key,
        model_name=cfg.embedding_model,
        dim=cfg.embedding_dim,
        batch_size=cfg.embedding_batch_size,
        max_retries=cfg.api_max_retries,
        retry_delay=cfg.api_retry_delay,
    ))
    store = RedisVectorStore(
        redis_url=cfg.redis_url,
        index_name=eval_ns.index_name,
        prefix=eval_ns.chunk_prefix,
        hash_prefix=eval_ns.hash_prefix,
        hnsw_m=cfg.redis_hnsw_m,
        hnsw_ef_construction=cfg.redis_hnsw_ef_construction,
        hnsw_initial_cap=cfg.redis_hnsw_initial_cap,
        distance_metric=cfg.redis_distance_metric,
    )
    chunker = MarkdownChunker(
        min_chunk_chars=cfg.min_chunk_size,
        max_chunk_chars=cfg.max_chunk_size,
        extra_skill_patterns=cfg.extra_skill_patterns,
    )

    prod_docs_before = _num_docs(store, prod_ns.index_name)
    if args.reindex:
        # 先清空評測命名空間：資料集刪除的履歷若只重建索引定義，其舊切片仍會被新索引收錄而污染排名
        logger.info("重建前已清除評測鍵 %d 個", _cleanup(store, eval_ns))
    index_result = IndexResumesUseCase(chunker, embedding, store).execute(
        IndexCommand(dir_path=resume_dir, recreate_index=args.reindex)
    )
    if index_result.errors:
        for msg in index_result.errors:
            logger.error("寫入失敗：%s", msg)
        return 1
    logger.info("寫入評測索引：新寫入 %d 份、略過 %d 份（內容未變）、%d 個切片",
                index_result.indexed_files, index_result.skipped_files, index_result.total_chunks)

    search = SearchResumesUseCase(embedding_service=embedding, vector_store=store)
    cases: dict[str, RetrievalCase] = {}
    per_query = []
    max_k = max(args.k)
    for q in queries:
        results = search.execute(SearchQuery(query_text=q["query"], top_k=args.top_chunks))
        ranking = candidate_ranking(item.candidate_id for item in results)
        relevant = frozenset(q["relevant_ids"])
        cases[q["query_id"]] = RetrievalCase(q["query_id"], relevant, tuple(ranking))
        hits = [i + 1 for i, cid in enumerate(ranking) if cid in relevant]
        row = {
            "query_id": q["query_id"],
            "difficulty": q["difficulty"],
            "note": q.get("note", ""),
            "query": q["query"],
            "relevant_ids": " ".join(sorted(relevant)),
            f"top_{max_k}": " ".join(ranking[:max_k]),
            "hit_ranks": " ".join(map(str, hits)),
            "reciprocal_rank": reciprocal_rank(relevant, ranking),
        }
        for k in args.k:
            row[f"recall@{k}"] = recall_at_k(relevant, ranking, k)
            row[f"ndcg@{k}"] = ndcg_at_k(relevant, ranking, k)
        per_query.append(row)

    summaries: dict[str, dict] = {}
    for subset, subset_queries in subsets_by(queries, "difficulty", DIFFICULTY_LEVELS).items():
        subset_cases = [cases[q["query_id"]] for q in subset_queries]
        summaries[subset] = {}
        for k in sorted(set(args.k)):
            s = summarize_retrieval(subset_cases, k)
            summaries[subset][f"@{k}"] = {"recall": s.recall, "precision": s.precision, "mrr": s.mrr,
                                          "ndcg": s.ndcg, "counted": s.counted, "excluded": s.excluded}

    prod_docs_after = _num_docs(store, prod_ns.index_name)
    out = new_results_dir("retrieval")
    fieldnames = ["query_id", "difficulty", "note", "query", "relevant_ids", f"top_{max_k}", "hit_ranks", "reciprocal_rank"]
    for k in args.k:
        fieldnames += [f"recall@{k}", f"ndcg@{k}"]
    write_csv(out / "retrieval_per_query.csv", per_query, fieldnames)
    write_json(out / "retrieval_summary.json", {
        "dataset_version": DATASET_VERSION,
        "embedding_model": cfg.embedding_model,
        "eval_namespace": eval_ns.__dict__,
        "top_chunks": args.top_chunks,
        "summaries": summaries,
        "index": {"indexed_files": index_result.indexed_files, "skipped_files": index_result.skipped_files,
                  "total_chunks": index_result.total_chunks},
        "prod_index_num_docs": {"before": prod_docs_before, "after": prod_docs_after},
    })
    write_json(out / "usage.json", {"embedding": embedding.stats, "llm": None})

    if args.cleanup:
        logger.info("已清除評測鍵 %d 個", _cleanup(store, eval_ns))

    for subset, by_k in summaries.items():
        for key, s in by_k.items():
            logger.info("[%s] %s Recall=%s Precision=%s MRR=%s nDCG=%s（計入 %d、排除 %d）", subset, key,
                        _fmt(s["recall"]), _fmt(s["precision"]), _fmt(s["mrr"]), _fmt(s["ndcg"]),
                        s["counted"], s["excluded"])
    logger.info("Embedding 用量：%s", embedding.stats)
    logger.info("正式索引文件數：執行前 %s、執行後 %s", prod_docs_before, prod_docs_after)
    logger.info("結果輸出：%s", out.relative_to(Path(__file__).resolve().parents[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
