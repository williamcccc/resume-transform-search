"""
Spec-0024 評測共用工具：資料載入驗證、隔離防呆、混淆矩陣、用量統計、結果輸出。
本模組只用標準函式庫與 src.domain，單元測試見 tests/unit/test_eval_support.py。
"""
from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.domain.evaluation_metrics import dedupe_ranked  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
DATA_DIR = EVAL_DIR / "data"
RESULTS_DIR = EVAL_DIR / "results"
DATASET_VERSION = "v2"

STATUS_LABELS: tuple[str, ...] = ("SUPPORTED", "CONTRADICTED", "NOT_MENTIONED")
DIFFICULTY_LEVELS: tuple[str, ...] = ("basic", "hard")

# 評測專用 Redis 命名空間（與正式 idx:resumes:v1 / resume:v1:* 不相交，啟動時另以 check_isolation 防呆）
EVAL_INDEX_NAME = "idx:eval:resumes:v1"
EVAL_CHUNK_PREFIX = "eval:resume:v1:chunk:"
EVAL_HASH_PREFIX = "eval:resume:v1:hash:"


@dataclass(frozen=True)
class RedisNamespace:
    index_name: str
    chunk_prefix: str
    hash_prefix: str


def _prefix_overlap(a: str, b: str) -> bool:
    return a.startswith(b) or b.startswith(a)


def check_isolation(eval_ns: RedisNamespace, prod_ns: RedisNamespace) -> None:
    """評測命名空間與正式命名空間有任何重疊即拋 ValueError。"""
    problems = []
    if not eval_ns.index_name or eval_ns.index_name == prod_ns.index_name:
        problems.append(f"索引名稱與正式相同：{eval_ns.index_name!r}")
    eval_prefixes = (eval_ns.chunk_prefix, eval_ns.hash_prefix)
    prod_prefixes = (prod_ns.chunk_prefix, prod_ns.hash_prefix)
    for ep in eval_prefixes:
        if not ep:
            problems.append("評測前綴不可為空字串")
            continue
        for pp in prod_prefixes:
            if pp and _prefix_overlap(ep, pp):
                problems.append(f"評測前綴 {ep!r} 與正式前綴 {pp!r} 互相包含")
    if problems:
        raise ValueError("評測 Redis 命名空間未與正式隔離：" + "；".join(problems))


def load_jsonl(
    path: Path,
    required_fields: Sequence[str],
    id_field: str,
    enum_fields: Mapping[str, Iterable[str]] | None = None,
) -> list[dict[str, Any]]:
    """讀取 JSONL 並驗證欄位、枚舉值與 ID 唯一性；錯誤時拋 ValueError 並指出行號。"""
    allowed = {k: set(v) for k, v in (enum_fields or {}).items()}
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    with Path(path).open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as err:
                raise ValueError(f"{path.name} 第 {lineno} 行不是合法 JSON") from err
            if not isinstance(row, dict):
                raise ValueError(f"{path.name} 第 {lineno} 行必須是 JSON 物件")
            missing = [f for f in required_fields if f not in row]
            if missing:
                raise ValueError(f"{path.name} 第 {lineno} 行缺少欄位：{', '.join(missing)}")
            for field_name, values in allowed.items():
                if row.get(field_name) not in values:
                    raise ValueError(f"{path.name} 第 {lineno} 行 {field_name} 值不合法：{row.get(field_name)!r}")
            row_id = row.get(id_field)
            if row_id in seen:
                raise ValueError(f"{path.name} 第 {lineno} 行 {id_field} 重複：{row_id!r}")
            seen.add(row_id)
            rows.append(row)
    return rows


def subsets_by(rows: Sequence[Mapping[str, Any]], key: str, levels: Sequence[str]) -> dict[str, list]:
    """回傳 {"all": 全部, level: 該層級資料}；每個 level 都有鍵（無資料時為空列表），未列出的值只計入 all。"""
    groups: dict[str, list] = {"all": list(rows)}
    for level in levels:
        groups[level] = [r for r in rows if r.get(key) == level]
    return groups


