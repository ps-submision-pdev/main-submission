"""Tests for buddy/kb_build/prereqs.py with a fake LLM."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from buddy.kb_build.prereqs import prerequisites  # noqa: E402

TRUST = {"explicit": 0.9, "inferred": 0.3, "llm_inferred": 0.3}


def rec(code, prereq=None, description=None, page=31):
    claim = [{"value": prereq, "source_id": "cbe_btech", "page": page, "span": f"Pre-requisite | {prereq}"}] if prereq else []
    return {"id": code, "title": {"value": f"Title {code}"},
            "prerequisite": {"value": prereq, "claims": claim, "chosen": claim[0] if claim else None},
            **{f: {"value": None} for f in ("objectives", "content", "outcomes")},
            "description": {"value": description}}


DB = {
    "CB3103": rec("CB3103", "CB2103 (Heat Transfer), CB2202 (Mass Transfer-I)", "Design of equipment."),
    "CB2103": rec("CB2103"), "CB2202": rec("CB2202"), "CB2205": rec("CB2205"),
    "ME1202": rec("ME1202", "Nil", "Statics."),
    "CS3202": rec("CS3202", "offline", "Deep learning needs linear algebra and probability from MA1201."),
    "CB3105": rec("CB3105", None, "Uses reaction engineering models from CB2205 and numerical methods."),
    "CE3105": rec("CE3105"),                                   # no text at all
    "MA1201": rec("MA1201"),
}
SLICE_CODES = ["CB3103", "ME1202", "CS3202", "CB3105", "CE3105"]
ALREADY_DONE = ["CB2103", "CB2202", "CB2205", "MA1201"]


class FakeLLM:
    model = "fake"

    def __init__(self, reply):
        self.reply, self.messages = reply, None

    def ask_json(self, messages, schema, prompt_version):
        self.messages = messages
        return {**self.reply, "cached": False,
                "usage": {"attempts": 1, "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


def proposals(*items):
    return {"ok": True, "data": {"prerequisites": [
        {"course": c, "prerequisite": p, "evidence_quote": q} for c, p, q in items]}}


def run(reply, llm=True):
    fake = FakeLLM(reply) if llm else None
    return prerequisites(SLICE_CODES, ALREADY_DONE, DB, fake, TRUST), fake


def test_explicit_codes_come_from_the_database_with_high_trust():
    out, _ = run(proposals())
    edges = out["edges"]["CB3103"]
    assert [(e["code"], e["source"], e["trust"]) for e in edges] == [("CB2103", "explicit", 0.9), ("CB2202", "explicit", 0.9)]
    assert edges[0]["raw"] == "CB2103 (Heat Transfer), CB2202 (Mass Transfer-I)" and edges[0]["verified"] is False
    assert out["status"]["CB3103"] == "explicit"


def test_nil_is_an_explicit_no_and_no_text_means_no_question():
    out, fake = run(proposals())
    assert out["status"]["ME1202"] == "explicit: none" and out["edges"]["ME1202"] == []
    assert out["status"]["CE3105"] == "no text: model not asked"
    asked = [c["code"] for c in json.loads(fake.messages[1]["content"])["courses"]]
    assert asked == ["CB3105", "CS3202"]                 # "offline" names no code, so CS3202 is asked


def test_model_edges_are_checked_and_labelled():
    out, _ = run(proposals(
        ("CB3105", "CB2205", "Uses reaction engineering models from CB2205"),   # quote found -> inferred
        ("CS3202", "MA1201", "needs a strong maths background"),               # quote not found -> llm_inferred
        ("CS3202", "ZZ9999", ""),                                              # unknown code
        ("CS3202", "CS3202", ""),                                              # itself
        ("CE3105", "CB2205", ""),                                              # course was not asked
        ("CB3105", "CB3103", ""),                                              # in the slice: allowed
    ))
    cb3105 = {e["code"]: e for e in out["edges"]["CB3105"]}
    assert (cb3105["CB2205"]["source"], cb3105["CB2205"]["trust"]) == ("inferred", 0.3)
    assert cb3105["CB3103"]["source"] == "llm_inferred"
    cs = out["edges"]["CS3202"]
    assert [(e["code"], e["source"], e["verified"]) for e in cs] == [("MA1201", "llm_inferred", False)]
    verdicts = [d["verdict"] for d in out["decisions"]]
    assert "dropped:not a course in the slice or already_done" in verdicts
    assert "dropped:a course cannot require itself" in verdicts
    assert "dropped:course was not asked about" in verdicts


def test_an_edge_that_would_make_a_cycle_is_dropped():
    out, _ = run(proposals(("CB3105", "CS3202", ""), ("CS3202", "CB3105", "")))
    assert [e["code"] for e in out["edges"]["CB3105"]] == ["CS3202"]
    assert out["edges"]["CS3202"] == []
    assert out["decisions"][-1]["verdict"] == "dropped:would create a cycle"


def test_no_model_keeps_only_the_database_edges():
    out, _ = run(None, llm=False)
    assert out["status"]["CB3105"] == "no model: not asked" and out["edges"]["CB3105"] == []
    assert len(out["edges"]["CB3103"]) == 2
