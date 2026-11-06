"""Tests for ingest/slots.py. Every input line is copied from the real extracted documents."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
import slots  # noqa: E402

SOURCE = {"id": "test_source", "url": "https://example.invalid/test.pdf"}


def walk(text_lines):
    entries = []
    slots.walk([(1, line) for line in text_lines], SOURCE, entries)
    slots.keep_known_codes(entries)
    return entries


def test_slot_label_with_real_looking_code_is_a_placeholder():
    entries = walk([
        "(1.) B. Tech. Programme from the Department of Chemical and Biochemical Engineering",
        "SEMESTER VIII L T P C",
        "3. CB4298 DE-VI 3 0 0 3",
        "4. CB4299 Project – II 0 0 16 8",
    ])
    de6, project = entries
    assert (de6["code"], de6["slot_code"], de6["is_placeholder"], de6["in_scope"]) == (None, "CB4298", True, False)
    assert (de6["slot_type"], de6["slot_number"], de6["semester"]) == ("DE", "VI", 8)
    assert (project["code"], project["slot_type"]) == ("CB4299", "project")
    assert de6["owner_department"]["value"] == "Chemical and Biochemical Engineering"


def test_minor_row_with_a_known_code_stays_a_course():
    entries = walk([
        "SEMESTER III L T P C",
        "4. EC2102 Signals and Systems 3 1 0 4",
        "1. EC2102 Minor I 3 1 0 4",
    ])
    assert [e["code"] for e in entries] == ["EC2102", "EC2102"]
    assert entries[1]["is_placeholder"] is False and entries[1]["slot_type"] == "minor"


def test_ide_list_ignores_the_owners_semester_and_eligibility_is_verbatim():
    entries = walk([
        "IDE from AI&DS (Available to students other than Dept. of CSE)",
        "IDE-I Semester-4 CS2207 Introduction to Data Science 3 0 0 3",
    ])
    e = entries[0]
    assert (e["code"], e["slot_type"], e["slot_number"], e["semester"]) == ("CS2207", "IDE", "I", None)
    assert e["eligibility_note"]["value"] == "IDE from AI&DS (Available to students other than Dept. of CSE)"
    assert e["owner_department"] is None   # no "Programme from the Department of" line: not guessed


def test_ide_semester_comes_from_the_students_programme_table():
    entries = walk([
        "B. Tech. Programme from the Department of Chemical and Biochemical Engineering",
        "Sl. No. | Subject Code | SEMESTER V | L | T | P | C",
        "6. | XX31PQ | IDE-II | 3 | 0 | 0 | 3",
    ])
    assert slots.slot_semester(entries, "Chemical and Biochemical", "IDE", "II") == 5
    assert slots.slot_semester(entries, "Chemical and Biochemical", "IDE", "III") is None


def test_code_after_title_rows_get_owner_slot_and_semester():
    entries = walk([
        "(1.) B. Tech. Programme from the Department of Chemical and Biochemical Engineering",
        "SEMESTER VI L T P C",
        "6. CB32XX DE-I 3 0 0 3",
        "List of Departmental Electives (DE)",
        "DE-I 1. Catalysis Science and Engineering (CB3211)",
        "2. Biopharmaceutical Downstream Processing (CB3212)",
    ])
    slots.place_department_electives(entries)
    first, second = entries[1], entries[2]
    assert (first["code"], first["slot_type"], first["slot_number"], first["semester"]) == ("CB3211", "DE", "I", 6)
    assert (second["code"], second["slot_number"], second["semester"]) == ("CB3212", "I", 6)  # group carried
    assert second["ltpc"] is None and second["in_scope"] is True
    assert second["owner_department"]["value"] == "Chemical and Biochemical Engineering"


def test_sub_heading_keeps_the_eligibility_note_of_its_list():
    entries = walk([  # curriculum_nep2020 pp35-37: an HSS list printed under the BS programme
        "(6.) BS Programme from the Department of Humanities and Social Sciences",
        "(List of HSS Electives for all approved B. Tech. / BS Program of the Institute:)",
        "HSS Elective-I",
        "1. HS2106 Literature: Voices and Culture 3 0 0 3",
    ])
    e = entries[0]
    assert (e["code"], e["slot_type"], e["slot_number"]) == ("HS2106", "HSS", "I")
    assert "for all approved B. Tech." in e["eligibility_note"]["value"]
    assert e["in_scope"] is True                    # open to B. Tech. students although printed under BS


def test_eligibility_note_without_a_space_in_btech_still_counts():
    entries = walk([  # curriculum_nep2020 p38: "B.Tech." without a space, heading wrapped onto two lines
        "(6.) BS Programme from the Department of Humanities and Social Sciences",
        "Interdisciplinary Elective (IDE) Course for B.Tech. (Available to students other than Dept.",
        "of HSS)",
        "IDE-I",
        "1. HS2205 Science, Technology and Society 3 0 0 3",
    ])
    e = entries[0]
    assert (e["code"], e["slot_type"], e["slot_number"], e["in_scope"]) == ("HS2205", "IDE", "I", True)
    assert e["eligibility_note"]["value"].endswith("other than Dept. of HSS)")


def test_an_unnamed_list_heading_closes_the_ide_list_above_it():
    entries = walk([  # curriculum_nep2020 pp38-39: IDE-III of HSS, then the BS Economics electives
        "(6.) BS Programme from the Department of Humanities and Social Sciences",
        "Interdisciplinary Elective (IDE) Course for B.Tech. (Available to students other than Dept.",
        "of HSS)",
        "IDE-III",
        "2. HS4122 Forensic Linguistics 3 0 0 3",
        "List of Elective for Semester VII and VIII:",
        "1. HS4101 Game Theory 3 1 0 4",
    ])
    ide, bs = entries
    assert (ide["slot_type"], ide["slot_number"], ide["in_scope"]) == ("IDE", "III", True)
    assert (bs["code"], bs["slot_type"], bs["in_scope"]) == ("HS4101", None, False)


def test_code_above_row_in_an_ide_list_keeps_its_note():
    entries = walk([  # curriculum_nep2020 p48
        "(8.) B. Tech. Programme from the Department of Mechanical Engineering",
        "Interdisciplinary Elective (IDE) Courses for B. Tech. (Available to students other than",
        "Dept. of ME)",
        "ME2205 Manufacturing Processes for",
        "1. 3 0 0 3",
        "Metallic Materials",
        "2. ME3106 Automotive Technology 3 0 0 3",
    ])
    me2205, me3106 = entries
    assert (me2205["code"], me2205["slot_type"], me2205["in_scope"]) == ("ME2205", "IDE", True)
    assert me2205["title"] == "Manufacturing Processes for Metallic Materials"
    assert me2205["eligibility_note"]["value"].endswith("other than Dept. of ME)")
    assert me3106["slot_type"] == "IDE"