def candidate_ranking(candidate_ids: Iterable[str]) -> list[str]:
    """切片層級結果（已依分數排序）轉為候選人層級排名：保留每位候選人首次出現的位置。"""
    return dedupe_ranked(list(candidate_ids))


def confusion_matrix(
    pairs: Iterable[tuple[str, str]], labels: Sequence[str] = STATUS_LABELS
) -> dict[str, dict[str, int]]:
    """pairs 為 (標準, 預測)；回傳 {標準: {預測: 次數}}，包含全部格子。"""
    label_set = set(labels)
    matrix = {exp: {pred: 0 for pred in labels} for exp in labels}
    for expected, predicted in pairs:
        if expected not in label_set or predicted not in label_set:
            raise ValueError(f"未知標籤：expected={expected!r}, predicted={predicted!r}")
        matrix[expected][predicted] += 1
    return matrix


def _ratio(num: int, den: int) -> float | None:
    return None if den == 0 else num / den


def classification_summary(matrix: Mapping[str, Mapping[str, int]]) -> dict[str, Any]:
    """正確率、各類 precision/recall，以及 NOT_MENTIONED→SUPPORTED 誤判率（分母為 0 時為 None）。"""
    labels = list(matrix.keys())
    total = sum(matrix[e][p] for e in labels for p in labels)
    correct = sum(matrix[label][label] for label in labels)
    per_class = {}
    for label in labels:
        predicted_total = sum(matrix[e][label] for e in labels)
        expected_total = sum(matrix[label][p] for p in labels)
        per_class[label] = {
            "precision": _ratio(matrix[label][label], predicted_total),
            "recall": _ratio(matrix[label][label], expected_total),
            "support": expected_total,
        }
    nm_row = matrix.get("NOT_MENTIONED", {})
    nm_total = sum(nm_row.values())
    return {
        "total": total,
        "accuracy": _ratio(correct, total),
        "per_class": per_class,
        "false_support_count": nm_row.get("SUPPORTED", 0),
        "false_support_rate": _ratio(nm_row.get("SUPPORTED", 0), nm_total),
    }


def merge_usage(total: dict[str, int], usage: Mapping[str, Any] | None) -> dict[str, int]:
    """累加 LangChain usage_metadata（input/output/total tokens 與 reasoning）；缺漏欄位視為 0。"""
    usage = usage or {}
    details = usage.get("output_token_details") or {}
    for key, value in (
        ("input_tokens", usage.get("input_tokens")),
        ("output_tokens", usage.get("output_tokens")),
        ("total_tokens", usage.get("total_tokens")),
        ("thinking_tokens", details.get("reasoning") if isinstance(details, Mapping) else None),
    ):
        total[key] = total.get(key, 0) + int(value or 0)
    return total


class CountingEmbeddingService:
    """包裝 IEmbeddingService：依階段記錄呼叫次數、文字筆數與輸入字元數（Gemini Embedding 回應不保證含 Token 數）。"""

    def __init__(self, inner: Any):
        self._inner = inner
        self.dim = getattr(inner, "dim", 768)
        self.stats: dict[str, dict[str, int]] = {}

    def _record(self, phase: str, texts: Sequence[str]) -> None:
        s = self.stats.setdefault(phase, {"calls": 0, "texts": 0, "chars": 0})
        s["calls"] += 1
        s["texts"] += len(texts)
        s["chars"] += sum(len(t) for t in texts)

    def embed_texts(self, texts: list[str], task_type: str = "retrieval_document") -> list[list[float]]:
        self._record("index", texts)
        return self._inner.embed_texts(texts, task_type=task_type)

    def embed_query(self, query: str) -> list[float]:
        self._record("query", [query])
        return self._inner.embed_query(query)


def new_results_dir(kind: str, base: Path = RESULTS_DIR) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = base / f"{stamp}_{kind}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fieldnames: Sequence[str]) -> None:
    """UTF-8 BOM，讓 Excel 直接正確顯示中文。"""
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(fieldnames), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
