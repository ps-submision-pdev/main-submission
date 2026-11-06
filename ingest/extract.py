"""Stage 2 - extract: turn each downloaded document (PDF or .docx) into per-page text and tables.

Run from the repo root:
    python3 -I ingest/extract.py                                  # every document in data/raw/manifest.json
    python3 -I ingest/extract.py --only cse_btech --max-pages 5   # quick look while developing
    python3 -I ingest/extract.py --no-tables                      # faster, text only (PDF)

Output: data/extracted/<id>.jsonl, one JSON object per page:
    {"source_id", "source_sha256", "page", "text", "tables", "error"}
A file is only rebuilt when the document's sha256 changed (or with --force).
--max-pages writes data/extracted/<id>.preview.jsonl instead, so a partial run never overwrites a full one.
Pages with no text usually mean a scanned page that would need OCR; they are counted in the summary.

A .docx has no fixed pages. For a docx, "page" n is the n-th part between the explicit
page breaks the author inserted, which is close to, but not always, the printed page.
Table rows are also written into "text" as "cell | cell | ...", so later stages can use
the same line-based parsing for both formats.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pdfplumber

ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"  # Word XML namespace
MAX_XML_BYTES = 50 * 1024 * 1024  # a docx is a zip: refuse a document.xml that unpacks to more than this


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def already_done(out_file: Path, sha: str) -> bool:
    """True if out_file was built from a document with this sha256."""
    if not out_file.exists():
        return False
    with open(out_file, encoding="utf-8") as f:
        first_line = f.readline()
    try:
        return json.loads(first_line)["source_sha256"] == sha
    except (ValueError, KeyError):
        return False


def pdf_pages(path: Path, with_tables: bool):
    """Yield (text, tables, error) for each page of a PDF."""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text, tables, error = "", [], None
            try:
                text = page.extract_text() or ""
                if with_tables:
                    tables = page.extract_tables() or []
            except Exception as e:  # one bad page must not stop the whole run
                error = f"{type(e).__name__}: {e}"
            page.flush_cache()
            yield text, tables, error


def docx_text(el) -> str:
    """Text of a Word paragraph or table cell. Paragraphs inside a cell are joined with a space."""
    paragraphs = [el] if el.tag == W + "p" else el.iter(W + "p")
    parts = ["".join(t.text or "" for t in p.iter(W + "t")) for p in paragraphs]
    return " ".join(" ".join(parts).split())


def has_page_break(paragraph) -> bool:
    return any(br.get(W + "type") == "page" for br in paragraph.iter(W + "br"))


def docx_pages(path: Path):
    """Yield (text, tables, error) for each part of a .docx between explicit page breaks."""
    with zipfile.ZipFile(path) as z:
        if z.getinfo("word/document.xml").file_size > MAX_XML_BYTES:
            raise ValueError("word/document.xml is too large")
        xml = z.read("word/document.xml")
    if b"<!DOCTYPE" in xml or b"<!ENTITY" in xml:  # Word never needs these; they enable entity tricks
        raise ValueError("document.xml declares a DTD or entities; refusing to parse it")

    lines, tables = [], []
    for el in ET.fromstring(xml).find(W + "body"):
        if el.tag == W + "p":
            line = docx_text(el)
            if line:
                lines.append(line)
            if has_page_break(el):
                yield "\n".join(lines), tables, None
                lines, tables = [], []
        elif el.tag == W + "tbl":
            rows = [[docx_text(cell) for cell in row.findall(W + "tc")] for row in el.findall(W + "tr")]
            tables.append(rows)
            lines.extend(" | ".join(row) for row in rows if any(row))
    if lines or tables:
        yield "\n".join(lines), tables, None


def extract_one(sid: str, path: Path, fmt: str, sha: str, out_file: Path,
                max_pages: int | None, with_tables: bool) -> tuple[int, int, int]:
    """Write one JSON line per page. Returns (pages, pages without text, pages with errors)."""
    pages = pdf_pages(path, with_tables) if fmt == "pdf" else docx_pages(path)
    count = empty_pages = error_pages = 0
    tmp = out_file.with_suffix(".jsonl.part")
    with open(tmp, "w", encoding="utf-8") as f:
        for text, tables, error in pages:
            count += 1
            record = {"source_id": sid, "source_sha256": sha, "page": count,
                      "text": text, "tables": tables, "error": error}
            if error:
                error_pages += 1
            if not text.strip():
                empty_pages += 1
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            if count % 25 == 0:
                print(f"    ... {count} pages")
            if max_pages and count >= max_pages:
                break
    tmp.replace(out_file)
    return count, empty_pages, error_pages


def main() -> int:
    ap = argparse.ArgumentParser(description="PDF or .docx -> per-page text and tables")
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--out", default="data/extracted")
    ap.add_argument("--only", action="append", help="only this source id (repeatable)")
    ap.add_argument("--max-pages", type=int, help="first N pages only; writes a .preview.jsonl")
    ap.add_argument("--no-tables", action="store_true", help="skip PDF table detection (faster)")
    ap.add_argument("--force", action="store_true", help="rebuild even if up to date")
    args = ap.parse_args()

    raw, out = Path(args.raw), Path(args.out)
    manifest_path = raw / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"{manifest_path} not found - run ingest/fetch.py first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)

    ids = sorted(manifest)
    if args.only:
        unknown = set(args.only) - set(ids)
        if unknown:
            raise SystemExit(f"not in manifest: {', '.join(sorted(unknown))}")
        ids = [i for i in ids if i in args.only]

    failures = 0
    for sid in ids:
        if not ID_PATTERN.match(sid):
            print(f"[FAIL] {sid!r}: bad id in manifest")
            failures += 1
            continue
        fmt = manifest[sid].get("format", "pdf")  # entries fetched before docx support have no format
        if fmt not in ("pdf", "docx"):
            print(f"[FAIL] {sid}: unknown format {fmt!r} in manifest")
            failures += 1
            continue
        path = raw / f"{sid}.{fmt}"
        if not path.exists():
            print(f"[FAIL] {sid}: {path} is missing - run ingest/fetch.py")
            failures += 1
            continue
        sha = sha256_file(path)
        if sha != manifest[sid]["sha256"]:
            print(f"[FAIL] {sid}: file does not match manifest checksum (changed since fetch)")
            failures += 1
            continue

        suffix = ".preview.jsonl" if args.max_pages else ".jsonl"
        out_file = out / f"{sid}{suffix}"
        if not args.force and not args.max_pages and already_done(out_file, sha):
            print(f"[skip] {sid}: up to date")
            continue

        try:
            pages, empty, errors = extract_one(sid, path, fmt, sha, out_file,
                                               args.max_pages, not args.no_tables)
        except Exception as e:  # unreadable or corrupt document
            print(f"[FAIL] {sid}: {type(e).__name__}: {e}")
            out_file.with_suffix(".jsonl.part").unlink(missing_ok=True)
            failures += 1
            continue
        note = ""
        if pages and empty / pages > 0.5:
            note = "  <- mostly empty, may be scanned (needs OCR)"
        print(f"[ok]   {sid}: {pages} pages, {empty} without text, {errors} with errors -> {out_file}{note}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
