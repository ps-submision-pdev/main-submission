"""Tests for buddy/kb_build/horizon.py and the size check in buddy/kb_build/checks.py."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from buddy.kb_build.checks import check_size  # noqa: E402
from buddy.kb_build.horizon import full_record_count, split_horizon, text_report  # noqa: E402

SETTINGS = {"kb_horizon_semesters": 2, "options_per_slot": 2, "kb_min_courses": 8, "kb_max_courses": 15}
AVAILABLE = {
    "slots": [
        {"slot": "IDE-II", "slot_type": "IDE", "number": "II", "semester": 5, "options": ["CE3105", "MA3107", "CS3106"],
         "unknown": [], "eligibility": {}, "dropped": []},
        {"slot": "DE-I", "slot_type": "DE", "number": "I", "semester": 6, "options": ["CB3206"],
         "unknown": [], "eligibility": {}, "dropped": []},
        {"slot": "DE-II", "slot_type": "DE", "number": "II", "semester": 7, "options": ["CB4102", "CB4103"],
         "unknown": [], "eligibility": {}, "dropped": []},
    ],
    "core": {5: ["CB3101", "CB3105"], 6: ["CB3204"], 7: ["CB4199"], 8: ["CB4299"]},
}
PERSONA = {"planning_semester": 5, "programme_id": "cbe_btech"}


def text(description=None, objectives=None, outcomes=None, owner="Chemical and Biochemical Engineering"):
    return {"description": {"value": description}, "objectives": {"value": objectives},
            "outcomes": {"value": outcomes}, "owner_department": {"value": owner}, "title": {"value": "t"}}


DB = {"CB3101": text(description="d"), "CB3105": text(objectives="o"), "CB3204": text(outcomes="x"),
      "CE3105": text(owner="Civil and Environmental Engineering"), "MA3107": text(description="d", owner="Mathematics"),
      "CS3106": text(description="d", owner="Computer Science & Engineering"), "CB3206": text()}


def test_horizon_keeps_two_semesters_and_lists_later_ones_as_codes():
    h = split_horizon(AVAILABLE, PERSONA, SETTINGS)
    assert h["semesters"] == [5, 6]
    assert [s["slot"] for s in h["inside"]["slots"]] == ["IDE-II", "DE-I"]
    assert h["inside"]["core"] == {5: ["CB3101", "CB3105"], 6: ["CB3204"]}
    assert h["later_slots"] == [{"slot": "DE-II", "semester": 7, "options": ["CB4102", "CB4103"]}]
    assert h["later_core"] == {7: ["CB4199"], 8: ["CB4299"]}


def test_full_record_count_is_core_plus_options_per_slot():
    h = split_horizon(AVAILABLE, PERSONA, SETTINGS)
    assert full_record_count(h["inside"], SETTINGS) == 3 + 2 + 1     # 3 core, IDE-II keeps 2, DE-I has only 1


def test_size_check_warns_with_the_count_and_never_trims():
    assert check_size(7, SETTINGS) == ["KB size: 7 full course records, under the minimum of 8"]
    assert check_size(16, SETTINGS) == ["KB size: 16 full course records, over the maximum of 15"]
    assert check_size(8, SETTINGS) == [] and check_size(15, SETTINGS) == []


def test_text_report_lists_what_each_course_has_and_where_missing_text_would_come_from():
    rows = {r["code"]: r for r in text_report(split_horizon(AVAILABLE, PERSONA, SETTINGS)["inside"], DB)}
    assert rows["CB3101"]["has"] == {"description": True, "objectives": False, "outcomes": False}
    assert rows["CB3101"]["kind"] == "core S5" and rows["CE3105"]["kind"] == "option IDE-II"
    assert rows["CE3105"]["has_text"] is False
    assert rows["CE3105"]["syllabus"] == "not in ingest/sources.yaml (Civil and Environmental Engineering)"
    assert rows["CB3206"]["syllabus"] == "cbe_btech (downloaded; no course page found there)"
    assert rows["MA3107"]["syllabus"] is None                       # has text: nothing to fetch
