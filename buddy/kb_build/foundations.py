"""Weakness to foundations (model, ids only): which window options build each of the student's weak areas.

foundations(persona, options, db, llm, trust, description_chars) -> {items, decisions, usage}
    options  [{code, slot, semester}] every elective option in the planning window (not only the horizon)
    items    [{weakness, code, slot, semester, reason, source: "llm_inferred", trust, verified: False}]

One call. Code keeps a pick only if the weakness is one of the persona's, the code is one of the window
options, it is not a repeat, and the weakness has fewer than 2 picks so far. Everything kept is model
judgment: llm_inferred, low trust, verified=false. With no model, there are no foundations.
"""
from __future__ import annotations

import json
from pathlib import Path

PROMPT_VERSION = "foundations_v1"
PROMPT_FILE = Path(__file__).resolve().parent / "prompts" / f"{PROMPT_VERSION}.md"
SCHEMA = {"foundations": list}
MAX_PER_WEAKNESS = 2


def foundations(persona: dict, options: list, db: dict, llm, trust: float, description_chars: int) -> dict:
    usage = {"attempts": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if llm is None:
        return {"items": [], "usage": usage, "decisions": [{"step": "foundations", "said": {"note": "no model call"},
                                                            "verdict": "skipped", "evidence": None, "tokens": usage}]}
    by_code = {o["code"]: o for o in options}
    sent = [{"code": o["code"], "title": db[o["code"]]["title"]["value"], "slot": o["slot"], "semester": o["semester"],
             "text": (db[o["code"]]["description"]["value"] or db[o["code"]]["objectives"]["value"] or "")[:description_chars]}
            for o in sorted(options, key=lambda o: (o["semester"], o["slot"], o["code"]))]
    user = {"goal": persona["goal_text"], "weaknesses": persona["weaknesses"], "options": sent}
    messages = [{"role": "system", "content": PROMPT_FILE.read_text(encoding="utf-8")},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False, sort_keys=True)}]
    answer = llm.ask_json(messages, SCHEMA, PROMPT_VERSION)
    usage = answer["usage"]
    if not answer["ok"]:
        return {"items": [], "usage": usage, "decisions": [{"step": "foundations", "said": {"error": answer["error"]},
                                                            "verdict": "fallback", "evidence": None, "tokens": usage}]}
    weak = {w.lower(): w for w in persona["weaknesses"]}
    items, decisions = [], []
    for entry in answer["data"]["foundations"]:
        weakness = weak.get(str(entry.get("weakness", "")).lower()) if isinstance(entry, dict) else None
        reason = (entry.get("reason") or "").strip() if isinstance(entry, dict) else ""
        codes = entry.get("codes") if isinstance(entry, dict) and isinstance(entry.get("codes"), list) else []
        if weakness is None:
            decisions.append({"step": "foundations", "said": entry, "verdict": "dropped:not one of the persona's weaknesses",
                              "evidence": None, "tokens": usage})
            continue
        for code in codes:
            kept = [i for i in items if i["weakness"] == weakness]
            if code not in by_code:
                verdict = f"dropped:{code} is not an option in the planning window"
            elif any(i["code"] == code for i in kept):
                verdict = f"dropped:{code} is a repeat"
            elif len(kept) >= MAX_PER_WEAKNESS:
                verdict = f"dropped:{code} is over the limit of {MAX_PER_WEAKNESS} per weakness"
            else:
                verdict = "accepted"
                o = by_code[code]
                items.append({"weakness": weakness, "code": code, "slot": o["slot"], "semester": o["semester"],
                              "reason": reason, "source": "llm_inferred", "trust": trust, "verified": False})
            decisions.append({"step": "foundations", "said": {"weakness": weakness, "code": code, "reason": reason},
                              "verdict": verdict, "evidence": None, "tokens": usage})
    return {"items": items, "decisions": decisions, "usage": usage}
