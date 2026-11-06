"""Intake: turn what the student says about themselves into profile facts, keeping only what they said.

intake(message, profile, llm, version, now=None) -> {kept, dropped, call}
The model (intake_v1) lists {field, value, quote}. Code drops a fact if the field is not one of
FIELDS, the value is empty, or the quote is not in the message (lowercase, whitespace collapsed).
Kept facts go into the profile as self_declared (trust from config/trust.yaml) with the quote and time,
through profile.add_fact, so a stated CPI loses to the graded one and is kept only in history.
A failed call adds nothing.
"""
from __future__ import annotations

from buddy.profile import add_fact, now_iso
from buddy.prompting import ask

FIELDS = ("goal", "interest", "weakness", "known_topic", "cpi")


def norm(text: str) -> str:
    return " ".join(str(text).lower().split())


def intake(message: str, profile: dict, llm, version: str, now: str | None = None) -> dict:
    data, call = ask(llm, version, {"message": message}, {"facts": list}, "intake")
    kept, dropped = [], []
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
            new_id = f"f{len(profile['facts']) + len(profile['history']) + 1}"
            winner = add_fact(profile, field, value, "self_declared", now or now_iso())
            mine = next((f for f in profile["facts"] + profile["history"] if f["id"] == new_id), None)
            if mine is None:                              # the same statement was already there
                continue
            mine["quote"] = quote                         # the quote goes on the student's own fact
            kept.append({**mine, "current": winner["id"] == new_id})
    return {"kept": kept, "dropped": dropped, "call": call}
