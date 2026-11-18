"""Read handwritten or scanned homework with a vision model (Gemini or Claude), standard library only.

A scanned PDF or a photo has no text layer, so normal text extraction returns nothing. The file is sent to
the model, which returns the text it can read. Mistakes in the student's work are copied as written, not fixed.
"""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request

PROMPT = (
    "Transcribe everything written in this document, in reading order. The text may be handwritten, in Hebrew "
    "(right to left) with English terms and mathematics. Rules: copy exactly what is written, including "
    "mistakes; do not solve, correct or comment. Write formulas and matrices as plain text on one line, "
    "for example: det(A) = 2*(12-2) + 1*(1-0) = 21. Write [?] for anything you cannot read. "
    "Return only the transcription."
)


class HandwritingError(Exception):
    pass


class Transcriber:
    name = "none"

    def transcribe(self, data: bytes, mime: str) -> str:
        raise NotImplementedError


RETRY_CODES = (429, 500, 502, 503, 504)
RETRY_WAITS = (4, 10, 20)       # seconds; a busy model usually answers on the second or third try


def _call(request: urllib.request.Request, timeout: float, waits: tuple = RETRY_WAITS) -> dict:
    for attempt in range(len(waits) + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in RETRY_CODES and attempt < len(waits):
                time.sleep(waits[attempt])
                continue
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise HandwritingError(f"שירות הקריאה החזיר שגיאה {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise HandwritingError("לא הצלחתי להגיע לשירות הקריאה (זמן ההמתנה עבר או שאין חיבור)") from exc
    raise HandwritingError("שירות הקריאה לא זמין כרגע")


class GeminiTranscriber(Transcriber):
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout: float = 110.0):
        self.api_key, self.model, self.timeout = api_key, model, timeout

    def transcribe(self, data: bytes, mime: str) -> str:
        body = json.dumps({"contents": [{"parts": [
            {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode("ascii")}},
            {"text": PROMPT}]}], "generationConfig": {"temperature": 0}}).encode("utf-8")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        request = urllib.request.Request(url, data=body, method="POST", headers={
            "content-type": "application/json", "x-goog-api-key": self.api_key})
        payload = _call(request, self.timeout)
        parts = (payload.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
        return "".join(p.get("text", "") for p in parts).strip()


class ClaudeTranscriber(Transcriber):
    name = "claude"

    def __init__(self, api_key: str, model: str, timeout: float = 110.0):
        self.api_key, self.model, self.timeout = api_key, model, timeout

    def transcribe(self, data: bytes, mime: str) -> str:
        kind = "document" if mime == "application/pdf" else "image"
        block = {"type": kind, "source": {"type": "base64", "media_type": mime,
                                          "data": base64.b64encode(data).decode("ascii")}}
        body = json.dumps({"model": self.model, "max_tokens": 4000, "temperature": 0,
                           "messages": [{"role": "user", "content": [block, {"type": "text", "text": PROMPT}]}]}).encode()
        request = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST", headers={
            "content-type": "application/json", "x-api-key": self.api_key, "anthropic-version": "2023-06-01"})
        payload = _call(request, self.timeout)
        return "".join(b.get("text", "") for b in payload.get("content", []) if b.get("type") == "text").strip()


def build_transcriber(config) -> Transcriber | None:
    if config.GEMINI_API_KEY:
        return GeminiTranscriber(config.GEMINI_API_KEY, config.GEMINI_MODEL, config.COUNTER_TIMEOUT_SECONDS)
    if config.ANTHROPIC_API_KEY:
        return ClaudeTranscriber(config.ANTHROPIC_API_KEY, config.COUNTER_MODEL, config.COUNTER_TIMEOUT_SECONDS)
    return None
