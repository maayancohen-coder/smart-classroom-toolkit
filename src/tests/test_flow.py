"""End-to-end scenarios through the real HTTP routes (no phones needed)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app  # noqa: E402
from attendance.config import Config  # noqa: E402

CLASSROOM = (32.0853, 34.7818)  # arbitrary point
SAMPLE_REAL = [  # jittery, imprecise: what a real indoor fix looks like
    {"lat": 32.08531, "lng": 34.78181, "accuracy": 18},
    {"lat": 32.08533, "lng": 34.78179, "accuracy": 15},
    {"lat": 32.08529, "lng": 34.78183, "accuracy": 12},
]


class TestConfig(Config):
    LECTURER_KEY = "test-key"
    REQUIRE_LECTURER_PASSWORD = False
    REQUIRE_PIN = False             # the PIN and location-blocking scenarios use StrictConfig below
    BLOCK_WITHOUT_LOCATION = False


class StrictConfig(TestConfig):
    REQUIRE_PIN = True
    BLOCK_WITHOUT_LOCATION = True


@pytest.fixture()
def env():
    app = create_app(TestConfig)
    service = app.extensions["attendance_service"]
    lecturer = app.test_client()
    assert lecturer.get("/lecturer?key=test-key").status_code == 302
    created = lecturer.post("/api/session", json={
        "course": "Test", "lat": CLASSROOM[0], "lng": CLASSROOM[1], "radius": 100}).get_json()
    return app, service, lecturer, created["session_id"]


def qr_path(lecturer, sid):
    url = lecturer.get(f"/api/session/{sid}/qr").get_json()["url"]
    return url.split("localhost", 1)[1] if "localhost" in url else "/" + url.split("/", 3)[3]


def open_checkin(phone, path, headers=None):
    """Student scans the QR; returns the nonce embedded in the page."""
    res = phone.get(path, headers=headers or {})
    assert res.status_code == 200, res.get_data(as_text=True)
    html = res.get_data(as_text=True)
    marker = "const NONCE = "
    start = html.index(marker) + len(marker)
    return html[start:html.index(";", start)].strip().strip('"')


def near(student_id, dx=0.0):
    """A realistic fix for this student: a few metres from everyone else, never identical."""
    k = (int(student_id[-3:]) % 40) * 0.00001 + dx
    return [{**s, "lat": s["lat"] + k, "lng": s["lng"] - k / 2} for s in SAMPLE_REAL]


def submit(phone, nonce, student_id, samples=None, denied=False, headers=None, fp="", client_now=None, pin=None):
    body = {"nonce": nonce, "student_id": student_id,
            "samples": near(student_id) if samples is None else samples, "denied": denied}
    if pin:
        body["pin"] = pin
    if fp:
        body["fp"] = fp
    if client_now is not None:
        body["client_now"] = client_now
    return phone.post("/api/checkin", headers=headers or {}, json=body)


def status_of(lecturer, sid, student_id):
    rows = lecturer.get(f"/api/session/{sid}/report").get_json()["rows"]
    return next(r for r in rows if r["student_id"] == student_id)


def test_honest_student_is_present(env):
    app, _, lecturer, sid = env
    phone = app.test_client()
    nonce = open_checkin(phone, qr_path(lecturer, sid))
    assert submit(phone, nonce, "100000001").get_json()["ok"] is True
    assert status_of(lecturer, sid, "100000001")["status"] == "present"


def test_everyone_else_is_absent(env):
    _, _, lecturer, sid = env
    assert status_of(lecturer, sid, "100000002")["status"] == "absent"


def test_student_far_from_classroom_is_suspect(env):
    app, _, lecturer, sid = env
    phone = app.test_client()
    nonce = open_checkin(phone, qr_path(lecturer, sid))
    far = [{"lat": 32.2, "lng": 34.9, "accuracy": 20}] * 1
    submit(phone, nonce, "100000003", samples=far)
    row = status_of(lecturer, sid, "100000003")
    assert row["status"] == "suspect" and "classroom" in row["notes"]


def test_location_denied_is_suspect(env):
    app, _, lecturer, sid = env
    phone = app.test_client()
    nonce = open_checkin(phone, qr_path(lecturer, sid))
    submit(phone, nonce, "100000004", samples=[], denied=True)
    assert status_of(lecturer, sid, "100000004")["status"] == "suspect"


def test_spoofed_perfect_frozen_location_is_suspect(env):
    app, _, lecturer, sid = env
    phone = app.test_client()
    nonce = open_checkin(phone, qr_path(lecturer, sid))
    fake = [{"lat": CLASSROOM[0], "lng": CLASSROOM[1], "accuracy": 1}] * 3
    submit(phone, nonce, "100000005", samples=fake)
    row = status_of(lecturer, sid, "100000005")
    assert row["status"] == "suspect" and "precise" in row["notes"]


def test_one_phone_marking_two_students_flags_second(env):
    app, _, lecturer, sid = env
    phone = app.test_client()
    n1 = open_checkin(phone, qr_path(lecturer, sid))
    submit(phone, n1, "100000006")
    n2 = open_checkin(phone, qr_path(lecturer, sid))
    submit(phone, n2, "100000007")
    assert status_of(lecturer, sid, "100000006")["status"] == "present"
    second = status_of(lecturer, sid, "100000007")
    assert second["status"] == "suspect" and "already registered" in second["notes"]


def test_student_switching_phones_is_flagged(env):
    app, _, lecturer, sid = env
    first = app.test_client()
    submit(first, open_checkin(first, qr_path(lecturer, sid)), "100000008")
    # Next lecture, same student ID from a different phone: a new session, same registry.
    sid2 = lecturer.post("/api/session", json={
        "course": "Test 2", "lat": CLASSROOM[0], "lng": CLASSROOM[1]}).get_json()["session_id"]
    other = app.test_client()
    submit(other, open_checkin(other, qr_path(lecturer, sid2)), "100000008")
    row = status_of(lecturer, sid2, "100000008")
    assert row["status"] == "suspect" and "different phone" in row["notes"]


def test_lecturer_can_reset_device_after_phone_change(env):
    app, _, lecturer, sid = env
    old = app.test_client()
    submit(old, open_checkin(old, qr_path(lecturer, sid)), "100000009")
    lecturer.post(f"/api/session/{sid}/reset_device", json={"student_id": "100000009"})
    sid2 = lecturer.post("/api/session", json={
        "course": "T", "lat": CLASSROOM[0], "lng": CLASSROOM[1]}).get_json()["session_id"]
    new = app.test_client()
    submit(new, open_checkin(new, qr_path(lecturer, sid2)), "100000009")
    assert status_of(lecturer, sid2, "100000009")["status"] == "present"


def test_old_qr_relayed_is_rejected_or_flagged(env):
    app, service, lecturer, sid = env
    session = service.store.get(sid)
    slot = service.tokens.current(session.secret, sid)[0]

    # 3 periods old: beyond the grace window -> refused outright
    stale = f"/c/{sid}/{slot - 3}/{service.tokens.sign(session.secret, sid, slot - 3)}"
    assert app.test_client().get(stale).status_code == 400

    # 2 periods old: accepted (network delay) but the age is recorded and flagged as a weak signal
    phone = app.test_client()
    old = f"/c/{sid}/{slot - 2}/{service.tokens.sign(session.secret, sid, slot - 2)}"
    submit(phone, open_checkin(phone, old), "100000010")
    row = status_of(lecturer, sid, "100000010")
    assert row["token_age_s"] > 10  # one weak failure alone does not make a suspect


def test_forged_signature_is_rejected(env):
    app, service, _, sid = env
    slot = service.tokens.current(service.store.get(sid).secret, sid)[0]
    assert app.test_client().get(f"/c/{sid}/{slot}/{'0' * 16}").status_code == 400


def test_ticket_is_single_use(env):
    app, _, lecturer, sid = env
    phone = app.test_client()
    nonce = open_checkin(phone, qr_path(lecturer, sid))
    assert submit(phone, nonce, "100000001").get_json()["ok"] is True
    assert submit(phone, nonce, "100000002").status_code == 400


def test_unknown_student_id_is_refused_and_can_retry(env):
    app, _, lecturer, sid = env
    phone = app.test_client()
    nonce = open_checkin(phone, qr_path(lecturer, sid))
    assert submit(phone, nonce, "999").status_code == 400
    assert submit(phone, nonce, "100000001").get_json()["ok"] is True


def test_double_checkin_is_idempotent(env):
    app, _, lecturer, sid = env
    phone = app.test_client()
    submit(phone, open_checkin(phone, qr_path(lecturer, sid)), "100000001")
    again = submit(phone, open_checkin(phone, qr_path(lecturer, sid)), "100000001").get_json()
    assert again["ok"] and again["duplicate"]


def test_closed_session_refuses_scans(env):
    app, _, lecturer, sid = env
    path = qr_path(lecturer, sid)
    lecturer.post(f"/api/session/{sid}/close")
    assert app.test_client().get(path).status_code == 400


def test_student_response_never_leaks_status(env):
    app, _, lecturer, sid = env
    phone = app.test_client()
    nonce = open_checkin(phone, qr_path(lecturer, sid))
    body = submit(phone, nonce, "100000003", samples=[], denied=True).get_json()
    assert set(body) == {"ok", "name", "duplicate"}


def test_lecturer_endpoints_require_the_key(env):
    app, _, _, sid = env
    stranger = app.test_client()
    for path in (f"/api/session/{sid}/qr", f"/api/session/{sid}/report",
                 f"/api/session/{sid}/report.xlsx", f"/lecturer/{sid}"):
        assert stranger.get(path).status_code == 403
    assert stranger.post("/api/session", json={}).status_code == 403
    assert stranger.post(f"/api/session/{sid}/close").status_code == 403


def test_exports_are_valid_files(env):
    app, _, lecturer, sid = env
    xlsx = lecturer.get(f"/api/session/{sid}/report.xlsx")
    assert xlsx.status_code == 200 and xlsx.data[:2] == b"PK"
    csv_ = lecturer.get(f"/api/session/{sid}/report.csv")
    assert csv_.status_code == 200 and b"Student ID" in csv_.data


def test_campus_network_is_weak_signal_only(env):
    app, service, lecturer, sid = env
    service.store.get(sid).trusted_networks = ["132.68.0.0/16"]
    phone = app.test_client()
    nonce = open_checkin(phone, qr_path(lecturer, sid), headers={"X-Forwarded-For": "5.5.5.5"})
    submit(phone, nonce, "100000001", headers={"X-Forwarded-For": "5.5.5.5"})
    row = status_of(lecturer, sid, "100000001")
    assert row["status"] == "present" and "campus network" in row["notes"]


def test_frozen_realistic_location_alone_is_not_suspect(env):
    app, _, lecturer, sid = env
    phone = app.test_client()
    nonce = open_checkin(phone, qr_path(lecturer, sid))
    still = [{"lat": 32.08531, "lng": 34.78181, "accuracy": 20}] * 3  # phone resting on a desk
    submit(phone, nonce, "100000001", samples=still)
    row = status_of(lecturer, sid, "100000001")
    assert row["status"] == "present" and "frozen" in row["notes"]


def test_same_coordinates_as_another_student_is_suspect(env):
    app, _, lecturer, sid = env
    shared = [{"lat": 32.08531, "lng": 34.78181, "accuracy": 15}] * 2 + [{"lat": 32.08532, "lng": 34.78182, "accuracy": 15}]
    for student in ("100000001", "100000002"):
        phone = app.test_client()
        submit(phone, open_checkin(phone, qr_path(lecturer, sid)), student, samples=shared)
    assert "same coordinates" in status_of(lecturer, sid, "100000002")["notes"]
    assert status_of(lecturer, sid, "100000002")["status"] == "suspect"


def test_private_window_cheat_is_suspect_via_phone_profile(env):
    """One phone, a fresh cookie jar (private window), a second student's ID, same profile + network."""
    app, _, lecturer, sid = env
    fp = "ab12cd34ef56ab12cd34ef56"
    first = app.test_client()
    submit(first, open_checkin(first, qr_path(lecturer, sid)), "100000001", fp=fp)
    private = app.test_client()  # no cookies: looks like a brand new device
    submit(private, open_checkin(private, qr_path(lecturer, sid)), "100000002", fp=fp)
    row = status_of(lecturer, sid, "100000002")
    assert row["status"] == "suspect"
    assert "same phone profile" in row["notes"] and "private window" in row["notes"]
    assert status_of(lecturer, sid, "100000001")["status"] == "present"


