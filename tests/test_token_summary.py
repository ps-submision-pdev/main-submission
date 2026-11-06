"""Tests for scripts/token_summary.py on a fake log."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import token_summary  # noqa: E402


def line(version, purpose, ok=True, cached=False, prompt=0, completion=0, **extra):
    return json.dumps({"time": "2026-11-06T10:00:00+00:00", "model": "m", "prompt_version": version,
                       "purpose": purpose, "cached": cached, "ok": ok, "error": None if ok else "RateLimitError",
                       "prompt_tokens": prompt, "completion_tokens": completion,
                       "total_tokens": prompt + completion, **extra})


FAKE_LOG = [
    line("rank-v1", "first", prompt=100, completion=20),
    line("rank-v1", "first", prompt=300, completion=40),
    line("rank-v1", "first", ok=False),                    # a rate-limited attempt: not in the averages
    line("rank-v1", "cache", cached=True),
    line("rank-v1", "repair", prompt=150, completion=10),
    # a line carrying things that must never be printed
    line("intake-v1", "first", prompt=50, completion=5, api_key="sk-SECRET-123",
         messages=[{"role": "user", "content": "FULL PROMPT TEXT"}]),
    "this is not json",
]


def test_counts_and_averages_per_call_type():
    groups, bad = token_summary.summarise(FAKE_LOG)
    first = groups[("rank-v1", "first")]
    assert (first["calls"], first["cache_hits"], first["failures"], first["ok_calls"]) == (3, 0, 1, 2)
    assert groups[("rank-v1", "cache")]["cache_hits"] == 1
    assert bad == 1
    text = token_summary.table(groups, bad)
    assert "| rank-v1 | first | 3 | 0 | 1 | 200.0 | 30.0 |" in text      # (100+300)/2, (20+40)/2
    assert "| all | all | 6 | 1 | 1 | 150.0 | 18.8 |" in text           # 600/4 prompt, 75/4 completion
    assert "1 line(s) were not valid" in text


def test_never_prints_keys_or_prompts(tmp_path):
    log = tmp_path / "calls.jsonl"
    log.write_text("\n".join(FAKE_LOG) + "\n", encoding="utf-8")
    out = subprocess.run([sys.executable, "-I", str(ROOT / "scripts/token_summary.py"), str(log)],
                         capture_output=True, text=True, check=True).stdout
    assert "rank-v1" in out and "intake-v1" in out
    assert "sk-SECRET-123" not in out and "FULL PROMPT TEXT" not in out and "not json" not in out


def test_missing_log_is_not_an_error(tmp_path):
    out = subprocess.run([sys.executable, "-I", str(ROOT / "scripts/token_summary.py"), str(tmp_path / "none.jsonl")],
                         capture_output=True, text=True, check=True).stdout
    assert "no LLM calls" in out
