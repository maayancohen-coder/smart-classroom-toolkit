"""The state survives a restart when a database is configured (a memory backend stands in for Firestore)."""
import io
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app  # noqa: E402
from attendance.persistence import BLOB_MIN_BYTES, MemoryBackend, StatePersistence  # noqa: E402
from test_flow import TestConfig  # noqa: E402

RECORDING = bytes(range(256)) * (BLOB_MIN_BYTES // 256 * 3)     # big enough to be saved as a blob


def lecturer_of(app):
    client = app.test_client()
    assert client.post("/api/login/lecturer", json={"lecturer_id": "maayan", "key": "test-key"}).get_json()["ok"]
    return client


def test_without_a_database_nothing_is_saved():
    app = create_app(TestConfig)
    assert not app.extensions["persistence"].enabled
    assert app.extensions["persistence"].save_now() is False


def test_lectures_recordings_homework_and_passwords_survive_a_restart():
    backend = MemoryBackend()
    first = create_app(TestConfig, state_backend=backend)
    lecturer = lecturer_of(first)
    sid = lecturer.post("/api/course/i2se/past-lecture", json={"date": "2026-11-10"}).get_json()["session_id"]
    upload = {"file": (io.BytesIO(RECORDING), "lecture.m4a", "audio/mp4")}
    assert lecturer.post(f"/api/session/{sid}/recording-file", data=upload).status_code == 200
    service = first.extensions["attendance_service"]
    assert service.pins.check_or_set("100000001", "4321") == service.pins.SET
    first.extensions["homework_store"].create("Intro to Software Engineering", "Ex 1")
    assert first.extensions["persistence"].save_now()

    second = create_app(TestConfig, state_backend=backend)            # a new server process
    restored = second.extensions["attendance_service"]
    assert restored.store.get(sid).recording == RECORDING
    assert restored.pins.check_or_set("100000001", "4321") == restored.pins.OK
    assert restored.pins.check_or_set("100000001", "0000") == restored.pins.WRONG
    assert [a.title for a in second.extensions["homework_store"].all()] == ["Ex 1"]
    played = lecturer_of(second).get(f"/api/session/{sid}/recording")
    assert played.status_code == 200 and played.data == RECORDING


def test_a_recording_is_uploaded_once_and_the_snapshot_stays_small():
    backend = MemoryBackend()
    app = create_app(TestConfig, state_backend=backend)
    lecturer = lecturer_of(app)
    sid = lecturer.post("/api/course/i2se/past-lecture", json={"date": "2026-11-10"}).get_json()["session_id"]
    lecturer.post(f"/api/session/{sid}/recording-file", data={"file": (io.BytesIO(RECORDING), "a.m4a", "audio/mp4")})
    persistence = app.extensions["persistence"]
    persistence.save_now()
    persistence.save_now()
    assert len(backend.blobs) == 1
    assert len(backend.main) < len(RECORDING) // 4


def test_locks_are_recreated_and_a_damaged_snapshot_does_not_stop_the_server():
    class Holder:
        def __init__(self):
            self.items, self._lock = {"a": 1}, threading.Lock()

    backend, holder = MemoryBackend(), Holder()
    StatePersistence(backend, {"h": holder}).save_now()
    fresh = Holder()
    fresh.items = {}
    assert StatePersistence(backend, {"h": fresh}).load()
    assert fresh.items == {"a": 1} and fresh._lock.acquire(blocking=False)

    backend.main = b"not a snapshot"
    assert create_app(TestConfig, state_backend=backend).extensions["persistence"].last_error


def test_a_change_marks_the_state_for_saving():
    app = create_app(TestConfig, state_backend=MemoryBackend())
    persistence = app.extensions["persistence"]
    persistence._dirty.clear()
    lecturer_of(app).get("/lecturer")
    lecturer_of(app)                                                   # the sign-in itself is a POST
    assert persistence._dirty.is_set()
