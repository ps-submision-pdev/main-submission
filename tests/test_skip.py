"""Tests for buddy/skip.py and buddy/checks.py."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from buddy import checks, profile as P, skip  # noqa: E402
from buddy.kb_build.persona import load_persona  # noqa: E402

DB = json.loads((ROOT / "data/db/resolved.json").read_text(encoding="utf-8"))
PERSONA = load_persona(ROOT / "personas/chem_data_s4.json", db=DB)
T0, T1 = "2026-11-06T10:00:00+00:00", "2026-11-06T11:00:00+00:00"
EXAMPLE_CHECK = {"topic": "basic Python", "pass_mark": 2, "questions": [   # test-only example, not the student's
    {"question": "q1", "options": ["a", "b"], "answer": 0},
    {"question": "q2", "options": ["a", "b"], "answer": 1},
    {"question": "q3", "options": ["a", "b"], "answer": 1}]}


def test_self_declared_basic_python_does_not_skip():
    p = P.load_profile_from_persona(PERSONA, now=T0)
    out = skip.should_skip(p, "basic Python")
    assert out["skip"] is False and out["why"] == "self-declared, not enough to skip: ask check questions"
    assert len(out["fact_ids"]) == 1


def test_after_a_passed_check_it_skips():
    p = P.load_profile_from_persona(PERSONA, now=T0)
    result = checks.record_check(p, EXAMPLE_CHECK, [0, 1, 0], now=T1)        # 2 of 3 correct, pass mark 2
    assert result["passed"] and result["score"] == 2
    out = skip.should_skip(p, "basic Python")
    assert out["skip"] is True and P.supports(p, "basic Python")["best_trust"] == 0.7


def test_a_failed_check_adds_nothing():
    p = P.load_profile_from_persona(PERSONA, now=T0)
    assert checks.record_check(p, EXAMPLE_CHECK, [1, 0, 0], now=T1)["passed"] is False
    assert skip.should_skip(p, "basic Python")["skip"] is False


def test_unknown_topic_does_not_skip():
    p = P.load_profile_from_persona(PERSONA, now=T0)
    assert skip.should_skip(p, "linear algebra") == {"skip": False, "why": "no fact supports this topic", "fact_ids": []}


def test_the_stub_check_file_has_the_format_but_cannot_be_graded_yet():
    stub = checks.load_check(ROOT / "data/checks/basic_python.json")
    assert stub["topic"] == "basic Python" and len(stub["questions"]) == 3
    assert all(set(q) == {"question", "options", "answer"} for q in stub["questions"])
    with pytest.raises(checks.CheckError):
        checks.grade(stub, [0, 0, 0])
