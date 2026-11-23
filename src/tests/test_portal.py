"""Login, course lists, live notes, messages to the lecturer and the lecture summary."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app  # noqa: E402
from attendance.summary import summarize  # noqa: E402
from test_flow import TestConfig  # noqa: E402

TRANSCRIPT = ("היום דיברנו על Strategy pattern ואיך הוא מאפשר להחליף אלגוריתם בזמן ריצה. "
              "ה-Strategy מגדיר ממשק משותף לכל האלגוריתמים. אחר כך הייתה הפסקה קצרה וכולם הלכו לקפה במסדרון. "
              "אחר כך הראיתי דוגמה של Adapter שממיר ממשק אחד לממשק אחר ומאפשר לשתי מחלקות לעבוד יחד.")


def setup():
    app = create_app(TestConfig)
    lecturer = app.test_client()
    assert lecturer.post("/api/login/lecturer", json={"lecturer_id": "maayan", "key": "test-key"}).get_json()["ok"]
    return app, lecturer


def student_client(app, student_id="100000001"):
    client = app.test_client()
    assert client.post("/api/login/student", json={"student_id": student_id}).get_json()["ok"]
    return client


def open_lecture(lecturer, course_id="i2se"):
    return lecturer.post("/api/session", json={"course_id": course_id}).get_json()["session_id"]


def test_login_rejects_unknown_students_and_wrong_lecturer_keys():
    app, _ = setup()
    anonymous = app.test_client()
    assert anonymous.post("/api/login/student", json={"student_id": "nope"}).status_code == 400
    assert anonymous.post("/api/login/lecturer", json={"lecturer_id": "maayan", "key": "wrong"}).status_code == 400
    assert anonymous.get("/my").status_code == 302 and anonymous.get("/course/i2se").status_code == 302
    assert anonymous.get("/lecturer/course/i2se").status_code == 403


def test_student_sees_only_their_courses_and_a_live_badge():
    app, lecturer = setup()
    student = student_client(app)
    page = student.get("/my").get_data(as_text=True)
    assert "Intro to Software Engineering" in page and "Active lecture" not in page
    open_lecture(lecturer)
    assert "Active lecture" in student.get("/my").get_data(as_text=True)


def test_live_notes_reach_the_lecturer_and_anonymous_hides_the_name():
    app, lecturer = setup()
    sid = open_lecture(lecturer)
    one, two = student_client(app), student_client(app, "100000002")
    assert one.get(f"/live/{sid}").status_code == 200
    assert one.post(f"/api/session/{sid}/note", json={"text": "לא הבנתי את הדוגמה"}).get_json()["ok"]
    assert two.post(f"/api/session/{sid}/note", json={"text": "מהר מדי", "anonymous": True}).get_json()["ok"]
    notes = lecturer.get(f"/api/session/{sid}/notes").get_json()
    assert [n["text"] for n in notes] == ["לא הבנתי את הדוגמה", "מהר מדי"]
    assert notes[0]["name"] != "Anonymous" and notes[1]["name"] == "Anonymous"
    assert lecturer.get(f"/api/session/{sid}/notes?after=1").get_json()[0]["text"] == "מהר מדי"
    assert [n["text"] for n in one.get(f"/api/session/{sid}/my-notes").get_json()] == ["לא הבנתי את הדוגמה"]


def test_notes_are_rate_limited_and_closed_lectures_refuse_them():
    app, lecturer = setup()
    sid = open_lecture(lecturer)
    student = student_client(app)
    assert student.post(f"/api/session/{sid}/note", json={"text": "אחת"}).status_code == 200
    assert student.post(f"/api/session/{sid}/note", json={"text": "שתיים"}).status_code == 429
    lecturer.post(f"/api/session/{sid}/close")
    assert student.post(f"/api/session/{sid}/note", json={"text": "אחרי הסיום"}).status_code == 400
    assert student.get(f"/live/{sid}").status_code == 404


def test_students_can_write_to_the_course_lecturer():
    app, lecturer = setup()
    student = student_client(app)
    assert student.post("/api/course/i2se/message", json={"text": "אפשר להאריך את ההגשה?"}).get_json()["ok"]
    inbox = lecturer.get("/api/course/i2se/inbox").get_json()
    assert inbox[0]["text"] == "אפשר להאריך את ההגשה?" and inbox[0]["student_id"] == "100000001"
    assert student.get("/api/course/i2se/inbox").status_code == 403


def test_summary_is_visible_to_students_only_after_the_lecturer_publishes_it():
    app, lecturer = setup()
    sid = open_lecture(lecturer)
    lecturer.post(f"/api/session/{sid}/transcript", json={"raw": TRANSCRIPT, "glossary": "Strategy\nAdapter"})
    student = student_client(app)
    assert student.get("/api/course/i2se/summaries").get_json() == []
    lecturer.post(f"/api/session/{sid}/summary/publish", json={"published": True})
    shown = student.get("/api/course/i2se/summaries").get_json()
    assert len(shown) == 1 and "Strategy" in shown[0]["terms"]
    assert not any("קפה" in s for s in shown[0]["sentences"])
    lecturer.post(f"/api/session/{sid}/summary/publish", json={"published": False})
    assert student.get("/api/course/i2se/summaries").get_json() == []


def test_summary_keeps_the_main_topics_and_drops_chatter():
    result = summarize(TRANSCRIPT, ["Strategy", "Adapter"], max_sentences=3)
    text = " ".join(result["sentences"])
    assert "Strategy" in text and "קפה" not in text and len(result["sentences"]) == 2


def test_logout_clears_the_login():
    app, _ = setup()
    student = student_client(app)
    assert student.get("/my").status_code == 200
    student.get("/logout")
    assert student.get("/my").status_code == 302


def test_student_home_attendance_and_scan_pages():
    app, lecturer = setup()
    student = student_client(app)
    home = student.get("/my").get_data(as_text=True)
    assert "/attend" in home and "/homework" in home
    assert "No active lecture" in student.get("/attend").get_data(as_text=True)
    open_lecture(lecturer)
    assert "/scan?course=i2se" in student.get("/attend").get_data(as_text=True)
    assert student.get("/scan?course=i2se").status_code == 200
    anonymous = app.test_client()
    assert anonymous.get("/attend").status_code == 302 and anonymous.get("/scan").status_code == 302


def test_student_sees_own_submission_on_the_course_page():
    app, lecturer = setup()
    aid = lecturer.post("/api/homework", data={"course": "Intro to Software Engineering", "title": "H1",
                        "assignment_text": "Explain the Strategy pattern"}).get_json()["id"]
    student = student_client(app)
    page = student.get("/course/i2se").get_data(as_text=True)
    assert "Not submitted yet" in page
    assert student.post(f"/api/homework/{aid}/submit", data={"student_id": "100000001", "pin": "",
                        "file_text": "my answer about strategy objects"}).get_json()["ok"]
    page = student.get("/course/i2se").get_data(as_text=True)
    assert "View my submission" in page and "my answer about strategy objects" in page
    other = student_client(app, "100000002").get("/course/i2se").get_data(as_text=True)
    assert "my answer about strategy objects" not in other


def test_past_lecture_can_get_a_transcript_and_students_see_it_when_published():
    app, lecturer = setup()
    assert lecturer.post("/api/course/i2se/past-lecture", json={"date": "bad"}).status_code == 400
    assert lecturer.post("/api/course/i2se/past-lecture", json={"date": "2999-01-01"}).status_code == 400
    sid = lecturer.post("/api/course/i2se/past-lecture", json={"date": "2026-11-10"}).get_json()["session_id"]
    assert lecturer.get(f"/lecturer/{sid}/transcript").status_code == 200
    lecturer.post(f"/api/session/{sid}/transcript", json={"raw": TRANSCRIPT, "glossary": "Strategy"})
    lec = lecturer.get("/api/course/i2se/lectures").get_json()
    assert lec[0]["id"] == sid and lec[0]["closed"] and lec[0]["has_transcript"]
    student = student_client(app)
    assert student.get("/api/course/i2se/summaries").get_json() == []
    lecturer.post(f"/api/session/{sid}/summary/publish", json={"published": True})
    got = student.get("/api/course/i2se/summaries").get_json()
    assert len(got) == 1 and "Strategy" in got[0]["transcript"]


def test_recording_is_played_by_students_only_after_publishing():
    import io as _io
    app, lecturer = setup()
    sid = lecturer.post("/api/course/i2se/past-lecture", json={"date": "2026-11-10"}).get_json()["session_id"]
    lecturer.post(f"/api/session/{sid}/transcript", json={"raw": TRANSCRIPT, "glossary": ""})
    bad = lecturer.post(f"/api/session/{sid}/recording-file", data={"file": (_io.BytesIO(b"x"), "a.txt", "text/plain")})
    assert bad.status_code == 400
    ok = lecturer.post(f"/api/session/{sid}/recording-file", data={"file": (_io.BytesIO(b"0123456789"), "a.m4a", "audio/mp4")})
    assert ok.get_json()["ok"]
    student, outsider = student_client(app), app.test_client()
    assert student.get(f"/api/session/{sid}/recording").status_code in (401, 403)
    assert lecturer.get(f"/api/session/{sid}/recording").data == b"0123456789"
    lecturer.post(f"/api/session/{sid}/summary/publish", json={"published": True})
    assert student.get(f"/api/session/{sid}/recording").data == b"0123456789"
    assert student.get(f"/api/session/{sid}/recording", headers={"Range": "bytes=2-4"}).data == b"234"
    assert outsider.get(f"/api/session/{sid}/recording").status_code in (401, 403)
    assert student.get("/api/course/i2se/summaries").get_json()[0]["recording"].endswith("/recording")
    lecturer.delete(f"/api/session/{sid}/recording-file")
    assert student.get(f"/api/session/{sid}/recording").status_code == 404
