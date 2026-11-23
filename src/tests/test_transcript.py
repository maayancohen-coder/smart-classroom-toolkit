"""Glossary correction of a speech-to-text transcript, and its routes."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from attendance.transcript import correct_transcript, parse_glossary  # noqa: E402
from test_flow import env  # noqa: E402,F401

GLOSSARY = ["Strategy", "Adapter", "Polymorphism", "Interface", "Abstract Class", "Facade", "UML", "Unit Test", "Service"]


def fix(text, glossary=None):
    return correct_transcript(text, glossary or GLOSSARY).text


def test_hebrew_spelling_of_english_terms_is_replaced():
    assert fix("תבנית סטרטגי מאפשרת") == "תבנית Strategy מאפשרת"
    assert fix("תבנית אדפטר") == "תבנית Adapter"
    assert fix("ראינו פולימורפיזם") == "ראינו Polymorphism"
    assert fix("תבנית פאסאד") == "תבנית Facade"


def test_multi_word_terms_and_spoken_acronyms():
    assert fix("צריך אבסטרקט קלאס כאן") == "צריך Abstract Class כאן"
    assert fix("כל מחלקה צריכה יוניט טסט") == "כל מחלקה צריכה Unit Test"
    assert fix("בתרשים יו אם אל אפשר לראות") == "בתרשים UML אפשר לראות"


def test_hebrew_prefix_and_punctuation_are_kept():
    assert fix("ראינו פולימורפיזם ואינטרפייס, ונראה") == "ראינו Polymorphism ו-Interface, ונראה"
    assert fix("בסטרטגי משתמשים.") == "ב-Strategy משתמשים."


def test_english_words_get_the_right_spelling():
    assert fix("we use strategy and unit test") == "we use Strategy and Unit Test"


def test_ordinary_hebrew_is_left_alone():
    text = "אם לא נצליח, נחזור מחר לשיעור ונדבר על המשימה"
    assert fix(text) == text


def test_missing_terms_are_reported():
    result = correct_transcript("תבנית סטרטגי", GLOSSARY)
    assert "Strategy" not in result.missing and "Facade" in result.missing
    assert [(f.heard, f.term) for f in result.fixes] == [("סטרטגי", "Strategy")]


def test_glossary_parsing():
    assert parse_glossary("Strategy, Adapter\nstrategy;  UML ") == ["Strategy", "Adapter", "UML"]


def test_route_corrects_stores_and_downloads(env):
    app, service, lecturer, sid = env
    res = lecturer.post(f"/api/session/{sid}/transcript", json={"raw": "תבנית סטרטגי", "glossary": "Strategy, Facade"})
    data = res.get_json()
    assert data["corrected"] == "תבנית Strategy" and data["missing"] == ["Facade"]
    assert service.store.get(sid).transcript_raw == "תבנית סטרטגי"
    download = lecturer.get(f"/api/session/{sid}/transcript.txt")
    assert download.status_code == 200 and "Strategy" in download.get_data(as_text=True)


def test_only_the_lecturer_can_use_the_transcript_routes(env):
    app, _, lecturer, sid = env
    stranger = app.test_client()
    assert stranger.post(f"/api/session/{sid}/transcript", json={"raw": "x"}).status_code == 403
    assert stranger.get(f"/lecturer/{sid}/transcript").status_code == 403
    assert lecturer.get(f"/lecturer/{sid}/transcript").status_code == 200


def test_download_without_transcript_is_404(env):
    _, _, lecturer, sid = env
    assert lecturer.get(f"/api/session/{sid}/transcript.txt").status_code == 404


# ---- only the lecturer's voice ------------------------------------------------------------
from attendance.transcript import Segment, assemble_lecturer_transcript  # noqa: E402

LOUD, QUIET, LIMIT = 0.20, 0.03, 0.10


def seg(text, level, t0, t1):
    return Segment(text, level, t0, t1)


def test_quiet_voices_that_are_not_questions_are_dropped():
    result = assemble_lecturer_transcript(
        [seg("היום נדבר על תבניות", LOUD, 0, 3), seg("מישהו הביא קפה", QUIET, 3, 5), seg("נתחיל", LOUD, 5, 7)],
        LIMIT, GLOSSARY)
    assert result.text == "היום נדבר על תבניות נתחיל" and result.questions == 0
    assert result.dropped == [{"text": "מישהו הביא קפה", "reason": "quiet voice, not a question"}]


def test_related_student_question_with_an_answer_is_kept():
    result = assemble_lecturer_transcript(
        [seg("תבנית Strategy מחליפה אלגוריתם", LOUD, 0, 4),
         seg("מה ההבדל בין Strategy לבין Adapter", QUIET, 4, 8),
         seg("ההבדל הוא שהאדפטר מתאים ממשק", LOUD, 8, 12)],
        LIMIT, GLOSSARY)
    assert "[Student question] מה ההבדל בין Strategy לבין Adapter" in result.text and result.questions == 1


def test_question_without_an_answer_is_dropped():
    result = assemble_lecturer_transcript(
        [seg("תבנית Strategy", LOUD, 0, 3), seg("מה זה Adapter", QUIET, 3, 6), seg("נמשיך הלאה", LOUD, 40, 43)],
        LIMIT, GLOSSARY)
    assert result.questions == 0 and result.dropped[0]["reason"] == "question that the lecturer did not answer"


def test_unrelated_question_is_dropped():
    result = assemble_lecturer_transcript(
        [seg("תבנית Strategy", LOUD, 0, 3), seg("איפה החנייה של הפקולטה", QUIET, 3, 6), seg("בואו נמשיך לנושא", LOUD, 6, 9)],
        LIMIT, GLOSSARY)
    assert result.questions == 0 and result.dropped[0]["reason"].startswith("question not related")


def test_spoken_letters_can_be_a_or_i():
    assert fix("חשוב להכיר איי פי איי", GLOSSARY + ["API"]) == "חשוב להכיר API"


def test_route_uses_segments_threshold_and_the_lecturers_glossary(env):
    _, _, lecturer, sid = env
    body = {"threshold": LIMIT, "glossary": "Strategy", "segments": [
        {"text": "תבנית סטרטגי", "level": LOUD, "t0": 0, "t1": 3},
        {"text": "שיחה בצד", "level": QUIET, "t0": 3, "t1": 5}]}
    data = lecturer.post(f"/api/session/{sid}/transcript", json=body).get_json()
    assert data["corrected"] == "תבנית Strategy" and len(data["dropped"]) == 1
    body["glossary"] = ""
    assert lecturer.post(f"/api/session/{sid}/transcript", json=body).get_json()["corrected"] == "תבנית סטרטגי"


def test_a_word_before_the_term_is_not_swallowed():
    assert fix("ההבדל הוא שהאדפטר מתאים ממשק") == "ההבדל הוא ש-Adapter מתאים ממשק"


def test_a_term_is_not_matched_to_many_more_words_than_it_has():
    from attendance.transcript import correct_transcript
    result = correct_transcript("ההסתברות שהם K-הנה כל", ["inclusive"])
    assert "inclusive" not in result.text


def test_terms_from_slides_skip_pieces_of_sentences():
    from attendance.slides import extract_terms
    terms = extract_terms("Let X be the number of balls. The ball came up heads. Unit Test and Design Pattern.")
    assert "Unit Test" in terms and "Design Pattern" in terms
    assert not any(t in terms for t in ("Let X be", "came up heads", "ball came up heads"))


def test_the_lecturer_can_reject_a_term_and_it_is_no_longer_used():
    import os, sys
    sys.path.insert(0, os.path.dirname(__file__))
    from app import create_app
    from test_flow import TestConfig
    app = create_app(TestConfig)
    lecturer = app.test_client()
    lecturer.get("/lecturer?key=test-key")
    sid = lecturer.post("/api/session", json={"course": "T"}).get_json()["session_id"]
    body = {"raw": "היום נדבר על סטרטגי", "glossary": "Strategy"}
    assert lecturer.post(f"/api/session/{sid}/transcript", json=body).get_json()["fixes"]
    body["exclude"] = ["strategy"]
    assert lecturer.post(f"/api/session/{sid}/transcript", json=body).get_json()["fixes"] == []
