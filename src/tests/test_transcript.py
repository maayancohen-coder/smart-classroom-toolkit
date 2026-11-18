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
