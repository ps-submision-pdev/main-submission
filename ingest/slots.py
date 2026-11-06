"""Stage 4 - slots: for every table row, record which list it sits in. Deterministic, no LLM.

Run from the repo root (after parse):
    python3 -I ingest/slots.py

Reads  data/extracted/<id>.jsonl (the same sources as parse.py)
Writes data/db/list_entries.json   one entry per table row, in document order

Each entry is one row of one table, with:
  owner_department   the department in the nearest "Programme from the Department of X" line
                     above the row, as a fact {value, source_id, url, page, span}. null if the
                     document has no such line: we do not guess from the course code.
  level              the words before "Programme" on that line: "B. Tech.", "M. Tech.", "BS", ...
  slot_type          core | DE | IDE | HSS | minor | project | lab, read from the row's own label
                     or the heading of the list it sits in. null if neither names one.
  eligibility_note   the list heading, verbatim, when it says who may take the list
                     ("Available to students other than Dept. of CSE"), as a fact. null otherwise.
  slot_number        "I", "II", ... from the row's label or its list heading ("IDE - I (...)").
  is_placeholder     true for a slot written where a course should be: "CB32XX DE-I", and also
                     "CB4298 DE-VI", whose code looks real but whose title is only a slot label.
                     A placeholder has code null (its code moves to slot_code), so it never
                     counts as a real course. Placeholders are what the slot count is built from.
  semester           from the semester table the row sits in. IDE list rows get null even when
                     the label says "IDE-I Semester-4": that is the owner's semester, not the
                     student's. Use slot_semester() to place an IDE in the student's programme.
  in_scope           false for placeholders, rows with no slot type, and M. Tech., M. Sc. and
                     dual-degree tables. These stay in the database but are never candidates.
At the end the script prints the optional slots per semester for the Chemical B. Tech.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))  # python3 -I leaves the script's folder off sys.path
import parse  # noqa: E402  reuse its row pattern and helpers

# "(1.) M. Tech. Programme from the Department of Chemical and Biochemical Engineering"
DEPARTMENT_LINE = re.compile(r"^(?:\(\d+\.\)\s*)?(?P<level>.*?)\s*Programme from the Department of (?P<dept>.+?)\s*:?\s*$")
# An elective slot in a semester table: "6. CB32XX DE-I 3 0 0 3", "5. DE-I 3 0 0 3", "Minor - IV 3 0 2 4".
SLOT_ROW = re.compile(r"^(?:\d+\.\s+)?(?:(?P<slot_code>[A-Z]{2}(?:\d{2}[A-Za-z*]{2}|[Xx*]{2,4}))\s+)?"
                      r"(?P<label>(?:HSS|IDE|DE|Minor|Department(?:al)?\s+Elective|Elective)\b.*?)"
                      r"\s+(?P<l>\d+)\s+(?P<t>\d+)\s+(?P<p>\d+)\s+(?P<c>\d+(?:\.\d+)?)\s*$")
ELIGIBILITY = re.compile(r"available to|other than|not applicable|open to|for students of|for all approved", re.I)
COLUMN_HEADER = re.compile(r"Course Name|Subject Code|Sl\. No")
LIST_START = re.compile(r"^\(?List of\b")  # a list heading; if it names no slot type, it closes the current list
LAB_TITLE = re.compile(r"\bLab(?:oratory)?\b", re.I)
# A title that is only a slot label: "DE-VI", "IDE - II", "HSS Elective-I".
SLOT_LABEL = re.compile(r"(?:HSS\s+Elective|IDE|DE|Department(?:al)?\s+Elective|Elective|Minor)\s*[-–]?\s*[IVX]+")
SLOT_NUMBER = re.compile(r"\b(?:IDE|DE|Elective|Minor)\s*[-–]?\s*([IVX]+)\b")
REPORT = Path("reports/parse_quality.md")


def slot_type_of(text: str) -> str | None:
    """The slot type a row label or list heading names, or None. Case-sensitive on purpose:
    "minor losses" in a course description must not read as a Minor list."""
    if re.search(r"\bIDE\b|Interdisciplinary", text):  # first: "IDE ... other than Dept. of HSS" is an IDE list
        return "IDE"
    if re.search(r"\bHSS\b", text):
        return "HSS"
    if re.search(r"\bMinor\b", text):
        return "minor"
    if re.search(r"\bDE\b|Department(?:al)?\s+Electives?|^Elective\s*[-–]?\s*[IVX]+\b|Elective\s+List", text):
        return "DE"
    return None


def is_list_heading(line: str) -> bool:
    """A short line that names a slot type and is not a table row or column header."""
    return (len(line) < 160 and not line[-1].isdigit()
            and not COLUMN_HEADER.search(line) and slot_type_of(line) is not None)


def slot_number_of(*texts: str | None) -> str | None:
    """The first slot number ("I", "II", ...) found in the given texts, in order."""
    for text in texts:
        m = SLOT_NUMBER.search(text or "")
        if m:
            return m.group(1)
    return None


def walk(lines: list[tuple[int, str]], source: dict, entries: list) -> None:
    owner = level = eligibility = heading = None
    slot = semester = None  # slot type and semester of the table we are in
    carried = None          # slot number of a "DE-I 1. ... (CB3211)" group, carried to the rows below it
    joined = -1             # index of a line already joined onto the heading above it
    for i, (page, raw) in enumerate(lines):
        if i == joined:     # "of HSS)" was the second half of the heading before it
            continue
        line = parse.normalise(raw)
        m = DEPARTMENT_LINE.search(line)
        if m:  # a new programme starts: forget the previous tables
            dept, span = m.group("dept"), raw
            nxt = lines[i + 1][1].strip() if i + 1 < len(lines) else ""
            if re.fullmatch(r"[A-Za-z& ]{1,40}", nxt) and not parse.SEMESTER_HEADING.search(nxt):  # wrapped: "...of Civil and" / "Environmental Engineering"
                dept, span = f"{dept} {parse.normalise(lines[i + 1][1])}", f"{raw}\n{lines[i + 1][1]}"
                joined = i + 1
            owner, level = parse.fact(dept.rstrip(":"), source, page, span), m.group("level")
            eligibility = heading = slot = semester = carried = None
            continue

        row = parse.ROW.search(line)
        slot_row = None if row else SLOT_ROW.match(line)
        late = None if row or slot_row else parse.CODE_AFTER_TITLE.match(line)
        above = None if row or slot_row or late else parse.code_above_row(lines, i)
        if row or slot_row or late or above:
            span, values = raw, None
            if row or above:
                if row:
                    code, title, label = row.group("code"), row.group("title").strip(), row.group("prefix")
                else:  # "ME2205 Manufacturing Processes for" / "1. 3 0 0 3" / "Metallic Materials"
                    (code, title, values, span), label = above, ""
                kind = slot_type_of(title) or slot  # "IDE I: Construction ..." names its own slot
                if kind == "core" and parse.PROJECT_TITLE.search(title):
                    kind = "project"
                elif kind == "core" and LAB_TITLE.search(title):
                    kind = "lab"
            elif slot_row:
                code, title, label = slot_row.group("slot_code"), slot_row.group("label"), ""
                kind = slot_type_of(title)
            else:
                code, title, label = late.group("code"), late.group("title"), late.group("slot") or ""
                kind = slot
            number = slot_number_of(label, title, heading)
            if late:  # "DE-I 1. ..." starts group I; "2. ..." below it stays in group I
                carried = slot_number_of(label) or carried
                number = carried
            is_placeholder = bool(slot_row) or bool(SLOT_LABEL.fullmatch(title))
            row_semester = semester
            prefix = parse.ROW_SEMESTER.search(label)
            if prefix and kind != "IDE":  # "Sem III" in a Minor table; an IDE label's semester is the owner's
                row_semester = parse.semester_number(prefix.group(1))
            m = row or slot_row
            if m:
                values = parse.ltpc(*m.group("l", "t", "p", "c"))
            entry = {
                "source_id": source["id"], "page": page, "span": span,
                "code": None if is_placeholder else code, "slot_code": code if is_placeholder else None,
                "title": title, "ltpc": values, "semester": row_semester,
                "heading": heading, "slot_type": kind, "slot_number": number,
                "is_placeholder": is_placeholder,
                "owner_department": owner, "level": level, "eligibility_note": eligibility,
            }
            entry["in_scope"] = in_scope(entry)
            entries.append(entry)
            continue

        m = parse.SEMESTER_HEADING.search(line)
        if m:  # "Sl. No. | Subject Code | SEMESTER III | L | T | P | C": a core semester table
            heading, slot, semester = f"SEMESTER {m.group(1)}", "core", parse.semester_number(m.group(1))
            eligibility = carried = None
        elif is_list_heading(line):  # "IDE from CSE (Available to student other than Dept. of CSE)"
            span = raw
            if line.count("(") > line.count(")") and i + 1 < len(lines):  # heading wrapped onto the next line
                span = f"{raw}\n{lines[i + 1][1]}"
                line = f"{line} {parse.normalise(lines[i + 1][1])}"
                joined = i + 1
            note = parse.fact(line, source, page, span) if ELIGIBILITY.search(line) else None
            if note is None and slot_type_of(line) == slot:  # "HSS Elective-I" under "(List of HSS Electives for
                note = eligibility                           # all approved B. Tech. ...)": same list, same note
            heading, slot, semester, carried = line, slot_type_of(line), None, None
            eligibility = note
        elif LIST_START.match(line):  # "List of Elective for Semester VII and VIII: The students of B. S.
            heading, slot, semester, carried, eligibility = line, None, None, None, None  # Economics ...": a new, unnamed list


def keep_known_codes(entries: list) -> None:
    """Second pass, over all documents. "EC2102 Minor I" looks like a placeholder, but EC2102 has a
    real title elsewhere (Signals and Systems): it is a real course filling Minor slot I. Only a
    code that never appears with a real title (CB4298 "DE-VI") stays a placeholder."""
    real = {e["code"] for e in entries if e["code"]}
    for e in entries:
        if e["is_placeholder"] and e["slot_code"] in real:
            e["code"], e["slot_code"], e["is_placeholder"] = e["slot_code"], None, False
            e["in_scope"] = in_scope(e)


def place_department_electives(entries: list) -> None:
    """A DE list row gets the semester where its slot (DE-I, DE-II, ...) sits in the owning
    department's own semester table. Same rule as slot_semester(); stays null if unclear."""
    for e in entries:
        owner = e["owner_department"]
        if e["slot_type"] == "DE" and not e["is_placeholder"] and e["semester"] is None and owner:
            e["semester"] = slot_semester(entries, owner["value"], "DE", e["slot_number"])


