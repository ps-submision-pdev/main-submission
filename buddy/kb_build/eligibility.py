"""Eligibility filter (code only): what is left of the available set once the student's own record is
applied, and one list of everything code removed before the model sees anything.

filter_available(persona, available, db) -> {"available": copy without already_done, "removed": [...]}
    available  the output of available.available_for(); it is not changed (a copy is returned)
    removed    [{code, slot, category, reason}], sorted by code, for Section C of the review report:
        already done         the code is in persona["already_done"] (removed from options and core)
        ineligible           an eligibility note excludes the student          (decided in available.py)
        alias                a lower-priority duplicate code (Senate)          (decided in available.py)
        out of scope         key-field conflict, or not in a B. Tech. list     (decided in available.py)
        eligibility unknown  no note says the student may take it: never assumed open
        core outside window  core of a semester before planning_semester that is not in already_done
db is accepted for symmetry with the other steps and not used yet.
"""
from __future__ import annotations

import copy

CATEGORIES = (("alias of", "alias"), ("eligibility note excludes", "ineligible"), ("out of scope", "out of scope"))


def category_of(reason: str) -> str:
    for start, category in CATEGORIES:
        if reason.startswith(start):
            return category
    return "other"


def filter_available(persona: dict, available: dict, db: dict) -> dict:
    done = set(persona["already_done"])
    out = copy.deepcopy(available)
    removed = []
    for slot in out["slots"]:
        for code in [c for c in slot["options"] if c in done]:
            slot["options"].remove(code)
            slot["eligibility"].pop(code, None)
            removed.append({"code": code, "slot": slot["slot"], "category": "already done",
                            "reason": "in the persona's already_done list"})
        for d in slot["dropped"]:
            removed.append({"code": d["code"], "slot": slot["slot"], "category": category_of(d["reason"]),
                            "reason": d["reason"]})
        for code in slot["unknown"]:
            removed.append({"code": code, "slot": slot["slot"], "category": "eligibility unknown",
                            "reason": "no eligibility note says this student may take it"})
    for d in available.get("excluded_unplaced", []):
        removed.append({"code": d["code"], "slot": "IDE (no slot number)", "category": "ineligible",
                        "reason": d["reason"]})
    for sem, codes in out["core"].items():
        for code in [c for c in codes if c in done]:
            codes.remove(code)
            removed.append({"code": code, "slot": f"core S{sem}", "category": "already done",
                            "reason": "in the persona's already_done list"})
    for sem, codes in available.get("core_before_window", {}).items():
        for code in codes:
            if code not in done:
                removed.append({"code": code, "slot": f"core S{sem}", "category": "core outside window",
                                "reason": f"core of semester {sem}, before the planning window, not in already_done"})
    removed.sort(key=lambda r: (r["code"], r["slot"], r["category"]))
    return {"available": out, "removed": removed}
