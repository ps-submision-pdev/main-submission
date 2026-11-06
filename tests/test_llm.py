"""Tests for buddy/llm.py with a fake LiteLLM: no API key and no network needed."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import litellm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from buddy.llm import LLMClient  # noqa: E402

SCHEMA = {"codes": list, "reason": str}
MESSAGES = [{"role": "user", "content": "Pick course codes from: CB3204, MA2206."}]
GOOD = '{"codes": ["CB3204"], "reason": "AI/ML for Chemical Engineers matches the goal"}'


class FakeLiteLLM:
    """Plays a script: each call takes the next item. An exception is raised, a string is the reply."""

    def __init__(self, *script):
        self.script, self.calls = list(script), []

    def completion(self, **kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        usage = SimpleNamespace(prompt_tokens=50, completion_tokens=10, total_tokens=60)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=item))], usage=usage)


def rate_limit():
    return litellm.RateLimitError(message="429 slow down", llm_provider="openrouter", model="test-model")


def timeout():
    return litellm.Timeout(message="timed out", model="test-model", llm_provider="openrouter")


def client(fake, tmp_path, sleeps=None):
    return LLMClient(model="test-model", api_key="not-a-real-key", api_base=None,
                     cache_dir=tmp_path / "cache", log_file=tmp_path / "calls.jsonl",
                     completion=fake.completion, sleep=(sleeps.append if sleeps is not None else lambda s: None))


def test_rate_limit_then_success(tmp_path):
    fake, sleeps = FakeLiteLLM(rate_limit(), GOOD), []
    result = client(fake, tmp_path, sleeps).ask_json(MESSAGES, SCHEMA, prompt_version="v1")
    assert result["ok"] and result["data"]["codes"] == ["CB3204"]
    assert len(fake.calls) == 2 and sleeps == [1]           # waited once, 1 second
    assert fake.calls[0]["temperature"] == 0


def test_timeout_then_success(tmp_path):
    fake = FakeLiteLLM(timeout(), GOOD)
    result = client(fake, tmp_path).ask_json(MESSAGES, SCHEMA, prompt_version="v1")
    assert result["ok"] and len(fake.calls) == 2


def test_retries_exhausted_returns_an_error(tmp_path):
    fake, sleeps = FakeLiteLLM(rate_limit(), rate_limit(), rate_limit(), rate_limit()), []
    result = client(fake, tmp_path, sleeps).ask_json(MESSAGES, SCHEMA, prompt_version="v1")
    assert result["ok"] is False and "RateLimitError" in result["error"]
    assert len(fake.calls) == 4 and sleeps == [1, 2, 4]    # 1 call + 3 retries, backoff doubles


def test_broken_json_then_repaired(tmp_path):
    fake = FakeLiteLLM('{"codes": ["CB3204"], "reason": ', GOOD)
    result = client(fake, tmp_path).ask_json(MESSAGES, SCHEMA, prompt_version="v1")
    assert result["ok"] and result["data"]["reason"].startswith("AI/ML")
    repair = fake.calls[1]["messages"]
    assert repair[-2] == {"role": "assistant", "content": '{"codes": ["CB3204"], "reason": '}
    assert "codes" in repair[-1]["content"] and "reason" in repair[-1]["content"]


def test_broken_json_twice_returns_a_clear_error(tmp_path):
    fake = FakeLiteLLM("Sure! Here are the codes: CB3204", '{"codes": "CB3204"}')
    result = client(fake, tmp_path).ask_json(MESSAGES, SCHEMA, prompt_version="v1")
    assert result["ok"] is False
    assert "invalid JSON after one repair" in result["error"]
    assert len(fake.calls) == 2


def test_cache_hit_makes_no_second_call(tmp_path):
    fake = FakeLiteLLM(GOOD)
    llm = client(fake, tmp_path)
    first = llm.ask_json(MESSAGES, SCHEMA, prompt_version="v1")
    second = llm.ask_json(MESSAGES, SCHEMA, prompt_version="v1")
    assert len(fake.calls) == 1
    assert first["cached"] is False and second["cached"] is True and second["data"] == first["data"]


def test_new_prompt_version_is_not_a_cache_hit(tmp_path):
    fake = FakeLiteLLM(GOOD, GOOD)
    llm = client(fake, tmp_path)
    llm.ask_json(MESSAGES, SCHEMA, prompt_version="v1")
    llm.ask_json(MESSAGES, SCHEMA, prompt_version="v2")
    assert len(fake.calls) == 2


def test_token_log_line_is_written(tmp_path):
    fake = FakeLiteLLM(GOOD)
    client(fake, tmp_path).ask_json(MESSAGES, SCHEMA, prompt_version="v1")
    lines = (tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    assert (entry["prompt_tokens"], entry["completion_tokens"], entry["total_tokens"]) == (50, 10, 60)
    assert entry["model"] == "test-model" and entry["prompt_version"] == "v1" and entry["ok"] is True
    assert "not-a-real-key" not in lines[0]                 # the key is never logged


def test_missing_model_setting_is_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    llm = LLMClient(cache_dir=tmp_path / "cache", log_file=tmp_path / "calls.jsonl", completion=lambda **k: None)
    result = llm.ask_json(MESSAGES, SCHEMA, prompt_version="v1")
    assert result["ok"] is False and "LLM_MODEL" in result["error"]


def test_result_carries_the_usage_of_this_question(tmp_path):
    fake = FakeLiteLLM(rate_limit(), "not json", GOOD)       # 1 failed attempt, 1 bad reply, 1 repaired reply
    result = client(fake, tmp_path).ask_json(MESSAGES, SCHEMA, prompt_version="v1")
    assert result["ok"] and result["usage"] == {"attempts": 3, "prompt_tokens": 100, "completion_tokens": 20,
                                                "total_tokens": 120}
    again = client(fake, tmp_path).ask_json(MESSAGES, SCHEMA, prompt_version="v1")   # cache hit
    assert again["cached"] and again["usage"] == {"attempts": 0, "prompt_tokens": 0, "completion_tokens": 0,
                                                  "total_tokens": 0}
