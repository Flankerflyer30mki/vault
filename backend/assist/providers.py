"""AI providers behind one interface (D-079). Switching providers changes this file and env vars, nothing else.

    provider.complete(messages) -> Completion(text, tokens_in, tokens_out, model)

messages are OpenAI-style [{"role": "system"|"user"|"assistant", "content": str}]. Real providers are plain HTTP (no SDK):
Groq exposes an OpenAI-compatible API. FakeProvider (tests) and ReplayProvider (evals in CI) never touch the network.
"""
import hashlib
import json
import logging
import time
from dataclasses import dataclass

import requests
from django.conf import settings

log = logging.getLogger(__name__)


@dataclass
class Completion:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    model: str = ""


class ProviderError(Exception):
    """The provider couldn't answer. `retryable` is True for rate limits, timeouts and 5xx."""

    def __init__(self, message, retryable=False):
        super().__init__(message)
        self.retryable = retryable


class GroqProvider:
    name = "groq"
    URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self, api_key, model, timeout_s=30, max_tokens=2000, reasoning_effort="", retries=2, max_wait_s=10.0,
                 sleep=time.sleep):
        self.api_key, self.model, self.timeout_s = api_key, model, timeout_s
        self.max_tokens, self.reasoning_effort, self.retries, self._sleep = max_tokens, reasoning_effort, retries, sleep
        self.max_wait_s = max_wait_s
        self.waited_s = 0.0  # time spent waiting out rate limits, so latency can be reported without it

    def sleep(self, s):
        self.waited_s += s
        self._sleep(s)

    def complete(self, messages):
        body = {"model": self.model, "messages": messages, "temperature": 0, "max_completion_tokens": self.max_tokens,
                "response_format": {"type": "json_object"}}
        if self.reasoning_effort:  # only reasoning models accept it (e.g. openai/gpt-oss-*)
            body["reasoning_effort"] = self.reasoning_effort
        for attempt in range(self.retries + 1):
            r = None
            try:
                r = requests.post(self.URL, json=body, timeout=self.timeout_s,
                                  headers={"Authorization": f"Bearer {self.api_key}"})
            except requests.RequestException as e:
                err = ProviderError(f"network error: {type(e).__name__}", retryable=True)
            else:
                if r.status_code == 200:
                    data = r.json()
                    usage = data.get("usage") or {}
                    return Completion(text=data["choices"][0]["message"].get("content") or "",
                                      tokens_in=usage.get("prompt_tokens", 0),
                                      tokens_out=usage.get("completion_tokens", 0), model=data.get("model", self.model))
                retryable = r.status_code == 429 or r.status_code >= 500
                # The body names the problem (e.g. "json_validate_failed"); never log the request, which has the prompt.
                detail = _error_detail(r)
                err = ProviderError(f"HTTP {r.status_code}: {detail}", retryable=retryable)
                if r.status_code == 400 and "json_validate_failed" in detail:
                    # The model produced text that isn't JSON. Hand it back as an answer so the repair loop handles it.
                    failed = (_json(r).get("error") or {}).get("failed_generation") or ""
                    return Completion(text=failed, model=self.model)
            if not err.retryable or attempt == self.retries:
                raise err
            wait = _retry_after(r, self.max_wait_s) if r is not None else 1.0
            log.warning("event=ai_retry provider=groq attempt=%s wait_s=%.1f reason=%s", attempt + 1, wait, err)
            self.sleep(wait)
        raise AssertionError("unreachable")


def _json(r):
    try:
        return r.json()
    except ValueError:
        return {}


def _error_detail(r):
    e = _json(r).get("error") or {}
    return f"{e.get('code') or e.get('type') or ''} {e.get('message', '')}".strip()[:200] or r.reason


def _retry_after(r, cap=10.0):
    try:
        return min(float(r.headers.get("retry-after", 1)), cap)
    except (TypeError, ValueError, AttributeError):
        return 1.0


