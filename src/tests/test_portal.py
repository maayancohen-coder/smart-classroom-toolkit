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
    assert "Intro to Software Engineering" in page and "שיעור פעיל" not in page
    open_lecture(lecturer)
    assert "שיעור פעיל" in student.get("/my").get_data(as_text=True)


def test_live_notes_reach_the_lecturer_and_anonymous_hides_the_name():
    app, lecturer = setup()
    sid = open_lecture(lecturer)
    one, two = student_client(app), student_client(app, "100000002")
    assert one.get(f"/live/{sid}").status_code == 200
    assert one.post(f"/api/session/{sid}/note", json={"text": "לא הבנתי את הדוגמה"}).get_json()["ok"]
    assert two.post(f"/api/session/{sid}/note", json={"text": "מהר מדי", "anonymous": True}).get_json()["ok"]
    notes = lecturer.get(f"/api/session/{sid}/notes").get_json()
    assert [n["text"] for n in notes] == ["לא הבנתי את הדוגמה", "מהר מדי"]
    assert notes[0]["name"] != "אנונימי" and notes[1]["name"] == "אנונימי"
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
    assert "אין שיעור פעיל" in student.get("/attend").get_data(as_text=True)
    open_lecture(lecturer)
    assert "/scan?course=i2se" in student.get("/attend").get_data(as_text=True)
    assert student.get("/scan?course=i2se").status_code == 200
    anonymous = app.test_client()
    assert anonymous.get("/attend").status_code == 302 and anonymous.get("/scan").status_code == 302
