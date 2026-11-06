"""Tests for buddy/kb_build/skills.py with a fake model."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from buddy.kb_build.skills import skills  # noqa: E402

TRUST = {"inferred": 0.3, "llm_inferred": 0.3}


def rec(code, **text):
    fields = {f: {"value": text.get(f)} for f in ("objectives", "outcomes", "content", "description")}
    return {"id": code, "title": {"value": f"Title {code}"}, **fields}


DB = {
    "CS2207": rec("CS2207", objectives="Learn data cleaning and\n  exploratory   data analysis with Python.",
                  outcomes="Build simple predictive models."),
    "MA2206": rec("MA2206", content="Numerical solution of ODEs; finite differences."),
    "CE3105": rec("CE3105"),                                    # no text at all
}


class FakeLLM:
    model = "fake"

    def __init__(self, reply):
        self.reply, self.messages = reply, None

    def ask_json(self, messages, schema, prompt_version):
        self.messages = messages
        return {**self.reply, "cached": False,
                "usage": {"attempts": 1, "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}


def reply(*items):
    return {"ok": True, "data": {"skills": [{"course": c, "skill": s, "quote": q} for c, s, q in items]}}


def run(*items):
    fake = FakeLLM(reply(*items))
    return skills(["CE3105", "CS2207", "MA2206"], DB, fake, "skills_v1", TRUST), fake


def test_quote_found_even_with_case_and_whitespace_differences():
    out, _ = run(("CS2207", "Data cleaning", "learn DATA cleaning and exploratory data analysis"))
    assert out["skills"]["CS2207"] == [{"skill": "Data cleaning", "quote": "learn DATA cleaning and exploratory data analysis",
                                        "source": "inferred", "trust": 0.3, "verified": False}]


def test_quote_not_found_is_kept_as_llm_inferred_without_a_quote():
    out, _ = run(("MA2206", "Linear algebra", "matrix decompositions"))
    assert out["skills"]["MA2206"] == [{"skill": "Linear algebra", "quote": None, "source": "llm_inferred",
                                        "trust": 0.3, "verified": False}]


def test_course_without_text_is_not_asked_and_gets_no_skills():
    out, fake = run(("CE3105", "Green design", "sustainable buildings"))
    asked = [c["code"] for c in json.loads(fake.messages[1]["content"])["courses"]]
    assert asked == ["CS2207", "MA2206"]
    assert out["skills"]["CE3105"] == [] and out["status"]["CE3105"] == "no text, no skills"
    assert out["decisions"][0]["verdict"] == "dropped:course was not asked about"


def test_duplicate_skills_are_removed():
    out, _ = run(("CS2207", "Python programming", "with Python"), ("CS2207", "  python   PROGRAMMING ", "with Python"))
    assert [s["skill"] for s in out["skills"]["CS2207"]] == ["Python programming"]
    assert out["decisions"][1]["verdict"] == "dropped:duplicate skill"


def test_hallucinated_course_code_and_empty_skill_are_dropped():
    out, _ = run(("ZZ9999", "Anything", "x"), ("MA2206", "  ", "finite differences"))
    verdicts = [d["verdict"] for d in out["decisions"]]
    assert verdicts == ["dropped:course was not asked about", "dropped:empty skill"]
    assert out["skills"]["MA2206"] == []


def test_at_most_six_skills_per_course():
    out, _ = run(*[("MA2206", f"Skill {n}", "finite differences") for n in range(8)])
    assert len(out["skills"]["MA2206"]) == 6
    assert out["decisions"][-1]["verdict"] == "dropped:over the limit of 6 skills"


def test_no_model_means_no_skills_and_no_call():
    out = skills(["CS2207"], DB, None, "skills_v1", TRUST)
    assert out["skills"] == {"CS2207": []} and out["status"]["CS2207"] == "no model: not asked"
