"""Stage 1 - fetch: download the documents listed in ingest/sources.yaml into data/raw/.

Run from the repo root:
    python3 -I ingest/fetch.py                   # download what is missing
    python3 -I ingest/fetch.py --only cse_btech  # one source (repeatable)
    python3 -I ingest/fetch.py --refresh         # download everything again

Downloads are untrusted data, so:
  * only URLs written in sources.yaml are fetched, never URLs found inside a PDF
  * the file must start with the magic bytes of its format (PDF or docx) and stay under MAX_BYTES
  * robots.txt is honoured and requests are spaced out
  * a file is written under a temporary name first and moved into place when complete

Result: data/raw/<id>.<format> plus data/raw/manifest.json (url, format, fetched_at, sha256, bytes).
The manifest only changes when a file is new or its content changed, so git diffs stay clean.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import robotparser
from urllib.parse import urlsplit

import requests
import yaml

USER_AGENT = "mini-project-ingest/0.1 (student project; public documents only)"
MAX_BYTES = 100 * 1024 * 1024
PAUSE_SECONDS = 1.0
RETRIES = 3
TIMEOUT = 30
ID_PATTERN = re.compile(r"^[a-z0-9_]+$")
# format -> the bytes every file of that format starts with (a .docx is a zip archive)
MAGIC = {"pdf": b"%PDF-", "docx": b"PK\x03\x04"}


class PermanentError(Exception):
    """Retrying will not help: HTTP 4xx, wrong file type, too big."""


def load_sources(path: Path) -> list[dict]:
    sources = yaml.safe_load(path.read_text(encoding="utf-8"))["sources"]
    seen = set()
    for s in sources:
        # the id becomes a file name, so keep it boring
        if not ID_PATTERN.match(s["id"]):
            raise SystemExit(f"bad source id {s['id']!r}: use lowercase letters, digits, underscore")
        if s["id"] in seen:
            raise SystemExit(f"duplicate source id {s['id']!r}")
        seen.add(s["id"])
        if urlsplit(s["url"]).scheme not in ("http", "https"):
            raise SystemExit(f"{s['id']}: url must be http(s)")
        s.setdefault("format", "pdf")
        if s["format"] not in MAGIC:
            raise SystemExit(f"{s['id']}: format must be one of {', '.join(MAGIC)}")
    return sources


def allowed_by_robots(url: str, cache: dict) -> bool:
    """RFC 9309: robots.txt found -> obey it; 4xx -> allowed; unreachable or 5xx -> do not fetch."""
    parts = urlsplit(url)
    host = f"{parts.scheme}://{parts.netloc}"
    if host not in cache:
        rp = robotparser.RobotFileParser()
        try:
            r = requests.get(host + "/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT)
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
            elif 400 <= r.status_code < 500:
                rp.parse([])  # no rules
            else:
                rp.parse(["User-agent: *", "Disallow: /"])
        except requests.RequestException:
            rp.parse(["User-agent: *", "Disallow: /"])
        cache[host] = rp
    return cache[host].can_fetch(USER_AGENT, url)


def download(url: str, tmp: Path, fmt: str) -> tuple[str, int]:
    """Stream url into tmp. Returns (sha256, size in bytes)."""
    digest = hashlib.sha256()
    size = 0
    with requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, stream=True) as r:
        if r.status_code == 429 or r.status_code >= 500:
            raise requests.HTTPError(f"HTTP {r.status_code}")  # worth retrying
        if r.status_code >= 400:
            raise PermanentError(f"HTTP {r.status_code}")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=64 * 1024):
                if size == 0 and not chunk.startswith(MAGIC[fmt]):
                    raise PermanentError(f"response is not a {fmt} file (wrong first bytes)")
                size += len(chunk)
                if size > MAX_BYTES:
                    raise PermanentError(f"larger than {MAX_BYTES:,} bytes")
                digest.update(chunk)
                f.write(chunk)
    if size == 0:
        raise PermanentError("empty response")
    return digest.hexdigest(), size


def download_with_retries(url: str, tmp: Path, fmt: str) -> tuple[str, int]:
    for attempt in range(1, RETRIES + 1):
        try:
            return download(url, tmp, fmt)
        except requests.RequestException as e:  # network trouble, 429, 5xx
            if attempt == RETRIES:
                raise PermanentError(f"gave up after {RETRIES} attempts: {e}") from e
            wait = 2 ** attempt
            print(f"    retry {attempt}/{RETRIES - 1} in {wait}s ({e})")
            time.sleep(wait)
    raise AssertionError("unreachable")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def save_manifest(path: Path, manifest: dict) -> None:
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Download the documents listed in sources.yaml into data/raw/")
    ap.add_argument("--sources", default="ingest/sources.yaml")
    ap.add_argument("--out", default="data/raw")
    ap.add_argument("--only", action="append", help="fetch only this source id (repeatable)")
    ap.add_argument("--refresh", action="store_true", help="download again even if the file is already here")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest_path = out / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}

    sources = load_sources(Path(args.sources))
    if args.only:
        unknown = set(args.only) - {s["id"] for s in sources}
        if unknown:
            raise SystemExit(f"unknown source id(s): {', '.join(sorted(unknown))}")
        sources = [s for s in sources if s["id"] in args.only]

    robots_cache: dict = {}
    failures = 0
    did_network = False
    for s in sources:
        sid, url, fmt = s["id"], s["url"], s["format"]
        dest = out / f"{sid}.{fmt}"
        entry = manifest.get(sid)

        if (dest.exists() and entry and entry["url"] == url and not args.refresh
                and sha256_file(dest) == entry["sha256"]):
            print(f"[skip] {sid}: already downloaded, checksum matches")
            continue

        if not allowed_by_robots(url, robots_cache):
            print(f"[FAIL] {sid}: robots.txt does not allow fetching {url}")
            failures += 1
            continue

        if did_network:
            time.sleep(PAUSE_SECONDS)
        did_network = True

        tmp = out / f"{sid}.{fmt}.part"
        try:
            sha, size = download_with_retries(url, tmp, fmt)
            tmp.replace(dest)
        except PermanentError as e:
            print(f"[FAIL] {sid}: {e}")
            failures += 1
            continue
        finally:
            if tmp.exists():
                tmp.unlink()

        if entry and entry["sha256"] == sha and entry["url"] == url:
            print(f"[same] {sid}: downloaded again, content unchanged")
        else:
            changed = " (content changed)" if entry else ""
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            manifest[sid] = {"url": url, "format": fmt, "fetched_at": now, "sha256": sha, "bytes": size}
            print(f"[ok]   {sid}: {size:,} bytes{changed}")

    save_manifest(manifest_path, manifest)
    print(f"done: {len(sources) - failures}/{len(sources)} sources available in {out}/")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
