"""Stage 3 - parse: turn extracted pages into course records. Deterministic, no LLM.

Run from the repo root (after fetch and extract):
    python3 -I ingest/parse.py

Reads  data/extracted/<id>.jsonl for every source of kind syllabus or curriculum in sources.yaml.
Writes data/db/courses.json        one record per course code
       reports/parse_quality.md    counts and everything that looks wrong; nothing is fixed

Two passes over each source:
  1. table rows      "1. CB2101 Introduction to Chemical Engineering 2 0 0 2"
                     -> title, L-T-P-C, and where it is offered (semester or elective group)
  2. detail blocks   "Course Number CB3204", "Course Title ...", "Pre-requisite ...", ...
                     -> title, L-T-P-C, prerequisite text, description, content, outcomes

A docx table row arrives as "1. | CB2101 | Title | 2 | 0 | 0 | 2". Replacing " | " with a
space makes it look like a PDF row, so one set of patterns handles both formats.

Every value is stored as a fact: {value, source_id, url, page, span}. "span" is the raw
line(s) exactly as they appear in the extracted page text. Sources are never merged into
one value: if two documents disagree, the record keeps both facts and the report lists it.
Prerequisites are kept as the raw text from the document; mapping them to course ids is
a later step.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

KINDS_TO_PARSE = ("syllabus", "curriculum")

CODE = r"[A-Z]{2}\d{4}"
# A table row: optional prefix ("1.", "IDE-I Semester-4", "Minor-3"), a code, an optional
# second code after "/", a title (may be empty when the PDF wrapped it), then L T P C.
ROW = re.compile(rf"(?P<prefix>.*?)\b(?P<code>{CODE})(?:\s*/\s*(?P<alt>{CODE}))?(?:\s*[-–]\s*|\s+)"
                 r"(?P<title>.*?)\s*(?P<l>\d+)\s+(?P<t>\d+)\s+(?P<p>\d+)\s+(?P<c>\d+(?:\.\d+)?)\s*$")
# Elective slots written in place of a code: CS32XX, EE41xx, HS21**, HSXXXX, XX22PQ.
PLACEHOLDER = re.compile(r"\b[A-Z]{2}(?:\d{2}[A-Za-z*]{2}|[Xx*]{2,4})|^\d+\.\s+(?:DE|IDE|HSS|Minor)\b", re.I)
# A row-shaped line with no course code, e.g. "3. Heat Transfer 3 0 3 4.5" (code cell empty).
ROW_WITHOUT_CODE = re.compile(r"^\d+\.\s+(?P<title>[A-Za-z].*?)\s+\d+\s+\d+\s+\d+\s+\d+(?:\.\d+)?\s*$")
# Slot labels some tables put in front of the title: "Core I", "Minor II:", "IDE III:".
TITLE_PREFIX = re.compile(r"^(?:Core|Minor|IDE)\s*[-–]?\s*[IVX]+\s*:?\s+", re.I)
# Internships and projects carry credits by their own convention, not L + T + P/2.
PROJECT_TITLE = re.compile(r"Project|Internship|Seminar|Thesis|Dissertation", re.I)
# A list row with the code AFTER the title and no credits (Senate document's DE lists):
# "DE-I 1. Catalysis Science and Engineering (CB3211)", then "2. Biopharmaceutical ... (CB3212)".
CODE_AFTER_TITLE = re.compile(rf"^(?P<slot>(?:DE|IDE)\s*[-–]\s*[IVX]+\s+)?\d+\.\s+(?P<title>[A-Za-z].*?)\s*\((?P<code>{CODE})\)\s*$")
# Code above the row (curriculum p48): "ME2205 Manufacturing Processes for" / "1. 3 0 0 3" / "Metallic Materials".
CODE_ABOVE = re.compile(rf"^(?P<code>{CODE})\s+(?P<title>[A-Za-z].*)$")
CREDITS_ONLY = re.compile(r"^\d+\.\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+(?:\.\d+)?)\s*$")
TITLE_END = re.compile(r"[A-Za-z][A-Za-z ,&()\-–]{0,58}")  # plain words only: no digits, so not a footer or a row
SEMESTER_HEADING = re.compile(r"\bSEMESTER\s+([IVX]+)\b")
GROUP_HEADING = re.compile(r"^(Department Elective\s*[-–]\s*[IVX]+|IDE\b.*|Minor\b.*|.*\bMinor in\b.*"
                           r"|.*\bInterdisciplinary Electives?\b.*|.*\bELECTIVE GROUPS\b.*)$", re.I)
ROW_SEMESTER = re.compile(r"\bSem(?:ester)?[-\s]*([IVX]+|\d)\b", re.I)
CREDITS = re.compile(r"(\d+)\s*[-–]\s*(\d+)\s*[-–]\s*(\d+)\s*[-–]\s*(\d+(?:\.\d+)?)")

# Labels of a course detail block, in the spellings found in the real documents.
LABELS = [
    ("course_number", r"Course\s+Number"),
    ("credits", r"(?:Course\s+Credit(?:\s*\(L-T-P-C\))?|L-T-P-C)"),
    ("title", r"Course\s+Title"),
    ("prerequisite", r"Pre-?\s?requisites?\s*:?"),
    ("learning_mode", r"Learning\s+Mode"),
    ("objectives", r"Learning\s+Objectives?"),
    ("description", r"Course\s+Description"),
    ("content", r"Course\s+(?:Content|Outline)"),
    ("outcomes", r"Learning\s+Outcomes?"),
    ("assessment", r"Assessment\s+Method"),
    ("offered_term", r"Semester"),  # "Semester | Spring"; "SEMESTER III" table headings are handled before labels
    ("_end", r"(?:Text\s*Books?|Reference\s*Books?|References|Suggested\s+Readings?)"),
]
LABEL_PATTERNS = [(name, re.compile(rf"^{pattern}\b\s*(?P<rest>.*)$", re.I)) for name, pattern in LABELS]
DETAIL_FIELDS = [name for name, _ in LABELS if name not in ("course_number", "_end")]

ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6, "VII": 7, "VIII": 8}


def normalise(line: str) -> str:
    """Make a docx row look like a PDF row: drop the cell separators, squeeze spaces."""
    return " ".join(line.replace("|", " ").split())


def semester_number(token: str) -> int | None:
    return int(token) if token.isdigit() else ROMAN.get(token.upper())


def read_lines(path: Path) -> list[tuple[int, str]]:
    """All lines of an extracted source as (page, raw line), in order."""
    lines = []
    with open(path, encoding="utf-8") as f:
        for row in f:
            page = json.loads(row)
            lines.extend((page["page"], line) for line in page["text"].splitlines() if line.strip())
    return lines


def fact(value, source: dict, page: int, span: str) -> dict:
    return {"value": value, "source_id": source["id"], "url": source["url"], "page": page, "span": span}


def ltpc(l: str, t: str, p: str, c: str) -> dict:
    return {"l": int(l), "t": int(t), "p": int(p), "c": float(c)}


# ---------- pass 1: table rows ----------

def code_above_row(lines: list[tuple[int, str]], i: int) -> tuple[str, str, dict, str] | None:
    """Line i is only "1. 3 0 0 3" and line i-1 is "ME2205 Manufacturing Processes for": one row whose
    code and title start sit above the credits. The line below is the end of the title only if it
    is plain words and not a heading. Returns (code, title, ltpc, span) or None."""
    credits = CREDITS_ONLY.match(normalise(lines[i][1]))
    above = CODE_ABOVE.match(normalise(lines[i - 1][1])) if i > 0 else None
    if not (credits and above):
        return None
    title, span = above.group("title"), f"{lines[i - 1][1]}\n{lines[i][1]}"
    below = normalise(lines[i + 1][1]) if i + 1 < len(lines) else ""
    if TITLE_END.fullmatch(below) and not GROUP_HEADING.match(below) and not SEMESTER_HEADING.search(below):
        title, span = f"{title} {below}", f"{span}\n{lines[i + 1][1]}"
    return above.group("code"), title, ltpc(*credits.groups()), span


def parse_rows(lines: list[tuple[int, str]], source: dict, found: list, problems: list) -> None:
    heading, heading_semester = None, None
    for i, (page, raw) in enumerate(lines):
        line = normalise(raw)
        row = ROW.search(line)
        late = None if row else CODE_AFTER_TITLE.match(line)
        if late:  # the slot, owner and semester of these rows are read by slots.py
            found.append({"code": late.group("code"), "alias": None, "page": page, "span": raw,
                          "title": late.group("title"), "ltpc": None,
                          "offering": {"heading": None, "semester": None}})
            continue
        above = None if row else code_above_row(lines, i)
        if above:
            code, title, values, span = above
            found.append({"code": code, "alias": None, "page": page, "span": span, "title": title,
                          "ltpc": values, "offering": {"heading": heading, "semester": heading_semester}})
            continue
        if not row:
            m = SEMESTER_HEADING.search(line)
            if m:
                heading, heading_semester = f"SEMESTER {m.group(1)}", semester_number(m.group(1))
            elif len(line) < 120 and GROUP_HEADING.match(line):
                heading, heading_semester = line, None
            elif ROW_WITHOUT_CODE.match(line) and not PLACEHOLDER.search(line):
                problems.append(f"{source['id']} p{page}: table row without a course code: `{raw.strip()}`")
            continue

        title, span = row.group("title").strip(), raw
        if not title and 0 < i < len(lines) - 1:  # PDF wrapped the title above and below the row
            title = f"{normalise(lines[i - 1][1])} {normalise(lines[i + 1][1])}"
            span = "\n".join([lines[i - 1][1], raw, lines[i + 1][1]])
        title = TITLE_PREFIX.sub("", title)
        m = ROW_SEMESTER.search(row.group("prefix"))
        semester = semester_number(m.group(1)) if m else heading_semester
        found.append({
            "code": row.group("code"), "alias": row.group("alt"), "page": page, "span": span,
            "title": title, "ltpc": ltpc(*row.group("l", "t", "p", "c")),
            "offering": {"heading": heading, "semester": semester},
        })


# ---------- pass 2: course detail blocks ----------

def match_label(line: str) -> tuple[str | None, str]:
    for name, pattern in LABEL_PATTERNS:
        m = pattern.match(line)
        if m:
            return name, m.group("rest").strip()
    return None, ""


def parse_blocks(lines: list[tuple[int, str]], source: dict, found: list, problems: list) -> None:
    block, field = None, None
    for page, raw in lines:
        line = normalise(raw)
        if SEMESTER_HEADING.search(line):  # a semester table ends any open block
            block, field = None, None
            continue
        name, rest = match_label(line)
        if name == "course_number":
            codes = re.findall(CODE, rest)
            if not codes:  # e.g. "Course Number | Engineering Mechanics": the title under the wrong label
                problems.append(f"{source['id']} p{page}: 'Course Number' line without a course code: `{raw.strip()}`")
                continue
            block = {"code": codes[0], "alias": codes[1] if len(codes) > 1 else None,
                     "page": page, "span": raw, "fields": {}}
            found.append(block)
            field = None
        elif block is None:
            continue
        elif name == "_end":
            field = None
        elif name:
            field = name
            block["fields"].setdefault(field, {"text": rest, "page": page, "span": raw})
        elif field and line != "(L-T-P-C)":
            entry = block["fields"][field]
            entry["text"] = f"{entry['text']} {line}".strip()


# ---------- merge into one record per course ----------

def empty_record(code: str) -> dict:
    record = {"id": code, "aliases": [], "title": [], "ltpc": [], "offerings": []}
    record.update({name: [] for name in DETAIL_FIELDS if name not in ("title", "credits")})
    return record


def add_alias(record: dict, alias: str | None) -> None:
    if alias and alias != record["id"] and alias not in record["aliases"]:
        record["aliases"].append(alias)


def merge(courses: dict, rows: list, blocks: list, source: dict, problems: list) -> None:
    for r in rows:
        rec = courses.setdefault(r["code"], empty_record(r["code"]))
        add_alias(rec, r["alias"])
        if r["title"]:
            rec["title"].append(fact(r["title"], source, r["page"], r["span"]))
        if r["ltpc"]:  # rows with the code after the title carry no L-T-P-C
            rec["ltpc"].append(fact(r["ltpc"], source, r["page"], r["span"]))
        rec["offerings"].append(fact(r["offering"], source, r["page"], r["span"]))

    for b in blocks:
        rec = courses.setdefault(b["code"], empty_record(b["code"]))
        add_alias(rec, b["alias"])
        rec.setdefault("detail_pages", []).append(fact(b["code"], source, b["page"], b["span"]))
        for name, entry in sorted(b["fields"].items()):
            if name == "credits":
                m = CREDITS.search(entry["text"])
                if m:
                    rec["ltpc"].append(fact(ltpc(*m.groups()), source, entry["page"], entry["span"]))
                else:
                    problems.append(f"{source['id']} p{entry['page']}: {b['code']} credits not readable: "
                                    f"`{entry['text'][:80]}`")
            else:
                rec[name].append(fact(entry["text"], source, entry["page"], entry["span"]))
        for name in ("title", "credits", "description"):
            if name not in b["fields"]:
                problems.append(f"{source['id']} p{b['page']}: {b['code']} detail block has no {name}")


# ---------- quality report ----------

REPORT_STAGES = ("parse", "slots", "resolve", "check")  # order of the sections in the shared report


def write_report_section(path: Path, stage: str, lines: list[str]) -> None:
    """Replace one stage's section of the shared report and keep the other stages' sections."""
    sections = {}
    if path.exists():
        for chunk in path.read_text(encoding="utf-8").split("<!-- stage: ")[1:]:
            name, body = chunk.split(" -->\n", 1)
            sections[name] = body
    sections[stage] = "\n".join(lines) + "\n"
    order = sorted(sections, key=lambda s: REPORT_STAGES.index(s) if s in REPORT_STAGES else len(REPORT_STAGES))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"<!-- stage: {s} -->\n{sections[s]}" for s in order), encoding="utf-8")


def distinct(facts: list, key=lambda v: v) -> list:
    seen = []
    for f in facts:
        if key(f["value"]) not in seen:
            seen.append(key(f["value"]))
    return seen


def write_report(path: Path, courses: dict, counts: dict, problems: list) -> int:
    out = ["# Parse quality report", "", "Generated by `ingest/parse.py`. Nothing here was fixed automatically.", "",
           "| source | table rows | detail blocks |", "|---|---|---|"]
    out += [f"| {sid} | {n_rows} | {n_blocks} |" for sid, (n_rows, n_blocks) in sorted(counts.items())]
    out += ["", f"Courses: {len(courses)}", ""]

    sections = {"Credits not equal to L + T + P/2": [], "Projects and internships (own credit rule)": [],
                "Sources disagree on L-T-P-C": [],
                "Sources disagree on the title": [], "In a table but no detail block": [],
                "Problems while reading": sorted(set(problems))}
    for code, rec in sorted(courses.items()):
        for f in rec["ltpc"]:
            v = f["value"]
            if abs(v["l"] + v["t"] + v["p"] / 2 - v["c"]) > 1e-9:
                is_project = any(PROJECT_TITLE.search(t["value"]) for t in rec["title"])
                key = "Projects and internships (own credit rule)" if is_project else "Credits not equal to L + T + P/2"
                sections[key].append(f"{code}: {v['l']}-{v['t']}-{v['p']}-{v['c']} ({f['source_id']} p{f['page']})")
        values = distinct(rec["ltpc"], key=lambda v: (v["l"], v["t"], v["p"], v["c"]))
        if len(values) > 1:
            sections["Sources disagree on L-T-P-C"].append(f"{code}: {values}")
        titles = distinct(rec["title"], key=lambda v: " ".join(re.sub(r"[*–-]", " ", v.lower()).split()))
        if len(titles) > 1:
            sections["Sources disagree on the title"].append(f"{code}: {titles}")
        if "detail_pages" not in rec:
            sections["In a table but no detail block"].append(code)

    issues = 0
    for heading, items in sections.items():
        out += [f"## {heading} ({len(items)})", ""]
        out += [f"- {item}" for item in items] or ["None."]
        out.append("")
        if heading not in ("In a table but no detail block", "Projects and internships (own credit rule)"):
            issues += len(items)
    write_report_section(path, "parse", out)
    return issues


def main() -> int:
    sources = yaml.safe_load(Path("ingest/sources.yaml").read_text(encoding="utf-8"))["sources"]
    courses: dict = {}
    counts: dict = {}
    problems: list = []
    for source in sorted(sources, key=lambda s: s["id"]):
        if source["kind"] not in KINDS_TO_PARSE:
            continue
        path = Path("data/extracted") / f"{source['id']}.jsonl"
        if not path.exists():
            print(f"[FAIL] {source['id']}: {path} missing - run ingest/extract.py")
            return 1
        lines = read_lines(path)
        rows, blocks = [], []
        parse_rows(lines, source, rows, problems)
        parse_blocks(lines, source, blocks, problems)
        merge(courses, rows, blocks, source, problems)
        counts[source["id"]] = (len(rows), len(blocks))
        print(f"[ok]   {source['id']}: {len(rows)} table rows, {len(blocks)} detail blocks")

    out = Path("data/db/courses.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(courses, indent=1, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    issues = write_report(Path("reports/parse_quality.md"), courses, counts, problems)
    print(f"done: {len(courses)} courses -> {out}; {issues} issues listed in reports/parse_quality.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
