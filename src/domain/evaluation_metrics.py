"""
檢索與抽取品質指標計算（純函式，零外部依賴）。
規格見 docs/specs/0023-retrieval-quality-metrics-spec.md。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True)
class RetrievalCase:
    query_id: str
    relevant_ids: frozenset[str]
    ranked_ids: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalSummary:
    k: int
    recall: float | None
    precision: float | None
    mrr: float | None
    ndcg: float | None
    counted: int
    excluded: int


def dedupe_ranked(ranked: Iterable[str]) -> list[str]:
    """去除重複 ID，保留首次出現的順序。"""
    return list(dict.fromkeys(ranked))


def _validate_k(k: int) -> None:
    if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
        raise ValueError(f"K 必須為正整數，實際為 {k!r}")


def recall_at_k(relevant: Iterable[str], ranked: Sequence[str], k: int) -> float | None:
    _validate_k(k)
    rel = set(relevant)
    if not rel:
        return None
    top = dedupe_ranked(ranked)[:k]
    hits = sum(1 for item in top if item in rel)
    return hits / len(rel)


def precision_at_k(relevant: Iterable[str], ranked: Sequence[str], k: int) -> float | None:
    _validate_k(k)
    rel = set(relevant)
    if not rel:
        return None
    top = dedupe_ranked(ranked)[:k]
    if not top:
        return 0.0
    hits = sum(1 for item in top if item in rel)
    return hits / len(top)


def reciprocal_rank(relevant: Iterable[str], ranked: Sequence[str]) -> float | None:
    rel = set(relevant)
    if not rel:
        return None
    for position, item in enumerate(dedupe_ranked(ranked), start=1):
        if item in rel:
            return 1 / position
    return 0.0


def ndcg_at_k(relevant: Iterable[str], ranked: Sequence[str], k: int) -> float | None:
    """二元相關的 nDCG@K：DCG 以 log2(i+1) 折扣，IDCG 以 min(K, 相關數) 計算。"""
    _validate_k(k)
    rel = set(relevant)
    if not rel:
        return None
    top = dedupe_ranked(ranked)[:k]
    dcg = sum(1 / math.log2(i + 1) for i, item in enumerate(top, start=1) if item in rel)
    ideal_count = min(k, len(rel))
    idcg = sum(1 / math.log2(i + 1) for i in range(1, ideal_count + 1))
    return dcg / idcg


def _normalize_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip().casefold()
    return value


def _facts(fields: Mapping[str, Any]) -> set[tuple[str, Any]]:
    """將欄位展開為事實集合。None 與正規化後的空字串視為缺漏；清單欄位逐項展開。"""
    facts: set[tuple[str, Any]] = set()
    for name, value in fields.items():
        items = value if isinstance(value, (list, tuple, set, frozenset)) else [value]
        for item in items:
            if item is None:
                continue
            normalized = _normalize_value(item)
            if normalized == "":
                continue
            facts.add((name, normalized))
    return facts


def field_f1(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> float:
    """欄位抽取的 F1：以 (欄位, 正規化值) 為單位計算 precision 與 recall 的調和平均。"""
    exp = _facts(expected)
    act = _facts(actual)
    if not exp and not act:
        return 1.0
    tp = len(exp & act)
    if tp == 0:
        return 0.0
    precision = tp / len(act)
    recall = tp / len(exp)
    return 2 * precision * recall / (precision + recall)


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def summarize_retrieval(cases: Sequence[RetrievalCase], k: int) -> RetrievalSummary:
    """彙總多筆查詢的指標平均。相關集合為空的查詢不計入平均，並回報排除筆數。"""
    _validate_k(k)
    recalls: list[float] = []
    precisions: list[float] = []
    mrrs: list[float] = []
    ndcgs: list[float] = []
    excluded = 0
    for case in cases:
        if not case.relevant_ids:
            excluded += 1
            continue
        recalls.append(recall_at_k(case.relevant_ids, case.ranked_ids, k))
        precisions.append(precision_at_k(case.relevant_ids, case.ranked_ids, k))
        mrrs.append(reciprocal_rank(case.relevant_ids, case.ranked_ids))
        ndcgs.append(ndcg_at_k(case.relevant_ids, case.ranked_ids, k))
    return RetrievalSummary(
        k=k,
        recall=_mean(recalls),
        precision=_mean(precisions),
        mrr=_mean(mrrs),
        ndcg=_mean(ndcgs),
        counted=len(cases) - excluded,
        excluded=excluded,
    )
