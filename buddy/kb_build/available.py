"""Available set (code only): what a persona may actually take, slot by slot, in the planning window.

available_for(persona, list_entries, db) -> {
    department, window: [first, last],
    slots:    [{slot, slot_type, number, semester, options:[codes], unknown:[codes],
                eligibility: {code: why it is allowed}, dropped:[{code, reason}]}],
    core:     {semester: [codes]}               fixed courses of the persona's own semester tables
    core_before_window: {semester: [codes]}     the same, for semesters before planning_semester
    unplaced: [{code, slot_type, owner, reason}] allowed, but the list prints no slot number
    excluded_unplaced: [{code, reason}]          a list with no slot number whose note excludes the student
    minors:   [{name, owner, courses, eligibility: "unknown"}]
    problems: [text]                             e.g. a slot the documents place in two semesters
}
    list_entries  data/db/list_entries.json     db  data/db/resolved.json

Slots are the persona's own B. Tech. semester-table placeholders (e.g. "CB32XX DE-I" in semester 6),
from planning_semester to 8. Options of a slot, all in scope:
    DE-n   the persona's own department's DE-n list (another department's DE list is never offered)
    HSS-n  an HSS-n list whose note opens it to B. Tech. students
    IDE-n  another department's IDE-n list whose note allows this student
note_verdict() reads an eligibility note as allowed | excluded | unknown. One "excluded" row excludes a
course; otherwise one "allowed" row is enough; no note means unknown, and unknown is never a yes.
Within a slot, a Senate duplicate (possible_alias_of) from a lower-priority source is dropped.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from buddy.kb_build.persona import programme_of

ROOT = Path(__file__).resolve().parents[2]
PRIORITY_FILE = ROOT / "ingest/source_priority.yaml"
SLOT_TYPES = ("DE", "IDE", "HSS")
CORE_TYPES = ("core", "lab", "project")
LAST_SEMESTER = 8


def same_department(a: str | None, b: str | None) -> bool:
    """"Computer Science & Engineering" and "Computer Science and Engineering" are the same department."""
    def norm(s):
        return " ".join(s.lower().replace("&", "and").split())
    return bool(a and b) and norm(a) == norm(b)


def note_verdict(note: str | None, owner: str | None, programme: dict) -> str:
    """allowed | excluded | unknown for one list's eligibility note. programme is the sources.yaml entry."""
    if not note:
        return "unknown"
    text = note.lower()
    if "not applicable" in text:  # "not applicable for B. Tech. Chemical Engineering students"
        name = re.sub(r"^b\.?\s*tech\.?\s*", "", programme["programme"].lower()).strip()
        return "excluded" if name and name in text else "unknown"
    if "other than" in text:      # "other than Dept. of X": X is the department that owns the list
        if owner is None:
            return "unknown"
        return "excluded" if same_department(owner, programme["department"]) else "allowed"
    if re.search(r"(?:for all approved|open to) b\.?\s*tech", text):
        return "allowed"
    return "unknown"


def owner_of(entry: dict) -> str | None:
    return entry["owner_department"]["value"] if entry["owner_department"] else None


def window_slots(own: list, start: int, problems: list) -> dict:
    """label -> slot, from the persona's own semester-table placeholders in the window."""
    semesters: dict = {}
    for e in own:
        if e["is_placeholder"] and e["slot_type"] in SLOT_TYPES and e["slot_number"] and e["semester"]:
            semesters.setdefault((e["slot_type"], e["slot_number"]), set()).add(e["semester"])
    slots = {}
    for (kind, number), sems in semesters.items():
        label = f"{kind}-{number}"
        if len(sems) > 1:
            problems.append(f"{label} is placed in semesters {sorted(sems)} by different documents; left out")
        elif min(sems) >= start:
            slots[label] = {"slot": label, "slot_type": kind, "number": number, "semester": min(sems)}
    return slots


def merge_minors(minors: dict, db: dict) -> list[dict]:
    """One entry per Minor: the same owner and the same in-scope courses printed in two documents
    (e.g. "Minor in CSE (List of Courses)" and "Minor in Computer Science & Engineering") count once."""
    out, seen = [], set()
    for (name, owner), codes in sorted(minors.items()):
        courses = sorted(c for c in codes if db[c]["in_scope"])
        key = (" ".join(owner.lower().replace("&", "and").split()), tuple(courses))
        if key not in seen:
            seen.add(key)
            out.append({"name": name, "owner": owner, "courses": courses, "eligibility": "unknown"})
    return out


