"""What ONE model call is allowed to see. Code only.

build_context(profile, plans, slice, rules) -> {"profile", "plans", "rules"}

IN, and nothing else:
    profile  a short summary: the CURRENT facts only, each {id, field, value, source, trust}, so the
             model can cite fact ids. Passed courses are left out: code has already removed them from
             the plans, and listing them would only make the context longer.
    plans    the valid plans from buddy/planner/candidates.py, lettered A, B, C... in their fixed order;
             per semester the core codes, and per elective its code, title, slot and the names of its
             skills from the slice (quote-checked or not, as stored)
    rules    each rule's id, short text, clause and page

OUT, always:
    the fact history (e.g. a losing "my CPI is 9" claim), the chat turns, plan versions, quotes, raw
    syllabus text, and anything about other students or other courses. Each call starts from this
    summary only; the chat history is never sent.

The context rule for the whole chat (buddy/chat):
    - choose and revise see only this summary: profile facts, valid plans or slot options, rules;
    - intake sees only the student's current message; answer sees only the question and the matched
      course records;
    - the profile keeps the last `recent_turns` (config/buddy.yaml, 6) turns, and ONLY the router's
      model call sees them, to tell a follow-up from a new topic. No call ever gets the whole chat.
"""
from __future__ import annotations

import string


def build_context(profile: dict, plans: list, kb: dict, rules: list) -> dict:
    facts = [{k: f[k] for k in ("id", "field", "value", "source", "trust")}
             for f in profile["facts"] if f["field"] != "passed"]
    lettered = {}
    for letter, plan in zip(string.ascii_uppercase, plans):
        lettered[letter] = {}
        for sem, codes in sorted(plan.items()):
            core = [c for c in codes if kb["courses"][c]["category"] == "core"]
            electives = [{"code": c, "title": kb["courses"][c]["title"], "slot": kb["courses"][c]["slot"],
                          "skills": [s["skill"] for s in kb["courses"][c]["skills"]]}
                         for c in codes if kb["courses"][c]["category"] != "core"]
            lettered[letter][str(sem)] = {"core": core, "electives": electives}
    short_rules = [{"id": r["id"], "text": r["text"], "clause": r["provenance"]["clause"], "page": r["provenance"]["page"]}
                   for r in rules]
    return {"profile": facts, "plans": lettered, "rules": short_rules}
