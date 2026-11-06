"""Tests for buddy/kb_build/persona.py."""
import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from buddy.kb_build import persona as P  # noqa: E402

DEMO = ROOT / "personas/chem_ml_demo.json"


def write(tmp_path, data):
    path = tmp_path / "p.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def demo():
    return json.loads(DEMO.read_text(encoding="utf-8"))


def rejected(tmp_path, data, words, db=None):
    with pytest.raises(P.PersonaError) as e:
        P.load_persona(write(tmp_path, data), db=db)
    assert words in str(e.value)


def test_demo_persona_loads_and_names_its_department():
    p = P.load_persona(DEMO)
    assert p["persona_id"] == "chem_ml_demo" and p["planning_semester"] == 5 and p["year"] == 3
    assert P.programme_of(p)["department"] == "Chemical and Biochemical Engineering"  # read from sources.yaml


def test_unknown_field_is_rejected(tmp_path):
    rejected(tmp_path, {**demo(), "goal_keyword": ["typo"]}, "unknown field: goal_keyword")


def test_missing_field_is_rejected(tmp_path):
    data = demo()
    del data["weaknesses"]
    rejected(tmp_path, data, "missing field: weaknesses")


def test_wrong_type_is_rejected(tmp_path):
    rejected(tmp_path, {**demo(), "goal_keywords": "machine learning"}, "goal_keywords")
    rejected(tmp_path, {**demo(), "planning_semester": 9}, "planning_semester")


def test_year_must_match_planning_semester(tmp_path):
    rejected(tmp_path, {**demo(), "year": 2}, "year 2 does not match planning_semester 5")


def test_bad_evidence_source_is_rejected(tmp_path):
    data = demo()
    data["evidence"][0]["source"] = "rumour"
    rejected(tmp_path, data, "source must be one of")


def test_trust_must_come_from_the_config(tmp_path):
    data = copy.deepcopy(demo())
    data["evidence"][0]["trust"] = 0.99
    rejected(tmp_path, data, "config/trust.yaml")


def test_unknown_programme_is_rejected(tmp_path):
    rejected(tmp_path, {**demo(), "programme_id": "no_such_programme"}, "programme_id")


def test_unknown_course_code_is_rejected_when_a_database_is_given(tmp_path):
    db = {code: {} for code in demo()["already_done"]}
    rejected(tmp_path, {**demo(), "already_done": demo()["already_done"] + ["ZZ9999"]}, "ZZ9999", db=db)
    assert P.load_persona(DEMO, db=db)["persona_id"] == "chem_ml_demo"


def test_chem_data_s4_persona_loads_with_the_database():
    db = json.loads((ROOT / "data/db/resolved.json").read_text(encoding="utf-8"))
    p = P.load_persona(ROOT / "personas/chem_data_s4.json", db=db)
    assert (p["persona_id"], p["year"], p["planning_semester"]) == ("chem_data_s4", 2, 4)
    assert "HS2113" in p["already_done"] and "CB2201" not in p["already_done"]
    assert p["known_topics"] == ["basic Python", "data structures"]
