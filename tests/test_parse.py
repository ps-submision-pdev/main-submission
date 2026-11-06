"""Tests for ingest/parse.py. Every input line below is copied from the real extracted documents."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
import parse  # noqa: E402

SOURCE = {"id": "test_source", "url": "https://example.invalid/test.pdf"}


def rows_of(text_lines, page=1):
    found, problems = [], []
    parse.parse_rows([(page, line) for line in text_lines], SOURCE, found, problems)
    return found, problems


def blocks_of(text_lines, page=1):
    found, problems = [], []
    parse.parse_blocks([(page, line) for line in text_lines], SOURCE, found, problems)
    return found, problems


def test_docx_row_under_semester_heading():
    found, _ = rows_of([
        "Sl. No. | Subject Code | SEMESTER VI | L | T | P | C",
        "4. | CB3204 | AI/ML for Chemical Engineers | 1 | 0 | 4 | 3",
    ])
    assert len(found) == 1
    row = found[0]
    assert row["code"] == "CB3204"
    assert row["title"] == "AI/ML for Chemical Engineers"
    assert row["ltpc"] == {"l": 1, "t": 0, "p": 4, "c": 3.0}
    assert row["offering"]["semester"] == 6


def test_pdf_row_with_wrapped_title():
    found, _ = rows_of([
        "Probability Theory and Ordinary",
        "1. MA1201 3 1 0 4",
        "Differential Equations",
    ])
    assert found[0]["title"] == "Probability Theory and Ordinary Differential Equations"
    assert "1. MA1201 3 1 0 4" in found[0]["span"]


def test_paired_code_keeps_alias():
    found, _ = rows_of(["3. PH1101/PH1201 Physics 3 1 3 5.5"])
    assert (found[0]["code"], found[0]["alias"]) == ("PH1101", "PH1201")


def test_row_without_code_is_reported_not_guessed():
    found, problems = rows_of(["3. |  | Heat Transfer | 3 | 0 | 3 | 4.5"])
    assert found == []
    assert len(problems) == 1 and "Heat Transfer" in problems[0]


def test_elective_placeholders_are_skipped_silently():
    found, problems = rows_of([
        "5. CS32XX DE-I (AI ELECTIVES LIST) 3 0 0 3",
        "1. EE41xx Departmental Elective – I 3 0 0 3",
        "5. DE-I 3 0 0 3",
    ])
    assert found == [] and problems == []


def test_detail_block_fields_and_raw_prerequisite():
    found, _ = blocks_of([
        "Course Number | CB3105",
        "Course Credit (L-T-P-C) | 2-0-3-3.5",
        "Course Title | Chemical Process Modeling and Simulation",
        "Pre-requisite | CB2205 (Chemical Reaction Engineering-I)",
        "Learning Mode | Lectures and lab",
        "Text Books",
        "Some Author, Some Book, 2020.",
    ])
    block = found[0]
    assert block["code"] == "CB3105"
    assert block["fields"]["prerequisite"]["text"] == "CB2205 (Chemical Reaction Engineering-I)"
    assert block["fields"]["learning_mode"]["text"] == "Lectures and lab"  # stops at "Text Books"


def test_course_number_line_without_code_keeps_block_open():
    found, problems = blocks_of([
        "Course Number | ME1202/ ME1102",
        "Course Number | Engineering Mechanics",
        "L-T-P-C | 3-1-0-4",
        "Pre-requisites | Nil",
        "Semester | Spring",
    ])
    block = found[0]
    assert (block["code"], block["alias"]) == ("ME1202", "ME1102")
    assert block["fields"]["credits"]["text"] == "3-1-0-4"
    assert block["fields"]["prerequisite"]["text"] == "Nil"  # "Semester" is its own field
    assert "title" not in block["fields"]                   # flagged, not guessed
    assert any("Engineering Mechanics" in p for p in problems)


def test_semester_table_ends_a_detail_block():
    found, _ = blocks_of([
        "Course Number | CB2101",
        "Course Title | Introduction to Chemical Engineering",
        "Sl. No. | Subject Code | SEMESTER III | L | T | P | C",
        "1. | CB2101 | Introduction to Chemical Engineering | 2 | 0 | 0 | 2",
    ])
    assert found[0]["fields"]["title"]["text"] == "Introduction to Chemical Engineering"


def test_code_after_title_row_has_title_and_no_credits():
    found, problems = rows_of(["DE-I 1. Catalysis Science and Engineering (CB3211)"], page=3)
    assert problems == []
    row = found[0]
    assert (row["code"], row["title"], row["ltpc"]) == ("CB3211", "Catalysis Science and Engineering", None)
    assert row["span"] == "DE-I 1. Catalysis Science and Engineering (CB3211)"


def test_code_above_the_credits_row():
    found, _ = rows_of([  # curriculum_nep2020 p48
        "ME2205 Manufacturing Processes for",
        "1. 3 0 0 3",
        "Metallic Materials",
        "ME3104 Engineering Software Laboratory",
        "3. 1 0 3 2.5",
        "Page 48 of 195",
    ], page=48)
    me2205, me3104 = found
    assert (me2205["code"], me2205["title"]) == ("ME2205", "Manufacturing Processes for Metallic Materials")
    assert me2205["ltpc"] == {"l": 3, "t": 0, "p": 0, "c": 3.0}
    assert me2205["span"] == "ME2205 Manufacturing Processes for\n1. 3 0 0 3\nMetallic Materials"
    assert me3104["title"] == "Engineering Software Laboratory"          # the footer is not part of the title
    assert me3104["ltpc"] == {"l": 1, "t": 0, "p": 3, "c": 2.5}
