"""Answer a question about courses, using only the knowledge-base slice.

answer(question, kb, llm, version) -> {reply, by, courses, flags, call}
1. Code finds the courses: codes named in the question, else keyword match on title and skill names
   (words of 4+ letters, minus common words). Only the best-scoring courses are kept, at most 3.
2. None found: "That course is not in my knowledge base", no model call. A code held only as a code
   (later semesters): "I only have its code", no model call.
3. Otherwise the model (answer_v1) answers from those records only. Code, not the model, appends the
   source tags (page and URL from each record's provenance), and flags any course code in the answer
   that the slice does not hold.
"""
from __future__ import annotations

import re

from buddy.chat.route import CODE, code_only
from buddy.prompting import ask

COMMON = {"about", "what", "which", "course", "courses", "tell", "does", "this", "that", "with", "from",
          "have", "should", "would", "could", "there", "their", "into", "know", "take", "want"}
MAX_COURSES = 3


def find_courses(question: str, kb: dict) -> list[str]:
    named = [c for c in CODE.findall(question) if c in kb["courses"]]
    if named:
        return list(dict.fromkeys(named))[:MAX_COURSES]
    words = {w for w in re.findall(r"[a-z]{4,}", question.lower()) if w not in COMMON}
    scores = {}
    for code, r in kb["courses"].items():
        text = " ".join([r["title"]] + [s["skill"] for s in r["skills"]]).lower()
        score = sum(1 for w in words if re.search(rf"\b{w}", text))
        if score:
            scores[code] = score
    best = max(scores.values(), default=0)
    return sorted(c for c, s in scores.items() if s == best)[:MAX_COURSES]


def record_for_model(code: str, r: dict) -> dict:
    return {"code": code, "title": r["title"], "credits": r["credits"], "ltp": f"{r['l']}-{r['t']}-{r['p']}",
            "semester": r["semester"], "category": r["category"], "slot": r["slot"],
            "skills": [{"skill": s["skill"], "quote": s["quote"]} for s in r["skills"]]}


def answer(question: str, kb: dict, llm, version: str) -> dict:
    held = code_only(kb)
    only_code = [c for c in CODE.findall(question) if c in held and c not in kb["courses"]]
    if only_code:
        return {"reply": f"I only have its code: {only_code[0]} ({held[only_code[0]]}).", "by": "code",
                "courses": [], "flags": [], "call": None}
    codes = find_courses(question, kb)
    if not codes:
        return {"reply": "That course is not in my knowledge base.", "by": "code", "courses": [], "flags": [],
                "call": None}
    data, call = ask(llm, version, {"question": question, "courses": [record_for_model(c, kb["courses"][c]) for c in codes]},
                     {"answer": str}, "answer")
    tags = "\n".join(f"Source: {c} {kb['courses'][c]['title']}, {kb['courses'][c]['provenance']['source_id']} "
                     f"page {kb['courses'][c]['provenance']['page']}, {kb['courses'][c]['provenance']['url']}" for c in codes)
    if data is None:
        facts = "; ".join(f"{c} {kb['courses'][c]['title']}: {kb['courses'][c]['credits']} credits, semester "
                          f"{kb['courses'][c]['semester']}" for c in codes)
        return {"reply": f"Here is what my knowledge base holds: {facts}.\n{tags}", "by": "fallback",
                "courses": codes, "flags": [], "call": call}
    known = set(kb["courses"]) | set(held)
    flags = [f"the answer mentions {c}, which is not in my knowledge base" for c in dict.fromkeys(CODE.findall(data["answer"]))
             if c not in known]
    reply = data["answer"] + ("\n" + "\n".join(f"Warning: {f}" for f in flags) if flags else "") + "\n" + tags
    return {"reply": reply, "by": "model", "courses": codes, "flags": flags, "call": call}
