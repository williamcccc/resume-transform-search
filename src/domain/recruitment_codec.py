"""
招募助手領域物件 <-> JSON 相容 dict 編解碼（純函式，零第三方依賴）

供 Checkpointer 與 Profile 快取以原生型別（str/int/float/bool/list/dict/None）持久化，
避免將 Python 物件直接序列化造成跨版本反序列化風險。
"""
from typing import Any, Dict, Optional

from src.domain.recruitment import (
    CandidateEvaluation,
    CandidateProfile,
    ChatMessage,
    ChatSessionState,
    EvidenceQuote,
    JdRequirements,
    JobRequirement,
    MatchStatus,
    RelaxationItem,
    RelaxationReport,
    RequirementCategory,
    RequirementEvidence,
    RequirementPriority,
    SeniorityLevel,
    ShortlistEntry,
)


def requirement_to_dict(req: JobRequirement) -> Dict[str, Any]:
    return {
        "requirement_id": req.requirement_id,
        "category": req.category.value,
        "priority": req.priority.value,
        "label": req.label,
        "skill": req.skill,
        "skills": list(req.skills),
        "min_value": req.min_value,
        "min_level": int(req.min_level) if req.min_level is not None else None,
    }


def requirement_from_dict(data: Dict[str, Any]) -> JobRequirement:
    level = data.get("min_level")
    skill = data.get("skill")
    raw_skills = data.get("skills")
    if raw_skills is not None:
        skills = tuple(str(x) for x in raw_skills if x)
    else:
        skills = (str(skill),) if skill else ()  # 舊格式（無 skills 鍵）以 [skill] 回填
    return JobRequirement(
        requirement_id=str(data["requirement_id"]),
        category=RequirementCategory(data["category"]),
        priority=RequirementPriority(data["priority"]),
        label=str(data.get("label", "")),
        skill=skill,
        min_value=data.get("min_value"),
        min_level=SeniorityLevel(int(level)) if level is not None else None,
        skills=skills,
    )


def jd_to_dict(jd: JdRequirements) -> Dict[str, Any]:
    return {
        "jd_hash": jd.jd_hash,
        "title": jd.title,
        "must": [requirement_to_dict(r) for r in jd.must],
        "nice": [requirement_to_dict(r) for r in jd.nice],
        "retrieval_query": jd.retrieval_query,
        "ignored_protected_terms": list(jd.ignored_protected_terms),
    }


def jd_from_dict(data: Dict[str, Any]) -> JdRequirements:
    return JdRequirements(
        jd_hash=str(data.get("jd_hash", "")),
        title=str(data.get("title", "")),
        must=tuple(requirement_from_dict(r) for r in data.get("must", [])),
        nice=tuple(requirement_from_dict(r) for r in data.get("nice", [])),
        retrieval_query=str(data.get("retrieval_query", "")),
        ignored_protected_terms=tuple(data.get("ignored_protected_terms", [])),
    )


def profile_to_dict(profile: CandidateProfile) -> Dict[str, Any]:
    return {
        "candidate_id": profile.candidate_id,
        "content_hash": profile.content_hash,
        "extractor_version": profile.extractor_version,
        "years_of_experience": profile.years_of_experience,
        "has_led_team": profile.has_led_team,
        "max_team_size": profile.max_team_size,
        "seniority": int(profile.seniority) if profile.seniority is not None else None,
        "core_skills": list(profile.core_skills),
        "evidence": [{"field": e.field, "quote": e.quote, "verified": e.verified} for e in profile.evidence],
        "degraded": profile.degraded,
        "unverified_skills": list(profile.unverified_skills),
    }


def profile_from_dict(data: Dict[str, Any]) -> CandidateProfile:
    seniority = data.get("seniority")
    return CandidateProfile(
        candidate_id=str(data["candidate_id"]),
        content_hash=str(data.get("content_hash", "")),
        extractor_version=str(data.get("extractor_version", "")),
        years_of_experience=data.get("years_of_experience"),
        has_led_team=data.get("has_led_team"),
        max_team_size=data.get("max_team_size"),
        seniority=SeniorityLevel(int(seniority)) if seniority is not None else None,
        core_skills=tuple(data.get("core_skills", [])),
        evidence=tuple(
            EvidenceQuote(field=str(e["field"]), quote=str(e["quote"]), verified=bool(e.get("verified", False)))
            for e in data.get("evidence", [])
        ),
        degraded=bool(data.get("degraded", False)),
        unverified_skills=tuple(data.get("unverified_skills", [])),
    )


def evaluation_to_dict(ev: CandidateEvaluation) -> Dict[str, Any]:
    return {
        "candidate_id": ev.candidate_id,
        "candidate_name": ev.candidate_name,
        "semantic_score": ev.semantic_score,
        "statuses": {k: v.value for k, v in ev.statuses.items()},
        "profile": profile_to_dict(ev.profile),
        "must_ids": list(ev.must_ids),
        "nice_ids": list(ev.nice_ids),
    }


