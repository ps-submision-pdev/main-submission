"""Stage 5 - resolve: one value per field for each course, without dropping any claim.

Run from the repo root (after parse and slots):
    python3 -I ingest/resolve.py

Reads  data/db/courses.json, data/db/list_entries.json, ingest/source_priority.yaml
Writes data/db/resolved.json             one resolved record per course code
       the "resolve" section of reports/parse_quality.md

For every field the record keeps:
    value     the value of the winning claim (highest source priority, then lowest page)
    chosen    where that claim came from {source_id, page, span}
    conflict  true if the claims disagree, ignoring formatting (see same())
    claims    every claim, best first. Nothing is dropped, even when all claims agree.
A field with no claims gets value null, conflict false.

A conflict on a key field (title, credits, prerequisite, owner) keeps the course in the database
but sets in_scope false, so it can never become a KB candidate; "excluded_for_conflict" says which
fields. Conflicts on text fields (objectives, outcomes, ...) are flagged only.

The lists a course appears in (core in one programme, IDE in another, Minor list, ...) are not
a conflict: a course can sit in several lists. They are copied as they are into "lists".
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python3 -I leaves the script's folder off sys.path
import parse  # noqa: E402  for the shared report

FIELDS = ["title", "ltpc", "prerequisite", "learning_mode", "objectives", "description",
          "content", "outcomes", "assessment", "offered_term"]
LIST_KEYS = ["source_id", "page", "span", "slot_type", "slot_number", "semester", "heading",
             "owner_department", "eligibility_note"]
KEY_FIELDS = ["title", "ltpc", "prerequisite", "owner_department"]  # a conflict here excludes the course
REPORT = Path("reports/parse_quality.md")


def same(value) -> str:
    """Comparison key that ignores formatting, not content: case, spacing, punctuation, bullets,
    list numbers and a "(Minor I)" suffix. So "M e chanical Fabrication" = "Mechanical Fabrication",
    "• To understand ..." = "To understand ...", "Mass Transfer–I" = "Mass Transfer-I*"."""
    if not isinstance(value, str):
        return json.dumps(value, sort_keys=True)
    text = re.sub(r"\((?:minor|ide|core)\s*[ivx]+\)", "", value.lower())
    text = re.sub(r"(?:^|\s)(?:\d+\.|[a-z]\)|•)(?=\s|[a-z])", " ", text)
    return re.sub(r"[^a-z0-9]", "", text)


def resolve_claims(claims: list, priority: list) -> dict:
    if not claims:
        return {"value": None, "chosen": None, "conflict": False, "claims": []}
    ranked = sorted(claims, key=lambda c: (priority.index(c["source_id"]), c["page"]))
    best = ranked[0]
    return {"value": best["value"],
            "chosen": {"source_id": best["source_id"], "page": best["page"], "span": best["span"]},
            "conflict": len({same(c["value"]) for c in claims}) > 1,
            "claims": ranked}


def resolve(course_id: str, db: dict) -> dict:
    """One resolved record for a course code. db = load_db()."""
    record, config = db["courses"][course_id], db["config"]
    out = {"id": course_id, "aliases": record["aliases"]}
    for field in FIELDS:
        out[field] = resolve_claims(record[field], config["priority"])

    mine = db["entries_by_code"].get(course_id, [])
    owners = []  # owner facts from the NEP-2020 documents only; one per distinct line
    for e in mine:
        fact = e["owner_department"]
        if e["in_scope"] and fact and e["source_id"] in config["owner_sources"] and fact not in owners:
            owners.append(fact)
    out["owner_department"] = resolve_claims(owners, config["priority"])
    out["lists"] = [{k: e[k] for k in LIST_KEYS} for e in mine]
    out["excluded_for_conflict"] = [f for f in KEY_FIELDS if out[f]["conflict"]]
    out["in_scope"] = any(e["in_scope"] for e in mine) and not out["excluded_for_conflict"]
    out["has_detail_page"] = "detail_pages" in record
    return out


SENATE = "btech_program_nep2020"


def mark_possible_aliases(resolved: dict) -> list[tuple[str, str]]:
    """Mark only, never choose: a code that only the Senate document has, whose title matches a course
    under a different code in another document (CB3211 "Catalysis Science and Engineering" = CB3206),
    gets possible_alias_of = [those codes], and each of those gets the Senate code back.
    in_scope is not changed. Returns the (senate code, other code) pairs."""
    def sources(r):
        return {c["source_id"] for f in FIELDS for c in r[f]["claims"]}
    codes_by_title: dict = {}
    for code, r in resolved.items():
        for c in r["title"]["claims"]:
            if c["source_id"] != SENATE:
                codes_by_title.setdefault(same(c["value"]), set()).add(code)
    pairs = []
    for code, r in sorted(resolved.items()):
        if r["in_scope"] and sources(r) == {SENATE} and r["title"]["value"]:
            for other in sorted(codes_by_title.get(same(r["title"]["value"]), set()) - {code}):
                pairs.append((code, other))
    for code, other in pairs:
        resolved[code].setdefault("possible_alias_of", []).append(other)
        resolved[other].setdefault("possible_alias_of", []).append(code)
    return pairs


def alias_lines(resolved: dict, pairs: list) -> list[str]:
    out = ["", f"## Possible aliases: Senate-only code vs another code with the same title ({len(pairs)} pairs)", "",
           "Marked only (possible_alias_of on both records); nothing chosen, in_scope unchanged.", "",
           "| Senate code | Senate page and line | other code | other source, page and line | other in scope |",
           "|---|---|---|---|---|"]
    for code, other in pairs:
        mine = resolved[code]["title"]["claims"][0]
        theirs = next(c for c in resolved[other]["title"]["claims"]  # the claim whose title matched
                      if c["source_id"] != SENATE and same(c["value"]) == same(mine["value"]))
        cell = lambda c: f"p{c['page']} `{' / '.join(c['span'].split(chr(10)))}`"
        out.append(f"| {code} | {cell(mine)} | {other} | {theirs['source_id']} {cell(theirs)} "
                   f"| {resolved[other]['in_scope']} |")
    return out


def load_db() -> dict:
    courses = json.loads(Path("data/db/courses.json").read_text(encoding="utf-8"))
    entries = json.loads(Path("data/db/list_entries.json").read_text(encoding="utf-8"))
    config = yaml.safe_load(Path("ingest/source_priority.yaml").read_text(encoding="utf-8"))
    by_code: dict = {}
    for e in entries:
        if e["code"]:
            by_code.setdefault(e["code"], []).append(e)
    return {"courses": courses, "entries_by_code": by_code, "config": config,
            "placeholder_codes": sorted({e["slot_code"] for e in entries if e["is_placeholder"] and e["slot_code"]})}


def short(value, n: int = 70) -> str:
    text = value if isinstance(value, str) else "{l}-{t}-{p}-{c}".format(**value) if isinstance(value, dict) else str(value)
    return text if len(text) <= n else text[:n] + "..."


def report_lines(resolved: dict) -> list[str]:
    fields = FIELDS + ["owner_department"]
    out = ["# Resolve (ingest/resolve.py)", "",
           f"Courses: {len(resolved)}; in scope (B. Tech. lists): {sum(r['in_scope'] for r in resolved.values())}. "
           "Priority order: ingest/source_priority.yaml.", "",
           "| field | courses with a value | conflicts |", "|---|---|---|"]
    for f in fields:
        out.append(f"| {f} | {sum(r[f]['value'] is not None for r in resolved.values())} "
                   f"| {sum(r[f]['conflict'] for r in resolved.values())} |")
    for f in fields:
        rows = [r for r in resolved.values() if r[f]["conflict"]]
        out += ["", f"## Conflicts: {f} ({len(rows)})", ""]
        for r in rows:
            chosen = r[f]["chosen"]
            others = sorted({short(c["value"]) for c in r[f]["claims"]} - {short(r[f]["value"])})
            out.append(f"- {r['id']}: chose `{short(r[f]['value'])}` ({chosen['source_id']} p{chosen['page']}); "
                       f"also: {'; '.join(f'`{o}`' for o in others)}")
        if not rows:
            out.append("None.")
    return out


def main() -> int:
    db = load_db()
    missing = {c["source_id"] for r in db["courses"].values() for f in FIELDS for c in r[f]} - set(db["config"]["priority"])
    if missing:
        print(f"[FAIL] not in ingest/source_priority.yaml: {sorted(missing)}")
        return 1
    resolved = {code: resolve(code, db) for code in sorted(db["courses"])}
    for code in db["placeholder_codes"]:  # e.g. CB4298 "DE-VI": a slot, not a course
        if code in resolved:
            resolved[code]["in_scope"] = False
            resolved[code]["placeholder_only"] = True
    pairs = mark_possible_aliases(resolved)
    out = Path("data/db/resolved.json")
    out.write_text(json.dumps(resolved, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    parse.write_report_section(REPORT, "resolve", report_lines(resolved) + alias_lines(resolved, pairs))
    print(f"done: {len(resolved)} courses -> {out}; conflicts in {REPORT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