def in_scope(entry: dict) -> bool:
    """Only B. Tech. rows can become candidates. A list whose heading says it is open to
    B. Tech. students (e.g. the institute's HSS list, printed under the BS programme) counts."""
    if entry["is_placeholder"] or entry["slot_type"] is None:
        return False
    note = entry["eligibility_note"]
    return entry["level"] in (None, "B. Tech.") or bool(note and re.search(r"B\.\s*Tech", note["value"]))  # "B. Tech" or "B.Tech"


def owned_by(entry: dict, department: str) -> bool:
    owner = entry["owner_department"]
    return entry["level"] == "B. Tech." and owner is not None and department in owner["value"]


def slot_semester(entries: list, department: str, slot_type: str, number: str | None) -> int | None:
    """Semester of a slot (e.g. IDE-II) in the department's own B. Tech. semester table.
    None if the number is unknown or the documents place that slot in different semesters."""
    semesters = {e["semester"] for e in entries
                 if e["is_placeholder"] and owned_by(e, department) and e["semester"]
                 and e["slot_type"] == slot_type and e["slot_number"] == number}
    return semesters.pop() if number and len(semesters) == 1 else None


def slot_table(entries: list, department: str) -> list[str]:
    """Optional slots (placeholder rows) per semester, per source, for one department's B. Tech."""
    labels = defaultdict(list)  # (source, semester) -> distinct (slot type, label)
    for e in entries:
        if e["is_placeholder"] and e["semester"] and owned_by(e, department):
            key = (e["source_id"], e["semester"])
            if (e["slot_type"], e["title"]) not in labels[key]:  # tables are repeated later in the docx
                labels[key].append((e["slot_type"], e["title"]))
    out = []
    for sid in sorted({s for s, _ in labels}):
        out += ["", f"{sid} (owner: {department})", "",
                "| sem | DE | IDE | HSS | other | slot labels as written |", "|---|---|---|---|---|---|"]
        for sem in range(1, 9):
            found = labels.get((sid, sem), [])
            count = {t: sum(1 for kind, _ in found if kind == t) for t in ("DE", "IDE", "HSS")}
            other = len(found) - sum(count.values())
            names = ", ".join(title for _, title in found) or "-"
            out.append(f"| {sem} | {count['DE']} | {count['IDE']} | {count['HSS']} | {other} | {names} |")
    return out


