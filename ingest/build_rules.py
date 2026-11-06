"""Build the rule records from hand-picked clauses, and verify every quote with code.

Run from the repo root (after fetch and extract):
    python3 -I ingest/build_rules.py

Reads  data/extracted/<id>.jsonl, data/raw/manifest.json
Writes data/kb/rules.json: {"rules": [...], "open_limits": [...]}

The student chose the clauses; this script does not choose. Each quote must appear in the stored
text of its page. The comparison collapses whitespace, because the PDF breaks lines mid-sentence;
every word and character must still match. If one quote is missing, nothing is written and the
script exits with 1. Every record starts with verified=false: the student checks it against the
PDF and sets it to true by hand.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

OUT = Path("data/kb/rules.json")

RULES = [
    {
        "id": "ord-8.4a-first-year-before-third-year",
        "kind": "prerequisite",
        "text": "All first-year courses must be passed before registering for any third-year course.",
        "parameters": {"required_before": {"from_year": 3, "requires_passed_year": 1}},
        "source_id": "btech_ordinance", "clause": "8.4(a)", "page": 4,
        "quote": "(a) A student must pass all first year courses before registering for the third year courses.",
    },
    {
        "id": "ord-8.4c-overload",
        "kind": "eligibility",
        "text": "From semester 5, a student with CPI at least 8.0 may take one extra course per semester, "
                "with Dean/Associate Dean (Academic) approval.",
        "parameters": {"min_cpi": 8.0, "from_semester": 5, "extra_courses": 1, "requires_approval": True},
        "source_id": "btech_ordinance", "clause": "8.4(c)", "page": 4,
        "quote": "(c) Provision for overloading: Students of 5th semester onwards having CPI of at least 8.0 may be "
                 "allowed to credit an extra course per semester over the prescribed list of courses of the department "
                 "for the concerned semester. Interested students with CPI of at least 8.0 may apply to Dean/ Associate "
                 "Dean (Academic) through Faculty advisor and HoD",
    },
    {
        "id": "ord-12.1a-low-cpi",
        "kind": "other",
        "text": "A CPI below 5.0 at the end of a semester brings a warning; a CPI below 5.0 in two consecutive "
                "semesters may end the student's continuation in the programme.",
        "parameters": {"warn_below": 5.0, "consecutive_semesters": 2},
        "source_id": "btech_ordinance", "clause": "12.1(a)", "page": 5,
        "quote": "(a) If a student fails to secure a CPI of 5.0 at the end of any semester. However, a student securing "
                 "a CPI below 5.0 may be allowed to continue in the following semester on the recommendation of DAPC and "
                 "with the approval of IAPC. Simultaneously the student will be issued a warning that his/her CPI has to "
                 "come up to a value of at least 5.0. Students who secure a CPI below 5.0 in two consecutive semesters "
                 "may not be allowed to continue in the undergraduate program.",
    },
    {
        "id": "ord-8.4b-contact-hours",
        "kind": "credit_limit",
        "text": "A semester's L-T-P load may not exceed 32 contact hours per week.",
        "parameters": {"max_contact_hours_per_week": 32},
        "source_id": "btech_ordinance", "clause": "8.4(b), second sentence", "page": 4,
        "quote": "The L-T-P loading for a semester should not exceed 32 contact hours per week.",
        "note": "Only the second sentence is used. The first sentence (not less than 30 and not more than 50 credits "
                "per semester) is on an old scale: NEP-2020 semester totals are 16-23.5 credits and the Chemical "
                "degree total is 166.",
    },
]

OPEN_LIMITS = [
    {"id": "open-semester-credit-limit",
     "text": "No per-semester credit limit on the NEP-2020 scale was found. The only per-semester credit limit "
             "(ordinance 8.4(b), 30-50 credits) is on an old scale and is not used.",
     "searched": "btech_ordinance, curriculum_nep2020, btech_program_nep2020, cbe_btech (reports/rule_candidates.md, topic 1)"},
    {"id": "open-minor-eligibility",
     "text": "No rule found on who may take a Minor, when, or with what CPI. The only related line is a list "
             "heading: 'Minor in Business Studies: (Only open to B. Tech. / BS-MBA Dual Degree)' "
             "(curriculum_nep2020 p40).",
     "searched": "btech_ordinance, curriculum_nep2020, btech_program_nep2020, cbe_btech (reports/rule_candidates.md, topic 3)"},
]


def squeeze(text: str) -> str:
    return " ".join(text.split())


def page_text(source_id: str, page: int) -> str:
    with open(Path("data/extracted") / f"{source_id}.jsonl", encoding="utf-8") as f:
        for row in f:
            p = json.loads(row)
            if p["page"] == page:
                return p["text"]
    return ""


def build(rule: dict, manifest: dict) -> dict:
    source = manifest[rule["source_id"]]
    record = {k: rule[k] for k in ("id", "kind", "text", "parameters")}
    record["provenance"] = {"source_id": rule["source_id"], "url": source["url"], "clause": rule["clause"],
                            "page": rule["page"], "quote": rule["quote"]}
    if "note" in rule:
        record["note"] = rule["note"]
    record.update({"fetched_at": source["fetched_at"], "sha256": source["sha256"], "verified": False})
    return record


def main() -> int:
    manifest = json.loads(Path("data/raw/manifest.json").read_text(encoding="utf-8"))
    missing = [r["id"] for r in RULES if squeeze(r["quote"]) not in squeeze(page_text(r["source_id"], r["page"]))]
    for rule_id in missing:
        print(f"[FAIL] {rule_id}: quote not found in the stored page text")
    if missing:
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = {"rules": [build(r, manifest) for r in RULES], "open_limits": OPEN_LIMITS}
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"done: {len(RULES)} rules, every quote found in its page -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
