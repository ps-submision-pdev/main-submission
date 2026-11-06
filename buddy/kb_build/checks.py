"""KB checks (code only). Failing records go to reports/, never into the slice; nothing is trimmed.

check_size(count, settings) -> [warning]   the brief asks for 8-15 real courses (kb_min_courses,
    kb_max_courses in config/kb_build.yaml); outside that range, a warning naming the count.
check_course_exists(kb, db) -> [problem]       every code the slice refers to exists in the database
check_slot_membership(kb, available) -> [problem]  slot options and core match the available set
Cycles are prevented when prerequisites are added (prereqs.py). Still to add from CLAUDE.md: credits =
L + T + P/2, quotes appear in the page text, required fields.
"""
from __future__ import annotations


def check_size(count: int, settings: dict) -> list[str]:
    low, high = settings["kb_min_courses"], settings["kb_max_courses"]
    if count < low:
        return [f"KB size: {count} full course records, under the minimum of {low}"]
    if count > high:
        return [f"KB size: {count} full course records, over the maximum of {high}"]
    return []


def referenced_codes(kb: dict) -> list[tuple[str, str]]:
    """Every (code, where) the slice refers to: core, slot options, records, prerequisites, foundations."""
    out = [(c, "core") for codes in list(kb["core"].values()) + list(kb["later_core"].values()) for c in codes]
    out += [(c, f"slot {s['slot']}") for s in kb["slots"] for c in s["options"]]
    out += [(c, "courses") for c in kb["courses"]]
    out += [(e["code"], f"prerequisite of {c}") for c, r in kb["courses"].items() for e in r["prerequisites"]]
    out += [(f["code"], "foundations") for f in kb["foundations"]]
    return out


def check_course_exists(kb: dict, db: dict) -> list[str]:
    """Every code the slice refers to must be a course in the database."""
    return [f"{code} ({where}) is not in the database" for code, where in referenced_codes(kb) if code not in db]


def check_slot_membership(kb: dict, available: dict) -> list[str]:
    """Every slot option must be an available option of that slot in that semester; core must be core there."""
    offered = {(s["slot"], s["semester"]): set(s["options"]) for s in available["slots"]}
    core = {int(sem): set(codes) for sem, codes in available["core"].items()}
    out = [f"{c} is not an option of {s['slot']} (semester {s['semester']})"
           for s in kb["slots"] for c in s["options"] if c not in offered.get((s["slot"], s["semester"]), set())]
    out += [f"{c} is not core in semester {sem}" for sem, codes in list(kb["core"].items()) + list(kb["later_core"].items())
            for c in codes if c not in core.get(int(sem), set())]
    return out
