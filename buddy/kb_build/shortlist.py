"""Shortlist (code only): which AVAILABLE courses share words with what the student said.

shortlist(persona, db, available, limit=40) -> {results, matched, cut, cut_inside_tie}
    available  the output of available.available_for(): only slot options are searched, so a course
               the student may not take never reaches the model
    results    [{code, title, slot, score, matched: {term: [fields]}}], at most `limit`
    matched    how many available courses scored above 0
    cut        how many of those the limit left out; cut_inside_tie: whether the last kept course has
               the same score as the first one cut (the cut then depends on the tie-break, not the score)
    db         data/db/resolved.json (course id -> resolved record)
    terms      persona goal_keywords + weaknesses + known_topics (case-insensitive, duplicates merged)
    fields     the resolved title, objectives, outcomes and description
    match      whole word or phrase, an optional plural "s"/"es" allowed: "data" does not match
               "database", "statistic" matches "statistics". No other stemming ("modeling" does not
               match "modelling").
    score      +1 per distinct term found anywhere, +1 more if the term is in the title
    order      score high to low, then slot (semester, then label), then code

This is the one function to replace if a better retriever (BM25, embeddings) is added later.
"""
from __future__ import annotations

import re

FIELDS = ("title", "objectives", "outcomes", "description")


def terms_of(persona: dict) -> list[str]:
    words = persona["goal_keywords"] + persona["weaknesses"] + persona["known_topics"]
    return sorted({" ".join(w.lower().split()) for w in words if w.strip()})


def pattern(term: str) -> re.Pattern:
    words = r"\s+".join(re.escape(w) for w in term.split())
    return re.compile(rf"\b{words}(?:s|es)?\b", re.I)


def shortlist(persona: dict, db: dict, available: dict, limit: int = 40) -> dict:
    slot_of, slot_rank = {}, {}
    for position, slot in enumerate(sorted(available["slots"], key=lambda s: (s["semester"], s["slot"]))):
        for code in slot["options"]:
            if code not in slot_of:                  # a course in two slots counts under the earlier one
                slot_of[code], slot_rank[code] = slot["slot"], position
    patterns = {t: pattern(t) for t in terms_of(persona)}
    results = []
    for code in slot_of:
        record = db[code]
        matched = {}
        for term, rx in patterns.items():
            fields = [f for f in FIELDS if rx.search(record[f]["value"] or "")]
            if fields:
                matched[term] = fields
        score = len(matched) + sum("title" in fields for fields in matched.values())
        if score:
            results.append({"code": code, "title": record["title"]["value"], "slot": slot_of[code],
                            "score": score, "matched": matched})
    results.sort(key=lambda r: (-r["score"], slot_rank[r["code"]], r["code"]))
    kept, cut = results[:limit], results[limit:]
    return {"results": kept, "matched": len(results), "cut": len(cut),
            "cut_inside_tie": bool(kept and cut and kept[-1]["score"] == cut[0]["score"])}
