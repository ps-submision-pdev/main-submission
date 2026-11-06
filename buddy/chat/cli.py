"""The chat session: one student, one KB slice, one profile file. Used by `python3 -m buddy chat`.

Session(persona_id, llm, profile_path=None, now=None)
    start()          new profile: start from the persona's GRADED record only (passed courses, CPI,
                     grades) and ask the student to describe themselves; everything the student says
                     comes in through intake as self_declared. Existing profile: greet and show the
                     current plan version.
    handle(message)  -> {reply, by: "code" | "model" | "fallback", tokens, calls}
        by "code": no model call; "model": every call worked; "fallback": a call failed and the code
        fallback was used (a short notice is put in front of the reply). Never raises for a model failure.
Flow: route -> command | lookup | rule | not in KB | intake | change_plan (revise) | question (answer).
After intake: check questions for self-declared known topics (if written), then the first plan
(candidates.enumerate_plans -> choose). The profile is saved after every turn; it keeps the last
recent_turns entries for the router only (see buddy/context.py).
Commands: /plan, /profile, /tokens, /quit.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from buddy import profile as P
from buddy.chat.answer import answer
from buddy.chat.intake import intake
from buddy.chat.route import route
from buddy.checks import CheckError, grade, load_check, record_check
from buddy.context import build_context
from buddy.kb_build.persona import load_persona
from buddy.planner.candidates import check_candidate, enumerate_plans
from buddy.planner.choose import choose
from buddy.planner.render import fact_text, render_plan
from buddy.planner.revise import revise
from buddy.skip import should_skip

ROOT = Path(__file__).resolve().parents[2]
HELP = "I can show /plan, /profile or /tokens, change your plan, and answer questions about your courses and rules."


def slug(topic: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", topic.lower()).strip("_")


def problem_lines(findings: list) -> list[str]:
    """Violations and warnings in plain words, with the ordinance page and quote when a rule is behind them."""
    return [f"  {f['severity']}: {f['rule_id']}: {f['message']}"
            + (f" [ordinance page {f['page']}: \"{f['quote']}\"]" if f.get("page") else "")
            for f in findings]


class Session:
    def __init__(self, persona_id: str, llm, profile_path=None, now=None):
        self.persona = load_persona(ROOT / "personas" / f"{persona_id}.json")
        self.kb = __import__("json").loads((ROOT / "data/kb/slices" / f"{persona_id}.json").read_text(encoding="utf-8"))
        self.settings = yaml.safe_load((ROOT / "config/buddy.yaml").read_text(encoding="utf-8"))
        self.path = Path(profile_path or P.profile_path(persona_id))
        self.llm, self.now = llm, now or P.now_iso
        self.profile = P.load_profile(self.path) if self.path.exists() else None
        self.calls, self.transcript, self.pending, self.done = [], [], None, False

    # ----- start and turns -----

    def start(self) -> str:
        if self.profile is None:
            full = P.load_profile_from_persona(self.persona, now=self.now())
            self.profile = P.new_profile(self.persona["persona_id"])
            for f in full["facts"]:
                if f["source"] == "graded":
                    P.add_fact(self.profile, f["field"], f["value"], "graded", f["time"])
            P.save_profile(self.profile, self.path)
            return ("Hello! I have your grade record, but I don't know you yet. Tell me about yourself: your year "
                    "and branch, what you want to learn, what you find hard, and what you already know.")
        if not self.profile["plan_versions"]:
            return "Welcome back. You have no plan yet: tell me about yourself to get one."
        v = self.profile["plan_versions"][-1]
        return f"Welcome back. Your current plan is plan version {v['version']} ({v['time']}).\n" + self.show_plan()

    def handle(self, message: str) -> dict:
        before = len(self.calls)
        reply = self.turn(message)
        calls = self.calls[before:]
        failed = [c for c in calls if not c["ok"]]
        by = "code" if not calls else "fallback" if failed else "model"
        if failed:
            reply = f"(The model is not available right now: {failed[0]['error']}. I used the code answer.)\n" + reply
        tokens = {k: sum(c["tokens"][k] for c in calls) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
        keep = self.settings["recent_turns"]
        self.profile["turns"] = (self.profile["turns"] + [{"role": "student", "text": message},
                                                          {"role": "buddy", "text": reply[:200]}])[-keep:]
        P.save_profile(self.profile, self.path)
        result = {"message": message, "reply": reply, "by": by, "tokens": tokens, "calls": calls}
        self.transcript.append(result)
        return result

    def turn(self, message: str) -> str:
        if self.pending:
            return self.check_answers(message)
        prompts = self.settings["prompts"]
        r = route(message, self.kb, self.profile, self.llm, prompts["route"])
        if r["call"]:
            self.calls.append(r["call"])
        if r["intent"] == "command":
            return self.command(message.strip().split()[0].lower())
        if r["reply"] is not None:
            return r["reply"]
        if r["intent"] == "intake":
            return self.do_intake(message)
        if r["intent"] == "change_plan":
            return self.do_revise(message)
        if r["intent"] == "question":
            out = answer(message, self.kb, self.llm, prompts["answer"])
            if out["call"]:
                self.calls.append(out["call"])
            return out["reply"]
        return HELP

    # ----- steps -----

    def do_intake(self, message: str) -> str:
        out = intake(message, self.profile, self.llm, self.settings["prompts"]["intake"], self.now(), kb=self.kb)
        self.calls.append(out["call"])
        lines = ["I noted:"] + [f"  {fact_text(f)}: \"{f['quote']}\"" + ("" if f["current"] else " (kept in history: a "
                 "higher-trust fact wins)") for f in out["kept"]] if out["kept"] else ["I could not note any facts."]
        if out["dropped"]:
            lines.append(f"  ({len(out['dropped'])} item(s) not kept: " + "; ".join(d["reason"] for d in out["dropped"]) + ")")
        for f in [f for f in self.profile["facts"] if f["field"] == "known_topic"]:
            lines.append(self.offer_check(f["value"]))
        if not self.profile["plan_versions"]:
            lines.append(self.first_plan())
        if self.pending:
            lines.append(self.pending["prompt"])
        return "\n".join(line for line in lines if line)

    def offer_check(self, topic: str) -> str:
        decision = should_skip(self.profile, topic)
        if decision["skip"]:
            return f"{topic}: {decision['why']}, so I can skip it."
        path = ROOT / "data/checks" / f"{slug(topic)}.json"
        if not path.exists():
            return f"{topic}: {decision['why']}, but I have no check questions for it, so I will not skip it."
        check = load_check(path)
        try:
            grade(check, [0] * len(check["questions"]))
        except CheckError:
            return f"{topic}: no check questions yet ({path.name} is empty), so I will not skip it."
        questions = "\n".join(f"  {i}. {q['question']} " + " ".join(f"({j}) {o}" for j, o in enumerate(q["options"], 1))
                              for i, q in enumerate(check["questions"], 1))
        self.pending = {"topic": topic, "check": check,
                        "prompt": f"To skip {topic}, answer these (one number per question, e.g. 1 3 2):\n{questions}"}
        return f"{topic}: {decision['why']}."

    def check_answers(self, message: str) -> str:
        pending, self.pending = self.pending, None
        answers = [int(n) - 1 for n in re.findall(r"\d+", message)]
        try:
            result = record_check(self.profile, pending["check"], answers, self.now())
        except CheckError as e:
            return f"I could not grade that: {e}."
        decision = should_skip(self.profile, pending["topic"])
        return (f"{pending['topic']}: {result['score']}/{result['total']} correct, "
                f"{'passed' if result['passed'] else 'not passed'}. Skip: {decision['skip']} ({decision['why']}).")

    def first_plan(self) -> str:
        found = enumerate_plans(self.kb, self.profile, self.kb["rules"])
        if not found["plans"]:
            return "No plan passes all the rules for you; I cannot suggest one."
        ctx = build_context(self.profile, found["plans"], self.kb, self.kb["rules"])
        out = choose(ctx, found["plans"], self.profile, self.llm, self.settings["prompts"]["choose"])
        self.calls.append(out["call"])
        P.add_plan_version(self.profile, out["plan"], "first plan after intake", self.now(), by=out["by"],
                           letter=out["letter"], reasons=out["reasons"])
        return "Your plan:\n" + self.show_plan()

    def do_revise(self, message: str) -> str:
        if not self.profile["plan_versions"]:
            return "You have no plan yet: tell me about yourself first."
        current = {int(k): v for k, v in self.profile["plan_versions"][-1]["plan"].items()}
        out = revise(message, current, self.kb, self.profile, self.llm, self.settings["prompts"]["revise"],
                     self.settings["max_revise_attempts"], self.now())
        self.calls.extend(out["calls"])
        warnings = [f"Warning: {f['message']}" for f in out["findings"] if f["severity"] == "warning"]
        lines = []
        if out["rejected"]:                      # the change as first proposed broke a rule: say so, with the source
            lines += ["I could not make that change as asked, because it breaks a rule:"]
            lines += problem_lines(out["rejected"][0]["findings"])
        if out["accepted"]:
            head = "Instead, " if out["rejected"] else ""
            lines += [f"{head}this plan is checked: no rule is broken. {out['note']}".strip()] + warnings + [self.show_plan()]
            return "\n".join(lines)
        if not out["rejected"]:
            lines += ["I could not make that change."] + problem_lines(out["findings"])
        if out["nearest"]:
            lines += ["The nearest plan that is checked: no rule is broken (not saved; ask me to switch if you want it):",
                      render_plan("nearest", out["nearest"], self.kb, self.profile, [])]
        return "\n".join(lines)

    # ----- commands and views -----

    def show_plan(self) -> str:
        v = self.profile["plan_versions"][-1]
        plan = {int(k): codes for k, codes in v["plan"].items()}
        findings = check_candidate(plan, self.kb, self.profile, self.kb["rules"])
        text = render_plan(f"version {v['version']}", plan, self.kb, self.profile, findings)
        for r in v.get("reasons", []):
            ids = ", ".join(r["fact_ids"]) or "no fact ids"
            text += f"\n  why {r['code'] or 'this plan'}: {r['why']} ({ids}) [model guess, unverified]" if r["code"] \
                else f"\n  why this plan: {r['why']}"
        return text

    def command(self, name: str) -> str:
        if name == "/plan":
            return self.show_plan() if self.profile["plan_versions"] else "No plan yet."
        if name == "/profile":
            return "\n".join(["Facts (current):"] + [f"  {fact_text(f)}" for f in self.profile["facts"]] +
                             [f"History: {len(self.profile['history'])} replaced fact(s); plan versions: "
                              f"{len(self.profile['plan_versions'])}"])
        if name == "/tokens":
            t = {k: sum(c["tokens"][k] for c in self.calls) for k in ("prompt_tokens", "completion_tokens", "total_tokens")}
            code_turns = sum(1 for r in self.transcript if r["by"] == "code")
            return (f"This session: {len(self.calls)} model call(s), {t['prompt_tokens']} prompt + "
                    f"{t['completion_tokens']} completion = {t['total_tokens']} tokens; {code_turns} turn(s) "
                    f"answered by code with 0 tokens.")
        if name == "/quit":
            self.done = True
            return "Bye. Your profile is saved."
        return HELP
