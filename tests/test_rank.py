"""Tests for buddy/kb_build/rank.py with a fake LLM (no key, no network)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from buddy.kb_build.rank import rank  # noqa: E402

SETTINGS = {"options_per_slot": 2, "description_chars": 60}
USAGE = {"attempts": 1, "prompt_tokens": 900, "completion_tokens": 120, "total_tokens": 1020}


def course(code, title, owner="Chemical and Biochemical Engineering"):
    return {"id": code, "title": {"value": title}, "ltpc": {"value": {"l": 3, "t": 0, "p": 0, "c": 3.0}},
            "owner_department": {"value": owner}, "description": {"value": f"About {title.lower()}."},
            "objectives": {"value": None}}


DB = {c: course(c, t, o) for c, t, o in [
    ("MA3107", "Partial Differential Equations", "Mathematics"), ("CS3106", "Computer Graphics", "CSE"),
    ("CE3105", "Green Building", "Civil"), ("CB4102", "Computational Biology", None),
    ("CB4103", "Molecular Modeling", None), ("CB4101", "Industrial Pollution Control", None),
    ("CB3105", "Core Course", None)]}
AVAILABLE = {"slots": [
    {"slot": "IDE-II", "semester": 5, "options": ["CE3105", "CS3106", "MA3107"]},
    {"slot": "DE-II", "semester": 7, "options": ["CB4101", "CB4102", "CB4103"]}],
    "core": {5: ["CB3105"]}}
SHORTLISTED = {"results": [
    {"code": "CB4103", "slot": "DE-II", "score": 4, "matched": {"modeling": ["title"]}},
    {"code": "MA3107", "slot": "IDE-II", "score": 2, "matched": {"differential equations": ["title"]}}]}
PERSONA = {"persona_id": "p", "goal_text": "ML for chemical processes", "goal_keywords": ["machine learning"],
           "weaknesses": ["linear algebra"], "known_topics": ["basic Python"], "planning_semester": 5}


class FakeLLM:
    model = "fake-model"

    def __init__(self, reply):
        self.reply, self.messages = reply, None

    def ask_json(self, messages, schema, prompt_version):
        self.messages = messages
        return {**self.reply, "usage": USAGE, "cached": False}


def run(reply, settings=SETTINGS):
    llm = FakeLLM(reply)
    return rank(PERSONA, AVAILABLE, SHORTLISTED, DB, llm, settings), llm


def ranked(*pairs):
    return {"ok": True, "data": {"ranked": [{"code": c, "reason": r} for c, r in pairs]}}


def kept(result):
    return {s: [(i["code"], i["source"]) for i in items] for s, items in result["by_slot"].items()}


def test_valid_ranking_is_accepted_and_capped_per_slot():
    result, _ = run(ranked(("MA3107", "builds PDE maths"), ("CB4103", "simulation"), ("CS3106", "python"),
                           ("CB4102", "data"), ("CE3105", "not related"), ("CB4101", "not related")))
    assert result["rank_source"] == "model"
    assert kept(result) == {"IDE-II": [("MA3107", "model"), ("CS3106", "model")],
                            "DE-II": [("CB4103", "model"), ("CB4102", "model")]}
    assert result["by_slot"]["IDE-II"][0]["reason"] == "builds PDE maths"
    verdicts = {d["said"]["code"]: d["verdict"] for d in result["decisions"]}
    assert verdicts["CE3105"] == "dropped:over the slot budget (2 per slot)"


def test_bad_items_are_dropped_with_a_reason():
    result, _ = run(ranked(("ZZ9999", "invented"), ("MA3107", "maths"), ("MA3107", "again"), ("CB4103", " "),
                           ("CB3105", "core course")))
    verdicts = [(d["said"].get("code"), d["verdict"]) for d in result["decisions"]]
    assert ("ZZ9999", "dropped:code not in the candidate list") in verdicts
    assert ("MA3107", "dropped:duplicate") in verdicts
    assert ("CB4103", "dropped:empty reason") in verdicts
    assert ("CB3105", "dropped:code not in the candidate list") in verdicts   # core is never a candidate


def test_short_slots_are_topped_up_from_the_fallback_order():
    result, _ = run(ranked(("MA3107", "maths")))
    assert kept(result) == {"IDE-II": [("MA3107", "model"), ("CE3105", "fallback")],
                            "DE-II": [("CB4103", "fallback"), ("CB4101", "fallback")]}
    assert result["rank_source"] == "model"
    assert result["by_slot"]["DE-II"][0]["reason"] == "fallback: keyword score 4 (modeling)"


def test_model_failure_gives_a_full_fallback():
    result, _ = run({"ok": False, "error": "RateLimitError after 4 attempts"})
    assert result["rank_source"] == "fallback"
    assert kept(result)["IDE-II"] == [("MA3107", "fallback"), ("CE3105", "fallback")]   # score 2, then by code
    assert result["decisions"][0]["verdict"] == "fallback"
    assert result["decisions"][0]["tokens"] == USAGE


def test_no_llm_is_a_fallback_without_a_call():
    result = rank(PERSONA, AVAILABLE, SHORTLISTED, DB, None, SETTINGS)
    assert result["rank_source"] == "fallback" and result["model"] is None
    assert kept(result)["DE-II"] == [("CB4103", "fallback"), ("CB4101", "fallback")]


def test_prompt_holds_only_candidates_and_the_prompt_file():
    _, llm = run(ranked(("MA3107", "maths")))
    system, user = llm.messages
    assert "Rank EVERY candidate code exactly once" in system["content"]
    payload = json.loads(user["content"])
    assert sorted(c["code"] for c in payload["candidates"]) == ["CB4101", "CB4102", "CB4103", "CE3105", "CS3106", "MA3107"]
    assert len(payload["candidates"][0]["text"]) <= SETTINGS["description_chars"]


def test_same_input_same_output():
    a, _ = run(ranked(("MA3107", "maths"), ("CB4103", "sim")))
    b, _ = run(ranked(("MA3107", "maths"), ("CB4103", "sim")))
    assert a == b


def test_rank_v2_sends_no_keyword_hints():
    llm = FakeLLM(ranked(("MA3107", "maths")))
    result = rank(PERSONA, AVAILABLE, SHORTLISTED, DB, llm, SETTINGS, prompt_version="rank_v2")
    system, user = llm.messages
    payload = json.loads(user["content"])
    assert all("score" not in c and "matched" not in c for c in payload["candidates"])
    assert "matched" not in system["content"] and "keyword" not in system["content"].lower()
    assert result["prompt_version"] == "rank_v2"


def test_rank_v1_is_still_the_default_and_sends_hints():
    llm = FakeLLM(ranked(("MA3107", "maths")))
    assert rank(PERSONA, AVAILABLE, SHORTLISTED, DB, llm, SETTINGS)["prompt_version"] == "rank_v1"
    assert all("score" in c and "matched" in c for c in json.loads(llm.messages[1]["content"])["candidates"])


# ---- text_available, title-only claims, lab claims, trust ----

def db_with_text():
    db = {c: dict(r) for c, r in DB.items()}
    db["CE3105"] = {**db["CE3105"], "description": {"value": None}, "outcomes": {"value": None}}  # no text at all
    db["CS3106"] = {**db["CS3106"], "ltpc": {"value": {"l": 3, "t": 0, "p": 0, "c": 3.0}}}
    return db


def run_with(reply, db):
    llm = FakeLLM(reply)
    return rank(PERSONA, AVAILABLE, SHORTLISTED, db, llm, SETTINGS, prompt_version="rank_v2"), llm


def test_text_available_is_set_by_code_and_not_sent_to_the_model():
    result, llm = run_with(ranked(("MA3107", "maths"), ("CE3105", "Judged by title only; a civil topic.")), db_with_text())
    sent = json.loads(llm.messages[1]["content"])["candidates"]
    assert all("text_available" not in c for c in sent)
    flags = {d["said"]["code"]: d["text_available"] for d in result["decisions"]}
    assert flags == {"MA3107": True, "CE3105": False}


def test_title_only_claim_is_stripped_and_a_wrong_one_is_recorded():
    result, _ = run_with(ranked(("MA3107", "Judged by title only; PDEs help modelling."),
                                ("CE3105", "Judged by title only; a civil topic.")), db_with_text())
    items = {i["code"]: i for i in result["by_slot"]["IDE-II"]}
    assert items["MA3107"]["reason"] == "PDEs help modelling."
    assert items["CE3105"]["reason"] == "a civil topic."
    mismatch = {d["said"]["code"]: d.get("mismatch") for d in result["decisions"]}
    assert mismatch["MA3107"] == "model says title only, but the course has text"
    assert mismatch["CE3105"] is None


def test_no_text_course_is_title_based_llm_inferred_with_config_trust():
    result, _ = run_with(ranked(("CE3105", "a civil topic.")), db_with_text())
    item = result["by_slot"]["IDE-II"][0]
    assert (item["basis"], item["reason_source"], item["trust"]) == ("title-based", "llm_inferred", 0.3)


def test_lab_claim_on_a_course_with_no_practical_hours_is_contradicted():
    # the real CH3106 case from rank_v1: 3-0-0-3, called "a chemistry lab course"
    result, _ = run_with(ranked(("CS3106", "Synthesis of inorganic molecules is a chemistry lab course.")), db_with_text())
    item = result["by_slot"]["IDE-II"][0]
    assert item["reason"] is None and item["reason_check"] == "contradicted: claims lab/practical work but P = 0"


def test_practical_used_as_an_ordinary_word_is_not_a_lab_claim():
    # the real MA2206 reason: "giving practical tools for simulations" on a 3-0-0-3 course
    result, _ = run_with(ranked(("CS3106", "Covers numerical methods, giving practical tools for simulations.")),
                         db_with_text())
    item = result["by_slot"]["IDE-II"][0]
    assert item["reason"].startswith("Covers numerical") and item.get("reason_check") is None
