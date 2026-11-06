"""Tests for ingest/resolve.py. Claims are copied from data/db/courses.json."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ingest"))
import resolve  # noqa: E402

PRIORITY = ["curriculum_nep2020", "cbe_btech", "cse_btech", "cse_aids_btech", "math_btech_mc", "btech_program_nep2020"]


def claim(value, source_id, page, span):
    return {"value": value, "source_id": source_id, "url": "https://example.invalid", "page": page, "span": span}


def test_agreeing_sources_pick_priority_and_no_conflict():
    claims = [  # CB2202 as written in two documents: dash style differs, the title does not
        claim("Mass Transfer–I", "btech_program_nep2020", 2, "2. CB2202 Mass Transfer–I 3 0 0 3"),
        claim("Mass Transfer-I", "cbe_btech", 2, "2. | CB2202 | Mass Transfer-I | 3 | 0 | 0 | 3"),
    ]
    out = resolve.resolve_claims(claims, PRIORITY)
    assert out["value"] == "Mass Transfer-I"            # cbe_btech is above btech_program_nep2020
    assert out["chosen"]["source_id"] == "cbe_btech"
    assert out["conflict"] is False
    assert len(out["claims"]) == 2                     # agreeing claims are kept too


def test_disagreeing_sources_keep_both_claims():
    # PH1101 Physics: the semester tables say 3-1-3-5.5, the Maths syllabus detail page says 3-1-0-4.
    claims = [
        claim({"l": 3, "t": 1, "p": 0, "c": 4.0}, "math_btech_mc", 9, "Course Credit 3-1-0-4"),
        claim({"l": 3, "t": 1, "p": 3, "c": 5.5}, "curriculum_nep2020", 1, "3. PH1101/PH1201 Physics 3 1 3 5.5"),
    ]
    out = resolve.resolve_claims(claims, PRIORITY)
    assert out["value"] == {"l": 3, "t": 1, "p": 3, "c": 5.5}
    assert out["chosen"]["source_id"] == "curriculum_nep2020"
    assert out["conflict"] is True
    assert [c["source_id"] for c in out["claims"]] == ["curriculum_nep2020", "math_btech_mc"]


def test_field_with_no_claim_is_null():
    out = resolve.resolve_claims([], PRIORITY)        # e.g. CB3204 has no Pre-requisite field
    assert out == {"value": None, "chosen": None, "conflict": False, "claims": []}


def test_owner_comes_only_from_nep_documents_and_flags_disagreement():
    def entry(source_id, owner):
        fact = owner and claim(owner, source_id, 1, f"Programme from the Department of {owner}")
        return {"source_id": source_id, "page": 5, "span": "1. MA2206 Introduction to Numerical Methods 3 0 0 3",
                "slot_type": "IDE", "slot_number": "I", "semester": None, "heading": "IDE - I",
                "owner_department": fact, "eligibility_note": None, "in_scope": True}
    record = {"aliases": [], "title": [], "ltpc": [], **{f: [] for f in resolve.FIELDS}}
    db = {"courses": {"MA2206": record},
          "config": {"priority": PRIORITY, "owner_sources": ["curriculum_nep2020", "btech_program_nep2020"]},
          "entries_by_code": {"MA2206": [entry("math_btech_mc", None),           # no owner line: ignored
                                         entry("cse_btech", "Computer Science"),  # not a NEP document: ignored
                                         entry("curriculum_nep2020", "Mathematics"),
                                         entry("btech_program_nep2020", "Physics")]}}
    owner = resolve.resolve("MA2206", db)["owner_department"]
    assert owner["value"] == "Mathematics"
    assert owner["conflict"] is True
    assert {c["source_id"] for c in owner["claims"]} == {"curriculum_nep2020", "btech_program_nep2020"}


def test_formatting_noise_is_not_a_conflict():
    claims = [  # ME1201 and CS1101 as captured from different documents
        claim("M e chanical Fabrication", "curriculum_nep2020", 1, "4. ME1201/ME1101 M e chanical Fabrication 0 0 3 1.5"),
        claim("Mechanical Fabrication", "cbe_btech", 1, "4. | ME1201/ME1101 | Mechanical Fabrication | 0 | 0 | 3 | 1.5"),
    ]
    assert resolve.resolve_claims(claims, PRIORITY)["conflict"] is False
    bullets = [claim("• To understand the fundamental concepts", "cse_btech", 9, "x"),
               claim("To understand the fundamental concepts", "cbe_btech", 6, "y")]
    assert resolve.resolve_claims(bullets, PRIORITY)["conflict"] is False


def test_key_field_conflict_excludes_text_conflict_does_not():
    def db_with(field, a, b):
        record = {"aliases": [], **{f: [] for f in resolve.FIELDS}}
        record[field] = [claim(a, "cbe_btech", 1, "a"), claim(b, "cse_btech", 1, "b")]
        entry = {"source_id": "cbe_btech", "page": 1, "span": "a", "slot_type": "core", "slot_number": None,
                 "semester": 5, "heading": "SEMESTER V", "owner_department": None,
                 "eligibility_note": None, "in_scope": True}
        return {"courses": {"XX0000": record}, "entries_by_code": {"XX0000": [entry]},
                "config": {"priority": PRIORITY, "owner_sources": []}}
    excluded = resolve.resolve("XX0000", db_with("title", "Industrial Automation", "Nonlinear Dynamics and Chaos"))
    assert excluded["in_scope"] is False and excluded["excluded_for_conflict"] == ["title"]
    flagged = resolve.resolve("XX0000", db_with("outcomes", "Students will design reactors", "Students will model plants"))
    assert flagged["in_scope"] is True and flagged["outcomes"]["conflict"] is True


def test_senate_only_code_is_marked_as_possible_alias_not_chosen():
    def record(title, source_id, page, span, in_scope=True):
        r = {f: resolve.resolve_claims([], PRIORITY) for f in resolve.FIELDS}
        r["title"] = resolve.resolve_claims([claim(title, source_id, page, span)], PRIORITY)
        return {**r, "in_scope": in_scope}
    resolved = {
        "CB3211": record("Catalysis Science and Engineering", "btech_program_nep2020", 3,
                         "DE-I 1. Catalysis Science and Engineering (CB3211)"),
        "CB3206": record("Catalysis Science and Engineering", "curriculum_nep2020", 4,
                         "1. CB3206 Catalysis Science and Engineering 3 0 0 3"),
    }
    assert resolve.mark_possible_aliases(resolved) == [("CB3211", "CB3206")]
    assert resolved["CB3211"]["possible_alias_of"] == ["CB3206"]
    assert resolved["CB3206"]["possible_alias_of"] == ["CB3211"]
    assert resolved["CB3211"]["in_scope"] is True and resolved["CB3206"]["in_scope"] is True  # unchanged
