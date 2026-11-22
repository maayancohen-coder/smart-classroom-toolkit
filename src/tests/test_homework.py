"""Homework: similarity, course-content check, submissions, scanned files, routes."""
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from attendance.handwriting import HandwritingError, Transcriber  # noqa: E402
from attendance.homework import content_check, shingles, similarity, tokens  # noqa: E402
from test_flow import TestConfig  # noqa: E402
from app import create_app  # noqa: E402

QUESTIONS = "Solve the system and find the determinant of the matrix A and the eigenvalues of B."
REFERENCE = ("The determinant is computed by expanding along the first row: 2 times 10 plus 1 equals 21. "
             "The eigenvalues satisfy the characteristic polynomial, so lambda equals 1 or 3.")
MATERIALS = ("determinant expansion eigenvalues characteristic polynomial lambda matrix vector "
             "linear independence rank basis ") * 4


class FakeReader(Transcriber):
    name = "fake"

    def __init__(self, text="", fail=False):
        self.text, self.fail, self.calls = text, fail, []

    def complete(self, prompt):
        self.prompts = getattr(self, "prompts", []) + [prompt]
        if self.fail:
            raise HandwritingError("boom")
        return "Strengths: fine. Mistakes: none."

    def transcribe(self, data, mime):
        self.calls.append(mime)
        if self.fail:
            raise HandwritingError("boom")
        return self.text


def upload(text, name="x.txt"):
    return (io.BytesIO(text.encode()), name)


def make_assignment(lecturer):
    res = lecturer.post("/api/homework", data={
        "course": "Linear Algebra", "title": "HW3", "assignment": upload(QUESTIONS),
        "reference": upload(REFERENCE), "materials": upload(MATERIALS)}, content_type="multipart/form-data")
    assert res.get_json()["ok"], res.get_json()
    return res.get_json()["id"]


def lecturer_client():
    app = create_app(TestConfig)
    client = app.test_client()
    assert client.get("/lecturer?key=test-key").status_code == 302
    return app, client


def submit(client, aid, student_id, text="", file=None):
    data = {"student_id": student_id}
    data.update({"file": file} if file else {"file_text": text})
    return client.post(f"/api/homework/{aid}/submit", data=data, content_type="multipart/form-data")


def test_similarity_counts_shared_three_word_sequences():
    a, b = shingles(tokens("one two three four five")), shingles(tokens("one two three four nine"))
    assert similarity(a, b) == 2 / 3 and similarity(a, set()) == 0.0


def test_content_check_finds_missing_and_outside_terms():
    check = content_check("The determinant uses kubernetes and docker", MATERIALS)
    assert "kubernetes" in check["outside"] and "determinant" not in check["outside"]
    assert "eigenvalues" in check["missing"] and 0 < check["coverage"] < 100


def test_report_flags_copying_and_compares_to_the_reference():
    app, lecturer = lecturer_client()
    aid = make_assignment(lecturer)
    student = app.test_client()
    mine = REFERENCE.replace("21", "19")
    assert submit(student, aid, "100000001", mine).get_json()["ok"]
    assert submit(student, aid, "100000002", mine + " extra").get_json()["ok"]
    assert submit(student, aid, "100000003", "I do not know how to do this one").get_json()["ok"]
    report = lecturer.get(f"/api/homework/{aid}/report").get_json()
    assert report["count"] == 3 and report["has_reference"] and report["pairs"][0]["percent"] >= 90
    by_id = {r["student_id"]: r for r in report["rows"]}
    assert by_id["100000001"]["flagged"] and not by_id["100000003"]["flagged"]
    assert by_id["100000001"]["vs_reference"] > 50 > by_id["100000003"]["vs_reference"]


def test_question_text_alone_is_not_counted_as_copying():
    app, lecturer = lecturer_client()
    aid = make_assignment(lecturer)
    student = app.test_client()
    submit(student, aid, "100000001", QUESTIONS + " my own answer is here 1")
    submit(student, aid, "100000002", QUESTIONS + " a completely different reply 2")
    assert lecturer.get(f"/api/homework/{aid}/report").get_json()["pairs"] == []


def test_resubmission_replaces_and_unknown_student_is_refused():
    app, lecturer = lecturer_client()
    aid = make_assignment(lecturer)
    student = app.test_client()
    assert submit(student, aid, "100000001", "first answer text").get_json()["replaced"] is False
    assert submit(student, aid, "100000001", "second answer text").get_json()["replaced"] is True
    assert lecturer.get(f"/api/homework/{aid}/report").get_json()["count"] == 1
    assert submit(student, aid, "999", "answer text here").status_code == 400


