"""Tests for buddy/kb_build/eligibility.py."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from buddy.kb_build.eligibility import filter_available  # noqa: E402

AVAILABLE = {
    "department": "Chemical and Biochemical Engineering", "window": [5, 8],
    "slots": [
        {"slot": "IDE-II", "slot_type": "IDE", "number": "II", "semester": 5,
         "options": ["CS3106", "MA3107"], "unknown": ["CH3104"],
         "eligibility": {"CS3106": "IDE from CSE (Available to student other than Dept. of CSE)",
                         "MA3107": "IDE - II (Available to students other than Dept. of M&C)"},
         "dropped": [{"code": "MA3152", "reason": "alias of MA3107 (higher-priority source)"},
                     {"code": "CB3106", "reason": "eligibility note excludes this student: not applicable"},
                     {"code": "CE3190", "reason": "out of scope (title)"}]},
        {"slot": "DE-I", "slot_type": "DE", "number": "I", "semester": 6, "options": ["CB3206", "CB3207"],
         "unknown": [], "eligibility": {"CB3206": "own department DE list", "CB3207": "own department DE list"},
         "dropped": []},
    ],
    "core": {5: ["CB3101", "CB3105"]},
    "core_before_window": {3: ["CB2101", "CB2103"], 4: ["CB2201"]},
    "unplaced": [], "minors": [], "problems": [],
}
PERSONA = {"already_done": ["CB2101", "CB2201", "CB3207", "CB3105"]}


def removed_by(result):
    return {(r["code"], r["category"]) for r in result["removed"]}


def test_already_done_is_removed_from_options_and_core():
    out = filter_available(PERSONA, AVAILABLE, db={})
    slots = {s["slot"]: s for s in out["available"]["slots"]}
    assert slots["DE-I"]["options"] == ["CB3206"]
    assert out["available"]["core"] == {5: ["CB3101"]}
    assert {("CB3207", "already done"), ("CB3105", "already done")} <= removed_by(out)


def test_every_reason_from_available_is_carried_with_a_category():
    got = removed_by(filter_available(PERSONA, AVAILABLE, db={}))
    assert {("MA3152", "alias"), ("CB3106", "ineligible"), ("CE3190", "out of scope"),
            ("CH3104", "eligibility unknown")} <= got


def test_core_before_the_window_that_is_not_done_is_reported():
    got = removed_by(filter_available(PERSONA, AVAILABLE, db={}))
    assert ("CB2103", "core outside window") in got          # semester 3 core, not in already_done
    assert ("CB2101", "core outside window") not in got      # done: nothing to report


def test_input_is_not_changed_and_output_is_stable():
    before = copy.deepcopy(AVAILABLE)
    first = filter_available(PERSONA, AVAILABLE, db={})
    assert AVAILABLE == before
    assert first == filter_available(PERSONA, AVAILABLE, db={})
    assert [r["code"] for r in first["removed"]] == sorted(r["code"] for r in first["removed"])


def test_real_demo_persona():
    from buddy.kb_build.available import available_for
    from buddy.kb_build.persona import load_persona
    db = json.loads((ROOT / "data/db/resolved.json").read_text(encoding="utf-8"))
    entries = json.loads((ROOT / "data/db/list_entries.json").read_text(encoding="utf-8"))
    persona = load_persona(ROOT / "personas/chem_ml_demo.json", db=db)
    out = filter_available(persona, available_for(persona, entries, db), db)
    offered = {c for s in out["available"]["slots"] for c in s["options"]}
    assert not offered & set(persona["already_done"])
    assert all(s["eligibility"].get(c) for s in out["available"]["slots"] for c in s["options"])


def test_ineligible_course_from_a_list_without_slot_numbers_is_recorded():
    available = {**AVAILABLE, "excluded_unplaced": [
        {"code": "CB3106", "reason": "eligibility note excludes this student: IDE floated by the Department "
                                     "(not applicable for B. Tech. Chemical Engineering students)"}]}
    got = [r for r in filter_available(PERSONA, available, db={})["removed"] if r["slot"] == "IDE (no slot number)"]
    assert [(r["code"], r["category"]) for r in got] == [("CB3106", "ineligible")]
