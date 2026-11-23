"""Reading lecture slides: PowerPoint (stdlib), PDF (pypdf), text; terms; routes."""
import io
import os
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from attendance.slides import SlidesError, extract_terms, extract_text, hebrew_words  # noqa: E402
from test_flow import env  # noqa: E402,F401


def make_pptx(*slides):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for i, paragraphs in enumerate(slides, 1):
            body = "".join(f"<a:p><a:r><a:t>{p}</a:t></a:r></a:p>" for p in paragraphs)
            z.writestr(f"ppt/slides/slide{i}.xml", f"<p:sld><p:txBody>{body}</p:txBody></p:sld>")
    return buf.getvalue()


SLIDES = make_pptx(["תבניות עיצוב", "Strategy &amp; Adapter"], ["Abstract Class", "הממשק Interface מגדיר התנהגות"])


def test_pptx_text_is_read_in_slide_order():
    text = extract_text("lecture.pptx", SLIDES)
    assert text.index("Strategy & Adapter") < text.index("Abstract Class") and "תבניות עיצוב" in text


def test_terms_are_english_words_and_phrases_without_filler():
    terms = extract_terms("Strategy and the Abstract Class, plus UML and the Facade pattern. תבנית Interface")
    assert "Abstract Class" in terms and "Strategy" in terms and "UML" in terms and "Facade" in terms
    assert "the" not in [t.lower() for t in terms] and "and" not in [t.lower() for t in terms]


def test_unknown_file_types_and_broken_files_are_refused():
    with pytest.raises(SlidesError):
        extract_text("notes.exe", b"x")
    with pytest.raises(SlidesError):
        extract_text("broken.pptx", b"not a zip")


def test_plain_text_is_read():
    assert "Facade" in extract_text("terms.txt", "Facade, Adapter".encode())


def make_pdf(text: str) -> bytes:
    """A one-page PDF with a correct cross-reference table (built here so the test needs no extra tools)."""
    content = f"BT /F1 12 Tf 20 100 Td ({text}) Tj ET".encode()
    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 200]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>",
        b"<</Length " + str(len(content)).encode() + b">>\nstream\n" + content + b"\nendstream",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    out, offsets = b"%PDF-1.4\n", []
    for n, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer<</Size {len(objects) + 1}/Root 1 0 R>>\nstartxref\n{xref}\n%%EOF".encode()
    return out


def test_pdf_text_is_read():
    pytest.importorskip("pypdf")
    assert "Strategy Adapter Facade" in extract_text("slides.pdf", make_pdf("Strategy Adapter Facade"))


def test_route_reads_slides_and_returns_terms(env):
    _, service, lecturer, sid = env
    res = lecturer.post(f"/api/session/{sid}/slides", data={"slides": (io.BytesIO(SLIDES), "lecture.pptx")})
    data = res.get_json()
    assert data["ok"] and "Strategy" in data["terms"] and "Abstract Class" in data["terms"]
    assert "Interface" in service.store.get(sid).slides_text


def test_route_refuses_bad_files_and_non_lecturers(env):
    app, _, lecturer, sid = env
    bad = lecturer.post(f"/api/session/{sid}/slides", data={"slides": (io.BytesIO(b"x"), "a.exe")})
    assert bad.status_code == 400
    stranger = app.test_client().post(f"/api/session/{sid}/slides", data={"slides": (io.BytesIO(SLIDES), "l.pptx")})
    assert stranger.status_code == 403


def test_slide_words_make_a_student_question_relevant(env):
    _, _, lecturer, sid = env
    lecturer.post(f"/api/session/{sid}/slides", data={"slides": (io.BytesIO(make_pptx(["הממשק מגדיר התנהגות"])), "l.pptx")})
    body = {"threshold": 0.1, "glossary": "", "segments": [
        {"text": "נמשיך הלאה", "level": 0.2, "t0": 0, "t1": 2},
        {"text": "מה זה הממשק", "level": 0.03, "t0": 2, "t1": 5},
        {"text": "זה חוזה בין מחלקות", "level": 0.2, "t0": 5, "t1": 8}]}
    data = lecturer.post(f"/api/session/{sid}/transcript", json=body).get_json()
    assert data["questions"] == 1 and "[Student question] מה זה הממשק" in data["corrected"]


def test_hebrew_words_helper():
    assert hebrew_words("הממשק Interface מגדיר") == {"הממשק", "מגדיר"}
