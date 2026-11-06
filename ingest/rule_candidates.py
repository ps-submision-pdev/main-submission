"""Find candidate rule clauses by keyword and regex search. Plain code, no LLM; it chooses nothing.

Run from the repo root (after extract):
    python3 -I ingest/rule_candidates.py

Reads  data/extracted/<id>.jsonl for SOURCES
Writes reports/rule_candidates.md: every matching paragraph, verbatim, with source id, page and
       clause number when there is one, grouped by topic and then by keyword.

What counts as a paragraph:
  btech_ordinance   one row of the page's table: [clause number, text]. The PDF centres the clause
                    number beside its text, so plain text cannot show where a clause starts, but the
                    stored table can. An empty number cell means "same clause as the row above".
  cbe_btech (docx)  one line = one Word paragraph or table row.
  other PDFs        consecutive lines, joined until a line ends with "." or ":" or the next line
                    starts with a marker such as "a)", "(i)", "1.", "Note" or a bullet.
Skipped: course table rows ("1. CB2101 ... 2 0 0 2") and course syllabus pages (pages with a
"Course Number" label), so "minor losses" in a fluid mechanics syllabus is no hit.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python3 -I leaves the script's folder off sys.path
import parse  # noqa: E402
import slots  # noqa: E402

SOURCES = ["btech_ordinance", "curriculum_nep2020", "btech_program_nep2020", "cbe_btech"]
REPORT = Path("reports/rule_candidates.md")

TOPICS = {
    "1. Credits per semester (minimum, maximum, extra credits)": [
        r"\bcredits?\b[^.]{0,80}\bsemester", r"\bsemester\b[^.]{0,80}\bcredits?\b",
        r"\b(?:minimum|maximum)\b[^.]{0,60}\bcredits?\b", r"\bextra\s+credits?\b", r"\boverload"],
    "2. CPI/CGPA conditions (extra course, probation, eligibility)": [
        r"\bCPI\b", r"\bCGPA\b", r"\bSPI\b", r"\bprobation"],
    "3. Minor (eligibility, who may take it, credits, CPI needed)": [r"\bminors?\b"],
    "4. Prerequisites and registration (incl. first-year before third-year)": [
        r"pre-?\s?requisite", r"\bregist(?:er|ers|ered|ering|ration)\b", r"\bfirst\s+year\s+courses?\b", r"\bthird\s+year\b"],
}
KEYWORDS = ["minor", "honours", "audit", "withdraw", "repeat", "backlog", "extra course", "overload",
            "probation", "attendance"]
# Questions inside a topic that need two things in the same paragraph; reported as found / not found.
SUB_CHECKS = {
    "Minor + who may take it": (r"\bminors?\b", r"\beligib|\bmay\s+(?:opt|take|register)|\ballowed\b|\bopen\s+to\b|\bonly\b"),
    "Minor + CPI/CGPA needed": (r"\bminors?\b", r"\bCPI\b|\bCGPA\b"),
    "Minor + credits": (r"\bminors?\b", r"\bcredits?\b"),
    "Probation (any rule)": (r"\bprobation", r"."),
    "First-year courses before third-year courses": (r"\bfirst\s+year\s+courses?\b", r"\bthird\s+year\b"),
}

MARKER = re.compile(r"^(?:\(?[a-z]\)|\([ivx]+\)|\d+\.\s|•|Note\b|\*)")
CLAUSE_START = re.compile(r"^((?:\(?[a-z]\)\s*)?(?:\([ivx]+\))?)")
DETAIL_PAGE = re.compile(r"^Course\s+Number\b", re.M)  # not "Course Title": that is also a column header
TOTAL_ROW = re.compile(r"^TOTAL\s+\d+\s+\d+\s+\d+\s+(\d+(?:\.\d+)?)", re.I)
DEGREE_TOTAL = re.compile(r"Total Credits \(including[^:]*:\s*(\d+)")
CREDIT_NUMBER = re.compile(r"(\d+(?:\.\d+)?)\s*credits?\b", re.I)


def pages_of(sid: str) -> list[dict]:
    with open(Path("data/extracted") / f"{sid}.jsonl", encoding="utf-8") as f:
        return [json.loads(row) for row in f]


def is_table_row(line: str) -> bool:
    line = parse.normalise(line)
    return bool(parse.ROW.search(line) or slots.SLOT_ROW.match(line) or parse.CODE_AFTER_TITLE.match(line)
                or TOTAL_ROW.match(line))


def ordinance_paragraphs(page: dict, clause: str) -> tuple[list[dict], str]:
    """One paragraph per table row; the clause number carries down until the next one."""
    out = []
    for table in page["tables"]:
        for row in table:
            cells = [(c or "").strip() for c in row]
            if cells and re.fullmatch(r"\d+(?:\.\d+)*\.?", cells[0]):
                clause = cells[0].rstrip(".")
            text = "\n".join(c for c in cells[1:] if c)
            if text:
                label = CLAUSE_START.match(text).group(1).replace(" ", "")
                out.append({"page": page["page"], "clause": clause + label, "text": text})
    return out, clause


def prose_paragraphs(page: dict, one_line_each: bool) -> list[dict]:
    out, current = [], []
    for line in page["text"].splitlines():
        if not line.strip() or is_table_row(line):
            current = []
            continue
        if one_line_each or not current or MARKER.match(line.strip()) or current[-1].rstrip().endswith((".", ":")):
            current = [line]
            out.append({"page": page["page"], "clause": None, "lines": current})
        else:
            current.append(line)
    for p in out:
        p["text"] = "\n".join(p.pop("lines"))
        marker = MARKER.match(p["text"].strip())
        p["clause"] = marker.group(0).strip() if marker and not p["text"].startswith("•") else None
    return out


def paragraphs(sid: str) -> list[dict]:
    """All paragraphs of a source, identical repeats merged (the docx repeats its tables)."""
    found, clause = [], ""
    for page in pages_of(sid):
        if sid == "btech_ordinance":
            paras, clause = ordinance_paragraphs(page, clause)
        elif DETAIL_PAGE.search(page["text"]):
            continue
        else:
            paras = prose_paragraphs(page, one_line_each=(sid == "cbe_btech"))
        found += paras
    merged: dict = {}
    for p in found:
        key = " ".join(p["text"].split())
        if key in merged:
            merged[key]["also_pages"].append(p["page"])
        else:
            merged[key] = {**p, "source_id": sid, "also_pages": []}
    return list(merged.values())


def nep_semester_scale() -> tuple[list[float], list[int]]:
    """Semester TOTAL rows and degree totals of the B. Tech. tables in the NEP-2020 curriculum."""
    totals, degree, level = [], [], None
    for page in pages_of("curriculum_nep2020"):
        for line in page["text"].splitlines():
            m = slots.DEPARTMENT_LINE.search(line)
            if m:
                level = m.group("level")
            elif level in (None, "B. Tech."):
                t, d = TOTAL_ROW.match(line.strip()), DEGREE_TOTAL.search(line)
                if t:
                    totals.append(float(t.group(1)))
                if d:
                    degree.append(int(d.group(1)))
    return totals, degree


def block(p: dict) -> list[str]:
    where = f"{p['source_id']} p{p['page']}" + (f" (also p{', p'.join(map(str, p['also_pages']))})" if p["also_pages"] else "")
    clause = f", clause {p['clause']}" if p["clause"] else ", no clause number"
    return [f"**{where}{clause}**", "", "```", p["text"], "```", ""]


def main() -> int:
    paras = [p for sid in SOURCES for p in paragraphs(sid)]
    totals, degree = nep_semester_scale()
    low, high = min(totals), max(totals)
    out = ["# Rule candidates (generated by ingest/rule_candidates.py)", "",
           "Plain keyword/regex search. Paragraphs are verbatim from the stored extracted text. "
           "Nothing here is chosen or summarised.", "",
           f"Sources searched: {', '.join(SOURCES)}.", "",
           f"NEP-2020 curriculum scale for comparison (B. Tech. tables): semester totals {low:g}-{high:g} credits "
           f"({len(totals)} TOTAL rows); degree totals stated: {sorted(set(degree))}.", ""]

    scale_flags = []
    for topic, patterns in TOPICS.items():
        hits = [p for p in paras if any(re.search(rx, p["text"], re.I) for rx in patterns)]
        out += [f"## {topic} ({len(hits)} paragraphs)", ""]
        per_source = {sid: sum(p["source_id"] == sid for p in hits) for sid in SOURCES}
        out += ["Hits per source: " + ", ".join(f"{sid} {n}" for sid, n in per_source.items()), ""]
        if not hits:
            out += ["No clause found in any searched document.", ""]
        for p in hits:
            out += block(p)
            if topic.startswith("1."):
                numbers = [float(n) for n in CREDIT_NUMBER.findall(p["text"])]
                if any(n > high for n in numbers) and re.search(r"semester", p["text"], re.I):
                    scale_flags.append((p, numbers))

    out += ["## Sub-questions: is there any paragraph that answers it?", ""]
    for name, (a, b) in SUB_CHECKS.items():
        hits = [p for p in paras if re.search(a, p["text"], re.I) and re.search(b, p["text"], re.I)]
        where = "; ".join(f"{p['source_id']} p{p['page']}" for p in hits) or "NONE in any searched document"
        out.append(f"- {name}: {len(hits)} paragraph(s): {where}")
    out.append("")

    out += ["## Flag: per-semester credit numbers above the NEP-2020 scale", "",
            f"A paragraph about semesters that names a credit number above the largest NEP-2020 B. Tech. "
            f"semester total ({high:g}).", ""]
    for p, numbers in scale_flags:
        out += [f"- {p['source_id']} p{p['page']} clause {p['clause'] or '-'}: credit numbers {numbers}"]
    out += ([] if scale_flags else ["None."]) + [""]

    out += ["## Flag: degree-level credit numbers that differ from the NEP-2020 degree total", "",
            f"A paragraph mentioning credits with a three-digit number other than the stated degree total(s) "
            f"{sorted(set(degree))}. Different programmes may have different totals: check the page.", ""]
    degree_flags = [(p, sorted({int(n) for n in re.findall(r"\b(\d{3})\b", re.sub(r"Page \d+ of \d+", "", p["text"]))} - set(degree)))
                    for p in paras if re.search(r"\bcredits?\b", p["text"], re.I)]
    degree_flags = [(p, n) for p, n in degree_flags if n]
    for p, numbers in degree_flags:
        out += [f"- {p['source_id']} p{p['page']} clause {p['clause'] or '-'}: {numbers}"]
    out += ([] if degree_flags else ["None."]) + [""]

    out += ["## Keyword search", ""]
    for word in KEYWORDS:
        rx = r"\b" + r"\s+".join(word.split()) + r"\w*"
        hits = [p for p in paras if re.search(rx, p["text"], re.I)]
        out += [f"### \"{word}\" ({len(hits)} paragraphs)", ""]
        out += ["No paragraph found in any searched document.", ""] if not hits else []
        for p in hits:
            out += block(p)

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(out), encoding="utf-8")
    print(f"{len(paras)} paragraphs searched -> {REPORT}")
    for line in out:
        if line.startswith(("## ", "### ", "- ", "Hits per", "NEP-2020")):
            print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
