"""Show a plan in plain words. Code only.

Per course: credits, contact hours (L + T + P per week), a source tag, and a "because" line.
    "checked, source page N"   the record was read from page N of a source document (trust 0.9)
    "model guess, unverified"  the model's reason for choosing an option (llm_inferred, trust 0.3)
"because" lists the profile facts that link to the course, with id, source and trust:
    an elective: the student's weakness facts that the slice's foundations link to this course;
    a core course: the passed facts of its prerequisites.
Warnings come from the rule findings, in plain words.
"""
from __future__ import annotations


def fact_text(f: dict) -> str:
    return f"{f['id']} {f['field']}={f['value']} ({f['source']}, {f['trust']})"


def because(code: str, record: dict, kb: dict, profile: dict) -> str:
    facts = profile["facts"]
    if record["category"] == "core":
        needed = {e["code"] for e in record["prerequisites"]}
        passed = [f for f in facts if f["field"] == "passed" and f["value"] in needed]
        reason = f"compulsory core of semester {record['semester']}"
        return reason + ("; prerequisites passed: " + ", ".join(fact_text(f) for f in passed) if passed else "")
    weak = {x["weakness"].lower() for x in kb["foundations"] if x["code"] == code}
    linked = [f for f in facts if f["field"] == "weakness" and str(f["value"]).lower() in weak]
    return ", ".join(fact_text(f) for f in linked) or "no profile fact links to this course"


def render_plan(letter: str, plan: dict, kb: dict, profile: dict, findings: list) -> str:
    lines = [f"Plan {letter}"]
    for sem, codes in sorted(plan.items()):
        lines.append(f"  Semester {sem}")
        credits = hours = 0
        for code in codes:
            r = kb["courses"][code]
            h = r["l"] + r["t"] + r["p"]
            credits, hours = credits + r["credits"], hours + h
            lines.append(f"    {code} {r['title']}: {r['credits']} credits, {h} contact hours/week "
                         f"[checked, source page {r['provenance']['page']}]")
            if r["rank"] and r["rank"]["source"] == "model":
                why = r["rank"]["reason"] or "(reason dropped by a code check)"
                lines.append(f"      why this option: {why} [model guess, unverified]")
            lines.append(f"      because: {because(code, r, kb, profile)}")
        lines.append(f"    total: {credits} credits, {hours} contact hours/week")
    warnings = [f["message"] for f in findings if f["severity"] == "warning"]
    lines += ["  Warnings: " + "; ".join(warnings)] if warnings else ["  Warnings: none"]
    return "\n".join(lines)