def test_two_phones_of_same_model_alone_stay_present(env):
    app, _, lecturer, sid = env
    fp = "ab12cd34ef56ab12cd34ef56"
    a, b = app.test_client(), app.test_client()
    submit(a, open_checkin(a, qr_path(lecturer, sid)), "100000001", fp=fp, headers={"X-Forwarded-For": "1.1.1.1"})
    submit(b, open_checkin(b, qr_path(lecturer, sid)), "100000002", fp=fp, headers={"X-Forwarded-For": "2.2.2.2"})
    assert status_of(lecturer, sid, "100000002")["status"] == "present"


def test_stale_cached_fix_is_weak_only(env):
    import time
    app, _, lecturer, sid = env
    phone = app.test_client()
    old = [{**s, "ts": time.time() - 300} for s in near("100000001")]
    submit(phone, open_checkin(phone, qr_path(lecturer, sid)), "100000001", samples=old, client_now=time.time())
    row = status_of(lecturer, sid, "100000001")
    assert row["status"] == "present" and "old" in row["notes"]


def test_student_inside_building_but_away_from_class_is_flagged(env):
    app, _, lecturer, sid = env
    for i in range(1, 8):  # seven students sitting together
        phone = app.test_client()
        submit(phone, open_checkin(phone, qr_path(lecturer, sid)), f"10000000{i}")
    away = [{"lat": 32.0853 + 0.0007, "lng": 34.7818, "accuracy": 10}] * 2 + [{"lat": 32.0853 + 0.00071, "lng": 34.7818, "accuracy": 10}]
    phone = app.test_client()
    submit(phone, open_checkin(phone, qr_path(lecturer, sid)), "100000009", samples=away)
    row = status_of(lecturer, sid, "100000009")
    assert row["status"] == "suspect" and "outside the class group" in row["notes"] and row["zone"] == "nearby"
    assert status_of(lecturer, sid, "100000001")["status"] == "present"


