"""Rule checker: plain code, no LLM. Given a plan and a student's profile, list what breaks a rule.

Inputs
    plan       {semester: [course codes]}, e.g. {5: ["CB3101", "MA3107"]}
    profile    {"passed": [codes], "cpi": 8.2, "cpi_history": [7.9, 8.2]}   (oldest first)
    programme  {"courses_by_year": {1: [first-year codes]}, "courses_per_semester": {5: 6, ...},
                "core": {semester: [codes]}, "slots": [{slot, semester, options: [codes]}]}
               (core and slots come from buddy.kb_build.available.available_for or the KB slice)
    catalog    {code: {"l", "t", "p", "year"}}   year = the year of study the course belongs to
    rules      the "rules" list of data/kb/rules.json

Output: a list of findings {rule_id, semester, severity, message}. severity is "violation" (the plan
must change) or "warning" (allowed, but the student must know: approval needed, low CPI).
Every number comes from the rule's "parameters", never from this file. Each rule id has one function
in CHECKS; a rule without a function raises an error instead of being skipped silently.
Two checks come from the knowledge base, not the ordinance: "kb-course-exists" (the code is known)
"kb-slot-membership" (a course is core for its semester or an option of a slot in that semester) and
"kb-already-passed" (a planned course the student has already passed).
"""
from __future__ import annotations

import json
from pathlib import Path

RULES_FILE = Path("data/kb/rules.json")


def int_keys(d: dict) -> dict:
    """JSON turns the key 5 into "5"; plans and programmes may have come from a JSON file."""
    return {int(k): v for k, v in d.items()}


def finding(rule: dict | str, semester: int | None, severity: str, message: str) -> dict:
    rule_id = rule if isinstance(rule, str) else rule["id"]
    return {"rule_id": rule_id, "semester": semester, "severity": severity, "message": message}


def first_year_before_third_year(rule, plan, profile, programme, catalog):
    """8.4(a): no course of year >= from_year until every course of requires_passed_year is passed."""
    p = rule["parameters"]["required_before"]
    missing = sorted(set(programme["courses_by_year"][p["requires_passed_year"]]) - set(profile["passed"]))
    out = []
    for sem, codes in sorted(plan.items()):
        blocked = [c for c in codes if c in catalog and catalog[c]["year"] >= p["from_year"]]
        if missing and blocked:
            out.append(finding(rule, sem, "violation",
                               f"{', '.join(blocked)} are year {p['from_year']}+ courses, but year "
                               f"{p['requires_passed_year']} courses are not passed: {', '.join(missing)}"))
    return out


def overload(rule, plan, profile, programme, catalog):
    """8.4(c): more courses than the programme prescribes for a semester is an overload."""
    p = rule["parameters"]
    out = []
    for sem, codes in sorted(plan.items()):
        extra = len(codes) - programme["courses_per_semester"].get(sem, len(codes))
        if extra <= 0:
            continue
        if sem < p["from_semester"] or profile["cpi"] < p["min_cpi"] or extra > p["extra_courses"]:
            out.append(finding(rule, sem, "violation",
                               f"{extra} extra course(s) in semester {sem}; allowed: at most {p['extra_courses']}, "
                               f"from semester {p['from_semester']}, with CPI at least {p['min_cpi']} "
                               f"(current CPI {profile['cpi']})"))
        elif p["requires_approval"]:
            out.append(finding(rule, sem, "warning",
                               f"1 extra course in semester {sem} is allowed but needs Dean/Associate Dean approval"))
    return out


def low_cpi(rule, plan, profile, programme, catalog):
    """12.1(a): about the student, not the plan. Uses the CPI history, newest last."""
    p = rule["parameters"]
    recent = profile["cpi_history"][-p["consecutive_semesters"]:]
    if len(recent) == p["consecutive_semesters"] and all(c < p["warn_below"] for c in recent):
        return [finding(rule, None, "warning", f"CPI below {p['warn_below']} in {p['consecutive_semesters']} "
                                              "consecutive semesters: continuation in the programme may be refused")]
    if profile["cpi_history"] and profile["cpi_history"][-1] < p["warn_below"]:
        return [finding(rule, None, "warning", f"CPI below {p['warn_below']}: the institute issues a warning")]
    return []


def contact_hours(rule, plan, profile, programme, catalog):
    """8.4(b), second sentence: L + T + P hours per week of a semester's courses."""
    limit = rule["parameters"]["max_contact_hours_per_week"]
    out = []
    for sem, codes in sorted(plan.items()):
        hours = sum(catalog[c]["l"] + catalog[c]["t"] + catalog[c]["p"] for c in codes if c in catalog)
        if hours > limit:
            out.append(finding(rule, sem, "violation", f"{hours} contact hours per week in semester {sem}; limit {limit}"))
    return out


def slot_membership(plan, programme, catalog):
    """A planned course must be core for that semester or an option of a slot in that same semester."""
    core = programme["core"]
    out = []
    for sem, codes in sorted(plan.items()):
        offered = {c for s in programme["slots"] if s["semester"] == sem for c in s["options"]}
        for code in codes:
            if code not in catalog or code in core.get(sem, []) or code in offered:
                continue                               # unknown codes are reported by kb-course-exists
            home = [f"{s['slot']} (semester {s['semester']})" for s in programme["slots"] if code in s["options"]]
            where = f"; it is an option of {', '.join(home)}" if home else "; it is in no slot open to this student"
            out.append(finding("kb-slot-membership", sem, "violation",
                               f"{code} is not core in semester {sem} and not an option of a semester-{sem} slot{where}"))
    return out


CHECKS = {
    "ord-8.4a-first-year-before-third-year": first_year_before_third_year,
    "ord-8.4c-overload": overload,
    "ord-12.1a-low-cpi": low_cpi,
    "ord-8.4b-contact-hours": contact_hours,
}


def check_plan(plan: dict, profile: dict, programme: dict, catalog: dict, rules: list) -> list[dict]:
    """All findings for a plan, in a fixed order: unknown codes, slot membership, then rule by rule."""
    plan = int_keys(plan)
    programme = {**programme, **{k: int_keys(programme[k]) for k in ("courses_by_year", "courses_per_semester", "core")}}
    out = [finding("kb-course-exists", sem, "violation", f"{code} is not a course in the knowledge base")
           for sem, codes in sorted(plan.items()) for code in codes if code not in catalog]
    out += slot_membership(plan, programme, catalog)
    out += [finding("kb-already-passed", sem, "violation", f"{code} is already passed; it cannot be taken again")
            for sem, codes in sorted(plan.items()) for code in codes if code in profile["passed"]]
    for rule in rules:
        if rule["id"] not in CHECKS:
            raise ValueError(f"no checker written for rule {rule['id']}")
        out += CHECKS[rule["id"]](rule, plan, profile, programme, catalog)
    return out


def load_rules(path: Path = RULES_FILE) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["rules"]
