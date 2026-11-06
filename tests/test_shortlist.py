"""Tests for buddy/kb_build/shortlist.py on a small fake database and available set."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from buddy.kb_build.shortlist import shortlist  # noqa: E402


def course(code, title, in_scope=True, **text):
    fields = {f: {"value": text.get(f)} for f in ("objectives", "outcomes", "description")}
    return {"id": code, "title": {"value": title}, "in_scope": in_scope, **fields}


DB = {
    "CS2207": course("CS2207", "Machine Learning Basics", outcomes="Apply machine learning to data."),
    "CB4102": course("CB4102", "Computational Biology", description="Uses machine learning on process data."),
    "CS2202": course("CS2202", "Database and Warehousing", description="Relational database design."),
    "MA3107": course("MA3107", "Probability and Differential Equations", objectives="Basic probability and statistics."),
    "CS3103": course("CS3103", "Machine Learning"),                  # strong match, but not available
    "CB2101": course("CB2101", "Introduction to Chemical Engineering", description="Mass balances."),
}
AVAILABLE = {"slots": [
    {"slot": "IDE-II", "semester": 5, "options": ["MA3107", "CS2207", "CS2202"]},
    {"slot": "DE-II", "semester": 7, "options": ["CB4102", "CB2101"]},
]}
PERSONA = {"goal_keywords": ["machine learning", "data"], "weaknesses": ["Probability", "statistic"],
           "known_topics": ["machine learning"]}


def test_only_available_options_are_searched():
    codes = [r["code"] for r in shortlist(PERSONA, DB, AVAILABLE)["results"]]
    assert "CS3103" not in codes                 # matches best, but no slot offers it
    assert "CB2101" not in codes                 # available, but scores 0


def test_ranks_by_score_then_slot_then_code_and_lists_matches():
    out = shortlist(PERSONA, DB, AVAILABLE)
    # CS2207 and MA3107 score 3 (same slot IDE-II: code decides), CB4102 scores 2
    assert [(r["code"], r["score"], r["slot"]) for r in out["results"]] == [
        ("CS2207", 3, "IDE-II"), ("MA3107", 3, "IDE-II"), ("CB4102", 2, "DE-II")]
    assert out["results"][0]["matched"] == {"data": ["outcomes"], "machine learning": ["title", "outcomes"]}


def test_whole_words_only_but_plurals_match():
    by_code = {r["code"]: r for r in shortlist(PERSONA, DB, AVAILABLE)["results"]}
    assert "CS2202" not in by_code               # "data" must not match "database"
    assert by_code["MA3107"]["matched"]["statistic"] == ["objectives"]   # matched "statistics"


def test_ties_break_by_slot_then_code_and_the_cut_is_reported():
    db = {c: course(c, "Data Methods") for c in ("ZZ1000", "AA1000", "MM1000")}
    available = {"slots": [{"slot": "IDE-II", "semester": 5, "options": ["ZZ1000"]},
                           {"slot": "DE-I", "semester": 6, "options": ["AA1000", "MM1000"]}]}
    out = shortlist({"goal_keywords": ["data"], "weaknesses": [], "known_topics": []}, db, available, limit=2)
    assert [r["code"] for r in out["results"]] == ["ZZ1000", "AA1000"]   # semester 5 slot first
    assert (out["matched"], out["cut"], out["cut_inside_tie"]) == (3, 1, True)


def test_no_cut_reports_zero():
    out = shortlist(PERSONA, DB, AVAILABLE)
    assert (out["matched"], out["cut"], out["cut_inside_tie"]) == (3, 0, False)


def test_same_input_same_output():
    assert shortlist(PERSONA, DB, AVAILABLE) == shortlist(PERSONA, DB, AVAILABLE)