@pytest.fixture()
def strict():
    app = create_app(StrictConfig)
    lecturer = app.test_client()
    lecturer.get("/lecturer?key=test-key")
    sid = lecturer.post("/api/session", json={
        "course": "Test", "lat": CLASSROOM[0], "lng": CLASSROOM[1], "radius": 100}).get_json()["session_id"]
    return app, app.extensions["attendance_service"], lecturer, sid


def test_no_location_permission_means_no_attendance(strict):
    app, _, lecturer, sid = strict
    phone = app.test_client()
    res = submit(phone, open_checkin(phone, qr_path(lecturer, sid)), "100000001", samples=[], denied=True, pin="1234")
    assert res.status_code == 400 and "location" in res.get_json()["error"].lower()
    assert status_of(lecturer, sid, "100000001")["status"] == "absent"


def test_pin_is_required(strict):
    app, _, lecturer, sid = strict
    phone = app.test_client()
    res = submit(phone, open_checkin(phone, qr_path(lecturer, sid)), "100000001")
    assert res.status_code == 400 and status_of(lecturer, sid, "100000001")["status"] == "absent"


def test_private_window_with_friends_id_but_no_pin_is_blocked(strict):
    app, _, lecturer, sid = strict
    owner = app.test_client()
    submit(owner, open_checkin(owner, qr_path(lecturer, sid)), "100000001", pin="4321")  # first time sets the PIN
    private = app.test_client()                      # fresh cookie jar: looks like a new phone
    res = submit(private, open_checkin(private, qr_path(lecturer, sid)), "100000002", pin="1111")
    assert res.get_json()["ok"] is True              # her own ID, her own first PIN: fine
    # Now the cheater tries to sign the absent friend (103) from the same private window, guessing a PIN.
    friend = app.test_client()
    submit(friend, open_checkin(friend, qr_path(lecturer, sid)), "100000003", pin="5555")  # friend registers own PIN
    cheat = app.test_client()
    res = submit(cheat, open_checkin(cheat, qr_path(lecturer, sid)), "100000003", pin="0000")
    assert res.status_code == 400 and "wrong" in res.get_json()["error"].lower()


