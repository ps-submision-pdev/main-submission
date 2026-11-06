"""Tests for buddy/kb_build/available.py: small fake data for each rule, then the real database."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from buddy.kb_build import available as A  # noqa: E402

CHEM = "Chemical and Biochemical Engineering"
PERSONA = {"programme_id": "cbe_btech", "planning_semester": 5}


def fact(value):
    return {"value": value, "source_id": "s", "page": 1, "span": value}


def entry(code, slot_type, number, owner, note=None, semester=None, placeholder=False, source="curriculum_nep2020"):
    return {"source_id": source, "page": 1, "span": "x", "code": None if placeholder else code,
            "slot_code": code if placeholder else None, "title": "t", "ltpc": None, "semester": semester,
            "heading": "h", "slot_type": slot_type, "slot_number": number, "is_placeholder": placeholder,
            "owner_department": fact(owner) if owner else None, "level": "B. Tech.",
            "eligibility_note": fact(note) if note else None, "in_scope": True}


def record(code, source="curriculum_nep2020", in_scope=True, alias=None):
    r = {"id": code, "in_scope": in_scope, "title": {"value": code, "chosen": {"source_id": source}}}
    if alias:
        r["possible_alias_of"] = alias
    return r


ENTRIES = [
    # the persona's own semester table: slots and core
    entry("XX31PQ", "IDE", "II", CHEM, semester=5, placeholder=True),
    entry("CB32XX", "DE", "I", CHEM, semester=6, placeholder=True),
    entry("XX41PQ", "IDE", "III", CHEM, semester=7, placeholder=True),
    entry("XX22PQ", "IDE", "I", CHEM, semester=4, placeholder=True),          # before the window
    entry("CB3101", "core", None, CHEM, semester=5),
    entry("CB2201", "core", None, CHEM, semester=4),                          # before the window
    # lists
    entry("CB3206", "DE", "I", CHEM),
    entry("CB3211", "DE", "I", CHEM, source="btech_program_nep2020"),         # Senate code for CB3206
    entry("CS3208", "DE", "I", "Computer Science & Engineering"),             # CSE's own DE: never for Chemical
    entry("MA3107", "IDE", "II", "Mathematics", note="IDE - II (Available to students other than Dept. of M&C)"),
    entry("CS4113", "IDE", "III", "Computer Science & Engineering",
          note="IDE from CSE (Available to student other than Dept. of CSE)"),
    entry("CB3106", "IDE", "II", CHEM,
          note="IDE floated by the Department (not applicable for B. Tech. Chemical Engineering students)"),
    entry("CH3104", "IDE", "II", "Chemistry"),                                # no note: unknown
    entry("ME3106", "IDE", None, "Mechanical Engineering",
          note="Interdisciplinary Elective (IDE) Courses for B. Tech. (Available to students other than Dept. of ME)"),
    entry("CS3103", "minor", None, "Computer Science & Engineering"),
]
for e in ENTRIES:
    if e["code"] == "CS3103":
        e["heading"] = "Minor in AI&DS (List of Courses)"
DB = {c: record(c) for c in ["CB3101", "CB2201", "CB3206", "CS3208", "MA3107", "CS4113", "CB3106", "CH3104",
                             "ME3106", "CS3103"]}
DB["CB3206"] = record("CB3206", alias=["CB3211"])
DB["CB3211"] = record("CB3211", source="btech_program_nep2020", alias=["CB3206"])


def slots_by_name(result):
    return {s["slot"]: s for s in result["slots"]}


def test_window_slots_and_core():
    result = A.available_for(PERSONA, ENTRIES, DB)
    assert [(s["slot"], s["semester"]) for s in result["slots"]] == [("IDE-II", 5), ("DE-I", 6), ("IDE-III", 7)]
    assert result["core"] == {5: ["CB3101"]}                                   # CB2201 is semester 4


def test_each_rule_on_fake_data():
    s = slots_by_name(A.available_for(PERSONA, ENTRIES, DB))
    assert s["DE-I"]["options"] == ["CB3206"]                                  # own DE; CSE DE never; alias dropped
    assert {"code": "CB3211", "reason": "alias of CB3206 (higher-priority source)"} in s["DE-I"]["dropped"]
    assert s["IDE-II"]["options"] == ["MA3107"]
    assert s["IDE-II"]["unknown"] == ["CH3104"]                                # no note: never assume yes
    assert {"code": "CB3106", "reason": "eligibility note excludes this student: IDE floated by the Department "
            "(not applicable for B. Tech. Chemical Engineering students)"} in s["IDE-II"]["dropped"]
    assert s["IDE-III"]["options"] == ["CS4113"]


def test_unnumbered_ide_and_minors_are_kept_apart():
    result = A.available_for(PERSONA, ENTRIES, DB)
    assert [u["code"] for u in result["unplaced"]] == ["ME3106"]
    assert result["minors"] == [{"name": "Minor in AI&DS (List of Courses)", "owner": "Computer Science & Engineering",
                                 "courses": ["CS3103"], "eligibility": "unknown"}]


def test_note_verdicts():
    chem = {"department": CHEM, "programme": "B.Tech. Chemical Engineering"}
    assert A.note_verdict("IDE (Available to students other than Dept. of CSE)", "Computer Science & Engineering", chem) == "allowed"
    assert A.note_verdict("IDE (Available to students other than Dept. of X)", "Chemical and Biochemical Engineering", chem) == "excluded"
    assert A.note_verdict("IDE floated by the Department (not applicable for B. Tech. Chemical Engineering students)", CHEM, chem) == "excluded"
    assert A.note_verdict("(List of HSS Electives for all approved B. Tech. / BS Program of the Institute:)", "Humanities", chem) == "allowed"
    assert A.note_verdict(None, "Chemistry", chem) == "unknown"
    assert A.note_verdict("IDE - I (Available to students other than Dept. of M&C)", None, chem) == "unknown"  # owner unknown


# ---- the real database ----

REAL_ENTRIES = json.loads((ROOT / "data/db/list_entries.json").read_text(encoding="utf-8"))
REAL_DB = json.loads((ROOT / "data/db/resolved.json").read_text(encoding="utf-8"))
REAL = A.available_for(PERSONA, REAL_ENTRIES, REAL_DB)


def test_real_cse_only_course_never_appears_for_a_chemical_persona():
    offered = {c for s in REAL["slots"] for c in s["options"] + s["unknown"]} | {u["code"] for u in REAL["unplaced"]}
    # CS3208 (CSE DE only), CS3103 (AI&DS Minor and CSE core only), CS4106 (CSE DE only)
    assert not {"CS3208", "CS3103", "CS4106"} & offered


def test_real_slot_lists_hold_only_that_slots_courses():
    for slot in REAL["slots"]:
        for code in slot["options"]:
            assert any(e["code"] == code and e["slot_type"] == slot["slot_type"] and e["slot_number"] == slot["number"]
                       for e in REAL_ENTRIES), (slot["slot"], code)


def test_real_window_is_semester_5_to_8():
    assert [(s["slot"], s["semester"]) for s in REAL["slots"]] == [
        ("IDE-II", 5), ("DE-I", 6), ("DE-II", 7), ("DE-III", 7), ("HSS-II", 7), ("IDE-III", 7),
        ("DE-IV", 8), ("DE-V", 8), ("DE-VI", 8)]


def test_unknown_senate_duplicate_of_an_allowed_option_is_dropped():
    entries = ENTRIES + [entry("MA3152", "IDE", "II", "Mathematics", source="btech_program_nep2020")]  # no note
    db = {**DB, "MA3107": record("MA3107", alias=["MA3152"]),
          "MA3152": record("MA3152", source="btech_program_nep2020", alias=["MA3107"])}
    s = slots_by_name(A.available_for(PERSONA, entries, db))["IDE-II"]
    assert "MA3152" not in s["unknown"] and s["options"] == ["MA3107"]
    assert {"code": "MA3152", "reason": "alias of MA3107 (higher-priority source)"} in s["dropped"]


def test_the_same_minor_printed_twice_counts_once():
    twice = [dict(e, heading=h, owner_department=fact(o)) for e in ENTRIES if e["code"] == "CS3103"
             for h, o in [("Minor in AI&DS (List of Courses)", "Computer Science & Engineering"),
                          ("Minor in AI and DS", "Computer Science and Engineering")]]
    result = A.available_for(PERSONA, ENTRIES + twice, DB)
    assert [m["courses"] for m in result["minors"]] == [["CS3103"]]
