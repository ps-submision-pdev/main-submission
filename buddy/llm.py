"""The only place the buddy calls a language model. Every LLM call goes through LiteLLM, here.

Settings come from the environment (never from this file, never printed or logged):
    LLM_MODEL      e.g. "openrouter/<provider>/<model>"
    LLM_API_KEY
    LLM_API_BASE   optional
This module does not read .env; the entry script loads it before creating an LLMClient.

ask_json(messages, schema, prompt_version) returns
    {"ok": True, "data": {...}, "cached": bool, "usage": {...}}   or   {"ok": False, "error": "...", "usage": {...}}
usage counts this one question: attempts (calls made, failed ones included) and token totals.
and never raises, so a bad model reply cannot crash the buddy. Steps:
    1. cache: the same model, prompt version and messages give the saved answer, with no call
    2. call: temperature 0, timeout; rate limits, timeouts, connection and server errors are
       retried with backoff 1s, 2s, 4s (capped at 8s, at most max_retries retries)
    3. parse: the reply must be a JSON object with every schema key of the right type
    4. repair: if not, one more call shows the model its reply and what was wrong
    5. save the good answer to the cache
Every call, including failed calls and cache hits, adds one line with token counts to the log file.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import litellm

RETRYABLE = (litellm.RateLimitError, litellm.Timeout, litellm.APIConnectionError,
             litellm.InternalServerError, litellm.ServiceUnavailableError)
FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.S)  # free models often wrap JSON in ```json ... ```


def parse_json(text: str | None, schema: dict) -> tuple[dict | None, str | None]:
    """(data, None) if text is a JSON object whose schema keys all have the right type, else (None, reason).
    schema maps key -> Python type, e.g. {"codes": list, "reason": str}."""
    text = (text or "").strip()
    fenced = FENCE.match(text)
    if fenced:
        text = fenced.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return None, f"not valid JSON ({e.msg})"
    if not isinstance(data, dict):
        return None, "not a JSON object"
    for key, kind in schema.items():
        if key not in data:
            return None, f"missing key '{key}'"
        if not isinstance(data[key], kind):
            return None, f"key '{key}' should be of type {kind.__name__}"
    return data, None


class LLMClient:
    def __init__(self, model=None, api_key=None, api_base=None, timeout=30, max_retries=3,
                 cache_dir="data/cache/llm", log_file="data/logs/llm_calls.jsonl",
                 completion=None, sleep=time.sleep):
        self.model = model or os.environ.get("LLM_MODEL")
        self.api_key = api_key or os.environ.get("LLM_API_KEY")
        self.api_base = api_base or os.environ.get("LLM_API_BASE")
        self.timeout, self.max_retries = timeout, max_retries
        self.cache_dir, self.log_file = Path(cache_dir), Path(log_file)
        self.completion = completion or litellm.completion  # tests pass a fake here
        self.sleep = sleep                                   # tests pass a fake here, so they do not wait
        self.usage = {"attempts": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def ask_json(self, messages: list, schema: dict, prompt_version: str) -> dict:
        self.usage = {"attempts": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        result = self.ask_json_once(messages, schema, prompt_version)
        return {**result, "usage": dict(self.usage)}

    def ask_json_once(self, messages: list, schema: dict, prompt_version: str) -> dict:
        if not self.model:
            return {"ok": False, "error": "LLM_MODEL is not set in the environment"}
        cache_file = self.cache_dir / f"{self.cache_key(messages, prompt_version)}.json"
        if cache_file.exists():
            self.log(prompt_version, "cache", None, ok=True, error=None, cached=True)
            return {"ok": True, "data": json.loads(cache_file.read_text(encoding="utf-8")), "cached": True}

        reply, error = self.call(messages, prompt_version, "first")
        if error:
            return {"ok": False, "error": error}
        data, problem = parse_json(reply, schema)
        if problem:  # one repair: show the model its own reply and what was wrong with it
            repair = messages + [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": f"Your reply was invalid: {problem}. Reply with only a JSON object "
                                            f"with these keys: {', '.join(schema)}."}]
            reply, error = self.call(repair, prompt_version, "repair")
            if error:
                return {"ok": False, "error": error}
            data, problem = parse_json(reply, schema)
            if problem:
                return {"ok": False, "error": f"model returned invalid JSON after one repair: {problem}"}

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        return {"ok": True, "data": data, "cached": False}

    def call(self, messages: list, prompt_version: str, purpose: str) -> tuple[str | None, str | None]:
        """(reply text, None) or (None, error). Retries only errors that waiting can fix."""
        for attempt in range(self.max_retries + 1):
            self.usage["attempts"] += 1
            try:
                response = self.completion(model=self.model, messages=messages, api_key=self.api_key,
                                           api_base=self.api_base, temperature=0, timeout=self.timeout)
            except RETRYABLE as e:
                self.log(prompt_version, purpose, None, ok=False, error=type(e).__name__)
                if attempt == self.max_retries:
                    return None, f"{type(e).__name__} after {attempt + 1} attempts: {e}"
                self.sleep(min(2 ** attempt, 8))
                continue
            except Exception as e:  # wrong key, bad request, unknown model: waiting will not help
                self.log(prompt_version, purpose, None, ok=False, error=type(e).__name__)
                return None, f"{type(e).__name__}: {e}"
            self.log(prompt_version, purpose, response.usage, ok=True, error=None)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                self.usage[key] += getattr(response.usage, key, 0) or 0
            return response.choices[0].message.content, None
        return None, "no attempt was made"  # only if max_retries < 0

    def cache_key(self, messages: list, prompt_version: str) -> str:
        key = {"model": self.model, "prompt_version": prompt_version, "messages": messages}
        return hashlib.sha256(json.dumps(key, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()

    def log(self, prompt_version, purpose, usage, ok, error, cached=False) -> None:
        """One JSON line per call. Never contains the API key or the messages."""
        entry = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": self.model,
                 "prompt_version": prompt_version, "purpose": purpose, "cached": cached, "ok": ok, "error": error,
                 "prompt_tokens": getattr(usage, "prompt_tokens", 0) or 0,
                 "completion_tokens": getattr(usage, "completion_tokens", 0) or 0,
                 "total_tokens": getattr(usage, "total_tokens", 0) or 0}
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
