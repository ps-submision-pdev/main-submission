"""Persona loader: read personas/<id>.json and reject anything malformed. Plain code, no LLM.

load_persona(path, db=None) returns the persona dict, or raises PersonaError naming the bad field.
Checks:
  - exactly the fields in FIELDS: a missing or unknown field (e.g. a typo) is an error
  - each field has the right type; planning_semester is 1-8; year = (planning_semester + 1) // 2
  - programme_id is a syllabus source in ingest/sources.yaml (its department is read from there,
    so nothing is hard-wired to one department)
  - constraints only has credit_cap, hours_per_week (number or null) and not_together (code pairs)
  - every evidence item has field, value, source (graded | tested | self_declared) and a trust
    equal to config/trust.yaml for that source (trust numbers live only in that file)
  - with a database: every code in already_done and not_together exists in it
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SOURCES_FILE = ROOT / "ingest/sources.yaml"
TRUST_FILE = ROOT / "config/trust.yaml"
EVIDENCE_SOURCES = ("graded", "tested", "self_declared")
CONSTRAINT_KEYS = ("credit_cap", "hours_per_week", "not_together")


class PersonaError(ValueError):
    pass


def is_text(v) -> bool:
    return isinstance(v, str) and v.strip() != ""


def is_text_list(v) -> bool:
    return isinstance(v, list) and all(is_text(x) for x in v)


def is_number_or_none(v) -> bool:
    return v is None or (isinstance(v, (int, float)) and not isinstance(v, bool))


# field -> (check, what it must be). persona_id goes into file names, so only a-z, 0-9 and _.
FIELDS = {
    "persona_id": (lambda v: isinstance(v, str) and re.fullmatch(r"[a-z0-9_]+", v) is not None, "lowercase a-z, 0-9, _"),
    "synthetic": (lambda v: isinstance(v, bool), "true or false"),
    "programme_id": (is_text, "a non-empty string"),
    "year": (lambda v: isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 4, "an integer 1-4"),
    "planning_semester": (lambda v: isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 8, "an integer 1-8"),
    "goal_text": (is_text, "a non-empty string"),
    "goal_keywords": (lambda v: is_text_list(v) and len(v) > 0, "a non-empty list of strings"),
    "weaknesses": (is_text_list, "a list of strings"),
    "constraints": (lambda v: isinstance(v, dict), "an object"),
    "already_done": (is_text_list, "a list of course codes"),
    "known_topics": (is_text_list, "a list of strings"),
    "evidence": (lambda v: isinstance(v, list) and all(isinstance(e, dict) for e in v), "a list of objects"),
}


def programmes() -> dict:
    """Syllabus sources in ingest/sources.yaml, by id: the programmes a persona can belong to."""
    sources = yaml.safe_load(SOURCES_FILE.read_text(encoding="utf-8"))["sources"]
    return {s["id"]: s for s in sources if s.get("kind") == "syllabus"}


def programme_of(persona: dict) -> dict:
    return programmes()[persona["programme_id"]]


def check_constraints(c: dict) -> None:
    unknown = sorted(set(c) - set(CONSTRAINT_KEYS))
    if unknown:
        raise PersonaError(f"constraints: unknown key(s) {unknown}; allowed {list(CONSTRAINT_KEYS)}")
    for key in ("credit_cap", "hours_per_week"):
        if not is_number_or_none(c.get(key)):
            raise PersonaError(f"constraints.{key} must be a number or null")
    pairs = c.get("not_together", [])
    if not (isinstance(pairs, list) and all(is_text_list(p) and len(p) == 2 for p in pairs)):
        raise PersonaError("constraints.not_together must be a list of [code, code] pairs")


def check_evidence(items: list) -> None:
    trust = yaml.safe_load(TRUST_FILE.read_text(encoding="utf-8"))["evidence"]
    for i, e in enumerate(items):
        if sorted(e) != ["field", "source", "trust", "value"]:
            raise PersonaError(f"evidence[{i}] must have exactly field, value, source, trust; has {sorted(e)}")
        if not is_text(e["field"]) or isinstance(e["value"], (dict, list)):
            raise PersonaError(f"evidence[{i}]: field must be a string and value a single value")
        if e["source"] not in EVIDENCE_SOURCES:
            raise PersonaError(f"evidence[{i}]: source must be one of {list(EVIDENCE_SOURCES)}")
        if e["trust"] != trust[e["source"]]:
            raise PersonaError(f"evidence[{i}]: trust {e['trust']} differs from config/trust.yaml "
                               f"({e['source']} = {trust[e['source']]})")


def load_persona(path, db: dict | None = None) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise PersonaError(f"cannot read {path}: {e}") from None
    if not isinstance(data, dict):
        raise PersonaError("a persona file must hold one JSON object")
    for name in sorted(set(data) - set(FIELDS)):
        raise PersonaError(f"unknown field: {name}")
    for name in FIELDS:
        if name not in data:
            raise PersonaError(f"missing field: {name}")
    for name, (check, expected) in FIELDS.items():
        if not check(data[name]):
            raise PersonaError(f"{name} must be {expected}")
    if data["year"] != (data["planning_semester"] + 1) // 2:
        raise PersonaError(f"year {data['year']} does not match planning_semester {data['planning_semester']}")
    if data["programme_id"] not in programmes():
        raise PersonaError(f"programme_id {data['programme_id']!r} is not a syllabus source in ingest/sources.yaml")
    check_constraints(data["constraints"])
    check_evidence(data["evidence"])
    if db is not None:
        codes = data["already_done"] + [c for pair in data["constraints"].get("not_together", []) for c in pair]
        unknown = sorted(set(codes) - set(db))
        if unknown:
            raise PersonaError(f"course codes not in the database: {unknown}")
    return data