def test_student_self_check_uses_course_material_only_and_stores_nothing():
    app, lecturer = lecturer_client()
    aid = make_assignment(lecturer)
    student = app.test_client()
    res = student.post(f"/api/homework/{aid}/check", data={"file_text": "determinant with kubernetes"},
                       content_type="multipart/form-data").get_json()
    assert res["ok"] and "kubernetes" in res["outside"] and "eigenvalues" in res["missing"]
    assert lecturer.get(f"/api/homework/{aid}/report").get_json()["count"] == 0


def test_lecturer_pages_need_the_key_but_the_student_page_does_not():
    app, _ = lecturer_client()
    anonymous = app.test_client()
    assert anonymous.get("/lecturer/homework").status_code == 403
    assert anonymous.post("/api/homework", data={"course": "a", "title": "b"}).status_code == 403
    assert anonymous.get("/homework").status_code == 200


def test_handwritten_scan_is_read_by_the_reader():
    app, lecturer = lecturer_client()
    aid = make_assignment(lecturer)
    fake = app.extensions["transcriber"] = FakeReader("det(A) = 2*(12-2) + 1*(1-0) = 19, lambda = 1 or 3")
    res = submit(app.test_client(), aid, "100000001", file=(io.BytesIO(b"\x89PNG fake"), "scan.png"))
    assert res.get_json()["ok"] and fake.calls == ["image/png"]
    text = lecturer.get(f"/api/homework/{aid}/submission/100000001").get_json()["text"]
    assert "= 19" in text


def test_scan_without_a_reader_or_with_a_failing_reader_gives_a_clear_error():
    app, lecturer = lecturer_client()
    aid = make_assignment(lecturer)
    scan = (io.BytesIO(b"\x89PNG fake"), "scan.png")
    app.extensions["transcriber"] = None
    assert "GEMINI_API_KEY" in submit(app.test_client(), aid, "100000001", file=scan).get_json()["error"]
    app.extensions["transcriber"] = FakeReader(fail=True)
    res = submit(app.test_client(), aid, "100000001", file=(io.BytesIO(b"\x89PNG fake"), "scan.png"))
    assert res.status_code == 400 and "boom" in res.get_json()["error"]


def test_busy_service_is_retried_then_succeeds(monkeypatch):
    import urllib.error
    import urllib.request
    from attendance import handwriting

    calls = []

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(request, timeout):
        calls.append(1)
        if len(calls) < 3:
            raise urllib.error.HTTPError("u", 503, "busy", {}, io.BytesIO(b"high demand"))
        return Reply()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert handwriting._call(urllib.request.Request("http://x"), 5, waits=(0, 0, 0)) == {"ok": True}
    assert len(calls) == 3


