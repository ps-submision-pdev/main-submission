"""Tests for buddy/kb_build/slice.py, review.py and the course-exists / slot-membership checks.
Real database, real rules, real persona chem_data_s4; a fake model."""
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from buddy.kb_build import checks  # noqa: E402
from buddy.kb_build.persona import load_persona  # noqa: E402
from buddy.kb_build.review import write_review  # noqa: E402
from buddy.kb_build.slice import build_slice, write_slice  # noqa: E402

DB = json.loads((ROOT / "data/db/resolved.json").read_text(encoding="utf-8"))
ENTRIES = json.loads((ROOT / "data/db/list_entries.json").read_text(encoding="utf-8"))
RULES = json.loads((ROOT / "data/kb/rules.json").read_text(encoding="utf-8"))
SETTINGS = yaml.safe_load((ROOT / "config/kb_build.yaml").read_text(encoding="utf-8"))
TRUST = yaml.safe_load((ROOT / "config/trust.yaml").read_text(encoding="utf-8"))
PERSONA = load_persona(ROOT / "personas/chem_data_s4.json", db=DB)
USAGE = {"attempts": 1, "prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}


class FakeLLM:
    """Answers each prompt version with a fixed reply."""
    model = "fake-model"

    def ask_json(self, messages, schema, prompt_version):
        replies = {
            "rank_v2": {"ranked": [{"code": "CS2207", "reason": "data science with Python"},
                                   {"code": "MA2206", "reason": "numerical methods for simulation"},
                                   {"code": "MA3107", "reason": "PDEs for modelling"},
                                   {"code": "CH3106", "reason": "Judged by title only; a chemistry lab course."},
                                   {"code": "ZZ9999", "reason": "invented"}]},
            "prereq_v1": {"prerequisites": [{"course": "MA2206", "prerequisite": "MA1101", "evidence_quote": ""}]},
            "foundations_v1": {"foundations": [{"weakness": "differential equations", "codes": ["MA3107"],
                                                "reason": "PDE course"}]},
            "skills_v1": {"skills": [{"course": "CS2207", "skill": "Data visualization", "quote": "VISUALIZATION"},
                                     {"course": "CS2207", "skill": "Mind reading", "quote": "telepathy"},
                                     {"course": "ZZ9999", "skill": "Anything", "quote": "x"}]},
        }
        return {"ok": True, "data": replies[prompt_version], "cached": False, "usage": USAGE}


def build():
    return build_slice(PERSONA, DB, ENTRIES, RULES, FakeLLM(), SETTINGS, TRUST)


def test_slice_holds_14_full_records_core_and_kept_options():
    kb, _ = build()
    assert len(kb["courses"]) == 14
    assert kb["core"] == {"4": ["CB2201", "CB2202", "CB2203", "CB2204", "CB2205"],
                          "5": ["CB3101", "CB3102", "CB3103", "CB3104", "CB3105"]}
    horizon = [s for s in kb["slots"] if s["full_records"]]
    assert [(s["slot"], s["semester"], s["options"]) for s in horizon] == [
        ("IDE-I", 4, ["CS2207", "MA2206"]), ("IDE-II", 5, ["MA3107", "CH3106"])]
    later = [s for s in kb["slots"] if not s["full_records"]]
    assert later and all(len(s["options"]) >= 1 for s in later)          # later slots: codes only


def test_records_are_unverified_and_carry_source_and_trust():
    kb, _ = build()
    assert kb["verified"] is False and all(r["verified"] is False for r in kb["courses"].values())
    cb3103 = kb["courses"]["CB3103"]
    assert (cb3103["source"], cb3103["trust"], cb3103["category"]) == ("database", 0.9, "core")
    assert [(e["code"], e["source"]) for e in cb3103["prerequisites"]] == [("CB2103", "explicit"), ("CB2202", "explicit")]
    ch = kb["courses"]["CH3106"]["rank"]
    assert ch["reason"] is None and ch["reason_check"].startswith("contradicted")   # lab claim, P = 0
    assert ch["basis"] == "title-based" and ch["reason_source"] == "llm_inferred" and ch["trust"] == 0.3


def test_rules_foundations_and_model_prerequisites():
    kb, _ = build()
    assert [r["id"] for r in kb["rules"]] == ["ord-8.4a-first-year-before-third-year", "ord-8.4c-overload",
                                              "ord-12.1a-low-cpi", "ord-8.4b-contact-hours"]
    assert all(r["provenance"]["url"].startswith("https://") and r["verified"] is False for r in kb["rules"])
    assert kb["foundations"][0]["code"] == "MA3107" and kb["foundations"][0]["source"] == "llm_inferred"
    ma2206 = kb["courses"]["MA2206"]["prerequisites"]
    assert [(e["code"], e["source"], e["verified"]) for e in ma2206] == [("MA1101", "llm_inferred", False)]


def test_checks_pass_on_the_built_slice_and_catch_bad_ones():
    kb, extra = build()
    assert kb["checks"] == {"size": [], "course_exists": [], "slot_membership": []}
    bad = json.loads(json.dumps(kb))
    bad["slots"][0]["options"].append("CS3208")                           # a CSE DE course in IDE-I
    bad["foundations"].append({**bad["foundations"][0], "code": "ZZ9999"})
    assert checks.check_course_exists(bad, DB) == ["ZZ9999 (foundations) is not in the database"]
    assert checks.check_slot_membership(bad, extra["available"]) == ["CS3208 is not an option of IDE-I (semester 4)"]


def test_same_input_gives_a_byte_identical_slice_and_review(tmp_path):
    for name in ("a", "b"):
        kb, extra = build()
        write_slice(kb, tmp_path / f"{name}.json")
        write_review(tmp_path / f"{name}.md", kb, extra, DB)
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()
    assert (tmp_path / "a.md").read_bytes() == (tmp_path / "b.md").read_bytes()


def test_review_names_source_trust_and_model_decisions(tmp_path):
    kb, extra = build()
    write_review(tmp_path / "r.md", kb, extra, DB)
    text = (tmp_path / "r.md").read_text(encoding="utf-8")
    for expected in ("| CB3103 |", "database", "0.9", "llm_inferred", "contradicted", "dropped:code not in the candidate list",
                     "ord-8.4a-first-year-before-third-year", "## Removed before the model"):
        assert expected in text, expected


def test_decision_log_has_one_line_per_model_decision(tmp_path):
    from buddy.kb_build.review import write_decisions
    kb, extra = build()
    write_decisions(tmp_path / "d.jsonl", extra)
    lines = [json.loads(line) for line in (tmp_path / "d.jsonl").read_text(encoding="utf-8").splitlines()]
    expected = sum(len(extra[s]["decisions"]) for s in ("rank", "prerequisites", "foundations", "skills"))
    assert len(lines) == expected
    assert {line["step"] for line in lines} == {"rank", "prerequisites", "foundations", "skills"}
    assert all({"step", "said", "verdict", "evidence", "tokens"} <= set(line) for line in lines)
    zz = [line for line in lines if isinstance(line["said"], dict) and line["said"].get("code") == "ZZ9999"]
    assert zz[0]["verdict"] == "dropped:code not in the candidate list"


def test_skills_are_in_the_slice_review_and_decision_log(tmp_path):
    from buddy.kb_build.review import write_decisions
    kb, extra = build()
    cs = kb["courses"]["CS2207"]["skills"]
    assert [(x["skill"], x["source"], x["quote"] is not None) for x in cs] == [
        ("Data visualization", "inferred", True), ("Mind reading", "llm_inferred", False)]
    assert kb["courses"]["CS2207"]["skills_status"] == "model" and kb["prompt_versions"]["skills"] == "skills_v1"
    write_review(tmp_path / "r.md", kb, extra, DB)
    text = (tmp_path / "r.md").read_text(encoding="utf-8")
    assert "## Skills" in text and "Data visualization" in text and "Mind reading" in text
    write_decisions(tmp_path / "d.jsonl", extra)
    steps = [json.loads(line)["step"] for line in (tmp_path / "d.jsonl").read_text().splitlines()]
    assert steps.count("skills") == 3


def test_model_steps_can_be_switched_off_one_by_one():
    only_rank = {**SETTINGS, "use_model": {"rank": True, "prerequisites": False, "skills": False, "foundations": False}}
    kb, extra = build_slice(PERSONA, DB, ENTRIES, RULES, FakeLLM(), only_rank, TRUST)
    assert kb["rank_source"] == "model" and kb["foundations"] == []
    assert all(r["skills"] == [] for r in kb["courses"].values())
    assert all(e["source"] == "explicit" for r in kb["courses"].values() for e in r["prerequisites"])
    assert kb["use_model"] == only_rank["use_model"]
    none = {**SETTINGS, "use_model": {k: False for k in ("rank", "prerequisites", "skills", "foundations")}}
    assert build_slice(PERSONA, DB, ENTRIES, RULES, FakeLLM(), none, TRUST)[0]["rank_source"] == "fallback"
