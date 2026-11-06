"""Summarise the LLM call log: calls, cache hits, failures and average tokens per call type.

Run from the repo root:
    python3 -I scripts/token_summary.py                    # reads data/logs/llm_calls.jsonl
    python3 -I scripts/token_summary.py path/to/log.jsonl

A call type is (prompt_version, purpose); purpose is "first", "repair" or "cache".
Averages count only successful real calls: failed calls and cache hits have 0 tokens.
Only counts and call-type names are printed: never a key, a prompt or any other field of a line.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT_LOG = Path("data/logs/llm_calls.jsonl")


def summarise(lines: list[str]) -> tuple[dict, int]:
    """{(prompt_version, purpose): counters} and the number of lines that were not valid log entries."""
    groups, bad = {}, 0
    for line in lines:
        try:
            entry = json.loads(line)
            key = (str(entry["prompt_version"]), str(entry["purpose"]))
        except (ValueError, KeyError, TypeError):
            bad += 1
            continue
        g = groups.setdefault(key, {"calls": 0, "cache_hits": 0, "failures": 0, "ok_calls": 0,
                                    "prompt_tokens": 0, "completion_tokens": 0})
        g["calls"] += 1
        if entry.get("cached"):
            g["cache_hits"] += 1
        elif not entry.get("ok"):
            g["failures"] += 1
        else:
            g["ok_calls"] += 1
            g["prompt_tokens"] += int(entry.get("prompt_tokens") or 0)
            g["completion_tokens"] += int(entry.get("completion_tokens") or 0)
    return groups, bad


def table(groups: dict, bad: int) -> str:
    def avg(total, n):
        return f"{total / n:.1f}" if n else "-"
    rows = ["| prompt version | purpose | calls | cache hits | failures | avg prompt tokens | avg completion tokens |",
            "|---|---|---|---|---|---|---|"]
    for (version, purpose), g in sorted(groups.items()):
        rows.append(f"| {version} | {purpose} | {g['calls']} | {g['cache_hits']} | {g['failures']} "
                    f"| {avg(g['prompt_tokens'], g['ok_calls'])} | {avg(g['completion_tokens'], g['ok_calls'])} |")
    total = {k: sum(g[k] for g in groups.values()) for k in ("calls", "cache_hits", "failures", "ok_calls",
                                                              "prompt_tokens", "completion_tokens")}
    rows.append(f"| all | all | {total['calls']} | {total['cache_hits']} | {total['failures']} "
                f"| {avg(total['prompt_tokens'], total['ok_calls'])} | {avg(total['completion_tokens'], total['ok_calls'])} |")
    if bad:
        rows.append(f"\n{bad} line(s) were not valid log entries and were skipped.")
    return "\n".join(rows)


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOG
    if not path.exists():
        print(f"no log at {path}: no LLM calls have been made yet")
        return 0
    groups, bad = summarise(path.read_text(encoding="utf-8").splitlines())
    print(table(groups, bad))
    return 0


if __name__ == "__main__":
    sys.exit(main())
