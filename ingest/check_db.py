"""Stage 6 - check the database: flag problems, never fix them. Deterministic, no LLM.

Run from the repo root (after parse, slots and resolve):
    python3 -I ingest/check_db.py

Reads  data/db/resolved.json, data/db/list_entries.json, data/extracted/<id>.jsonl
Writes the "check" section of reports/parse_quality.md, and prints 10 random in-scope records
(fixed seed, so the same 10 every run) with page numbers to check by hand against the PDF.

Sections: records per source; no L-T-P-C; credits != L + T + P/2; one code used for different
courses; spans not found in the page text; conflicts (excluded vs flagged); one title under
different codes; prerequisite text that names no course code.
"""
from __future__ import annotations

import json
import random
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python3 -I leaves the script's folder off sys.path
import parse  # noqa: E402
import resolve  # noqa: E402

NO_PREREQUISITE = re.compile(r"^[:\s]*(?:nil|none|na|n/a|-|no|not applicable)\.?$", re.I)
SAMPLE_SIZE, SAMPLE_SEED = 10, 7


def load_pages() -> dict:
    """(source_id, page) -> page text, for every extracted source."""
    pages = {}
    for path in sorted(Path("data/extracted").glob("*.jsonl")):
        if path.name.endswith(".preview.jsonl"):
            continue
        with open(path, encoding="utf-8") as f:
            for row in f:
                page = json.loads(row)
                pages[(page["source_id"], page["page"])] = page["text"]
    return pages


def all_facts(resolved: dict, entries: list) -> list:
    """Every fact that carries a span: claims in resolved records, list rows, owner and eligibility lines."""
    facts = [c for r in resolved.values() for f in resolve.FIELDS + ["owner_department"] for c in r[f]["claims"]]
    for e in entries:
        facts.append(e)
        facts += [fact for fact in (e["owner_department"], e["eligibility_note"]) if fact]
    return facts


def ltpc_text(v: dict) -> str:
    return f"{v['l']}-{v['t']}-{v['p']}-{v['c']}"


def check(resolved: dict, entries: list, pages: dict) -> dict:
    """Name of each section -> list of flagged lines."""
    real = {c: r for c, r in resolved.items() if not r.get("placeholder_only")}
    s = defaultdict(list)

    for code, r in sorted(real.items()):
        v = r["ltpc"]["value"]
        if v is None:
            s["No L-T-P-C"].append(code)
        elif abs(v["l"] + v["t"] + v["p"] / 2 - v["c"]) > 1e-9:
            where = f"{code} {r['title']['value']}: {ltpc_text(v)} ({r['ltpc']['chosen']['source_id']} p{r['ltpc']['chosen']['page']})"
            project = parse.PROJECT_TITLE.search(r["title"]["value"] or "")
            s["Projects and internships (own credit rule)" if project else "Credits not equal to L + T + P/2"].append(where)
        if r["title"]["conflict"]:
            titles = sorted({c["value"] for c in r["title"]["claims"]})
            s["One code used for different courses (title conflict)"].append(f"{code}: {titles}")
        if r["excluded_for_conflict"]:
            s["Excluded: conflict on a key field"].append(f"{code}: {', '.join(r['excluded_for_conflict'])}")
        flagged = [f for f in resolve.FIELDS if f not in resolve.KEY_FIELDS and r[f]["conflict"]]
        if flagged:
            s["Flagged only: conflict on a text field"].append(f"{code}: {', '.join(flagged)}")
        prereq = r["prerequisite"]["value"]
        if prereq and not re.search(parse.CODE, prereq) and not NO_PREREQUISITE.match(prereq.strip()):
            s["Prerequisite text names no course code"].append(
                f"{code}: `{prereq[:80]}` ({r['prerequisite']['chosen']['source_id']} p{r['prerequisite']['chosen']['page']})")

    for f in all_facts(resolved, entries):
        if f["span"] not in pages.get((f["source_id"], f["page"]), ""):
            s["Span not found in the stored page text"].append(f"{f['source_id']} p{f['page']}: `{f['span'][:80]}`")
    s["Span not found in the stored page text"] = sorted(set(s["Span not found in the stored page text"]))

    codes_by_title = defaultdict(set)
    for code, r in real.items():
        title = r["title"]["value"]
        if title and not parse.PROJECT_TITLE.search(title):
            codes_by_title[resolve.same(title)].add(code)
    for codes in sorted(codes_by_title.values(), key=sorted):
        if len(codes) > 1:
            s["One title under different codes"].append(
                ", ".join(f"{c} `{real[c]['title']['value']}`" for c in sorted(codes)))
    return s


def per_source_counts(resolved: dict) -> list[str]:
    counts = defaultdict(lambda: [0, 0])  # source -> [courses with a claim, of which in scope]
    for r in resolved.values():
        for sid in sorted({c["source_id"] for f in resolve.FIELDS for c in r[f]["claims"]}):
            counts[sid][0] += 1
            counts[sid][1] += r["in_scope"]
    out = ["| source | courses with a claim from it | of which in scope |", "|---|---|---|"]
    return out + [f"| {sid} | {n} | {m} |" for sid, (n, m) in sorted(counts.items())]


ORDER = ["No L-T-P-C", "Credits not equal to L + T + P/2", "Projects and internships (own credit rule)",
         "One code used for different courses (title conflict)", "One title under different codes",
         "Span not found in the stored page text", "Excluded: conflict on a key field",
         "Flagged only: conflict on a text field", "Prerequisite text names no course code"]


def report_lines(resolved: dict, sections: dict) -> list[str]:
    out = ["# Database checks (ingest/check_db.py)", "", "Flagged only; nothing was fixed. "
           f"Courses: {len(resolved)}; in scope: {sum(r['in_scope'] for r in resolved.values())}.", ""]
    out += per_source_counts(resolved)
    for name in ORDER:
        items = sections.get(name, [])
        out += ["", f"## {name} ({len(items)})", ""]
        out += [f"- {item}" for item in items] or ["None."]
    return out


def sample(resolved: dict) -> list[str]:
    """SAMPLE_SIZE random in-scope records, same every run, with where to look in the source."""
    codes = sorted(c for c, r in resolved.items() if r["in_scope"])
    out = []
    for code in sorted(random.Random(SAMPLE_SEED).sample(codes, SAMPLE_SIZE)):
        r = resolved[code]
        t, c = r["title"]["chosen"], r["ltpc"]["chosen"]
        url = r["title"]["claims"][0]["url"]
        out += [f"{code}  {r['title']['value']}  {ltpc_text(r['ltpc']['value'])}",
                f"    title: {t['source_id']} page {t['page']}   credits: {c['source_id']} page {c['page']}",
                f"    line:  {c['span']!r}", f"    pdf:   {url}"]
    return out


def main() -> int:
    resolved = json.loads(Path("data/db/resolved.json").read_text(encoding="utf-8"))
    entries = json.loads(Path("data/db/list_entries.json").read_text(encoding="utf-8"))
    sections = check(resolved, entries, load_pages())
    parse.write_report_section(resolve.REPORT, "check", report_lines(resolved, sections))
    for name in ORDER:
        print(f"{len(sections.get(name, [])):5d}  {name}")
    print(f"\n{SAMPLE_SIZE} random in-scope records (seed {SAMPLE_SEED}) to check against the PDF:\n")
    print("\n".join(sample(resolved)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
