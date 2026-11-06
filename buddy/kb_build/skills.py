"""Skills (model + code): what a student learns in each full-record course, backed by a quote.

skills(codes, db, llm, prompt_version, trust) -> {skills, status, decisions, usage}
    codes   the slice's full-record courses
    skills  {code: [{skill, quote, source, trust, verified: False}]}
    status  {code: "model" | "no text, no skills" | "no model: not asked"}
    trust   the "kb" part of config/trust.yaml

One call per build, all courses with text in one message (sorted, so the same input hits the cache).
Code drops an item whose course was not asked about (an invented code or a course with no text), an
empty skill, a repeat for that course, or a 7th skill. A kept skill is source "inferred" if its quote
appears in the course's objectives, outcomes, content or description (lowercase, whitespace collapsed),
else source "llm_inferred" with quote null. Both are low trust and verified=false. Courses with no
text are never sent and keep skills [].
"""
from __future__ import annotations

import json
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
SCHEMA = {"skills": list}
TEXT_FIELDS = ("objectives", "outcomes", "content", "description")
MAX_SKILLS = 6


def norm(text: str) -> str:
    return " ".join(text.lower().split())


def course_text(record: dict) -> str:
    return "\n".join(record[f]["value"] for f in TEXT_FIELDS if record[f]["value"])


def skills(codes: list, db: dict, llm, prompt_version: str, trust: dict) -> dict:
    found = {c: [] for c in sorted(codes)}
    ask = [c for c in sorted(codes) if course_text(db[c]).strip()]
    status = {c: ("no text, no skills" if c not in ask else "model" if llm is not None else "no model: not asked")
              for c in found}
    usage = {"attempts": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    decisions = []
    if llm is None or not ask:
        return {"skills": found, "status": status, "decisions": decisions, "usage": usage}

    user = {"courses": [{"code": c, "title": db[c]["title"]["value"], "text": course_text(db[c])} for c in ask]}
    messages = [{"role": "system", "content": (PROMPT_DIR / f"{prompt_version}.md").read_text(encoding="utf-8")},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False, sort_keys=True)}]
    answer = llm.ask_json(messages, SCHEMA, prompt_version)
    usage = answer["usage"]
    if not answer["ok"]:
        decisions.append({"step": "skills", "said": {"error": answer["error"]}, "verdict": "fallback",
                          "evidence": None, "tokens": usage})
        return {"skills": found, "status": status, "decisions": decisions, "usage": usage}

    for item in answer["data"]["skills"]:
        course = item.get("course") if isinstance(item, dict) else None
        skill = (item.get("skill") or "").strip() if isinstance(item, dict) and isinstance(item.get("skill"), str) else ""
        quote = (item.get("quote") or "").strip() if isinstance(item, dict) and isinstance(item.get("quote"), str) else ""
        verdict = "accepted"
        if course not in ask:
            verdict = "dropped:course was not asked about"
        elif not skill:
            verdict = "dropped:empty skill"
        elif any(norm(s["skill"]) == norm(skill) for s in found[course]):
            verdict = "dropped:duplicate skill"
        elif len(found[course]) >= MAX_SKILLS:
            verdict = f"dropped:over the limit of {MAX_SKILLS} skills"
        else:
            checked = bool(quote) and norm(quote) in norm(course_text(db[course]))
            source = "inferred" if checked else "llm_inferred"
            found[course].append({"skill": skill, "quote": quote if checked else None, "source": source,
                                  "trust": trust[source], "verified": False})
            if not checked:
                verdict = "accepted:quote not found in the course text, stored as llm_inferred"
        decisions.append({"step": "skills", "said": item, "verdict": verdict, "evidence": quote or None, "tokens": usage})
    return {"skills": found, "status": status, "decisions": decisions, "usage": usage}
