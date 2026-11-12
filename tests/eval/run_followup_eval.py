"""
Spec-0024 追問 answer_status 正確率評測與敘述人工抽查（人工觸發，不納入 CI）。

對 tests/eval/data/followup_questions.jsonl 每題呼叫 GeminiRecruitmentLlm.answer_followup，
計算 3×3 混淆矩陣；並對 narration_cases.jsonl 呼叫 narrate_match，輸出 CSV 供人工抽查。

用法：
    python tests/eval/run_followup_eval.py [--max-llm-calls 60] [--skip-narration]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.eval.eval_support import (  # noqa: E402
    DATA_DIR,
    DATASET_VERSION,
    DIFFICULTY_LEVELS,
    STATUS_LABELS,
    classification_summary,
    confusion_matrix,
    load_jsonl,
    merge_usage,
    new_results_dir,
    subsets_by,
    write_csv,
    write_json,
)

logger = logging.getLogger("eval.followup")
ALIAS = "候選人 #1"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Spec-0024 answer_status 正確率評測")
    parser.add_argument("--max-llm-calls", type=int, default=80, help="LLM 呼叫硬上限（不含 SDK 內部重試）")
    parser.add_argument("--skip-narration", action="store_true", help="只跑追問，不跑 narrate_match")
    args = parser.parse_args(argv)
    if args.max_llm_calls <= 0:
        parser.error("--max-llm-calls 必須為正整數")
    return args


def _usage_handler_cls():
    from langchain_core.callbacks import BaseCallbackHandler

    class UsageCounter(BaseCallbackHandler):
        """計算實際送出的 LLM 請求數並累加 usage_metadata（含 SDK 重試）。"""

        def __init__(self) -> None:
            self.api_calls = 0
            self.tokens: dict[str, int] = {}

        def on_llm_end(self, response, **kwargs: Any) -> None:
            self.api_calls += 1
            for gens in response.generations:
                for gen in gens:
                    message = getattr(gen, "message", None)
                    merge_usage(self.tokens, getattr(message, "usage_metadata", None))

    return UsageCounter


def _build_llm(cfg, counter):
    from langchain_google_genai import ChatGoogleGenerativeAI

    from src.domain.recruitment_services import CircuitBreaker
    from src.infrastructure.llm.gemini_recruitment_llm import GeminiRecruitmentLlm

    model_name = cfg.recruit_llm_model or cfg.gemini_model
    kwargs: dict[str, Any] = {}
    if cfg.recruit_llm_thinking_budget is not None and "thinking_budget" in ChatGoogleGenerativeAI.model_fields:
        kwargs["thinking_budget"] = int(cfg.recruit_llm_thinking_budget)
    # 與 GeminiRecruitmentLlm 內部預設建構相同參數，額外掛上用量 callback；model_copy 會保留 callbacks
    chat = ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=cfg.gemini_api_key,
        temperature=cfg.recruit_llm_temperature,
        max_output_tokens=cfg.recruit_llm_max_output_tokens,
        timeout=cfg.recruit_llm_timeout_seconds,
        max_retries=0,
        callbacks=[counter],
        **kwargs,
    )
    llm = GeminiRecruitmentLlm(
        api_key=cfg.gemini_api_key,
        model_name=model_name,
        temperature=cfg.recruit_llm_temperature,
        max_output_tokens=cfg.recruit_llm_max_output_tokens,
        timeout_seconds=cfg.recruit_llm_timeout_seconds,
        profile_max_output_tokens=cfg.recruit_profile_max_output_tokens,
        narrative_max_output_tokens=cfg.recruit_narrative_max_output_tokens,
        skill_aliases=cfg.recruit_skill_aliases,
        thinking_budget=cfg.recruit_llm_thinking_budget,
        circuit_breaker=CircuitBreaker(cfg.recruit_circuit_breaker_cooldown_seconds),
        max_retries=cfg.api_max_retries,
        retry_delay=cfg.api_retry_delay,
        chat_model=chat,
    )
    return llm, model_name


def build_narration_facts(case: dict[str, Any]):
    """narration_cases.jsonl 的一案 → MatchNarrationFacts（narrate_match 評測與 Ragas 練習共用，確保輸入一致）。"""
    from src.domain.recruitment import CandidateFact, MatchNarrationFacts

    candidates = tuple(
        CandidateFact(
            alias=f"候選人 #{i}",
            fully_qualified=bool(c["fully_qualified"]),
            met_labels=tuple(c["met_labels"]),
            unmet_labels=tuple(c["unmet_labels"]),
            unknown_labels=tuple(c["unknown_labels"]),
            evidence_quotes=tuple(c["evidence_quotes"]),
        )
        for i, c in enumerate(case["candidates"], start=1)
    )
    return MatchNarrationFacts(
        jd_title=case["jd_title"],
        requested_k=int(case["requested_k"]),
        pool_size=int(case["pool_size"]),
        must_labels=tuple(case["must_labels"]),
        nice_labels=tuple(case["nice_labels"]),
        candidates=candidates,
        relaxation=None,
    )


def _resume_name(text: str, fallback: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return fallback


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    from src.domain.recruitment import AnswerStatus, FollowupFacts
    from src.domain.recruitment_services import EvidenceVerifier, ProtectedAttributeGuard, mask_contact_info
    from src.infrastructure.config import AppConfig
    from src.interfaces.web.server import build_recruitment_settings

    cfg = AppConfig.load()
    if not cfg.gemini_api_key:
        logger.error("未設定 GEMINI_API_KEY")
        return 2
    settings = build_recruitment_settings(cfg)
    guard = ProtectedAttributeGuard(settings.protected_attr_terms)
    verifier = EvidenceVerifier(settings.evidence_min_chars)

    followups = load_jsonl(
        DATA_DIR / "followup_questions.jsonl",
        ["case_id", "candidate_id", "question", "expected_status", "profile_summary", "difficulty"],
        "case_id",
        enum_fields={"expected_status": STATUS_LABELS, "difficulty": DIFFICULTY_LEVELS},
    )
    narrations = [] if args.skip_narration else load_jsonl(
        DATA_DIR / "narration_cases.jsonl",
        ["case_id", "jd_title", "requested_k", "pool_size", "must_labels", "nice_labels", "candidates"],
        "case_id",
    )
    resumes: dict[str, str] = {}
    names: dict[str, str] = {}
    for path in sorted((DATA_DIR / "resumes").glob("*.md")):
        resumes[path.stem] = path.read_text(encoding="utf-8")
        names[path.stem] = _resume_name(resumes[path.stem], path.stem)
    unknown = sorted({f["candidate_id"] for f in followups} - resumes.keys())
    if unknown:
        logger.error("追問題引用了不存在的履歷：%s", ", ".join(unknown))
        return 2
    counts = {label: sum(1 for f in followups if f["expected_status"] == label) for label in STATUS_LABELS}
    logger.info("資料集 %s：追問 %d 題 %s、敘述 %d 案", DATASET_VERSION, len(followups), counts, len(narrations))

    counter = _usage_handler_cls()()
    llm, model_name = _build_llm(cfg, counter)
    logical_calls = 0
    incomplete = False

    def prepare_text(cid: str, alias: str) -> str:
        # 與 CandidateProfileService.prepare_llm_text 相同：受保護欄位遮蔽 → 姓名/聯絡方式遮蔽 → 截斷
        masked = mask_contact_info(guard.redact_resume(resumes[cid]), [names[cid]], alias)
        return masked[: settings.profile_max_resume_chars]

    rows: list[dict[str, Any]] = []
    for case in followups:
        if logical_calls >= args.max_llm_calls:
            incomplete = True
            logger.warning("已達 LLM 呼叫上限 %d，停止追問評測", args.max_llm_calls)
            break
        llm_text = prepare_text(case["candidate_id"], ALIAS)
        facts = FollowupFacts(
            alias=ALIAS,
            question=case["question"],
            profile_summary=dict(case["profile_summary"]),
            evidence_quotes=(),
            met_labels=tuple(case.get("met_labels", [])),
            unmet_labels=tuple(case.get("unmet_labels", [])),
            unknown_labels=tuple(case.get("unknown_labels", [])),
            resume_excerpt=llm_text,
        )
        row = {"case_id": case["case_id"], "difficulty": case["difficulty"], "note": case.get("note", ""),
               "candidate_id": case["candidate_id"], "question": case["question"],
               "expected_status": case["expected_status"], "spot_check_notes": ""}
        logical_calls += 1
        try:
            narration = llm.answer_followup(facts)
        except Exception as err:  # 單題失敗不中斷整批
            row.update(model_status="ERROR", verified_status="ERROR", error=type(err).__name__)
            logger.warning("%s 失敗：%s", case["case_id"], type(err).__name__)
            rows.append(row)
            continue
        quotes = list(narration.quotes)
        verified_quotes = [q for q in quotes if verifier.verify(q, llm_text)]
        status = narration.answer_status
        verified = status
        if status in (AnswerStatus.SUPPORTED, AnswerStatus.CONTRADICTED) and not verified_quotes:
            verified = AnswerStatus.NOT_MENTIONED
        row.update(
            model_status=status.value,
            verified_status=verified.value,
            answer_text=narration.answer_text,
            quotes=" | ".join(quotes),
            quotes_verbatim=f"{len(verified_quotes)}/{len(quotes)}",
            error="",
        )
        rows.append(row)

    narration_rows: list[dict[str, Any]] = []
    for case in narrations:
        if logical_calls >= args.max_llm_calls:
            incomplete = True
            logger.warning("已達 LLM 呼叫上限 %d，停止敘述評測", args.max_llm_calls)
            break
        facts = build_narration_facts(case)
        candidates = facts.candidates
        summary = "；".join(
            f"{c.alias}({'完全符合' if c.fully_qualified else '補位'}) 符合[{'、'.join(c.met_labels)}] "
            f"不符[{'、'.join(c.unmet_labels)}] 未提及[{'、'.join(c.unknown_labels)}]"
            for c in candidates
        )
        row = {"case_id": case["case_id"], "jd_title": case["jd_title"], "facts_summary": summary,
               "spot_check_notes": ""}
        logical_calls += 1
        try:
            row.update(narration=llm.narrate_match(facts), error="")
        except Exception as err:
            row.update(narration="", error=type(err).__name__)
            logger.warning("%s 失敗：%s", case["case_id"], type(err).__name__)
        narration_rows.append(row)

    scored = [r for r in rows if r["model_status"] != "ERROR"]
    results_by_subset = {}
    for subset, subset_rows in subsets_by(scored, "difficulty", DIFFICULTY_LEVELS).items():
        raw_m = confusion_matrix((r["expected_status"], r["model_status"]) for r in subset_rows)
        ver_m = confusion_matrix((r["expected_status"], r["verified_status"]) for r in subset_rows)
        results_by_subset[subset] = {
            "cases_scored": len(subset_rows),
            "raw": {"matrix": raw_m, **classification_summary(raw_m)},
            "verified": {"matrix": ver_m, **classification_summary(ver_m)},
        }
    usage = {
        "model": model_name,
        "llm_logical_calls": logical_calls,
        "llm_api_calls": counter.api_calls,
        "llm_tokens": counter.tokens,
        "embedding": None,
    }

    out = new_results_dir("followup")
    write_csv(out / "followup_spot_check.csv", rows,
              ["case_id", "difficulty", "note", "candidate_id", "question", "expected_status", "model_status",
               "verified_status",
               "answer_text", "quotes", "quotes_verbatim", "error", "spot_check_notes"])
    if narration_rows:
        write_csv(out / "narration_spot_check.csv", narration_rows,
                  ["case_id", "jd_title", "facts_summary", "narration", "error", "spot_check_notes"])
    write_json(out / "followup_summary.json", {
        "dataset_version": DATASET_VERSION,
        "model": model_name,
        "incomplete": incomplete,
        "cases_total": len(followups),
        "cases_scored": len(scored),
        "cases_error": len(rows) - len(scored),
        "subsets": results_by_subset,
        "usage": usage,
    })
    write_json(out / "usage.json", usage)

    for subset, res in results_by_subset.items():
        raw, ver = res["raw"], res["verified"]
        logger.info("[%s] %d 題｜原始正確率 %s、驗證後正確率 %s、NM→SUPPORTED %d 題（比率 %s）", subset,
                    res["cases_scored"], raw["accuracy"], ver["accuracy"], raw["false_support_count"],
                    raw["false_support_rate"])
        for exp in STATUS_LABELS:
            logger.info("  標準 %-13s → %s", exp, raw["matrix"][exp])
    logger.info("原始 status 與標準不符的題目：%s", ", ".join(
        r["case_id"] for r in scored if r["model_status"] != r["expected_status"]) or "無")
    logger.info("驗證後與標準不符的題目：%s", ", ".join(
        r["case_id"] for r in scored if r["verified_status"] != r["expected_status"]) or "無")
    logger.info("LLM 呼叫：邏輯 %d 次、實際請求 %d 次；Token %s", logical_calls, counter.api_calls, counter.tokens)
    logger.info("結果輸出：%s", out.relative_to(Path(__file__).resolve().parents[2]))
    return 1 if incomplete else 0


if __name__ == "__main__":
    sys.exit(main())
