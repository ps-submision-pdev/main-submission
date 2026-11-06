"""Tests for stage 2: router, intake, choose, revise, answer and the chat session. Fake model only."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import litellm

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from buddy import profile as P  # noqa: E402
from buddy.chat import answer as A, intake as I, route as R  # noqa: E402
from buddy.chat.cli import Session  # noqa: E402
from buddy.context import build_context  # noqa: E402
from buddy.kb_build.persona import load_persona  # noqa: E402
from buddy.llm import LLMClient  # noqa: E402
from buddy.planner import candidates as C, choose as CH, revise as RV  # noqa: E402
from buddy.planner.candidates import check_candidate  # noqa: E402

DB = json.loads((ROOT / "data/db/resolved.json").read_text(encoding="utf-8"))
KB = json.loads((ROOT / "data/kb/slices/chem_data_s4.json").read_text(encoding="utf-8"))
RULES = KB["rules"]
PERSONA = load_persona(ROOT / "personas/chem_data_s4.json", db=DB)
T0 = "2026-11-06T10:00:00+00:00"
S4, S5 = KB["core"]["4"], KB["core"]["5"]
USAGE = {"attempts": 1, "prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
INTRO = "I'm in 2nd year chemical. I want to get into data stuff, but I'm bad at maths. I know some Python."


class FakeLLM:
    """Replies per prompt version: a list is used in turn (the last one repeats). Records every call."""
    model = "fake"

    def __init__(self, **replies):
        self.replies, self.calls = replies, []

    def ask_json(self, messages, schema, prompt_version):
        self.calls.append(prompt_version)
        options = self.replies.get(prompt_version, [{"ok": False, "error": "no reply set"}])
        options = options if isinstance(options, list) else [options]
        reply = options[min(sum(v == prompt_version for v in self.calls) - 1, len(options) - 1)]
        return {**reply, "usage": USAGE, "cached": False}


def ok(data):
    return {"ok": True, "data": data}


def profile():
    return P.load_profile_from_persona(PERSONA, now=T0)


def plans_for(p):
    return C.enumerate_plans(KB, p, RULES)["plans"]


# ---------- intake ----------

def test_intake_keeps_quoted_facts_and_drops_unquoted_or_bad_ones():
    llm = FakeLLM(intake_v1=ok({"facts": [
        {"field": "interest", "value": "data science", "quote": "I want to get into DATA stuff"},  # case differs
        {"field": "weakness", "value": "maths", "quote": "I'm bad at maths"},
        {"field": "known_topic", "value": "basic Python", "quote": "I know some Python"},
        {"field": "weakness", "value": "physics", "quote": "I hate physics"},                     # not said
        {"field": "hobby", "value": "chess", "quote": "I'm in 2nd year"},                         # field not allowed
        {"field": "goal", "value": " ", "quote": "I'm in 2nd year chemical"}]}))                  # empty value
    p = P.new_profile("chem_data_s4")                     # a chat starts with no self-declared facts
    out = I.intake(INTRO, p, llm, "intake_v1", now=T0)
    assert [(f["field"], f["value"], f["source"]) for f in out["kept"]] == [
        ("interest", "data science", "self_declared"), ("weakness", "maths", "self_declared"),
        ("known_topic", "basic Python", "self_declared")]
    assert out["kept"][0]["quote"] == "I want to get into DATA stuff"
    assert [d["reason"] for d in out["dropped"]] == ["quote not in the message", "field not allowed", "empty value"]


def test_a_cpi_9_claim_changes_nothing_in_the_plan_checks():
    p = profile()
    before = C.enumerate_plans(KB, p, RULES)
    llm = FakeLLM(intake_v1=ok({"facts": [{"field": "cpi", "value": "9", "quote": "my CPI is 9"}]}))
    I.intake("Honestly my CPI is 9 now.", p, llm, "intake_v1", now=T0)
    assert P.current(p, "cpi")["value"] == 6.4 and any(h["value"] in ("9", 9.0) for h in p["history"])
    assert C.enumerate_plans(KB, p, RULES) == before
    extra = check_candidate({5: S5 + ["MA3107", "CS3106"]}, KB, p, RULES)
    assert [f["rule_id"] for f in extra if f["severity"] == "violation"] == ["ord-8.4c-overload"]
    assert "current CPI 6.4" in extra[0]["message"]


# ---------- choose ----------

def test_choose_accepts_a_valid_letter_and_drops_a_reason_with_an_unknown_fact_id():
    p = profile()
    plans = plans_for(p)
    weak = next(f["id"] for f in p["facts"] if f["field"] == "grade:MA1201")
    llm = FakeLLM(choose_v1=ok({"plan": "B", "reasons": [
        {"code": "CS2207", "why": "data skills", "fact_ids": [weak]},
        {"code": "CS3106", "why": "visualization", "fact_ids": ["f999"]},       # unknown fact id
        {"code": "MA2206", "why": "not in plan B", "fact_ids": []}]}))
    out = CH.choose(build_context(p, plans, KB, RULES), plans, p, llm, "choose_v1")
    assert (out["letter"], out["by"]) == ("B", "model") and out["plan"] == plans[1]
    assert [r["code"] for r in out["reasons"]] == ["CS2207"]
    assert {d["reason"] for d in out["dropped"]} == {"unknown fact id f999", "MA2206 is not in plan B"}


def test_a_bad_letter_or_a_failed_call_falls_back_to_the_first_plan():
    p = profile()
    plans = plans_for(p)
    for reply in (ok({"plan": "Z", "reasons": []}), {"ok": False, "error": "RateLimitError"}):
        out = CH.choose(build_context(p, plans, KB, RULES), plans, p, FakeLLM(choose_v1=reply), "choose_v1")
        assert (out["letter"], out["by"], out["plan"]) == ("A", "fallback", plans[0])
        assert out["reasons"] == [{"code": None, "why": "default plan: the model was not available", "fact_ids": []}]


# ---------- revise ----------

def test_revise_rejects_an_extra_course_at_cpi_6_4_and_offers_the_nearest_valid_plan():
    p = profile()
    current = plans_for(p)[0]                                     # CS2207 + MA3107
    bad = {"plan": {"4": S4 + ["CS2207"], "5": S5 + ["MA3107", "CS3106"]}, "note": "added CS3106"}
    llm = FakeLLM(revise_v1=ok(bad))
    out = RV.revise("Can I also take Computer Graphics?", current, KB, p, llm, "revise_v1")
    assert out["accepted"] is False and out["attempts"] == 2 and llm.calls == ["revise_v1", "revise_v1"]
    assert any(f["rule_id"] == "ord-8.4c-overload" and f["page"] == 4 and "overloading" in f["quote"]
               for f in out["findings"])
    assert out["nearest"] in plans_for(p) and out["nearest"] == plans_for(p)[0]   # fewest elective changes
    assert check_candidate(out["nearest"], KB, p, RULES) == [] or all(
        f["severity"] != "violation" for f in check_candidate(out["nearest"], KB, p, RULES))


def test_revise_accepts_a_valid_change_on_the_second_attempt_and_stores_a_version():
    p = profile()
    current = plans_for(p)[0]
    llm = FakeLLM(revise_v1=[ok({"plan": {"4": S4 + ["CS2207", "MA2206"], "5": S5 + ["MA3107"]}, "note": "both"}),
                             ok({"plan": {"4": S4 + ["MA2206"], "5": S5 + ["MA3107"]}, "note": "swapped"})])
    out = RV.revise("Can I also take Numerical Methods this semester?", current, KB, p, llm, "revise_v1", now=T0)
    assert out["accepted"] is True and out["attempts"] == 2 and out["plan"] == {4: S4 + ["MA2206"], 5: S5 + ["MA3107"]}
    v = p["plan_versions"][-1]
    assert (v["version"], v["request"]) == (1, "Can I also take Numerical Methods this semester?")


def test_revise_never_accepts_a_plan_that_drops_a_core_course():
    p = profile()
    llm = FakeLLM(revise_v1=ok({"plan": {"4": S4[1:] + ["CS2207"], "5": S5 + ["MA3107"]}, "note": "dropped one"}))
    out = RV.revise("drop Mechanical Operations", plans_for(p)[0], KB, p, llm, "revise_v1")
    assert out["accepted"] is False and any(f["rule_id"] == "kb-core-missing" for f in out["findings"])


# ---------- router and answer ----------

def test_lookup_rule_and_command_messages_make_no_model_call():
    llm = FakeLLM()
    p = profile()
    p["turns"] = [{"role": "student", "text": "hi"}]                      # not a new profile
    for message, intent in [("how many credits is CB2204?", "lookup"), ("what does rule 8.4(c) say", "rule"),
                            ("/plan", "command"), ("skills of MA2206", "lookup")]:
        out = R.route(message, KB, p, llm, "route_v1")
        assert (out["intent"], out["by"]) == (intent, "code")
    assert llm.calls == []
    assert "4.0 credits" in R.route("credits of CB2204?", KB, p, llm, "route_v1")["reply"]
    assert "page 4" in R.route("rule 8.4(c)?", KB, p, llm, "route_v1")["reply"]


def test_unknown_or_code_only_course_is_answered_by_code():
    llm, p = FakeLLM(), profile()
    p["turns"] = [{"role": "student", "text": "hi"}]
    assert "not in my knowledge base" in R.route("What is ZZ9999 about?", KB, p, llm, "route_v1")["reply"]
    later = KB["slots"][-1]["options"][0]
    assert "I only have its code" in R.route(f"Tell me about {later}?", KB, p, llm, "route_v1")["reply"]
    assert A.answer("What is Underwater Basket Weaving?", KB, llm, "answer_v1")["reply"].startswith("That course is not")
    assert llm.calls == []


def test_router_fallback_on_a_failed_call_and_first_message_is_intake():
    p = profile()
    assert R.route(INTRO, KB, p, FakeLLM(), "route_v1")["intent"] == "intake"            # new profile
    p["turns"] = [{"role": "student", "text": "hi"}]
    failed = FakeLLM(route_v1={"ok": False, "error": "Timeout"})
    assert (R.route("is this a good idea?", KB, p, failed, "route_v1")["intent"], "fallback") == ("question", "fallback")
    assert R.route("whatever then", KB, p, failed, "route_v1")["intent"] == "other"
    bad_label = FakeLLM(route_v1=ok({"intent": "dance"}))
    assert R.route("hmm, nice", KB, p, bad_label, "route_v1")["intent"] == "other"


def test_answer_uses_only_matched_records_adds_source_tags_and_flags_outside_codes():
    llm = FakeLLM(answer_v1=ok({"answer": "CB2204 covers control loops; see also XX1234 for more."}))
    out = A.answer("What is Process Dynamics about?", KB, llm, "answer_v1")
    assert out["courses"] == ["CB2204"] and llm.calls == ["answer_v1"]
    assert "page 2" in out["reply"] and "XX1234" in out["flags"][0]


# ---------- the session ----------

def session_llm():
    return FakeLLM(
        intake_v1=ok({"facts": [{"field": "known_topic", "value": "basic Python", "quote": "I know some Python"},
                                {"field": "weakness", "value": "maths", "quote": "I'm bad at maths"}]}),
        choose_v1=ok({"plan": "A", "reasons": [{"code": "CS2207", "why": "data skills", "fact_ids": []}]}),
        route_v1=ok({"intent": "change_plan"}),
        revise_v1=ok({"plan": {"4": S4 + ["MA2206"], "5": S5 + ["MA3107"]}, "note": "swapped"}))


def run_session(tmp_path, name):
    s = Session("chem_data_s4", session_llm(), profile_path=tmp_path / f"{name}.json", now=lambda: T0)
    s.start()
    s.handle(INTRO)
    s.handle("Can I swap to Numerical Methods?")
    return s


def test_the_same_session_twice_gives_the_same_plan(tmp_path):
    a, b = run_session(tmp_path, "a"), run_session(tmp_path, "b")
    assert a.profile["plan_versions"] == b.profile["plan_versions"]
    assert [v["version"] for v in a.profile["plan_versions"]] == [1, 2]


def test_session_saves_the_profile_and_a_new_session_shows_the_plan_version(tmp_path):
    run_session(tmp_path, "c")
    again = Session("chem_data_s4", FakeLLM(), profile_path=tmp_path / "c.json", now=lambda: T0)
    assert "plan version 2" in again.start()


def test_tokens_are_zero_for_code_answered_turns(tmp_path):
    s = run_session(tmp_path, "d")
    turn = s.handle("credits of CB2204?")
    assert (turn["by"], turn["tokens"]["total_tokens"]) == ("code", 0)
    assert "tokens" in s.handle("/tokens")["reply"]
    assert len(s.profile["turns"]) <= 6


def fake_completion(*outcomes):
    outcomes = list(outcomes)

    def completion(**kwargs):
        item = outcomes.pop(0) if len(outcomes) > 1 else outcomes[0]
        if isinstance(item, Exception):
            raise item
        usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=item))], usage=usage)
    return completion


def test_broken_json_timeout_and_rate_limit_give_a_friendly_message_and_no_crash(tmp_path):
    failures = {
        "broken JSON": "this is not json",
        "timeout": litellm.Timeout(message="timed out", model="m", llm_provider="openrouter"),
        "rate limit": litellm.RateLimitError(message="429", llm_provider="openrouter", model="m"),
    }
    for name, failure in failures.items():
        llm = LLMClient(model="m", api_key="not-a-real-key", cache_dir=tmp_path / name / "cache",
                        log_file=tmp_path / name / "log.jsonl", completion=fake_completion(failure), sleep=lambda s: None)
        s = Session("chem_data_s4", llm, profile_path=tmp_path / name / "p.json", now=lambda: T0)
        s.start()
        turn = s.handle(INTRO)                                    # intake and choose both fail
        assert turn["by"] == "fallback", name
        assert "model is not available" in turn["reply"], name
        assert s.profile["plan_versions"][-1]["plan"] == {"4": S4 + ["CS2207"], "5": S5 + ["MA3107"]}, name
