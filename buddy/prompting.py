"""One way to ask the model a question: a versioned prompt file plus a JSON payload, through buddy/llm.py.

ask(llm, version, payload, schema, step) -> (data or None, call record)
    messages  [system: buddy/prompts/<version>.md, user: the payload as sorted JSON]
    call      {step, prompt_version, ok, error, cached, tokens}: what the transcript and /tokens show
Never raises: no model (llm is None) or a failed call gives (None, record with ok False), and the caller
uses its code fallback.
"""
from __future__ import annotations

import json
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
ZERO = {"attempts": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def ask(llm, version: str, payload: dict, schema: dict, step: str):
    if llm is None:
        return None, {"step": step, "prompt_version": version, "ok": False, "error": "no model configured",
                      "cached": False, "tokens": dict(ZERO)}
    messages = [{"role": "system", "content": (PROMPT_DIR / f"{version}.md").read_text(encoding="utf-8")},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, sort_keys=True)}]
    result = llm.ask_json(messages, schema, version)
    call = {"step": step, "prompt_version": version, "ok": result["ok"], "error": result.get("error"),
            "cached": result.get("cached", False), "tokens": result.get("usage", dict(ZERO))}
    return (result["data"] if result["ok"] else None), call