def test_legit_student_on_new_phone_with_correct_pin_is_present(strict):
    app, _, lecturer, sid = strict
    first = app.test_client()
    submit(first, open_checkin(first, qr_path(lecturer, sid)), "100000001", pin="4321")
    lecturer.post("/api/session", json={})  # noop
    # Same student, next lecture, private window (no cookie): PIN proves identity.
    sid2 = lecturer.post("/api/session", json={"course": "T2", "lat": CLASSROOM[0], "lng": CLASSROOM[1],
                                               "radius": 100}).get_json()["session_id"]
    private = app.test_client()
    res = submit(private, open_checkin(private, qr_path(lecturer, sid2)), "100000001", pin="4321")
    assert res.get_json()["ok"] is True
    assert status_of(lecturer, sid2, "100000001")["status"] == "present"


def test_pin_locks_after_repeated_wrong_guesses(strict):
    app, _, lecturer, sid = strict
    owner = app.test_client()
    submit(owner, open_checkin(owner, qr_path(lecturer, sid)), "100000001", pin="4321")
    sid2 = lecturer.post("/api/session", json={"course": "T2", "lat": CLASSROOM[0], "lng": CLASSROOM[1],
                                               "radius": 100}).get_json()["session_id"]
    last = None
    for guess in ("0001", "0002", "0003", "0004", "0005", "4321"):  # the right PIN is rejected once locked
        attacker = app.test_client()
        last = submit(attacker, open_checkin(attacker, qr_path(lecturer, sid2)), "100000001", pin=guess)
    assert last.status_code == 400 and "attempts" in last.get_json()["error"].lower()