def report_lines(entries: list, department: str) -> list[str]:
    out = ["# Slots and owners (ingest/slots.py)", "",
           "| source | rows | placeholders | no owner | no slot type | in scope | with eligibility note |",
           "|---|---|---|---|---|---|---|"]
    for sid in sorted({e["source_id"] for e in entries}):
        mine = [e for e in entries if e["source_id"] == sid]
        out.append(f"| {sid} | {len(mine)} | {sum(e['is_placeholder'] for e in mine)} "
                   f"| {sum(e['owner_department'] is None for e in mine)} | {sum(e['slot_type'] is None for e in mine)} "
                   f"| {sum(e['in_scope'] for e in mine)} | {sum(e['eligibility_note'] is not None for e in mine)} |")
    notes = sorted({(n["source_id"], n["page"], n["value"]) for e in entries if (n := e["eligibility_note"])})
    out += ["", f"## Eligibility notes, verbatim ({len(notes)})", ""]
    out += [f"- {sid} p{page}: `{value}`" for sid, page, value in notes]
    odd = [e for e in entries if e["is_placeholder"] and e["slot_code"] and re.fullmatch(parse.CODE, e["slot_code"])]
    out += ["", f"## Placeholders written with a real-looking course code ({len(odd)})", ""]
    out += [f"- {e['source_id']} p{e['page']}: `{e['span'].strip()}`" for e in odd] or ["None."]
    out += ["", f"## Optional slots per semester: {department} B. Tech.", *slot_table(entries, department), ""]
    return out


def main() -> int:
    sources = yaml.safe_load(Path("ingest/sources.yaml").read_text(encoding="utf-8"))["sources"]
    entries: list = []
    for source in sorted(sources, key=lambda s: s["id"]):
        if source["kind"] not in parse.KINDS_TO_PARSE:
            continue
        path = Path("data/extracted") / f"{source['id']}.jsonl"
        if not path.exists():
            print(f"[FAIL] {source['id']}: {path} missing - run ingest/extract.py")
            return 1
        before = len(entries)
        walk(parse.read_lines(path), source, entries)
        print(f"[ok]   {source['id']}: {len(entries) - before} rows")

    keep_known_codes(entries)
    place_department_electives(entries)
    out = Path("data/db/list_entries.json")
    out.write_text(json.dumps(entries, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = report_lines(entries, "Chemical and Biochemical")
    parse.write_report_section(REPORT, "slots", lines)
    print(f"done: {len(entries)} entries -> {out}; summary in {REPORT}")
    print("\n".join(lines[lines.index(next(l for l in lines if l.startswith("## Optional"))):]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
