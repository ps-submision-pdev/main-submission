"""Every valid plan for the horizon, by enumeration. Code only, no model, no randomness.

enumerate_plans(slice, profile, rules, horizon=None) -> {plans, findings, rejected, missing}
    plans     [{semester: [codes]}]: each horizon semester's core plus exactly ONE option per slot, kept
              only if rules.check_plan gives no "violation"
    findings  the warnings of each kept plan (same order as plans)
    rejected  [{plan, findings}] for every combination with a violation
    missing   slice fields the checks need but could not find (named, never guessed)
Order: slots as stored in the slice (semester, then slot), options in the slice's rank order; the
first slot changes slowest. The same slice and profile always give the same list.
check_candidate(plan, slice, profile, rules) runs the same checks on any plan (used by tests and revise),
plus "kb-core-missing" (violation) and "kb-slot-unfilled" (warning).
"""
from __future__ import annotations

from itertools import product

from buddy.profile import to_rules_profile
from buddy.rules import check_plan, finding, int_keys


def programme_and_catalog(kb: dict) -> tuple[dict, dict, list]:
    """What rules.check_plan needs, built from the slice, plus the names of missing fields."""
    missing = []
    core = {int(sem): codes for sem, codes in kb["core"].items()}
    slots = [{"slot": s["slot"], "semester": s["semester"], "options": s["options"]}
             for s in kb["slots"] if s["full_records"]]
    if "earlier_core" not in kb:
        missing.append("earlier_core (first-year courses for rule 8.4(a))")
    earlier = kb.get("earlier_core", {})
    first_year = sorted(c for sem in ("1", "2") for c in earlier.get(sem, []))
    per_semester = {sem: len(codes) + sum(s["semester"] == sem for s in slots) for sem, codes in core.items()}
    catalog = {}
    for code, r in kb["courses"].items():
        if None in (r["l"], r["t"], r["p"], r["semester"]):
            missing.append(f"L-T-P or semester of {code}")
            continue
        catalog[code] = {"l": r["l"], "t": r["t"], "p": r["p"], "year": (r["semester"] + 1) // 2}
    programme = {"courses_by_year": {1: first_year}, "courses_per_semester": per_semester, "core": core, "slots": slots}
    return programme, catalog, missing


def check_candidate(plan: dict, kb: dict, profile: dict, rules: list) -> list[dict]:
    """rules.check_plan, plus two plan-shape checks for every semester the plan names:
    "kb-core-missing" (a violation: a core course was left out) and "kb-slot-unfilled" (a warning)."""
    programme, catalog, _ = programme_and_catalog(kb)
    plan = int_keys(plan)
    found = check_plan(plan, to_rules_profile(profile), programme, catalog, rules)
    for sem, codes in sorted(plan.items()):
        found += [finding("kb-core-missing", sem, "violation", f"core course {c} of semester {sem} is missing")
                  for c in programme["core"].get(sem, []) if c not in codes]
        found += [finding("kb-slot-unfilled", sem, "warning", f"slot {s['slot']} of semester {sem} has no course")
                  for s in programme["slots"] if s["semester"] == sem and not set(s["options"]) & set(codes)]
    return found


def enumerate_plans(kb: dict, profile: dict, rules: list, horizon: list | None = None) -> dict:
    semesters = horizon or kb["horizon"]
    programme, _, missing = programme_and_catalog(kb)
    slots = [s for s in programme["slots"] if s["semester"] in semesters]
    plans, findings, rejected = [], [], []
    for choice in product(*[s["options"] for s in slots]):
        plan = {sem: list(programme["core"].get(sem, [])) for sem in semesters}
        for slot, code in zip(slots, choice):
            plan[slot["semester"]].append(code)
        found = check_candidate(plan, kb, profile, rules)
        if any(f["severity"] == "violation" for f in found):
            rejected.append({"plan": plan, "findings": found})
        else:
            plans.append(plan)
            findings.append(found)
    return {"plans": plans, "findings": findings, "rejected": rejected, "missing": missing}
