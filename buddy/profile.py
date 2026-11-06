"""Profile store: what the buddy knows about one student, as facts with a source and a trust.

A profile is plain JSON at data/profile/<persona_id>.json (git-ignored: it is personal data):
    {"persona_id", "facts": [...], "history": [...], "plan_versions": [], "turns": []}
A fact is {id, field, value, source: graded | tested | self_declared, trust, time}; trust comes from the
"evidence" part of config/trust.yaml, never from the caller.

Fields:  cpi and grade:<code> hold ONE value; passed, known_topic, weakness, interest and goal hold many
         (two weaknesses do not compete; two claims about the same topic do).
Rule:    a new fact meets the current one for the same field (and value, for many-valued fields):
         higher trust wins; equal trust, the newer wins. The loser always goes to "history", with
         "lost_to" naming the winner's id, so a losing claim such as "my CPI is 9" is kept, not lost.
plan_versions and turns are kept for the chat (stage 2); nothing in this file reads them.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TRUST_FILE = ROOT / "config/trust.yaml"
PROFILE_DIR = ROOT / "data/profile"
MANY = ("passed", "known_topic", "weakness", "interest", "goal")


def trust_of(source: str) -> float:
    return yaml.safe_load(TRUST_FILE.read_text(encoding="utf-8"))["evidence"][source]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def key(field: str, value) -> tuple:
    """Facts with the same key compete. For many-valued fields the value is part of the key."""
    return (field, " ".join(str(value).lower().split())) if field in MANY else (field,)


def new_profile(persona_id: str) -> dict:
    return {"persona_id": persona_id, "facts": [], "history": [], "plan_versions": [], "turns": []}


def add_fact(profile: dict, field: str, value, source: str, now: str | None = None) -> dict:
    """Add a fact by the trust rule; returns the fact that is current afterwards."""
    fact = {"id": f"f{len(profile['facts']) + len(profile['history']) + 1}", "field": field, "value": value,
            "source": source, "trust": trust_of(source), "time": now or now_iso()}
    old = next((f for f in profile["facts"] if key(f["field"], f["value"]) == key(field, value)), None)
    if old is None:
        profile["facts"].append(fact)
        return fact
    if (old["value"], old["source"]) == (value, source):
        return old                                          # the same statement again: nothing changes
    if fact["trust"] > old["trust"] or (fact["trust"] == old["trust"] and fact["time"] >= old["time"]):
        profile["facts"][profile["facts"].index(old)] = fact
        profile["history"].append({**old, "lost_to": fact["id"]})
        return fact
    profile["history"].append({**fact, "lost_to": old["id"]})
    return old


def current(profile: dict, field: str) -> dict | None:
    """The current fact of a one-value field (cpi, grade:<code>)."""
    return next((f for f in profile["facts"] if f["field"] == field), None)


def load_profile_from_persona(persona: dict, now: str | None = None) -> dict:
    """A first profile from a persona file: evidence as given, weaknesses and known topics as
    self_declared, the goal as self_declared, and every already_done course as a graded "passed" fact."""
    profile = new_profile(persona["persona_id"])
    for code in persona["already_done"]:
        add_fact(profile, "passed", code, "graded", now)
    for e in persona["evidence"]:
        field = {"known_topic": "known_topic", "weakness": "weakness"}.get(e["field"], e["field"])
        add_fact(profile, field, e["value"], e["source"], now)
    for w in persona["weaknesses"]:
        add_fact(profile, "weakness", w, "self_declared", now)
    for t in persona["known_topics"]:
        add_fact(profile, "known_topic", t, "self_declared", now)
    add_fact(profile, "goal", persona["goal_text"], "self_declared", now)
    return profile


def to_rules_profile(profile: dict) -> dict:
    """What buddy/rules.check_plan needs: passed courses and the current CPI."""
    cpi = current(profile, "cpi")
    value = float(cpi["value"]) if cpi else 0.0
    return {"passed": sorted(f["value"] for f in profile["facts"] if f["field"] == "passed"),
            "cpi": value, "cpi_history": [value] if cpi else []}


def supports(profile: dict, topic: str) -> dict:
    """The facts saying the student knows a topic, and the best trust among them."""
    found = [f for f in profile["facts"] if key(f["field"], f["value"]) == key("known_topic", topic)]
    return {"fact_ids": [f["id"] for f in found], "best_trust": max((f["trust"] for f in found), default=0.0)}


def add_plan_version(profile: dict, plan: dict, request: str, now: str | None = None, **extra) -> dict:
    """Keep an accepted plan as a new version: {version, time, request, plan, ...}. Old versions stay."""
    version = {"version": len(profile["plan_versions"]) + 1, "time": now or now_iso(), "request": request,
               "plan": {str(sem): list(codes) for sem, codes in sorted(plan.items(), key=lambda kv: int(kv[0]))}, **extra}
    profile["plan_versions"].append(version)
    return version


def profile_path(persona_id: str) -> Path:
    return PROFILE_DIR / f"{persona_id}.json"


def save_profile(profile: dict, path=None) -> None:
    path = Path(path or profile_path(profile["persona_id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")


def load_profile(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