def evaluation_from_dict(data: Dict[str, Any]) -> CandidateEvaluation:
    return CandidateEvaluation(
        candidate_id=str(data["candidate_id"]),
        candidate_name=str(data.get("candidate_name", "")),
        semantic_score=float(data.get("semantic_score", 0.0)),
        statuses={k: MatchStatus(v) for k, v in data.get("statuses", {}).items()},
        profile=profile_from_dict(data["profile"]),
        must_ids=tuple(data.get("must_ids", [])),
        nice_ids=tuple(data.get("nice_ids", [])),
    )


def shortlist_entry_to_dict(entry: ShortlistEntry) -> Dict[str, Any]:
    return {
        "rank": entry.rank,
        "candidate_id": entry.candidate_id,
        "candidate_name": entry.candidate_name,
        "fully_qualified": entry.fully_qualified,
        "semantic_score": entry.semantic_score,
        "met": list(entry.met),
        "unmet": list(entry.unmet),
        "unknown": list(entry.unknown),
        "evidence": [
            {"requirement_id": e.requirement_id, "field": e.field, "quote": e.quote, "verified": e.verified}
            for e in entry.evidence
        ],
    }


def shortlist_entry_from_dict(data: Dict[str, Any]) -> ShortlistEntry:
    return ShortlistEntry(
        rank=int(data["rank"]),
        candidate_id=str(data["candidate_id"]),
        candidate_name=str(data.get("candidate_name", "")),
        fully_qualified=bool(data.get("fully_qualified", False)),
        semantic_score=float(data.get("semantic_score", 0.0)),
        met=tuple(data.get("met", [])),
        unmet=tuple(data.get("unmet", [])),
        unknown=tuple(data.get("unknown", [])),
        evidence=tuple(
            RequirementEvidence(
                requirement_id=e.get("requirement_id"),
                field=str(e.get("field", "")),
                quote=str(e.get("quote", "")),
                verified=bool(e.get("verified", True)),
            )
            for e in data.get("evidence", [])
        ),
    )


def relaxation_to_dict(rep: RelaxationReport) -> Dict[str, Any]:
    return {
        "pool_size": rep.pool_size,
        "baseline_qualified": rep.baseline_qualified,
        "requested_k": rep.requested_k,
        "items": [
            {
                "requirement_id": i.requirement_id,
                "label": i.label,
                "qualified_if_relaxed": i.qualified_if_relaxed,
                "delta": i.delta,
                "unknown_count": i.unknown_count,
                "met_count": i.met_count,
            }
            for i in rep.items
        ],
        "bottleneck_requirement_ids": list(rep.bottleneck_requirement_ids),
        "scope_note": rep.scope_note,
        "strictest_requirement_ids": list(rep.strictest_requirement_ids),
    }


def relaxation_from_dict(data: Dict[str, Any]) -> RelaxationReport:
    return RelaxationReport(
        pool_size=int(data["pool_size"]),
        baseline_qualified=int(data["baseline_qualified"]),
        requested_k=int(data["requested_k"]),
        items=tuple(
            RelaxationItem(
                requirement_id=str(i["requirement_id"]),
                label=str(i.get("label", "")),
                qualified_if_relaxed=int(i["qualified_if_relaxed"]),
                delta=int(i["delta"]),
                unknown_count=int(i["unknown_count"]),
                met_count=int(i.get("met_count", 0)),
            )
            for i in data.get("items", [])
        ),
        bottleneck_requirement_ids=tuple(data.get("bottleneck_requirement_ids", [])),
        scope_note=str(data.get("scope_note", "僅統計語意檢索候選池 Top-N")),
        strictest_requirement_ids=tuple(data.get("strictest_requirement_ids", [])),
    )


def session_to_dict(state: ChatSessionState) -> Dict[str, Any]:
    return {
        "session_id": state.session_id,
        "turn_count": state.turn_count,
        "jd_requirements": jd_to_dict(state.jd_requirements) if state.jd_requirements else None,
        "shortlist": [shortlist_entry_to_dict(e) for e in state.shortlist],
        "pool_evaluations": [evaluation_to_dict(e) for e in state.pool_evaluations],
        "relaxation": relaxation_to_dict(state.relaxation) if state.relaxation else None,
        "last_referenced_candidate_id": state.last_referenced_candidate_id,
        "history": [{"role": m.role, "content": m.content} for m in state.history],
    }


def session_from_dict(data: Optional[Dict[str, Any]], session_id: str) -> ChatSessionState:
    if not data:
        return ChatSessionState(session_id=session_id)
    jd = data.get("jd_requirements")
    relax = data.get("relaxation")
    return ChatSessionState(
        session_id=str(data.get("session_id") or session_id),
        turn_count=int(data.get("turn_count", 0)),
        jd_requirements=jd_from_dict(jd) if jd else None,
        shortlist=tuple(shortlist_entry_from_dict(e) for e in data.get("shortlist", [])),
        pool_evaluations=tuple(evaluation_from_dict(e) for e in data.get("pool_evaluations", [])),
        relaxation=relaxation_from_dict(relax) if relax else None,
        last_referenced_candidate_id=data.get("last_referenced_candidate_id"),
        history=tuple(ChatMessage(role=str(m["role"]), content=str(m["content"])) for m in data.get("history", [])),
    )