def test_lecturer_reset_clears_pin(strict):
    app, _, lecturer, sid = strict
    phone = app.test_client()
    submit(phone, open_checkin(phone, qr_path(lecturer, sid)), "100000001", pin="4321")
    lecturer.post(f"/api/session/{sid}/reset_device", json={"student_id": "100000001"})
    sid2 = lecturer.post("/api/session", json={"course": "T2", "lat": CLASSROOM[0], "lng": CLASSROOM[1],
                                               "radius": 100}).get_json()["session_id"]
    again = app.test_client()
    res = submit(again, open_checkin(again, qr_path(lecturer, sid2)), "100000001", pin="9999")  # new PIN accepted
    assert res.get_json()["ok"] is True


def make_suspect(env, student="100000001"):
    app, _, lecturer, sid = env
    phone = app.test_client()
    far = [{"lat": 32.2, "lng": 34.9, "accuracy": 20}] * 3
    submit(phone, open_checkin(phone, qr_path(lecturer, sid)), student, samples=far)
    assert status_of(lecturer, sid, student)["status"] == "suspect"


def approve(lecturer, sid, student, approved=True):
    return lecturer.post(f"/api/session/{sid}/approve", json={"student_id": student, "approved": approved})


def test_lecturer_can_approve_a_suspect_and_the_reasons_stay(env):
    _, _, lecturer, sid = env
    make_suspect(env)
    assert approve(lecturer, sid, "100000001").get_json()["ok"] is True
    row = status_of(lecturer, sid, "100000001")
    assert row["status"] == "present" and row["approved"] is True
    assert "approved by lecturer" in row["notes"] and "flagged" in row["notes"]
    counts = lecturer.get(f"/api/session/{sid}/report").get_json()["counts"]
    assert counts["present"] == 1 and counts["suspect"] == 0


def test_approval_can_be_undone(env):
    _, _, lecturer, sid = env
    make_suspect(env)
    approve(lecturer, sid, "100000001")
    approve(lecturer, sid, "100000001", approved=False)
    row = status_of(lecturer, sid, "100000001")
    assert row["status"] == "suspect" and row["approved"] is False


def test_approved_student_is_not_flagged_again_by_the_class_group(env):
    app, _, lecturer, sid = env
    for i in range(1, 8):
        phone = app.test_client()
        submit(phone, open_checkin(phone, qr_path(lecturer, sid)), f"10000000{i}")
    away = [{"lat": 32.0853 + 0.0007, "lng": 34.7818, "accuracy": 10}] * 2 + [{"lat": 32.0853 + 0.00071, "lng": 34.7818, "accuracy": 10}]
    phone = app.test_client()
    submit(phone, open_checkin(phone, qr_path(lecturer, sid)), "100000009", samples=away)
    assert status_of(lecturer, sid, "100000009")["status"] == "suspect"
    approve(lecturer, sid, "100000009")
    assert status_of(lecturer, sid, "100000009")["status"] == "present"


def test_cannot_approve_someone_who_did_not_check_in(env):
    _, _, lecturer, sid = env
    res = approve(lecturer, sid, "100000002")
    assert res.status_code == 400 and status_of(lecturer, sid, "100000002")["status"] == "absent"


def test_only_the_lecturer_can_approve(env):
    app, _, lecturer, sid = env
    make_suspect(env)
    assert approve(app.test_client(), sid, "100000001").status_code == 403
    assert status_of(lecturer, sid, "100000001")["status"] == "suspect"
