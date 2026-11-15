"""Head-count gap: photo (or manual) count versus check-ins."""
import io

import pytest

import json

from attendance.counting import CountingError, FakeCounter, GeminiVisionCounter, parse_count_reply
from test_flow import CLASSROOM, env, open_checkin, qr_path, status_of, submit  # noqa: F401

FAR = [{"lat": 32.2, "lng": 34.9, "accuracy": 20}]  # far from the classroom -> suspect


def check_in(app, lecturer, sid, student_id, samples=None):
    phone = app.test_client()
    nonce = open_checkin(phone, qr_path(lecturer, sid))
    if samples is None:
        submit(phone, nonce, student_id)
    else:
        submit(phone, nonce, student_id, samples=samples)


def post_count(lecturer, sid, count):
    return lecturer.post(f"/api/session/{sid}/headcount", data={"count": str(count)})


def summary(lecturer, sid):
    return lecturer.get(f"/api/session/{sid}/report").get_json()["headcount"]


def test_no_count_yet_means_no_summary(env):
    _, _, lecturer, sid = env
    assert summary(lecturer, sid) is None


def test_gap_above_tolerance_highlights_the_most_suspect(env):
    app, _, lecturer, sid = env
    for n in (1, 2, 3):
        check_in(app, lecturer, sid, f"10000000{n}")
    check_in(app, lecturer, sid, "100000004", samples=FAR)  # strong failure
    assert post_count(lecturer, sid, 3).get_json()["ok"]    # 4 check-ins, 3 people in the room
    s = summary(lecturer, sid)
    assert (s["checkins"], s["counted"], s["gap"], s["allowed"]) == (4, 3, 1, 0)
    assert s["verdict"] == "gap" and s["highlight_ids"] == ["100000004"]


def test_small_gap_within_ten_percent_is_ok(env):
    app, _, lecturer, sid = env
    for n in range(1, 10):
        check_in(app, lecturer, sid, f"10000000{n}")
    check_in(app, lecturer, sid, "100000010")
    post_count(lecturer, sid, 9)  # 10 check-ins, 9 counted: 1 person of tolerance
    s = summary(lecturer, sid)
    assert s["gap"] == 1 and s["allowed"] == 1 and s["verdict"] == "ok" and s["highlight_ids"] == []


def test_more_people_counted_than_checked_in(env):
    app, _, lecturer, sid = env
    check_in(app, lecturer, sid, "100000001")
    post_count(lecturer, sid, 5)
    assert summary(lecturer, sid)["verdict"] == "more_counted"


def test_photo_without_a_counter_is_refused(env):
    _, _, lecturer, sid = env
    res = lecturer.post(f"/api/session/{sid}/headcount",
                        data={"photo": (io.BytesIO(b"\xff\xd8fake"), "c.jpg")})
    assert res.status_code == 400


def test_photo_is_counted_and_never_kept(env):
    app, service, lecturer, sid = env
    service.counter = FakeCounter(7)
    image = b"\xff\xd8\xff" + b"x" * 1000
    res = lecturer.post(f"/api/session/{sid}/headcount", data={"photo": (io.BytesIO(image), "c.jpg")})
    assert res.get_json()["headcount"]["counted"] == 7 and service.counter.calls == 1
    session = service.store.get(sid)
    kept = [v for k, v in vars(session).items() if k != "secret" and isinstance(v, (bytes, bytearray))]
    assert kept == [] and image not in [bytes(v) for v in vars(session).values() if isinstance(v, (bytes, bytearray))]


def test_invalid_manual_values_are_refused(env):
    _, _, lecturer, sid = env
    assert post_count(lecturer, sid, "abc").status_code == 400
    assert post_count(lecturer, sid, -3).status_code == 400


def test_headcount_requires_the_lecturer_key(env):
    app, _, _, sid = env
    assert app.test_client().post(f"/api/session/{sid}/headcount", data={"count": "5"}).status_code == 403


def test_export_includes_the_head_count(env):
    app, _, lecturer, sid = env
    check_in(app, lecturer, sid, "100000001")
    post_count(lecturer, sid, 1)
    csv_ = lecturer.get(f"/api/session/{sid}/report.csv").data.decode("utf-8-sig")
    assert "Head count (photo),1" in csv_ and "Gap,0" in csv_


@pytest.mark.parametrize("reply, expected", [
    ('{"count": 23, "confidence": "high", "notes": "clear"}', 23),
    ('```json\n{"count": 8, "confidence": "low", "notes": "back rows"}\n```', 8),
    ('Here you go: {"count": 0, "confidence": "high", "notes": ""}', 0),
])
def test_model_reply_is_parsed(reply, expected):
    assert parse_count_reply(reply).count == expected


@pytest.mark.parametrize("reply", ["I cannot count", '{"count": "many"}', '{"count": -2}', '{"count": 99999}'])
def test_unusable_model_reply_raises(reply):
    with pytest.raises(CountingError):
        parse_count_reply(reply)


class _FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_gemini_adapter_sends_image_and_parses_the_answer(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout=None):
        seen["url"], seen["headers"], seen["body"] = request.full_url, dict(request.header_items()), json.loads(request.data)
        return _FakeResponse({"candidates": [{"content": {"parts": [
            {"text": '{"count": 31, "confidence": "medium", "notes": "back rows partly hidden"}'}]}}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = GeminiVisionCounter("KEY", "some-model").count(b"\xff\xd8img", "image/jpeg")
    assert result.count == 31 and result.confidence == "medium" and "gemini" in result.method
    assert seen["url"].endswith("/models/some-model:generateContent")
    assert seen["headers"]["X-goog-api-key"] == "KEY"           # key in a header, not in the URL
    assert seen["body"]["contents"][0]["parts"][0]["inline_data"]["mime_type"] == "image/jpeg"


def test_gemini_unreachable_is_reported_not_crashed(monkeypatch):
    import urllib.error

    def boom(request, timeout=None):
        raise urllib.error.URLError("down")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    with pytest.raises(CountingError):
        GeminiVisionCounter("KEY", "m").count(b"x", "image/jpeg")


def test_http_error_shows_status_and_reason_without_the_key(monkeypatch):
    import urllib.error

    def refuse(request, timeout=None):
        raise urllib.error.HTTPError(request.full_url, 404, "nf", {}, io.BytesIO(
            json.dumps({"error": {"message": "models/some-model is not found"}}).encode()))

    monkeypatch.setattr("urllib.request.urlopen", refuse)
    with pytest.raises(CountingError) as caught:
        GeminiVisionCounter("SECRET-KEY", "some-model").count(b"x", "image/jpeg")
    assert "404" in str(caught.value) and "not found" in str(caught.value)
    assert "SECRET-KEY" not in str(caught.value)
