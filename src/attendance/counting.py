"""People counting from a class photo. Counting only: no faces are recognised or stored."""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass


class CountingError(Exception):
    """The photo could not be counted (service unreachable, unreadable answer, ...)."""


@dataclass
class CountResult:
    count: int
    method: str          # e.g. "ai-vision", "manual", "fake"
    confidence: str = ""  # "high" | "medium" | "low" when the counter reports it
    note: str = ""


def _http_error_detail(exc: "urllib.error.HTTPError") -> str:
    """Short, key-free description of an HTTP error from the AI service (status + the service's message)."""
    try:
        data = json.loads(exc.read().decode("utf-8", "replace"))
        message = data.get("error", {}).get("message", "") if isinstance(data, dict) else ""
    except (ValueError, AttributeError):
        message = ""
    return f"Error {exc.code}" + (f": {message[:160]}" if message else "")


def _transport_detail(exc: Exception) -> str:
    """Connection / timeout / unreadable-reply failures: say which kind (no secrets in these messages)."""
    return f"The counting service is unavailable right now ({type(exc).__name__}: {str(exc)[:120]})"


class PeopleCounter(ABC):
    """Port. The service depends on this interface, not on a specific AI vendor (Adapter pattern)."""

    @abstractmethod
    def count(self, image: bytes, mime: str) -> CountResult: ...


class FakeCounter(PeopleCounter):
    """Test double: returns a fixed number."""

    def __init__(self, value: int):
        self.value = value
        self.calls = 0

    def count(self, image: bytes, mime: str) -> CountResult:
        self.calls += 1
        return CountResult(self.value, "fake")


PROMPT = (
    "This is a photo of a classroom during a lecture. Count the people you can actually see "
    "(students and the lecturer, seated or standing). Count only people that are visible; do not guess "
    "about hidden or out-of-frame people, and do not try to identify anyone. "
    'Reply with JSON only: {"count": <integer>, "confidence": "high|medium|low", '
    '"notes": "<one short sentence, e.g. which rows were hard to count>"}'
)


def parse_count_reply(text: str) -> CountResult:
    """Pull the JSON object out of the model's reply, tolerating surrounding text or code fences."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise CountingError("The service returned an invalid answer")
    try:
        data = json.loads(match.group(0))
        value = int(data["count"])
    except (ValueError, KeyError, TypeError):
        raise CountingError("The service returned an invalid answer") from None
    if value < 0 or value > 2000:
        raise CountingError("Unreasonable number in the service answer")
    return CountResult(value, "ai-vision", str(data.get("confidence", "")), str(data.get("notes", ""))[:200])


class ClaudeVisionCounter(PeopleCounter):
    """Counts with a vision-capable LLM through the Anthropic Messages API (standard library only)."""

    URL = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model: str, timeout: float = 45.0):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def count(self, image: bytes, mime: str) -> CountResult:
        body = json.dumps({
            "model": self.model,
            "max_tokens": 300,
            "messages": [{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": mime,
                                             "data": base64.b64encode(image).decode("ascii")}},
                {"type": "text", "text": PROMPT},
            ]}],
        }).encode("utf-8")
        request = urllib.request.Request(self.URL, data=body, method="POST", headers={
            "content-type": "application/json", "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise CountingError(_http_error_detail(exc)) from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise CountingError(_transport_detail(exc)) from exc
        text = "".join(block.get("text", "") for block in payload.get("content", []) if block.get("type") == "text")
        return parse_count_reply(text)


class GeminiVisionCounter(PeopleCounter):
    """Counts with Google Gemini (has a free API tier) through its REST API, standard library only."""

    def __init__(self, api_key: str, model: str, timeout: float = 45.0):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @property
    def url(self) -> str:
        return f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"

    def count(self, image: bytes, mime: str) -> CountResult:
        body = json.dumps({"contents": [{"parts": [
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(image).decode("ascii")}},
            {"text": PROMPT},
        ]}], "generationConfig": {"temperature": 0}}).encode("utf-8")
        request = urllib.request.Request(self.url, data=body, method="POST", headers={
            "content-type": "application/json", "x-goog-api-key": self.api_key})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise CountingError(_http_error_detail(exc)) from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise CountingError(_transport_detail(exc)) from exc
        parts = (payload.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
        result = parse_count_reply("".join(part.get("text", "") for part in parts))
        result.method = "ai-vision (gemini)"
        return result
