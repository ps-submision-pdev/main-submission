"""Intake: turn what the student says about themselves into profile facts, keeping only what they said.

intake(message, profile, llm, version, now=None) -> {kept, dropped, call}
The model (intake_v1) lists {field, value, quote}. Code drops a fact if the field is not one of
FIELDS, the value is empty, or the quote is not in the message (lowercase, whitespace collapsed).
Kept facts go into the profile as self_declared (trust from config/trust.yaml) with the quote and time,
through profile.add_fact, so a stated CPI loses to the graded one and is kept only in history.
A failed call adds nothing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from buddy.profile import add_fact, now_iso
from buddy.prompting import ask

ROOT = Path(__file__).resolve().parents[2]

FIELDS = ("goal", "interest", "weakness", "known_topic", "cpi")


def norm(text: str) -> str:
    return " ".join(str(text).lower().split())


def words(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", str(text).lower()))


def normalise_topic(value: str, checks_dir: Path) -> str:
    """"Python" -> "basic Python" when a check file's topic and the value share all the value's words
    (or all the topic's), so the topic finds its check file. Otherwise the value as said."""
    for path in sorted(checks_dir.glob("*.json")):
        topic = json.loads(path.read_text(encoding="utf-8"))["topic"]
        if words(value) and (words(value) <= words(topic) or words(topic) <= words(value)):
            return topic
    return value


def split_weakness(value: str, slice_weaknesses: list, umbrella: list) -> list[str]:
    """"maths: probability and statistics" -> ["probability", "statistics"] (the slice's names);
    a bare umbrella word ("maths") -> every slice weakness; anything else stays as said."""
    parts = [p.strip() for p in re.split(r"[:;,/&]|\band\b", str(value).lower()) if p.strip()]
    specific = sorted(w for w in slice_weaknesses if any(words(w) <= words(p) for p in parts))
    other = [p for p in parts if p not in umbrella and not any(words(w) <= words(p) for w in slice_weaknesses)]
    if specific:
        return specific + other
    if any(p in umbrella for p in parts):
        return sorted(slice_weaknesses) + other
    return [value]


def intake(message: str, profile: dict, llm, version: str, now: str | None = None, kb: dict | None = None,
           checks_dir=None) -> dict:
    data, call = ask(llm, version, {"message": message}, {"facts": list}, "intake")
    kept, dropped = [], []
    umbrella = yaml.safe_load((ROOT / "config/buddy.yaml").read_text(encoding="utf-8")).get("weakness_umbrella_words", [])
    slice_weak = sorted({f["weakness"] for f in kb["foundations"]}) if kb else []
    checks = Path(checks_dir or ROOT / "data/checks")
    for item in (data or {}).get("facts", []):
        if not isinstance(item, dict):
            dropped.append({"fact": item, "reason": "not an object"})
            continue
        field, value, quote = item.get("field"), item.get("value"), item.get("quote") or ""
        if field not in FIELDS:
            dropped.append({"fact": item, "reason": "field not allowed"})
        elif value is None or not str(value).strip():
            dropped.append({"fact": item, "reason": "empty value"})
        elif not str(quote).strip() or norm(quote) not in norm(message):
            dropped.append({"fact": item, "reason": "quote not in the message"})
        else:
            values = [value]
            if field == "known_topic":
                values = [normalise_topic(value, checks)]
            elif field == "weakness" and slice_weak:
                values = split_weakness(value, slice_weak, umbrella)
            for v in values:
                new_id = f"f{len(profile['facts']) + len(profile['history']) + 1}"
                winner = add_fact(profile, field, v, "self_declared", now or now_iso())
                mine = next((f for f in profile["facts"] + profile["history"] if f["id"] == new_id), None)
                if mine is None:                          # the same statement was already there
                    continue
                mine["quote"] = quote                     # the quote goes on the student's own fact
                kept.append({**mine, "current": winner["id"] == new_id})
    return {"kept": kept, "dropped": dropped, "call": call}
