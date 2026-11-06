"""Tests for buddy/kb_build/foundations.py with a fake LLM."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from buddy.kb_build.foundations import foundations  # noqa: E402

PERSONA = {"goal_text": "data skills", "weaknesses": ["probability", "linear algebra"]}
OPTIONS = [{"code": "MA2206", "slot": "IDE-I", "semester": 4}, {"code": "MA3107", "slot": "IDE-II", "semester": 5},
           {"code": "CS2207", "slot": "IDE-I", "semester": 4}]
DB = {c["code"]: {"title": {"value": c["code"]}, "description": {"value": "text"}, "objectives": {"value": None},
                  "outcomes": {"value": None}} for c in OPTIONS}


class FakeLLM:
    model = "fake"

    def __init__(self, reply):
        self.reply = reply

    def ask_json(self, messages, schema, prompt_version):
        return {**self.reply, "cached": False, "usage": {"attempts": 1, "prompt_tokens": 1, "completion_tokens": 1,
                                                         "total_tokens": 2}}


def reply(*items):
    return {"ok": True, "data": {"foundations": [{"weakness": w, "codes": c, "reason": r} for w, c, r in items]}}


def test_valid_picks_are_stored_as_llm_inferred():
    out = foundations(PERSONA, OPTIONS, DB, FakeLLM(reply(("probability", ["CS2207"], "covers statistics"))), 0.3, 240)
    assert out["items"] == [{"weakness": "probability", "code": "CS2207", "slot": "IDE-I", "semester": 4,
                             "reason": "covers statistics", "source": "llm_inferred", "trust": 0.3, "verified": False}]


def test_codes_must_be_window_options_and_at_most_two_per_weakness():
    out = foundations(PERSONA, OPTIONS, DB, FakeLLM(reply(
        ("linear algebra", ["MA2206", "ZZ9999", "MA3107", "CS2207"], "maths"),
        ("calculus", ["MA2206"], "not a weakness of this student"))), 0.3, 240)
    assert [i["code"] for i in out["items"]] == ["MA2206", "MA3107"]
    verdicts = [d["verdict"] for d in out["decisions"]]
    assert "dropped:ZZ9999 is not an option in the planning window" in verdicts
    assert "dropped:CS2207 is over the limit of 2 per weakness" in verdicts
    assert "dropped:not one of the persona's weaknesses" in verdicts


def test_no_model_means_no_foundations():
    out = foundations(PERSONA, OPTIONS, DB, None, 0.3, 240)
    assert out["items"] == [] and out["decisions"][0]["verdict"] == "skipped"
