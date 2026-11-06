"""Router: decide what a chat message is. Code first; the model only when code cannot decide.

route(message, kb, profile, llm, version) -> {intent, by: "code" | "model" | "fallback", reply, call}
Order:
  a. "/..." is a command                                                    (code)
  a2. a change word (add, take, also take, drop, remove, replace, swap,
     change my plan, instead of) together with a slice course, named by code or by its title
     words ("Numerical Methods"), is change_plan                            (code)
  b. a slice course code plus a lookup word (credits, prerequisite(s), skills, hours, slot,
     semester) is a lookup: the record's field with its source tag            (code, reply set)
  c. a rule id, or "rule" with a clause such as 8.4 or 12.1(a): the rule with page and quote (code, reply set)
  d. a course code the slice does not hold: "not in my knowledge base"; a code held only as a code
     (later semesters): "I only have its code"                              (code, reply set)
  e. the first message of a new profile (no turns yet) is intake            (code)
  f. otherwise the model (route_v1) picks intake | change_plan | question | other; code checks the
     label. A failed call or a bad label: a message with "?" is a question, otherwise other.
The model call sees the message and the recent turns kept in the profile; nothing else.
"""
from __future__ import annotations

import re

from buddy.prompting import ask

INTENTS = ("intake", "change_plan", "question", "other")
CODE = re.compile(r"\b[A-Z]{2}\d{4}\b")
LOOKUP = re.compile(r"\b(credits?|prerequisites?|skills?|hours?|slot|semester)\b", re.I)
CHANGE = re.compile(r"\b(also take|take|add|drop|remove|replace|swap|change my plan|instead of)\b", re.I)
GENERIC = {"introduction", "fundamentals", "basics", "basic", "engineering", "chemical", "process", "course"}
CLAUSE = re.compile(r"\b(8\.4|12\.1)\s*(?:\(?([a-d])\)?)?", re.I)


def source_tag(record: dict) -> str:
    p = record["provenance"]
    return f"[checked, {p['source_id']} page {p['page']}, {p['url']}]"


def lookup(code: str, field: str, record: dict) -> str:
    field = {"credits": "credit", "prerequisites": "prerequisite", "skills": "skill", "hour": "hours"}.get(
        field.lower(), field.lower())
    if field == "credit":
        text = f"{record['credits']} credits (L-T-P {record['l']}-{record['t']}-{record['p']})"
    elif field == "prerequisite":
        edges = [f"{e['code']} ({e['source']}, trust {e['trust']})" for e in record["prerequisites"]]
        text = "prerequisites: " + (", ".join(edges) or record["prerequisite_status"] or "none recorded")
    elif field == "skill":
        text = "skills: " + ("; ".join(f"{s['skill']} ({s['source']}, trust {s['trust']})" for s in record["skills"])
                             or "none recorded")
    elif field == "hours":
        text = f"{record['l'] + record['t'] + record['p']} contact hours per week (L-T-P {record['l']}-{record['t']}-{record['p']})"
    else:                                             # slot or semester
        text = f"semester {record['semester']}" + (f", slot {record['slot']}" if record["slot"] else ", core")
    return f"{code} {record['title']}: {text} {source_tag(record)}"


def courses_named(text: str, kb: dict) -> list[str]:
    """Slice courses a message names: by code, or by title (at least 2 of the title's specific words,
    or its only one), e.g. "Numerical Methods" -> MA2206 "Introduction to Numerical Methods"."""
    named = [c for c in CODE.findall(text) if c in kb["courses"]]
    said = set(re.findall(r"[a-z]{4,}", text.lower()))
    for code, r in sorted(kb["courses"].items()):
        title = {w for w in re.findall(r"[a-z]{4,}", r["title"].lower()) if w not in GENERIC}
        if title and len(title & said) >= min(2, len(title)) and code not in named:
            named.append(code)
    return named


def code_only(kb: dict) -> dict:
    """Codes the slice holds without a full record, with where they sit."""
    out = {c: f"slot {s['slot']}, semester {s['semester']}" for s in kb["slots"] if not s["full_records"] for c in s["options"]}
    for sem, codes in list(kb["later_core"].items()) + list(kb.get("earlier_core", {}).items()):
        out.update({c: f"core, semester {sem}" for c in codes})
    return out


def rule_reply(kb: dict, message: str) -> str | None:
    rules = [r for r in kb["rules"] if r["id"] in message]
    m = CLAUSE.search(message)
    if not rules and m and re.search(r"\brules?\b|\bclause\b|\bordinance\b", message, re.I):
        clause = m.group(1) + (f"({m.group(2).lower()})" if m.group(2) else "")
        rules = [r for r in kb["rules"] if r["provenance"]["clause"].startswith(clause)]
    if not rules:
        return None
    return "\n".join(f"{r['id']}: {r['text']} [ordinance {r['provenance']['clause']}, page {r['provenance']['page']}, "
                     f"{r['provenance']['url']}]\n  quote: \"{r['provenance']['quote']}\"" for r in rules)


def route(message: str, kb: dict, profile: dict, llm, version: str) -> dict:
    text = message.strip()
    if text.startswith("/"):
        return {"intent": "command", "by": "code", "reply": None, "call": None}
    if CHANGE.search(text) and courses_named(text, kb):
        return {"intent": "change_plan", "by": "code", "reply": None, "call": None}
    codes = CODE.findall(text)
    field = LOOKUP.search(text)
    full = [c for c in codes if c in kb["courses"]]
    if full and field:
        return {"intent": "lookup", "by": "code", "reply": lookup(full[0], field.group(1), kb["courses"][full[0]]),
                "call": None}
    rules = rule_reply(kb, text)
    if rules:
        return {"intent": "rule", "by": "code", "reply": rules, "call": None}
    held = code_only(kb)
    outside = [c for c in codes if c not in kb["courses"]]
    if outside and not full:
        c = outside[0]
        reply = (f"I only have its code: {c} ({held[c]}); there is no full record of it in my knowledge base."
                 if c in held else f"{c} is not in my knowledge base, so I cannot say anything about it.")
        return {"intent": "not_in_kb", "by": "code", "reply": reply, "call": None}
    if not profile["turns"]:
        return {"intent": "intake", "by": "code", "reply": None, "call": None}

    data, call = ask(llm, version, {"message": text, "recent": profile["turns"]}, {"intent": str}, "route")
    if data and data["intent"] in INTENTS:
        return {"intent": data["intent"], "by": "model", "reply": None, "call": call}
    return {"intent": "question" if "?" in text else "other", "by": "fallback", "reply": None, "call": call}
