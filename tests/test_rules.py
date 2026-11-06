"""Tests for buddy/rules.py, the rule checker. Rules come from the real data/kb/rules.json."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from buddy import rules  # noqa: E402

RULES = json.loads((ROOT / "data/kb/rules.json").read_text(encoding="utf-8"))["rules"]

# A small slice of the Chemical programme (cbe_btech pp1-2). year = year of study the course belongs to.
CATALOG = {
    "MA1101": {"l": 3, "t": 1, "p": 0, "year": 1}, "MA1201": {"l": 3, "t": 1, "p": 0, "year": 1},
    "CB2201": {"l": 2, "t": 0, "p": 3, "year": 2},
    "CB3101": {"l": 3, "t": 0, "p": 3, "year": 3}, "CB3102": {"l": 3, "t": 0, "p": 0, "year": 3},
    "CB3103": {"l": 1, "t": 2, "p": 0, "year": 3}, "CB3104": {"l": 3, "t": 0, "p": 2, "year": 3},
    "CB3105": {"l": 2, "t": 0, "p": 3, "year": 3}, "MA3107": {"l": 3, "t": 0, "p": 0, "year": 3},
    "CS4113": {"l": 3, "t": 0, "p": 0, "year": 4},
    "CS3106": {"l": 3, "t": 0, "p": 0, "year": 3}, "CE3105": {"l": 3, "t": 0, "p": 0, "year": 3},
    "CS3208": {"l": 3, "t": 0, "p": 0, "year": 3}, "CB3206": {"l": 3, "t": 0, "p": 0, "year": 3},
}
# core and slots as available_for() builds them (a small part of the real Chemical window)
PROGRAMME = {"courses_by_year": {1: ["MA1101", "MA1201"]}, "courses_per_semester": {5: 6},
             "core": {5: ["CB3101", "CB3102", "CB3103", "CB3104", "CB3105"]},
             "slots": [{"slot": "IDE-II", "semester": 5, "options": ["CE3105", "CS3106", "MA3107"]},
                       {"slot": "DE-I", "semester": 6, "options": ["CB3206"]},
                       {"slot": "IDE-III", "semester": 7, "options": ["CS4113"]}]}
SEM5 = ["CB3101", "CB3102", "CB3103", "CB3104", "CB3105", "MA3107"]  # semester V: 5 core + IDE-II


def profile(passed=("MA1101", "MA1201"), cpi=8.2):
    return {"passed": list(passed), "cpi": cpi, "cpi_history": [cpi]}


def violations(plan, prof, catalog=CATALOG, programme=PROGRAMME):
    return [v for v in rules.check_plan(plan, prof, programme, catalog, RULES) if v["severity"] == "violation"]


def test_year_three_course_with_a_failed_first_year_course_is_rejected():
    found = violations({5: SEM5}, profile(passed=["MA1101"]))   # MA1201 not passed
    assert [v["rule_id"] for v in found] == ["ord-8.4a-first-year-before-third-year"]
    assert "MA1201" in found[0]["message"]


def test_first_year_passed_means_no_violation():
    assert violations({5: SEM5}, profile()) == []


def test_cpi_8_2_in_semester_5_may_add_one_extra_course():
    found = rules.check_plan({5: SEM5 + ["CS3106"]}, profile(cpi=8.2), PROGRAMME, CATALOG, RULES)
    assert [v for v in found if v["severity"] == "violation"] == []
    assert any(v["rule_id"] == "ord-8.4c-overload" and v["severity"] == "warning" for v in found)  # needs approval


def test_cpi_7_9_in_semester_5_may_not_add_an_extra_course():
    found = violations({5: SEM5 + ["CS3106"]}, profile(cpi=7.9))
    assert [v["rule_id"] for v in found] == ["ord-8.4c-overload"]


def test_two_extra_courses_are_rejected_even_with_high_cpi():
    found = violations({5: SEM5 + ["CS3106", "CE3105"]}, profile(cpi=9.5))
    assert [v["rule_id"] for v in found] == ["ord-8.4c-overload"]


def test_contact_hours_33_rejected_32_accepted():
    def catalog_with(hours):  # one course carrying all the hours
        return {**CATALOG, "XX3000": {"l": hours, "t": 0, "p": 0, "year": 3}}
    plan = {5: ["XX3000"]}
    programme = {**PROGRAMME, "core": {5: ["XX3000"]}}
    assert [v["rule_id"] for v in violations(plan, profile(), catalog_with(33), programme)] == ["ord-8.4b-contact-hours"]
    assert violations(plan, profile(), catalog_with(32), programme) == []


def test_low_cpi_warns_and_two_semesters_warn_about_continuation():
    prof = {"passed": ["MA1101", "MA1201"], "cpi": 4.8, "cpi_history": [5.2, 4.8]}
    found = [v for v in rules.check_plan({}, prof, PROGRAMME, CATALOG, RULES) if v["rule_id"] == "ord-12.1a-low-cpi"]
    assert len(found) == 1 and "warning" in found[0]["message"]
    prof["cpi_history"] = [4.9, 4.8]
    found = [v for v in rules.check_plan({}, prof, PROGRAMME, CATALOG, RULES) if v["rule_id"] == "ord-12.1a-low-cpi"]
    assert "2 consecutive" in found[0]["message"]


def test_unknown_course_code_is_a_violation_not_a_crash():
    found = violations({5: ["ZZ9999"]}, profile())
    assert [v["rule_id"] for v in found] == ["kb-course-exists"]


def test_cse_course_in_a_de_slot_is_a_slot_membership_violation():
    found = violations({6: ["CS3208"]}, profile())      # CSE's own DE: not in Chemical's DE-I list
    assert [v["rule_id"] for v in found] == ["kb-slot-membership"]
    assert "CS3208" in found[0]["message"]


def test_course_from_another_semesters_slot_is_a_violation():
    found = violations({7: ["MA3107"]}, profile())      # MA3107 is an IDE-II option (semester 5), not IDE-III
    assert [v["rule_id"] for v in found] == ["kb-slot-membership"]
    assert "IDE-II (semester 5)" in found[0]["message"]


def test_core_and_slot_options_in_their_own_semester_pass_membership():
    assert violations({5: SEM5, 6: ["CB3206"], 7: ["CS4113"]}, profile()) == []


def test_core_keys_may_be_strings_after_a_json_round_trip():
    programme = json.loads(json.dumps(PROGRAMME))       # {"5": [...]} instead of {5: [...]}
    assert violations({5: SEM5}, profile(), programme=programme) == []
