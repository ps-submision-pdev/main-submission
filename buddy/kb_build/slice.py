"""Build and write one student's KB slice. Runs the steps in order; the model only ranks, proposes
prerequisites and picks foundations, and code checks every answer.

build_slice(persona, db, entries, rules_data, llm, settings, trust_config) -> (slice, extra)
    llm    an LLMClient, or None (no model: fallback ranking, database prerequisites only, no foundations)
    extra  what the review report needs (available set, removed list, every model decision)
write_slice(slice, path)  JSON with sorted keys: the same input and the same cached answers give the same bytes

Order: available -> eligibility -> horizon -> shortlist -> rank -> prerequisites -> foundations -> rules
-> checks. Full course records only for the horizon (core + kept options); later slots are codes only.
Everything in the slice has verified=false; the student checks it and sets it true by hand.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from buddy.kb_build import checks
from buddy.kb_build.available import available_for
from buddy.kb_build.eligibility import filter_available
from buddy.kb_build.foundations import PROMPT_VERSION as FOUNDATIONS_PROMPT, foundations
from buddy.kb_build.horizon import split_horizon
from buddy.kb_build.prereqs import PROMPT_VERSION as PREREQ_PROMPT, prerequisites
from buddy.kb_build.rank import TEXT_FIELDS, rank
from buddy.kb_build.shortlist import shortlist

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


def provenance(record: dict) -> dict:
    """Where the course's title row was read: source, page, the raw line(s) and the document URL."""
    chosen = record["title"]["chosen"]
    claim = next(c for c in record["title"]["claims"]
                 if (c["source_id"], c["page"], c["span"]) == (chosen["source_id"], chosen["page"], chosen["span"]))
    return {"source_id": chosen["source_id"], "page": chosen["page"], "quote": chosen["span"], "url": claim["url"]}


def course_record(code: str, db: dict, trust: float, category: str, semester: int, slot, ranked, prereq) -> dict:
    r = db[code]
    ltpc = r["ltpc"]["value"] or {}
    return {"code": code, "title": r["title"]["value"], "credits": ltpc.get("c"), "l": ltpc.get("l"),
            "t": ltpc.get("t"), "p": ltpc.get("p"), "semester": semester, "category": category, "slot": slot,
            "owner": r["owner_department"]["value"], "learning_mode": r["learning_mode"]["value"],
            "text_available": any((r[f]["value"] or "").strip() for f in TEXT_FIELDS),
            "source": "database", "trust": trust, "provenance": provenance(r),
            "rank": ranked, "prerequisites": prereq["edges"][code], "prerequisite_status": prereq["status"][code],
            "skills": [], "verified": False}


def input_hash(persona, settings, trust_config, rules_data, db, entries, prompt_versions) -> str:
    prompts = {v: (PROMPT_DIR / f"{v}.md").read_text(encoding="utf-8") for v in prompt_versions.values()}
    blob = json.dumps({"persona": persona, "settings": settings, "trust": trust_config, "rules": rules_data,
                       "db": db, "entries": entries, "prompts": prompts}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_slice(persona: dict, db: dict, entries: list, rules_data: dict, llm, settings: dict, trust_config: dict):
    kb_trust = trust_config["kb"]
    filtered = filter_available(persona, available_for(persona, entries, db), db)
    available = filtered["available"]
    horizon = split_horizon(available, persona, settings)
    inside = horizon["inside"]
    hints = shortlist(persona, db, inside)
    ranked = rank(persona, inside, hints, db, llm, settings, settings["rank_prompt_version"])

    full = [(c, "core", sem, None, None) for sem, codes in sorted(inside["core"].items()) for c in codes]
    for s in inside["slots"]:
        full += [(i["code"], s["slot_type"], s["semester"], s["slot"], i) for i in ranked["by_slot"][s["slot"]]]
    prereq = prerequisites([c for c, *_ in full], persona["already_done"], db, llm, kb_trust)
    options = [{"code": c, "slot": s["slot"], "semester": s["semester"]} for s in available["slots"] for c in s["options"]]
    found = foundations(persona, options, db, llm, kb_trust["llm_inferred"], settings["description_chars"])

    prompt_versions = {"rank": settings["rank_prompt_version"], "prerequisites": PREREQ_PROMPT,
                       "foundations": FOUNDATIONS_PROMPT}
    kb = {
        "persona_id": persona["persona_id"], "built_by": "buddy.kb_build", "verified": False,
        "model": getattr(llm, "model", None) if llm is not None else None, "prompt_versions": prompt_versions,
        "rank_source": ranked["rank_source"],
        "input_hash": input_hash(persona, settings, trust_config, rules_data, db, entries, prompt_versions),
        "horizon": horizon["semesters"], "window": available["window"],
        "core": {str(sem): codes for sem, codes in sorted(inside["core"].items())},
        "later_core": {str(sem): codes for sem, codes in sorted(horizon["later_core"].items())},
        "slots": [{"slot": s["slot"], "semester": s["semester"], "full_records": True,
                   "options": [i["code"] for i in ranked["by_slot"][s["slot"]]]} for s in inside["slots"]]
                 + [{**s, "full_records": False} for s in horizon["later_slots"]],
        "courses": {c: course_record(c, db, kb_trust["explicit"], cat, sem, slot, item, prereq)
                    for c, cat, sem, slot, item in full},
        "foundations": found["items"],
        "rules": [{**r, "verified": False} for r in rules_data["rules"]],
        "open_limits": rules_data["open_limits"],
    }
    kb["checks"] = {"size": checks.check_size(len(kb["courses"]), settings),
                    "course_exists": checks.check_course_exists(kb, db),
                    "slot_membership": checks.check_slot_membership(kb, available)}
    extra = {"available": available, "removed": filtered["removed"], "unplaced": available["unplaced"],
             "rank": ranked, "prerequisites": prereq, "foundations": found}
    return kb, extra


def write_slice(kb: dict, path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(kb, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