class FakeProvider:
    """Tests: answers from a list (one per call) or a function of the messages. Records every call."""
    name = "fake"

    def __init__(self, answers, model="fake-model", tokens=(100, 20)):
        self.answers, self.model, self.tokens, self.calls = answers, model, tokens, []

    def complete(self, messages):
        self.calls.append([dict(m) for m in messages])
        if callable(self.answers):
            out = self.answers(messages)
        else:
            out = self.answers[min(len(self.calls), len(self.answers)) - 1]
        if isinstance(out, Exception):
            raise out
        text = out if isinstance(out, str) else json.dumps(out)
        return Completion(text=text, tokens_in=self.tokens[0], tokens_out=self.tokens[1], model=self.model)


def messages_key(messages):
    return hashlib.sha256(json.dumps(messages, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class RecordingProvider:
    """Evals: wraps a real provider and keeps every answer, keyed by the exact messages sent, with its latency (time
    spent waiting out rate limits is excluded and kept separately). With `reuse`, messages already recorded are answered
    from the earlier recording, so re-running after a small change only calls the model for what changed."""

    def __init__(self, inner, reuse=None):
        self.inner, self.name, self.model = inner, inner.name, inner.model
        self.records, self.reuse, self.reused, self.live_calls = {}, reuse or {}, 0, 0
        self.elapsed_ms = 0  # model time only; the eval runner reads it instead of the wall clock

    def complete(self, messages):
        key = messages_key(messages)
        if key in self.reuse:
            self.reused += 1
            rec = self.records[key] = self.reuse[key]
            self.elapsed_ms += rec["ms"]
            return Completion(text=rec["text"], tokens_in=rec["tokens_in"], tokens_out=rec["tokens_out"],
                              model=rec["model"])
        t0, waited0 = time.monotonic(), getattr(self.inner, "waited_s", 0.0)
        c = self.inner.complete(messages)
        waited = getattr(self.inner, "waited_s", 0.0) - waited0
        self.live_calls += 1
        ms = int((time.monotonic() - t0 - waited) * 1000)
        self.elapsed_ms += ms
        self.records[key] = {"text": c.text, "tokens_in": c.tokens_in, "tokens_out": c.tokens_out, "model": c.model,
                             "ms": ms, "waited_ms": int(waited * 1000)}
        return c


class ReplayProvider:
    """Evals in CI: answers from a recording. A message that wasn't recorded (the prompt changed) is an error, so a
    prompt change can't pass CI without a new live run."""
    name = "replay"

    def __init__(self, records, model):
        self.records, self.model, self.elapsed_ms = records, model, 0

    def complete(self, messages):
        rec = self.records.get(messages_key(messages))
        if rec is None:
            raise ProviderError("no recorded answer for these messages (prompt changed? record a new live run)")
        self.elapsed_ms += rec["ms"]  # replays report the latency measured when recording
        return Completion(text=rec["text"], tokens_in=rec["tokens_in"], tokens_out=rec["tokens_out"],
                          model=rec["model"])


def get_provider(max_tokens=None, reasoning_effort=None):
    """The configured provider, or None when AI is off (no provider or no key). Callers with bigger answers (the
    research agent) pass their own output limit and reasoning effort."""
    cfg = settings.AI
    if cfg["PROVIDER"] == "groq" and cfg["GROQ_API_KEY"]:
        return GroqProvider(cfg["GROQ_API_KEY"], cfg["MODEL"], timeout_s=cfg["TIMEOUT_S"],
                            max_tokens=max_tokens or cfg["MAX_OUTPUT_TOKENS"],
                            reasoning_effort=cfg["REASONING_EFFORT"] if reasoning_effort is None else reasoning_effort)
    return None


def enabled():
    cfg = settings.AI
    return cfg["PROVIDER"] == "groq" and bool(cfg["GROQ_API_KEY"])
