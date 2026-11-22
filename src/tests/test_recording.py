"""Lecture recording: the browser sends audio parts, the server transcribes each one."""
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app  # noqa: E402
from attendance.handwriting import GeminiTranscriber, HandwritingError, Transcriber  # noqa: E402
from test_flow import TestConfig  # noqa: E402


class AudioReader(Transcriber):
    name = "audio-fake"

    def __init__(self, fail=False):
        self.fail, self.mimes = fail, []

    def transcribe_audio(self, data, mime):
        self.mimes.append((mime, len(data)))
        if self.fail:
            raise HandwritingError("quota")
        return "היום נדבר על Strategy"


def lecturer_with_lecture(reader):
    app = create_app(TestConfig)
    app.extensions["transcriber"] = reader
    client = app.test_client()
    assert client.get("/lecturer?key=test-key").status_code == 302
    sid = client.post("/api/session", json={"course": "Test"}).get_json()["session_id"]
    return app, client, sid


def part(data=b"RIFF....WAVE"):
    return {"audio": (io.BytesIO(data), "part.wav")}


def test_audio_part_is_transcribed_and_not_stored():
    reader = AudioReader()
    app, lecturer, sid = lecturer_with_lecture(reader)
    res = lecturer.post(f"/api/session/{sid}/recording-chunk", data=part(), content_type="multipart/form-data").get_json()
    assert res["ok"] and "Strategy" in res["text"] and reader.mimes == [("audio/wav", 12)]


def test_audio_part_needs_the_lecturer_and_a_file():
    app, lecturer, sid = lecturer_with_lecture(AudioReader())
    assert app.test_client().post(f"/api/session/{sid}/recording-chunk", data=part(),
                                  content_type="multipart/form-data").status_code == 403
    assert lecturer.post(f"/api/session/{sid}/recording-chunk", data={}, content_type="multipart/form-data").status_code == 400


def test_audio_errors_are_shown_and_missing_service_is_explained():
    app, lecturer, sid = lecturer_with_lecture(AudioReader(fail=True))
    bad = lecturer.post(f"/api/session/{sid}/recording-chunk", data=part(), content_type="multipart/form-data")
    assert bad.status_code == 400 and "quota" in bad.get_json()["error"]
    app.extensions["transcriber"] = None
    assert "GEMINI_API_KEY" in lecturer.post(f"/api/session/{sid}/recording-chunk", data=part(),
                                             content_type="multipart/form-data").get_json()["error"]


def test_a_service_without_audio_support_says_so():
    class TextOnly(Transcriber):
        name = "text-only"
    try:
        TextOnly().transcribe_audio(b"x", "audio/wav")
    except HandwritingError as exc:
        assert "cannot read audio" in str(exc)
    else:
        raise AssertionError("expected an error")


def test_gemini_sends_the_audio_with_the_lecture_prompt(monkeypatch):
    import attendance.handwriting as hw
    seen = {}

    def fake_call(request, timeout, waits=()):
        seen["body"] = request.data.decode("utf-8")
        return {"candidates": [{"content": {"parts": [{"text": " שלום "}]}}]}
    monkeypatch.setattr(hw, "_call", fake_call)
    text = GeminiTranscriber("key", "gemini-3.1-flash-lite").transcribe_audio(b"abc", "audio/wav")
    assert text == "שלום" and "audio/wav" in seen["body"] and "lecture" in seen["body"]