def available_for(persona: dict, list_entries: list, db: dict) -> dict:
    programme = programme_of(persona)
    dept, start = programme["department"], persona["planning_semester"]
    priority = yaml.safe_load(PRIORITY_FILE.read_text(encoding="utf-8"))["priority"]
    own = [e for e in list_entries if e["level"] == "B. Tech." and same_department(owner_of(e), dept)]
    problems: list = []
    slots = window_slots(own, start, problems)

    core: dict = {}
    core_before: dict = {}
    for e in own:
        if e["code"] and e["slot_type"] in CORE_TYPES and e["semester"]:
            (core if e["semester"] >= start else core_before).setdefault(e["semester"], set()).add(e["code"])

    verdicts: dict = {label: {} for label in slots}   # label -> code -> (verdict, reason)
    unplaced: dict = {}
    excluded_unplaced: dict = {}
    minors: dict = {}
    for e in list_entries:
        if not e["code"] or e["is_placeholder"] or not e["in_scope"]:
            continue
        owner, note = owner_of(e), e["eligibility_note"]["value"] if e["eligibility_note"] else None
        if e["slot_type"] == "minor":
            if e["heading"] and "Minor" in e["heading"] and owner and not same_department(owner, dept):
                minors.setdefault((e["heading"], owner), set()).add(e["code"])
            continue
        if e["slot_type"] not in SLOT_TYPES:
            continue
        if e["slot_type"] == "DE":
            if not same_department(owner, dept):
                continue                                  # another department's own electives
            verdict, reason, why = "allowed", None, "own department DE list"
        else:
            verdict = note_verdict(note, owner, programme)
            reason = f"eligibility note excludes this student: {note}" if verdict == "excluded" else None
            why = note
        if not e["slot_number"]:
            if verdict == "allowed" and not same_department(owner, dept):
                unplaced[e["code"]] = {"code": e["code"], "slot_type": e["slot_type"], "owner": owner,
                                       "reason": "the list prints no slot number (I, II, III)"}
            elif verdict == "excluded":
                excluded_unplaced[e["code"]] = {"code": e["code"], "reason": reason}
            continue
        label = f"{e['slot_type']}-{e['slot_number']}"
        if label not in verdicts:
            continue
        old = verdicts[label].get(e["code"], ("unknown", None, None))
        if old[0] != "excluded" and (verdict == "excluded" or old[0] == "unknown"):
            verdicts[label][e["code"]] = (verdict, reason, why)  # excluded beats allowed beats unknown

    out_slots = []
    for label, slot in sorted(slots.items(), key=lambda kv: (kv[1]["semester"], kv[0])):
        allowed, unknown, dropped = set(), set(), []
        for code, (verdict, reason, _why) in sorted(verdicts[label].items()):
            record = db[code]
            if not record["in_scope"]:
                why = ", ".join(record.get("excluded_for_conflict") or []) or "not in a B. Tech. list"
                dropped.append({"code": code, "reason": f"out of scope ({why})"})
            elif verdict == "excluded":
                dropped.append({"code": code, "reason": reason})
            elif verdict == "allowed":
                allowed.add(code)
            else:
                unknown.add(code)
        offered = allowed | unknown
        for code in sorted(offered):                     # Senate duplicates: keep the higher-priority source
            rank = priority.index(db[code]["title"]["chosen"]["source_id"])
            better = [a for a in db[code].get("possible_alias_of", [])
                      if a in offered and priority.index(db[a]["title"]["chosen"]["source_id"]) < rank]
            if better:
                allowed.discard(code)
                unknown.discard(code)
                dropped.append({"code": code, "reason": f"alias of {better[0]} (higher-priority source)"})
        out_slots.append({**slot, "options": sorted(allowed), "unknown": sorted(unknown),
                          "eligibility": {c: verdicts[label][c][2] for c in sorted(allowed)},
                          "dropped": sorted(dropped, key=lambda d: d["code"])})

    return {
        "department": dept, "window": [start, LAST_SEMESTER], "slots": out_slots,
        "core": {sem: sorted(codes) for sem, codes in sorted(core.items())},
        "core_before_window": {sem: sorted(codes) for sem, codes in sorted(core_before.items())},
        "unplaced": [unplaced[c] for c in sorted(unplaced) if db[c]["in_scope"]],
        "excluded_unplaced": [excluded_unplaced[c] for c in sorted(excluded_unplaced)],
        "minors": merge_minors(minors, db),
        "problems": problems,
    }
