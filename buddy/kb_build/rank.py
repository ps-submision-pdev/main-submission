"""Rank (model, ids only): order every elective option by usefulness for the student's goal.

rank(persona, available, shortlisted, db, llm, settings) -> {
    rank_source: "model" | "fallback", model, prompt_version,
    by_slot:   {slot: [{code, reason, source: "model" | "fallback", rank}]}   at most options_per_slot each
    decisions: [{step, said, verdict, evidence, tokens}]                        for the decision log
    usage:     token counts of the call (zeros without a call)
}
    available    eligibility.filter_available(...)["available"]: only its slot options are candidates
    shortlisted  shortlist(...): keyword score and matched terms, sent as weak hints
    llm          an LLMClient, or None for --no-llm
    settings     config/kb_build.yaml (options_per_slot, description_chars)
    prompt_version  "rank_v1" (default: sends the keyword score and matched terms as hints) or
                 "rank_v2" (no hints: the model judges from goal, title and text only)

The model judges; code verifies each item (ask_json checks only the top-level type): an object, a
candidate code, not a duplicate, a non-empty reason, and its slot still under options_per_slot.
Code, not the model, decides text_available (description, objectives or outcomes non-empty); it is never
sent. A model reason is stored as llm_inferred with the trust from config/trust.yaml, with basis "text" or
"title-based"; a leading "judged by title only" is removed (a wrong one is recorded as a mismatch), and a
reason claiming lab/practical work for a course with P = 0 is flagged "contradicted" and dropped.
Slots the model left short are topped up from the fallback order (shortlist score, slot, code); with
no model, a failed call or no valid item, the whole ranking is the fallback order.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

PROMPT_VERSION = "rank_v1"                      # default of the function; the builder passes the configured one
PROMPT_DIR = Path(__file__).resolve().parent / "prompts"
SENDS_HINTS = {"rank_v1": True, "rank_v2": False}  # rank_v2: no keyword score or matched terms in the prompt
SCHEMA = {"ranked": list}
TRUST_FILE = Path(__file__).resolve().parents[2] / "config/trust.yaml"
TEXT_FIELDS = ("description", "objectives", "outcomes")
INTERNAL = ("text_available", "p_hours")        # computed by code, never sent to the model
# "Judged by title only; ..." - the model's view of whether text exists. Code decides that instead.
TITLE_CLAIM = re.compile(r"title[- ]only|title alone|no (?:course )?(?:text|description)", re.I)
TITLE_CLAIM_LEAD = re.compile(r"^\s*(?:judged\s+(?:by|on)\s+(?:the\s+)?title\s+(?:only|alone)|title[- ]only)\s*[;:,.\-–—]*\s*", re.I)
# A claim of lab/practical work. A bare "practical" is not one: "practical tools for simulations".
LAB_CLAIM = re.compile(r"\blab(?:oratory)?\b|\bpractical\s+(?:course|component|sessions?|hours|work|class(?:es)?)\b", re.I)


def candidates_of(available: dict, shortlisted: dict, db: dict, settings: dict) -> list[dict]:
    hints = {r["code"]: r for r in shortlisted["results"]}
    out = []
    for slot in sorted(available["slots"], key=lambda s: (s["semester"], s["slot"])):
        for code in sorted(slot["options"]):
            r = db[code]
            ltpc, owner = r["ltpc"]["value"], r["owner_department"]["value"]
            text = r["description"]["value"] or r["objectives"]["value"] or ""
            has_text = any((r.get(f, {}).get("value") or "").strip() for f in TEXT_FIELDS)
            out.append({"code": code, "title": r["title"]["value"], "credits": ltpc["c"] if ltpc else None,
                        "owner": owner, "slot": slot["slot"], "semester": slot["semester"],
                        "text": text[:settings["description_chars"]],
                        "score": hints[code]["score"] if code in hints else 0,
                        "matched": sorted(hints[code]["matched"]) if code in hints else [],
                        "text_available": has_text, "p_hours": ltpc["p"] if ltpc else None})
    return out


def messages_for(persona: dict, candidates: list, prompt_version: str = PROMPT_VERSION) -> list[dict]:
    student = {k: persona[k] for k in ("goal_text", "goal_keywords", "weaknesses", "known_topics", "planning_semester")}
    hidden = INTERNAL if SENDS_HINTS[prompt_version] else INTERNAL + ("score", "matched")
    candidates = [{k: v for k, v in c.items() if k not in hidden} for c in candidates]
    user = json.dumps({"student": student, "candidates": candidates}, ensure_ascii=False, sort_keys=True)
    system = (PROMPT_DIR / f"{prompt_version}.md").read_text(encoding="utf-8")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def model_item(code: str, reason: str, cand: dict, trust: float, decision: dict) -> dict:
    """A model reason as stored: the model's title-only wording removed (code knows whether text exists),
    labelled llm_inferred, and dropped if it claims lab work on a course with no practical hours."""
    if TITLE_CLAIM.search(reason) and cand["text_available"]:
        decision["mismatch"] = "model says title only, but the course has text"
    item = {"code": code, "reason": TITLE_CLAIM_LEAD.sub("", reason).strip(), "source": "model",
            "basis": "text" if cand["text_available"] else "title-based", "reason_source": "llm_inferred",
            "trust": trust, "text_available": cand["text_available"]}
    if LAB_CLAIM.search(reason) and cand["p_hours"] == 0:
        item["reason"], item["reason_check"] = None, "contradicted: claims lab/practical work but P = 0"
        decision["reason_check"] = item["reason_check"]
    return item


def fallback_reason(c: dict) -> str:
    return f"fallback: keyword score {c['score']} ({', '.join(c['matched'])})" if c["score"] else "fallback: no keyword match"


def rank(persona: dict, available: dict, shortlisted: dict, db: dict, llm, settings: dict,
         prompt_version: str = PROMPT_VERSION) -> dict:
    per_slot = settings["options_per_slot"]
    trust = yaml.safe_load(TRUST_FILE.read_text(encoding="utf-8"))["kb"]["llm_inferred"]
    candidates = candidates_of(available, shortlisted, db, settings)
    by_code = {c["code"]: c for c in candidates}
    slot_order = [s["slot"] for s in sorted(available["slots"], key=lambda s: (s["semester"], s["slot"]))]
    by_slot = {slot: [] for slot in slot_order}
    decisions, usage = [], {"attempts": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    answer = None
    if llm is not None and candidates:
        answer = llm.ask_json(messages_for(persona, candidates, prompt_version), SCHEMA, prompt_version)
        usage = answer["usage"]
    if answer and answer["ok"]:
        for item in answer["data"]["ranked"]:
            verdict = "accepted"
            code = item.get("code") if isinstance(item, dict) else None
            if not isinstance(item, dict):
                verdict = "dropped:not an object"
            elif code not in by_code:
                verdict = "dropped:code not in the candidate list"
            elif any(code == k["code"] for items in by_slot.values() for k in items):
                verdict = "dropped:duplicate"
            elif not isinstance(item.get("reason"), str) or not item["reason"].strip():
                verdict = "dropped:empty reason"
            elif len(by_slot[by_code[code]["slot"]]) >= per_slot:
                verdict = f"dropped:over the slot budget ({per_slot} per slot)"
            decision = {"step": "rank", "said": item, "verdict": verdict, "evidence": None, "tokens": usage,
                        "text_available": by_code[code]["text_available"] if code in by_code else None}
            if verdict == "accepted":
                by_slot[by_code[code]["slot"]].append(model_item(code, item["reason"], by_code[code], trust, decision))
            decisions.append(decision)

    model_items = sum(len(items) for items in by_slot.values())
    if model_items == 0:
        said = {"error": answer["error"]} if answer and not answer["ok"] else (
            {"note": "no valid item from the model"} if answer else {"note": "no model call (--no-llm)"})
        decisions.append({"step": "rank", "said": said, "verdict": "fallback", "evidence": None, "tokens": usage})

    for c in sorted(candidates, key=lambda c: (-c["score"], slot_order.index(c["slot"]), c["code"])):
        items = by_slot[c["slot"]]
        if len(items) < per_slot and all(k["code"] != c["code"] for k in items):
            items.append({"code": c["code"], "reason": fallback_reason(c), "source": "fallback", "basis": "keyword score",
                          "reason_source": "code", "trust": None, "text_available": c["text_available"]})
    for items in by_slot.values():
        for position, item in enumerate(items, 1):
            item["rank"] = position

    return {"rank_source": "model" if model_items else "fallback",
            "model": getattr(llm, "model", None) if llm is not None else None,
            "prompt_version": prompt_version, "by_slot": by_slot, "decisions": decisions, "usage": usage}