def test_gemini_3_reads_with_low_thinking_and_older_models_do_not(monkeypatch):
    import json
    import urllib.request
    from attendance.handwriting import GeminiTranscriber

    sent = []

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"candidates": [{"content": {"parts": [{"text": "hello"}]}}]}'

    monkeypatch.setattr(urllib.request, "urlopen", lambda request, timeout: sent.append(json.loads(request.data)) or Reply())
    assert GeminiTranscriber("k", "gemini-3.8-flash").transcribe(b"x", "application/pdf") == "hello"
    GeminiTranscriber("k", "gemini-2.5-flash").transcribe(b"x", "application/pdf")
    assert sent[0]["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    assert "thinkingConfig" not in sent[1]["generationConfig"]


def reviewed_setup():
    app, lecturer = lecturer_client()
    aid = make_assignment(lecturer)
    mine = "My answer. Contact 123456789. Written by נועה לוי with the kernel method."
    for sid, text in (("100000001", mine), ("100000002", "Another student's idea about eigenvalues and דנה כהן עם איתי כהן")):
        submit(app.test_client(), aid, sid, text)
    app.extensions["transcriber"] = FakeReader()
    return app, lecturer, aid


def test_llm_review_removes_names_and_ids_and_labels_classmates_anonymously():
    app, lecturer, aid = reviewed_setup()
    res = lecturer.post(f"/api/homework/{aid}/review/100000001", json={"mode": "course_only", "peers": True})
    assert res.get_json()["ok"] and "Strengths" in res.get_json()["review"]
    prompt = app.extensions["transcriber"].prompts[0]
    assert "123456789" not in prompt and "[ID]" in prompt
    assert "נועה לוי" not in prompt and "איתי כהן" not in prompt and "[NAME]" in prompt
    assert "Student A" in prompt and "classmates" in prompt
    assert "100000002" not in prompt


def test_llm_review_modes_choose_what_the_model_sees():
    app, lecturer, aid = reviewed_setup()
    lecturer.post(f"/api/homework/{aid}/review/100000001", json={"mode": "course_only", "peers": False})
    lecturer.post(f"/api/homework/{aid}/review/100000001", json={"mode": "solution", "peers": False})
    only_course, with_solution = app.extensions["transcriber"].prompts
    assert "course_material" in only_course and "lecturer_solution" not in only_course
    assert "lecturer_solution" in with_solution and "classmates" not in with_solution


def test_student_ai_check_never_sees_the_solution_or_classmates_and_is_rate_limited():
    from test_portal import student_client
    app, lecturer, aid = reviewed_setup()
    student = student_client(app, "100000003")
    data = {"file_text": "my draft about determinant and rank"}
    res = student.post(f"/api/homework/{aid}/llm-check", data=data, content_type="multipart/form-data")
    assert res.get_json()["ok"]
    prompt = app.extensions["transcriber"].prompts[0]
    assert "lecturer_solution" not in prompt and "classmates" not in prompt and "Another student" not in prompt
    again = student.post(f"/api/homework/{aid}/llm-check", data=data, content_type="multipart/form-data")
    assert again.status_code == 429
    assert app.test_client().post(f"/api/homework/{aid}/llm-check", data=data).status_code == 401
    assert lecturer.get("/api/homework/list").status_code == 200


def test_llm_review_without_a_service_or_with_a_failing_one_explains_why():
    app, lecturer, aid = reviewed_setup()
    app.extensions["transcriber"] = None
    assert "GEMINI_API_KEY" in lecturer.post(f"/api/homework/{aid}/review/100000001", json={}).get_json()["error"]
    app.extensions["transcriber"] = FakeReader(fail=True)
    assert lecturer.post(f"/api/homework/{aid}/review/100000001", json={}).status_code == 400
    assert app.test_client().post(f"/api/homework/{aid}/review/100000001", json={}).status_code == 403


def feedback_setup(extra_students=3):
    from test_portal import student_client
    app, lecturer = lecturer_client()
    aid = make_assignment(lecturer)
    texts = {"100000001": "The determinant by expansion along the first row gives twenty one. Eigenvalues are one and three.",
             "100000002": "Totally different words here about rank and basis of the vector space, nothing shared.",
             "100000003": "Another independent attempt that talks about kernels and linear maps in detail.",
             "100000004": "A fourth answer with yet other sentences about orthogonality and projections."}
    for sid, text in list(texts.items())[:1 + extra_students]:
        submit(app.test_client(), aid, sid, text)
    app.extensions["transcriber"] = FakeReader()
    return app, lecturer, aid, student_client(app, "100000001")


def test_student_feedback_compares_with_the_class_without_exposing_anyone():
    app, lecturer, aid, student = feedback_setup()
    res = student.post(f"/api/homework/{aid}/my-feedback").get_json()
    assert res["ok"] and res["compared"] and res["similarity"]["enough"] and res["similarity"]["level"] == "low"
    prompt = app.extensions["transcriber"].prompts[0]
    assert "do NOT quote" in prompt and "Student A" in prompt
    assert "lecturer_solution" not in prompt and "100000002" not in prompt
    assert "name" not in str(res["similarity"])


def test_student_feedback_needs_enough_classmates_and_respects_the_lecturer_switch():
    app, lecturer, aid, student = feedback_setup(extra_students=1)
    few = student.post(f"/api/homework/{aid}/my-feedback").get_json()
    assert few["ok"] and not few["compared"] and not few["similarity"]["enough"]
    assert "classmates" not in app.extensions["transcriber"].prompts[0]
    app2, lecturer2, aid2, student2 = feedback_setup()
    lecturer2.post(f"/api/homework/{aid2}/settings", json={"allow_student_comparison": False})
    off = student2.post(f"/api/homework/{aid2}/my-feedback").get_json()
    assert off["ok"] and not off["compared"] and not off["comparison_allowed"]
    assert "classmates" not in app2.extensions["transcriber"].prompts[0]
    assert app2.test_client().post(f"/api/homework/{aid2}/settings", json={}).status_code == 403


def test_student_feedback_requires_a_submission_and_a_login():
    app, lecturer, aid, student = feedback_setup()
    from test_portal import student_client
    assert student_client(app, "100000009").post(f"/api/homework/{aid}/my-feedback").status_code == 400
    assert app.test_client().post(f"/api/homework/{aid}/my-feedback").status_code == 401


def test_a_copied_answer_is_reported_as_high_similarity_to_the_student():
    from test_portal import student_client
    app, lecturer, aid, student = feedback_setup()
    submit(app.test_client(), aid, "100000005", "The determinant by expansion along the first row gives twenty one. Eigenvalues are one and three.")
    res = student_client(app, "100000005").post(f"/api/homework/{aid}/my-feedback").get_json()
    assert res["similarity"]["level"] == "high" and res["similarity"]["percent"] >= 90
