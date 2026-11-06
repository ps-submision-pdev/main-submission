"""Revise a plan the way the student asks (model), never accepting a plan that breaks a rule (code).

revise(request, current_plan, kb, profile, llm, version, max_attempts=2, now=None)
  -> {accepted, plan, note, findings, nearest, attempts, calls}
1. The model (revise_v1) proposes {"plan": {semester: [codes]}, "note"}.
2. Code runs planner.candidates.check_candidate (rules.check_plan plus core-missing / slot-unfilled).
3. Any "violation": the findings go back to the model once more (at most max_attempts proposals).
4. Accepted: the plan is stored as a new version in the profile (number, time, request); warnings are
   returned as warnings. Not accepted: accepted False, the findings in plain words (rule id, page,
   quote) and the nearest valid plan from candidates.enumerate_plans (fewest elective differences,
   ties in the enumerator's order). That plan is offered, not stored: the student did not ask for it.
A plan with a violation is never accepted or stored.
"""
from __future__ import annotations

from buddy.context import build_context
from buddy.planner.candidates import check_candidate, enumerate_plans, programme_and_catalog
from buddy.profile import add_plan_version
from buddy.prompting import ask


def plain(findings: list, rules: list) -> list[dict]:
    """Findings with the rule's page and quote when the finding comes from an ordinance rule."""
    by_id = {r["id"]: r for r in rules}
    out = []
    for f in findings:
        r = by_id.get(f["rule_id"])
        out.append({**f, "page": r["provenance"]["page"] if r else None, "quote": r["provenance"]["quote"] if r else None})
    return out


def electives(plan: dict, kb: dict) -> set:
    return {c for codes in plan.values() for c in codes if c in kb["courses"] and kb["courses"][c]["category"] != "core"}


def nearest_valid(plan: dict, valid: list, kb: dict) -> dict | None:
    wanted = electives(plan, kb)
    return min(valid, key=lambda v: len(electives(v, kb) ^ wanted), default=None)   # min keeps the first tie


def as_plan(raw) -> dict | None:
    """{"4": ["CB2201", ...]} -> {4: [...]}; None if the shape is wrong."""
    if not isinstance(raw, dict):
        return None
    try:
        plan = {int(sem): codes for sem, codes in raw.items()}
    except (TypeError, ValueError):
        return None
    ok = all(isinstance(codes, list) and all(isinstance(c, str) for c in codes) for codes in plan.values())
    return plan if ok else None


def revise(request: str, current_plan: dict, kb: dict, profile: dict, llm, version: str,
           max_attempts: int = 2, now: str | None = None) -> dict:
    rules = kb["rules"]
    valid = enumerate_plans(kb, profile, rules)["plans"]
    programme, _, _ = programme_and_catalog(kb)
    options = {str(sem): {"core": programme["core"].get(sem, []),
                          "slots": {s["slot"]: s["options"] for s in programme["slots"] if s["semester"] == sem}}
               for sem in kb["horizon"]}
    summary = build_context(profile, [], kb, rules)
    payload = {"request": request, "current_plan": {str(k): v for k, v in current_plan.items()}, "options": options,
               "profile": summary["profile"], "rules": summary["rules"], "problems": []}
    calls, proposal, findings, note = [], None, [], ""
    for attempt in range(1, max_attempts + 1):
        data, call = ask(llm, version, payload, {"plan": dict, "note": str}, "revise")
        calls.append(call)
        if data is None:                                   # the model is not available
            break
        proposal, note = as_plan(data["plan"]), data["note"]
        if proposal is None:
            payload["problems"] = ["your plan was not in the form {semester: [course codes]}"]
            continue
        findings = plain(check_candidate(proposal, kb, profile, rules), rules)
        if not any(f["severity"] == "violation" for f in findings):
            add_plan_version(profile, proposal, request, now, by="model", note=note)
            return {"accepted": True, "plan": proposal, "note": note, "findings": findings, "nearest": None,
                    "attempts": attempt, "calls": calls}
        payload["problems"] = [f"{f['rule_id']}: {f['message']}" for f in findings if f["severity"] == "violation"]
    return {"accepted": False, "plan": None, "note": note, "findings": findings,
            "nearest": nearest_valid(proposal or current_plan, valid, kb), "attempts": len(calls), "calls": calls}
