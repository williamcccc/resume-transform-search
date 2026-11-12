"""
Ragas Faithfulness 練習：評 answer_followup／narrate_match 引號外的轉述是否忠於來源（非正式需求）。

只在 .venv-eval 執行（依賴見 requirements-eval.txt）；不進 CI、不進生產環境；src/ 禁止 import ragas。
不重新產生回答：沿用 run_followup_eval.py 已輸出的 followup_spot_check.csv／narration_spot_check.csv。

用法：
    .venv-eval\\Scripts\\python tests/eval/run_ragas_faithfulness.py [--limit 5] [--include-narration] [--langsmith]
    .venv-eval\\Scripts\\python tests/eval/run_ragas_faithfulness.py --calibrate <ragas_faithfulness.csv>
    .venv-eval\\Scripts\\python tests/eval/run_ragas_faithfulness.py --fetch-verdicts <結果目錄>

人工校準：在輸出的 CSV 填 human_label（faithful／exaggerated），再以 --calibrate 計算與評審的一致率。
逐條判定：以 --langsmith 跑過的結果目錄，可用 --fetch-verdicts 從 LangSmith 讀回評審拆出的陳述與 verdict，
寫成 verdicts.csv。送 trace 用 LANGSMITH_API_KEY（可為只能寫的 tracing key）；讀 trace 另用
LANGSMITH_READ_API_KEY（需有 projects:read 權限，例如 Personal Access Token），兩者分開以維持最小權限。
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import logging
import math
import os
import sys
import warnings
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.eval.eval_support import (  # noqa: E402
    DATA_DIR,
    DATASET_VERSION,
    EVAL_DIR,
    RESULTS_DIR,
    load_jsonl,
    new_results_dir,
    write_csv,
    write_json,
)

logger = logging.getLogger("eval.ragas")
PROMPTS_DIR = EVAL_DIR / "ragas_prompts"
HUMAN_LABELS = ("faithful", "exaggerated")
TRACING_PROJECT = "ragas-faithfulness-practice"
READ_KEY_ENV = "LANGSMITH_READ_API_KEY"
DEFAULT_EXPERIMENT_PREFIX = "faithfulness-"
STATEMENT_PROMPT = "statement_generator_prompt"
NLI_PROMPT = "n_l_i_statement_prompt"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Ragas Faithfulness 轉述誇大練習")
    p.add_argument("--followup-csv", type=Path, help="run_followup_eval.py 的輸出；預設取最新一次")
    p.add_argument("--include-narration", action="store_true", help="一併評同目錄的 narration_spot_check.csv")
    p.add_argument("--narration-only", action="store_true", help="只評 narration_spot_check.csv（不評追問）")
    p.add_argument("--limit", type=int, default=0, help="只評前 N 筆（0 = 全部）")
    p.add_argument("--judge-model", help="評審模型；預設沿用 RECRUIT_LLM_MODEL／GEMINI_MODEL")
    p.add_argument("--judge-max-output-tokens", type=int, default=8192)
    p.add_argument("--max-workers", type=int, default=4)
    p.add_argument("--language", default="traditional_chinese", help="adapt_prompts 目標語言（也是 prompt 檔名後綴）")
    p.add_argument("--readapt", action="store_true", help="重新翻譯評審 prompt（會花 Token），覆寫 ragas_prompts/")
    p.add_argument("--english", action="store_true", help="不用中文 prompt，使用 Ragas 原始英文 prompt（對照組）")
    p.add_argument("--langsmith", action="store_true", help=f"送 trace 到 LangSmith 專案 {TRACING_PROJECT}")
    p.add_argument("--calibrate", type=Path, help="讀取已填 human_label 的 CSV，計算與評審的一致率（不呼叫 API）")
    p.add_argument("--fetch-verdicts", type=Path, metavar="RESULTS_DIR",
                   help=f"從 LangSmith 讀回該次評測的逐條判定（需 {READ_KEY_ENV}，不呼叫 Gemini）")
    p.add_argument("--threshold", type=float, default=1.0, help="分數低於此值視為評審判定「誇大」")
    args = p.parse_args(argv)
    if args.limit < 0 or args.max_workers <= 0 or args.judge_max_output_tokens <= 0:
        p.error("--limit 不可為負，--max-workers／--judge-max-output-tokens 須為正整數")
    return args


# ── 人工校準（純函式，不需 ragas） ─────────────────────────────────────────────

def _score(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def calibrate(rows: list[dict[str, str]], threshold: float) -> dict[str, Any]:
    """評審（score < threshold → exaggerated）對照人工 human_label；NaN 與未標註者分開計數。"""
    matrix = {h: {j: 0 for j in (*HUMAN_LABELS, "nan")} for h in HUMAN_LABELS}
    unlabeled = 0
    for row in rows:
        human = (row.get("human_label") or "").strip().lower()
        if not human:
            unlabeled += 1
            continue
        if human not in HUMAN_LABELS:
            raise ValueError(f"{row.get('case_id')} 的 human_label 不合法：{human!r}（只接受 {HUMAN_LABELS}）")
        score = _score(row.get("faithfulness"))
        judge = "nan" if score is None else ("exaggerated" if score < threshold else "faithful")
        matrix[human][judge] += 1
    scored = sum(matrix[h][j] for h in HUMAN_LABELS for j in HUMAN_LABELS)
    agree = sum(matrix[h][h] for h in HUMAN_LABELS)
    caught = matrix["exaggerated"]["exaggerated"]
    flagged = matrix["faithful"]["exaggerated"] + caught
    exaggerated_total = matrix["exaggerated"]["faithful"] + caught
    return {
        "threshold": threshold,
        "labeled": scored + matrix["faithful"]["nan"] + matrix["exaggerated"]["nan"],
        "unlabeled": unlabeled,
        "judge_nan": matrix["faithful"]["nan"] + matrix["exaggerated"]["nan"],
        "matrix_human_to_judge": matrix,
        "agreement": None if scored == 0 else agree / scored,
        "exaggerated_recall": None if exaggerated_total == 0 else caught / exaggerated_total,
        "exaggerated_precision": None if flagged == 0 else caught / flagged,
    }


def read_labeled_csv(path: Path) -> list[dict[str, str]]:
    """讀取人工標註後的 CSV；容忍 Excel 另存造成的 Big5（cp950）編碼與 Tab 分隔。"""
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp950")
    header = text.split("\n", 1)[0]
    delimiter = "\t" if header.count("\t") > header.count(",") else ","
    rows = list(csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter))
    if rows and not {"faithfulness", "human_label"} <= rows[0].keys():
        raise ValueError(f"{Path(path).name} 缺少 faithfulness 或 human_label 欄位，實際欄位：{list(rows[0].keys())}")
    return rows


def _run_calibration(path: Path, threshold: float) -> int:
    rows = read_labeled_csv(path)
    result = calibrate(rows, threshold)
    out = path.with_name("calibration.json")
    write_json(out, result)
    logger.info("人工標註 %d 筆（未標 %d、評審 NaN %d）｜一致率 %s｜誇大 recall %s、precision %s",
                result["labeled"], result["unlabeled"], result["judge_nan"], result["agreement"],
                result["exaggerated_recall"], result["exaggerated_precision"])
    for human, row in result["matrix_human_to_judge"].items():
        logger.info("  人工 %-11s → 評審 %s", human, row)
    logger.info("輸出：%s", out)
    return 0


# ── 從 LangSmith trace 取回逐條判定 ─────────────────────────────────────────

def _first_statements(outputs: Any) -> list[Any]:
    """prompt run 的 outputs 形如 {"output": [{"statements": [...]}]}（n=1）；取第一組 statements。"""
    out = (outputs or {}).get("output")
    if isinstance(out, list):
        out = out[0] if out else {}
    return list((out or {}).get("statements") or []) if isinstance(out, dict) else []


def extract_verdicts(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """把一次 Ragas evaluate 的 trace（扁平 run 清單）整理成逐條判定。

    每個 run 需有 id、parent_run_id、name、outputs、metadata；row 由 metadata.row_index（或名稱 "row i"）識別，
    其下的 n_l_i_statement_prompt 提供 statement／verdict／reason。同一 row 有多個 NLI run（重試）時取最後一個。
    """
    by_id = {r["id"]: r for r in runs}

    def row_of(run: dict[str, Any]) -> int | None:
        seen = set()
        while run and run["id"] not in seen:
            seen.add(run["id"])
            meta = run.get("metadata") or {}
            if "row_index" in meta:
                return int(meta["row_index"])
            name = run.get("name") or ""
            if name.startswith("row ") and name[4:].isdigit():
                return int(name[4:])
            run = by_id.get(run.get("parent_run_id"))
        return None

    nli_by_row: dict[int, dict[str, Any]] = {}
    for run in runs:
        if run.get("name") != NLI_PROMPT:
            continue
        row = row_of(run)
        if row is None:
            continue
        prev = nli_by_row.get(row)
        if prev is None or str(run.get("start_time") or "") >= str(prev.get("start_time") or ""):
            nli_by_row[row] = run

    verdicts = []
    for row in sorted(nli_by_row):
        for idx, item in enumerate(_first_statements(nli_by_row[row].get("outputs")), start=1):
            if not isinstance(item, dict):
                continue
            verdicts.append({"row": row, "statement_no": idx, "statement": item.get("statement", ""),
                             "verdict": item.get("verdict"), "reason": item.get("reason", "")})
    return verdicts


def _langsmith_read_client(cfg):
    from langsmith import Client

    key = (os.environ.get(READ_KEY_ENV) or "").strip()
    if not key:
        raise SystemExit(f"--fetch-verdicts 需要 .env 設定 {READ_KEY_ENV}（具 projects:read 權限的 key）")
    return Client(api_key=key, api_url=cfg.langsmith_endpoint or None)


def _run_fetch_verdicts(results_dir: Path) -> int:
    from src.infrastructure.config import AppConfig

    summary = json.loads((results_dir / "summary.json").read_text(encoding="utf-8"))
    experiment = summary.get("langsmith_experiment") or f"{DEFAULT_EXPERIMENT_PREFIX}traditional_chinese"
    project = summary.get("langsmith_project") or TRACING_PROJECT
    labeled = read_labeled_csv(results_dir / "ragas_faithfulness.csv")
    client = _langsmith_read_client(AppConfig.load())

    if not summary.get("langsmith_experiment"):
        logger.warning("summary.json 未記錄 langsmith_experiment（舊版結果），改取名稱 %s 且 row 數相符的最新一次",
                       experiment)
    roots = sorted(client.list_runs(project_name=project, is_root=True, filter=f'eq(name, "{experiment}")'),
                   key=lambda r: r.start_time, reverse=True)
    verdicts, root = [], None
    for candidate in roots:
        runs = [{"id": r.id, "parent_run_id": r.parent_run_id, "name": r.name, "outputs": r.outputs,
                 "metadata": (r.extra or {}).get("metadata") or {}, "start_time": r.start_time}
                for r in client.list_runs(project_name=project, trace_id=candidate.trace_id)]
        found = extract_verdicts(runs)
        if len({v["row"] for v in found}) == len(labeled):
            verdicts, root = found, candidate
            break
    if root is None:
        logger.error("在 LangSmith 專案 %s 找不到名稱 %s 且涵蓋全部 %d 筆的 trace", project, experiment, len(labeled))
        return 2

    rows = []
    for v in verdicts:
        meta = labeled[v["row"]]
        rows.append({"case_id": meta.get("case_id", ""), "model_status": meta.get("model_status") or meta.get("kind", ""),
                     "faithfulness": meta.get("faithfulness", ""), "human_label": meta.get("human_label", ""), **v})
    write_csv(results_dir / "verdicts.csv", rows,
              ["case_id", "model_status", "faithfulness", "human_label", "row", "statement_no", "statement",
               "verdict", "reason"])
    zero = [r for r in rows if r["verdict"] == 0]
    logger.info("trace %s：%d 筆樣本、%d 條陳述，其中 verdict=0 共 %d 條", root.trace_id,
                len({r["row"] for r in rows}), len(rows), len(zero))
    logger.info("輸出：%s", (results_dir / "verdicts.csv"))
    return 0


# ── 樣本組裝（沿用 Spec-0024 已產生的回答） ───────────────────────────────────

def _latest_followup_csv() -> Path:
    candidates = sorted(RESULTS_DIR.glob("*_followup/followup_spot_check.csv"))
    if not candidates:
        raise FileNotFoundError("找不到 followup_spot_check.csv，請先執行 tests/eval/run_followup_eval.py")
    return candidates[-1]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _build_samples(args: argparse.Namespace, cfg) -> tuple[list[dict[str, Any]], Path]:
    from src.domain.recruitment_services import ProtectedAttributeGuard, mask_contact_info
    from src.interfaces.web.server import build_recruitment_settings
    from tests.eval.run_followup_eval import ALIAS, _resume_name

    csv_path = args.followup_csv or _latest_followup_csv()
    settings = build_recruitment_settings(cfg)
    guard = ProtectedAttributeGuard(settings.protected_attr_terms)
    questions = {q["case_id"]: q for q in load_jsonl(
        DATA_DIR / "followup_questions.jsonl", ["case_id", "candidate_id", "question", "profile_summary"], "case_id")}

    def resume_context(cid: str) -> str:
        # 與 run_followup_eval.prepare_text 相同：評審看到的來源 = answer_followup 當時看到的履歷
        text = (DATA_DIR / "resumes" / f"{cid}.md").read_text(encoding="utf-8")
        masked = mask_contact_info(guard.redact_resume(text), [_resume_name(text, cid)], ALIAS)
        return masked[: settings.profile_max_resume_chars]

    samples: list[dict[str, Any]] = []
    for row in _read_csv(csv_path):
        if row.get("error") or not row.get("answer_text"):
            continue
        q = questions[row["case_id"]]
        summary = "；".join(f"{k}={v}" for k, v in q["profile_summary"].items())
        samples.append({
            "case_id": row["case_id"], "kind": "followup", "difficulty": row["difficulty"],
            "model_status": row["model_status"],
            "user_input": row["question"],
            "response": row["answer_text"],
            "retrieved_contexts": [resume_context(row["candidate_id"]), f"候選人摘要：{summary}"],
        })

    if args.narration_only:
        samples = []
    narration_csv = csv_path.with_name("narration_spot_check.csv")
    if (args.include_narration or args.narration_only) and narration_csv.exists():
        from src.infrastructure.llm.gemini_recruitment_llm import GeminiRecruitmentLlm
        from tests.eval.run_followup_eval import build_narration_facts

        cases = {c["case_id"]: c for c in load_jsonl(
            DATA_DIR / "narration_cases.jsonl",
            ["case_id", "jd_title", "requested_k", "pool_size", "must_labels", "nice_labels", "candidates"],
            "case_id")}
        for row in _read_csv(narration_csv):
            if row.get("error") or not row.get("narration"):
                continue
            # 來源 = narrate_match 實際收到的 facts JSON（含職缺名稱、必備/加分條件、relaxation），與正式序列化一致
            facts_json = GeminiRecruitmentLlm._facts_json(build_narration_facts(cases[row["case_id"]]))
            samples.append({
                "case_id": row["case_id"], "kind": "narration", "difficulty": "", "model_status": "",
                "user_input": f"請說明「{row['jd_title']}」職缺的候選人比對結果",
                "response": row["narration"],
                "retrieved_contexts": [facts_json],
            })
    elif args.include_narration or args.narration_only:
        logger.warning("找不到 %s，略過敘述", narration_csv)

    if args.limit:
        samples = samples[: args.limit]
    return samples, csv_path


# ── 評審 LLM 與 prompt ──────────────────────────────────────────────────────

def _build_judge(cfg, args, counter):
    from langchain_google_genai import ChatGoogleGenerativeAI
    from ragas.llms import LangchainLLMWrapper
    from ragas.run_config import RunConfig

    model = args.judge_model or cfg.recruit_llm_model or cfg.gemini_model
    kwargs: dict[str, Any] = {}
    if cfg.recruit_llm_thinking_budget is not None and "thinking_budget" in ChatGoogleGenerativeAI.model_fields:
        kwargs["thinking_budget"] = int(cfg.recruit_llm_thinking_budget)
    chat = ChatGoogleGenerativeAI(
        model=model,
        google_api_key=cfg.gemini_api_key,
        temperature=0,
        max_output_tokens=args.judge_max_output_tokens,
        timeout=cfg.recruit_llm_timeout_seconds,
        max_retries=0,  # 重試交給 Ragas RunConfig，避免兩層重試疊加
        callbacks=[counter],
        **kwargs,
    )
    run_config = RunConfig(timeout=int(cfg.recruit_llm_timeout_seconds) * 2, max_retries=2,
                           max_workers=args.max_workers)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)  # LangchainLLMWrapper 已標示棄用，練習仍使用
        return LangchainLLMWrapper(chat, run_config=run_config), run_config, model


def _prepare_metric(judge, args, counter) -> tuple[Any, dict[str, Any]]:
    from ragas.metrics import Faithfulness

    metric = Faithfulness(llm=judge)
    info: dict[str, Any] = {"language": "english" if args.english else args.language, "adapted_now": False}
    if args.english:
        return metric, info
    PROMPTS_DIR.mkdir(exist_ok=True)
    names = metric.get_prompts().keys()
    files = [PROMPTS_DIR / f"{metric.name}_{n}_{args.language}.json" for n in names]
    if args.readapt or not all(f.exists() for f in files):
        before = dict(counter.tokens)
        adapted = asyncio.run(metric.adapt_prompts(args.language, llm=judge, adapt_instruction=True))
        metric.set_prompts(**adapted)
        metric.save_prompts(str(PROMPTS_DIR))
        info.update(adapted_now=True, adapt_tokens={k: v - before.get(k, 0) for k, v in counter.tokens.items()})
        logger.info("已翻譯評審 prompt 並存到 %s（請人工檢查譯文）", PROMPTS_DIR.relative_to(EVAL_DIR.parents[1]))
    else:
        metric.set_prompts(**metric.load_prompts(str(PROMPTS_DIR), args.language))
        logger.info("載入已翻譯的評審 prompt：%s", args.language)
    return metric, info


def _enable_langsmith(cfg) -> None:
    if not cfg.langsmith_api_key:
        raise SystemExit("--langsmith 需要 .env 設定 LANGSMITH_API_KEY")
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_API_KEY"] = cfg.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = TRACING_PROJECT
    if cfg.langsmith_endpoint:
        os.environ["LANGSMITH_ENDPOINT"] = cfg.langsmith_endpoint


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if args.calibrate:
        return _run_calibration(args.calibrate, args.threshold)
    if args.fetch_verdicts:
        return _run_fetch_verdicts(args.fetch_verdicts)

    from ragas import EvaluationDataset, evaluate

    from src.infrastructure.config import AppConfig
    from tests.eval.run_followup_eval import _usage_handler_cls

    cfg = AppConfig.load()
    if not cfg.gemini_api_key:
        logger.error("未設定 GEMINI_API_KEY")
        return 2
    if args.langsmith:
        _enable_langsmith(cfg)

    samples, source_csv = _build_samples(args, cfg)
    if not samples:
        logger.error("沒有可評的樣本")
        return 2
    logger.info("來源 %s：%d 筆樣本", source_csv.relative_to(EVAL_DIR.parents[1]), len(samples))

    counter = _usage_handler_cls()()
    judge, run_config, model = _build_judge(cfg, args, counter)
    metric, prompt_info = _prepare_metric(judge, args, counter)
    adapt_calls = counter.api_calls

    out = new_results_dir("ragas_faithfulness")
    # 每次唯一的實驗名稱 = LangSmith 根 run 名稱，供 --fetch-verdicts 精準找回這次的 trace
    experiment = f"{DEFAULT_EXPERIMENT_PREFIX}{prompt_info['language']}-{out.name}"
    dataset = EvaluationDataset.from_list(
        [{k: s[k] for k in ("user_input", "response", "retrieved_contexts")} for s in samples])
    result = evaluate(dataset, metrics=[metric], llm=judge, run_config=run_config,
                      experiment_name=experiment, show_progress=True)
    df = result.to_pandas()

    rows = []
    for sample, (_, rec) in zip(samples, df.iterrows()):
        score = _score(rec.get("faithfulness"))
        rows.append({
            "case_id": sample["case_id"], "kind": sample["kind"], "difficulty": sample["difficulty"],
            "model_status": sample["model_status"], "question": sample["user_input"],
            "response": sample["response"], "faithfulness": "" if score is None else round(score, 4),
            "human_label": "", "spot_check_notes": "",
        })
    scores = [r["faithfulness"] for r in rows if r["faithfulness"] != ""]
    by_status: dict[str, dict[str, Any]] = {}
    for r in rows:
        key = r["model_status"] or r["kind"]
        g = by_status.setdefault(key, {"n": 0, "nan": 0, "sum": 0.0})
        g["n"] += 1
        if r["faithfulness"] == "":
            g["nan"] += 1
        else:
            g["sum"] += r["faithfulness"]
    for g in by_status.values():
        valid = g["n"] - g["nan"]
        g["mean"] = None if valid == 0 else round(g.pop("sum") / valid, 4)
        g.pop("sum", None)

    usage = {
        "judge_model": model,
        "adapt_api_calls": adapt_calls,
        "eval_api_calls": counter.api_calls - adapt_calls,
        "tokens_total": counter.tokens,
        "prompt": prompt_info,
    }
    write_csv(out / "ragas_faithfulness.csv", rows, list(rows[0].keys()))
    write_json(out / "summary.json", {
        "dataset_version": DATASET_VERSION,
        "source_csv": source_csv.relative_to(EVAL_DIR.parents[1]).as_posix(),
        "samples": len(rows),
        "nan_count": len(rows) - len(scores),
        "nan_rate": round((len(rows) - len(scores)) / len(rows), 4),
        "mean": None if not scores else round(sum(scores) / len(scores), 4),
        "below_threshold": sum(1 for s in scores if s < args.threshold),
        "threshold": args.threshold,
        "by_status": by_status,
        "usage": usage,
        "langsmith_project": TRACING_PROJECT if args.langsmith else None,
        "langsmith_experiment": experiment if args.langsmith else None,
    })
    (out / "ragas_raw.json").write_text(df.to_json(orient="records", force_ascii=False, indent=2), encoding="utf-8")

    logger.info("樣本 %d｜NaN %d（%.0f%%）｜平均 %s｜低於 %.2f 者 %d 筆", len(rows), len(rows) - len(scores),
                100 * (len(rows) - len(scores)) / len(rows),
                None if not scores else round(sum(scores) / len(scores), 3), args.threshold,
                sum(1 for s in scores if s < args.threshold))
    for key, g in by_status.items():
        logger.info("  %-13s n=%d NaN=%d 平均=%s", key, g["n"], g["nan"], g["mean"])
    logger.info("評審呼叫：翻譯 %d 次、評分 %d 次；Token %s", adapt_calls, usage["eval_api_calls"], counter.tokens)
    logger.info("結果輸出：%s（請填 human_label 後執行 --calibrate）", out.relative_to(EVAL_DIR.parents[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
