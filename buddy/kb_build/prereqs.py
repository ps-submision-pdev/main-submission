"""Prerequisites: the database first; the model only where the documents name no prerequisite code.

prerequisites(slice_codes, already_done, db, llm, trust) -> {edges, status, decisions, usage}
    edges   {course: [{code, source, trust, quote, raw, verified: False}]}  code = the prerequisite
    status  {course: "explicit" | "explicit: none" | "model" | "no text: model not asked" | "no model: not asked"}
    trust   the "kb" part of config/trust.yaml

1. Database: codes named in the course's prerequisite field that exist in the database become
   source "explicit" edges (trust explicit). "Nil" / "None" means: the document says no prerequisite.
2. Model: one call for the courses still without a usable prerequisite that have syllabus text.
   It may only name codes from the slice or already_done. Code drops an edge whose code is unknown or
   not allowed, that points at the course itself, repeats, or would create a cycle. A kept edge is
   source "inferred" if its evidence_quote appears word for word in the course's stored text, else
   source "llm_inferred". Both are low trust and verified=false.
Courses with no text are never sent to the model.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

PROMPT_VERSION = "prereq_v1"
PROMPT_FILE = Path(__file__).resolve().parent / "prompts" / f"{PROMPT_VERSION}.md"
SCHEMA = {"prerequisites": list}
CODE = re.compile(r"\b[A-Z]{2}\d{4}\b")
NONE_WORDS = re.compile(r"^[\s:]*(?:nil|none|na|n/a|-|no|not applicable)\.?\s*$", re.I)
TEXT_FIELDS = ("description", "objectives", "content", "outcomes")


def squeeze(text: str) -> str:
    return " ".join(text.split())


def course_text(record: dict) -> str:
    return "\n".join(record[f]["value"] for f in TEXT_FIELDS if record[f]["value"])


def has_path(graph: dict, start: str, goal: str) -> bool:
    """graph: prerequisite -> courses that need it. Is there a chain start -> ... -> goal?"""
    seen, todo = set(), [start]
    while todo:
        node = todo.pop()
        if node == goal:
            return True
        if node not in seen:
            seen.add(node)
            todo.extend(graph.get(node, []))
    return False


def prerequisites(slice_codes: list, already_done: list, db: dict, llm, trust: dict) -> dict:
    edges, status, graph = {}, {}, {}
    for code in sorted(slice_codes):
        field = db[code]["prerequisite"]
        raw = field["value"] or ""
        named = [c for c in dict.fromkeys(CODE.findall(raw)) if c in db and c != code]
        quote = field["chosen"]["span"] if field.get("chosen") else None
        edges[code] = [{"code": c, "source": "explicit", "trust": trust["explicit"], "quote": quote, "raw": raw,
                        "verified": False} for c in named]
        for c in named:
            graph.setdefault(c, []).append(code)
        status[code] = "explicit" if named else "explicit: none" if raw and NONE_WORDS.match(raw) else None

    ask = [c for c in sorted(slice_codes) if status[c] is None and course_text(db[c])]
    for c in slice_codes:
        if status[c] is None and c not in ask:
            status[c] = "no text: model not asked"
    allowed = sorted(set(slice_codes) | set(already_done))
    decisions, usage = [], {"attempts": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if llm is None or not ask:
        for c in ask:
            status[c] = "no model: not asked"
        return {"edges": edges, "status": status, "decisions": decisions, "usage": usage}

    user = {"courses": [{"code": c, "title": db[c]["title"]["value"], "text": course_text(db[c])} for c in ask],
            "allowed": [{"code": c, "title": db[c]["title"]["value"]} for c in allowed]}
    messages = [{"role": "system", "content": PROMPT_FILE.read_text(encoding="utf-8")},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False, sort_keys=True)}]
    answer = llm.ask_json(messages, SCHEMA, PROMPT_VERSION)
    usage = answer["usage"]
    for c in ask:
        status[c] = "model"
    if not answer["ok"]:
        decisions.append({"step": "prerequisites", "said": {"error": answer["error"]}, "verdict": "fallback",
                          "evidence": None, "tokens": usage})
        return {"edges": edges, "status": status, "decisions": decisions, "usage": usage}

    for item in answer["data"]["prerequisites"]:
        course = item.get("course") if isinstance(item, dict) else None
        pre = item.get("prerequisite") if isinstance(item, dict) else None
        quote = (item.get("evidence_quote") or "").strip() if isinstance(item, dict) else ""
        verdict = "accepted"
        if course not in ask:
            verdict = "dropped:course was not asked about"
        elif pre not in allowed or pre not in db:
            verdict = "dropped:not a course in the slice or already_done"
        elif pre == course:
            verdict = "dropped:a course cannot require itself"
        elif any(e["code"] == pre for e in edges[course]):
            verdict = "dropped:duplicate"
        elif has_path(graph, course, pre):
            verdict = "dropped:would create a cycle"
        else:
            found = bool(quote) and squeeze(quote) in squeeze(course_text(db[course]))
            source = "inferred" if found else "llm_inferred"
            edges[course].append({"code": pre, "source": source, "trust": trust[source], "quote": quote or None,
                                  "raw": quote or None, "verified": False})
            graph.setdefault(pre, []).append(course)
            if not found:
                verdict = "accepted:no verbatim quote, stored as llm_inferred"
        decisions.append({"step": "prerequisites", "said": item, "verdict": verdict,
                          "evidence": quote or None, "tokens": usage})
    return {"edges": edges, "status": status, "decisions": decisions, "usage": usage}
