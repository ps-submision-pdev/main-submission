"""Choose one of the valid plans (model), checked by code.

choose(context, plans, profile, llm, version) -> {letter, plan, reasons, by, dropped, call}
    context  buddy/context.build_context(...): the only thing the model sees
    plans    the valid plans in candidates.enumerate_plans order (A = plans[0], B = plans[1], ...)
The model (choose_v1) returns {"plan": "<letter>", "reasons": [{code, why, fact_ids}]}. Code keeps a
reason only if its code is in the chosen plan, every fact id exists in the profile, and "why" is not
empty; dropped reasons are listed with the cause. A letter that is not a valid plan, or a failed call,
gives plan A with the reason "default plan: the model was not available".
Kept reasons are model guesses: render them with the "model guess, unverified" tag.
"""
from __future__ import annotations

import string

from buddy.prompting import ask

DEFAULT_REASON = "default plan: the model was not available"


def choose(context: dict, plans: list, profile: dict, llm, version: str) -> dict:
    letters = dict(zip(string.ascii_uppercase, plans))
    data, call = ask(llm, version, context, {"plan": str, "reasons": list}, "choose")
    if not data or data["plan"] not in letters:
        return {"letter": "A", "plan": plans[0], "by": "fallback", "dropped": [], "call": call,
                "reasons": [{"code": None, "why": DEFAULT_REASON, "fact_ids": []}]}
    plan = letters[data["plan"]]
    in_plan = {c for codes in plan.values() for c in codes}
    fact_ids = {f["id"] for f in profile["facts"]}
    reasons, dropped = [], []
    for r in data["reasons"]:
        ids = r.get("fact_ids") if isinstance(r, dict) and isinstance(r.get("fact_ids"), list) else []
        unknown = [i for i in ids if i not in fact_ids]
        if not isinstance(r, dict) or r.get("code") not in in_plan:
            dropped.append({"reason_given": r, "reason": f"{r.get('code') if isinstance(r, dict) else r} is not in plan {data['plan']}"})
        elif not str(r.get("why") or "").strip():
            dropped.append({"reason_given": r, "reason": "empty why"})
        elif unknown:
            dropped.append({"reason_given": r, "reason": f"unknown fact id {unknown[0]}"})
        else:
            reasons.append({"code": r["code"], "why": r["why"].strip(), "fact_ids": ids})
    return {"letter": data["plan"], "plan": plan, "reasons": reasons, "by": "model", "dropped": dropped, "call": call}
