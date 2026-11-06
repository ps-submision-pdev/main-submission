"""Tests for buddy/profile.py."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from buddy import profile as P  # noqa: E402
from buddy.kb_build.persona import load_persona  # noqa: E402

DB = json.loads((ROOT / "data/db/resolved.json").read_text(encoding="utf-8"))
PERSONA = load_persona(ROOT / "personas/chem_data_s4.json", db=DB)
T0, T1 = "2026-11-06T10:00:00+00:00", "2026-11-06T11:00:00+00:00"


def fresh():
    return P.load_profile_from_persona(PERSONA, now=T0)


def test_profile_from_persona_has_graded_cpi_passed_courses_and_self_declared_topics():
    p = fresh()
    cpi = P.current(p, "cpi")
    assert (cpi["value"], cpi["source"], cpi["trust"]) == (6.4, "graded", 0.9)
    assert {f["value"] for f in p["facts"] if f["field"] == "passed"} == set(PERSONA["already_done"])
    topics = {f["value"]: (f["source"], f["trust"]) for f in p["facts"] if f["field"] == "known_topic"}
    assert topics == {"basic Python": ("self_declared", 0.4), "data structures": ("self_declared", 0.4)}
    assert [f["id"] for f in p["facts"]][:2] == ["f1", "f2"]


def test_graded_beats_self_declared_and_the_claim_is_kept_in_history():
    p = fresh()
    P.add_fact(p, "cpi", 9.0, "self_declared", now=T1)
    assert P.current(p, "cpi")["value"] == 6.4
    lost = [h for h in p["history"] if h["field"] == "cpi"]
    assert lost[0]["value"] == 9.0 and lost[0]["lost_to"] == P.current(p, "cpi")["id"]
    assert P.to_rules_profile(p)["cpi"] == 6.4


def test_equal_trust_newer_wins_and_the_old_value_goes_to_history():
    p = fresh()
    P.add_fact(p, "goal", "data science", "self_declared", now=T1)       # goal is many-valued: a second goal
    P.add_fact(p, "cpi", 7.1, "graded", now=T1)                         # same trust, newer: replaces 6.4
    assert P.current(p, "cpi")["value"] == 7.1
    assert [h["value"] for h in p["history"] if h["field"] == "cpi"] == [6.4]


def test_a_tested_topic_replaces_the_self_declared_one():
    p = fresh()
    P.add_fact(p, "known_topic", "Basic python", "tested", now=T1)       # same topic, any case
    support = P.supports(p, "basic Python")
    assert support["best_trust"] == 0.7 and len(support["fact_ids"]) == 1
    assert any(h["field"] == "known_topic" and h["source"] == "self_declared" for h in p["history"])


def test_rules_profile_and_supports():
    p = fresh()
    rp = P.to_rules_profile(p)
    assert rp["cpi"] == 6.4 and rp["cpi_history"] == [6.4] and "MA1201" in rp["passed"]
    assert P.supports(p, "linear algebra") == {"fact_ids": [], "best_trust": 0.0}


def test_save_and_load_round_trip(tmp_path):
    p = fresh()
    P.save_profile(p, tmp_path / "p.json")
    assert P.load_profile(tmp_path / "p.json") == p
