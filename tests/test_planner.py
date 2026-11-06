"""Tests for buddy/planner/candidates.py, render.py and buddy/context.py on the real chem_data_s4 slice."""
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from buddy import profile as P  # noqa: E402
from buddy.context import build_context  # noqa: E402
from buddy.kb_build.persona import load_persona  # noqa: E402
from buddy.planner import candidates as C  # noqa: E402
from buddy.planner.render import render_plan  # noqa: E402

DB = json.loads((ROOT / "data/db/resolved.json").read_text(encoding="utf-8"))
SLICE = json.loads((ROOT / "data/kb/slices/chem_data_s4.json").read_text(encoding="utf-8"))
RULES = SLICE["rules"]
PERSONA = load_persona(ROOT / "personas/chem_data_s4.json", db=DB)
T0 = "2026-11-06T10:00:00+00:00"
S4 = ["CB2201", "CB2202", "CB2203", "CB2204", "CB2205"]
S5 = ["CB3101", "CB3102", "CB3103", "CB3104", "CB3105"]


def profile():
    return P.load_profile_from_persona(PERSONA, now=T0)


def ids(findings):
    return [f["rule_id"] for f in findings if f["severity"] == "violation"]


def test_exactly_four_plans_in_a_fixed_order_the_same_twice():
    first = C.enumerate_plans(SLICE, profile(), RULES)
    assert [(p[4][-1], p[5][-1]) for p in first["plans"]] == [
        ("CS2207", "MA3107"), ("CS2207", "CS3106"), ("MA2206", "MA3107"), ("MA2206", "CS3106")]
    assert first["plans"][0] == {4: S4 + ["CS2207"], 5: S5 + ["MA3107"]}
    assert first == C.enumerate_plans(SLICE, profile(), RULES)
    assert first["missing"] == []


def test_rejects_an_invented_code():
    assert ids(C.check_candidate({4: S4 + ["ZZ9999"]}, SLICE, profile(), RULES)) == ["kb-course-exists"]


def test_rejects_an_option_from_the_wrong_slot():
    assert ids(C.check_candidate({4: S4 + ["MA3107"]}, SLICE, profile(), RULES)) == ["kb-slot-membership"]


def test_rejects_a_course_already_passed():
    p = profile()
    P.add_fact(p, "passed", "CS2207", "graded", now=T0)
    found = C.check_candidate({4: S4 + ["CS2207"], 5: S5 + ["MA3107"]}, SLICE, p, RULES)
    assert ids(found) == ["kb-already-passed"]
    out = C.enumerate_plans(SLICE, p, RULES)
    assert len(out["plans"]) == 2 and all("CS2207" not in plan[4] for plan in out["plans"])
    assert any("kb-already-passed" in ids(r["findings"]) for r in out["rejected"])


def test_rejects_one_extra_course_at_cpi_6_4():
    found = C.check_candidate({5: S5 + ["MA3107", "CS3106"]}, SLICE, profile(), RULES)
    assert ids(found) == ["ord-8.4c-overload"] and "CPI 6.4" in found[0]["message"]


def test_rejects_year_three_courses_with_a_first_year_course_unpassed():
    p = profile()
    p["facts"] = [f for f in p["facts"] if not (f["field"] == "passed" and f["value"] == "MA1201")]
    found = C.check_candidate({5: S5 + ["MA3107"]}, SLICE, p, RULES)
    assert ids(found) == ["ord-8.4a-first-year-before-third-year"] and "MA1201" in found[0]["message"]


def test_rejects_more_than_32_contact_hours():
    heavy = {4: S4 + ["CS2207", "MA2206", "CB3101", "CB3104", "CB3105"]}
    assert "ord-8.4b-contact-hours" in ids(C.check_candidate(heavy, SLICE, profile(), RULES))


def test_missing_fields_are_reported():
    bad = copy.deepcopy(SLICE)
    del bad["earlier_core"]
    out = C.enumerate_plans(bad, profile(), RULES)
    assert "earlier_core (first-year courses for rule 8.4(a))" in out["missing"]


def test_render_shows_credits_hours_source_tags_and_because_lines():
    p = profile()
    out = C.enumerate_plans(SLICE, p, RULES)
    text = render_plan("A", out["plans"][0], SLICE, p, [])
    assert "CS2207 Introduction to Data Science: 3.0 credits, 3 contact hours/week" in text
    assert "checked, source page 19" in text and "model guess, unverified" in text
    assert "because:" in text and "(self_declared, 0.4)" in text


def test_build_context_holds_only_the_summary():
    p = profile()
    P.add_fact(p, "cpi", 9.0, "self_declared", now=T0)              # a losing claim goes to history
    p["turns"] = [{"role": "student", "text": "SECRET HISTORY " * 50}]
    plans = C.enumerate_plans(SLICE, p, RULES)["plans"]
    ctx = build_context(p, plans, SLICE, RULES)
    blob = json.dumps(ctx)
    assert set(ctx) == {"profile", "plans", "rules"}
    assert "SECRET HISTORY" not in blob and "9.0" not in blob          # no turns, no history
    assert len(blob) < 6000
    assert sorted(ctx["plans"]) == ["A", "B", "C", "D"]
    assert all({"id", "field", "value", "source", "trust"} == set(f) for f in ctx["profile"])
