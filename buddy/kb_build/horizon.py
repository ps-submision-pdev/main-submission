"""Horizon (code only): which semesters get full course records and a ranking call.

split_horizon(available, persona, settings) -> {semesters, inside, later_slots, later_core}
    semesters    planning_semester .. planning_semester + kb_horizon_semesters - 1
    inside       the available set cut to those semesters: its core and slot options get full
                 records, and only its slots are ranked
    later_slots  [{slot, semester, options: [codes]}] after the horizon: codes only, no ranking call
    later_core   {semester: [codes]} after the horizon: codes only
full_record_count(inside, settings)  core in the horizon + min(options_per_slot, options) per slot
text_report(inside, db)  per core course and option in the horizon: which of description, objectives
    and outcomes it has, and, if it has none, the department syllabus that text would come from
"""
from __future__ import annotations

from buddy.kb_build.available import same_department
from buddy.kb_build.persona import programmes

TEXT_FIELDS = ("description", "objectives", "outcomes")


def split_horizon(available: dict, persona: dict, settings: dict) -> dict:
    first = persona["planning_semester"]
    semesters = list(range(first, first + settings["kb_horizon_semesters"]))
    inside = {**available,
              "slots": [s for s in available["slots"] if s["semester"] in semesters],
              "core": {sem: codes for sem, codes in available["core"].items() if sem in semesters}}
    later_slots = [{"slot": s["slot"], "semester": s["semester"], "options": list(s["options"])}
                   for s in available["slots"] if s["semester"] > semesters[-1]]
    later_core = {sem: list(codes) for sem, codes in available["core"].items() if sem > semesters[-1]}
    return {"semesters": semesters, "inside": inside, "later_slots": later_slots, "later_core": later_core}


def full_record_count(inside: dict, settings: dict) -> int:
    core = sum(len(codes) for codes in inside["core"].values())
    return core + sum(min(settings["options_per_slot"], len(s["options"])) for s in inside["slots"])


def syllabus_for(owner: str | None) -> str:
    """Where the missing text would come from: the downloaded syllabus of that department, or none yet."""
    ids = sorted(sid for sid, src in programmes().items() if same_department(src.get("department"), owner))
    if ids:
        return f"{', '.join(ids)} (downloaded; no course page found there)"
    return f"not in ingest/sources.yaml ({owner or 'owner unknown'})"


def text_report(inside: dict, db: dict) -> list[dict]:
    courses = [(code, f"core S{sem}") for sem, codes in sorted(inside["core"].items()) for code in codes]
    courses += [(code, f"option {s['slot']}") for s in inside["slots"] for code in s["options"]]
    rows = []
    for code, kind in courses:
        record = db[code]
        has = {f: bool((record[f]["value"] or "").strip()) for f in TEXT_FIELDS}
        owner = record["owner_department"]["value"]
        rows.append({"code": code, "title": record["title"]["value"], "kind": kind, "owner": owner,
                     "has": has, "has_text": any(has.values()),
                     "syllabus": None if any(has.values()) else syllabus_for(owner)})
    return rows
