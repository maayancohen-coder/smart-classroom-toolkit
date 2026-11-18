"""Homework: assignments per course, student submissions, and checks that need no outside service.

Three checks, all computed locally and explained to the lecturer:
  * similarity of each submission to the lecturer's solution and to the other students' submissions
    (shared three-word sequences; the words of the assignment text itself are ignored);
  * course-content check: how many of the course's key terms the answer uses, and which English technical
    terms it uses that appear nowhere in the course material;
  * both are hints for a human reader, not a grade.
"""
from __future__ import annotations

import re
import secrets
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

TOKEN = re.compile(r"[A-Za-z\u0590-\u05FF_]+|[0-9]+(?:\.[0-9]+)?")
HEBREW_PREFIXES = "הובלמשכ"
SHINGLE = 3
PAIR_FLAG = 0.5          # shared-sequence ratio at which two submissions are shown as "very similar"
KEY_TERMS = 60
MAX_TEXT = 300_000
STOPWORDS = {
    "that", "this", "with", "from", "have", "will", "were", "been", "they", "their", "which", "there",
    "אשר", "היה", "היו", "כמו", "גם", "אבל", "כדי", "כל", "עם", "על", "זה", "זו", "הוא", "היא", "אנו", "אנחנו",
    "שלנו", "שלי", "לאחר", "לפני", "בין", "אותו", "אותה", "הזה", "הזאת", "ניתן", "יש", "אין", "מאוד",
}


COMMON_ENGLISH = set("""
about after also always another because before being between both cannot could does done each either else even
ever every first from further gets give given goes going good great have having here however into just keep kind
know last lets like made make many maybe more most much must need never next only other over part plus really
same should since some still such take than that then there these they thing things think this those through
time under until upon used uses using very want well were what when where whether which while whose will with
within without would write your their them then than also lots lot able above across along already among
around back been come comes down find found goal good help idea implementations implementation just let
long look makes means might note once own point right said says seem show shows small something start
still sure tell these today together took true turn type types understand usually value values way ways
work works yes objects object""".split())


def tokens(text: str) -> list[str]:
    return [t.lower() for t in TOKEN.findall(text or "")]


def shingles(words: list[str], skip: frozenset = frozenset()) -> set[tuple]:
    size = SHINGLE if len(words) >= SHINGLE else 1
    found = {tuple(words[i:i + size]) for i in range(len(words) - size + 1)}
    return found - skip


def similarity(a: set, b: set) -> float:
    """Share of the smaller text's sequences that also appear in the other text (0..1)."""
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def _known(word: str, vocabulary: set[str]) -> bool:
    if word in vocabulary:
        return True
    return len(word) > 4 and word[0] in HEBREW_PREFIXES and word[1:] in vocabulary


def vocabulary_of(text: str) -> set[str]:
    return {w for w in tokens(text) if len(w) >= 3}


def key_terms(text: str, limit: int = KEY_TERMS) -> list[str]:
    """The most frequent meaningful words of the course material (4+ letters, no filler)."""
    counts = Counter(w for w in tokens(text) if len(w) >= 4 and not w.isdigit() and w not in STOPWORDS)
    return [w for w, _ in counts.most_common(limit)]


def english_terms(words: list[str]) -> list[str]:
    return [w for w in dict.fromkeys(words) if len(w) >= 4 and w.isascii() and w.isalpha() and w not in STOPWORDS and w not in COMMON_ENGLISH]


def content_check(text: str, materials: str, extra_known: str = "") -> dict:
    """Course-content check; `materials` is the course material, `extra_known` the assignment text."""
    words = tokens(text)
    used = set(words)
    keys = key_terms(materials)
    vocabulary = vocabulary_of(materials) | vocabulary_of(extra_known)
    covered = [k for k in keys if k in used or any(_known(u, {k}) for u in used if len(u) > 4)]
    outside = [w for w in english_terms(words) if not _known(w, vocabulary)]
    return {
        "has_material": bool(keys),
        "key_terms": len(keys),
        "used": len(covered),
        "coverage": round(100 * len(covered) / len(keys)) if keys else None,
        "missing": [k for k in keys if k not in covered][:12],
        "outside": outside[:12],
    }


@dataclass
class Submission:
    student_id: str
    name: str
    filename: str
    text: str
    submitted_at: float


@dataclass
class Assignment:
    course: str
    title: str
    assignment_text: str = ""
    reference_text: str = ""
    materials_text: str = ""
    assignment_id: str = field(default_factory=lambda: secrets.token_urlsafe(6))
    created_at: float = field(default_factory=time.time)
    submissions: dict[str, Submission] = field(default_factory=dict)


class HomeworkStore:
    def __init__(self):
        self._items: dict[str, Assignment] = {}
        self._lock = threading.Lock()

    def create(self, course: str, title: str) -> Assignment:
        assignment = Assignment(course.strip(), title.strip())
        with self._lock:
            self._items[assignment.assignment_id] = assignment
        return assignment

    def get(self, assignment_id: str) -> Optional[Assignment]:
        return self._items.get(assignment_id)

    def all(self) -> list[Assignment]:
        return sorted(self._items.values(), key=lambda a: a.created_at, reverse=True)

    def courses(self) -> dict[str, list[Assignment]]:
        grouped: dict[str, list[Assignment]] = {}
        for a in self.all():
            grouped.setdefault(a.course, []).append(a)
        return grouped

    def submit(self, assignment: Assignment, student_id: str, name: str, filename: str, text: str) -> bool:
        """Returns True if this replaced an earlier submission of the same student."""
        with self._lock:
            replaced = student_id in assignment.submissions
            assignment.submissions[student_id] = Submission(student_id, name, filename, text[:MAX_TEXT], time.time())
        return replaced


def build_report(assignment: Assignment, threshold: float = PAIR_FLAG) -> dict:
    """Everything the lecturer sees for one assignment."""
    skip = frozenset(shingles(tokens(assignment.assignment_text)))
    reference = shingles(tokens(assignment.reference_text), skip) if assignment.reference_text else None
    subs = list(assignment.submissions.values())
    grams = {s.student_id: shingles(tokens(s.text), skip) for s in subs}
    materials = assignment.materials_text or assignment.reference_text

    pairs = []
    closest: dict[str, tuple[float, Submission]] = {}
    for i, a in enumerate(subs):
        for b in subs[i + 1:]:
            score = similarity(grams[a.student_id], grams[b.student_id])
            if score >= threshold:
                pairs.append({"a": a.name, "a_id": a.student_id, "b": b.name, "b_id": b.student_id,
                              "percent": round(100 * score)})
            for me, other in ((a, b), (b, a)):
                if score > closest.get(me.student_id, (0.0, None))[0]:
                    closest[me.student_id] = (score, other)

    rows = []
    for s in subs:
        check = content_check(s.text, materials, assignment.assignment_text)
        near_score, near = closest.get(s.student_id, (0.0, None))
        rows.append({
            "student_id": s.student_id, "name": s.name, "filename": s.filename, "words": len(tokens(s.text)),
            "vs_reference": round(100 * similarity(grams[s.student_id], reference)) if reference else None,
            "coverage": check["coverage"], "missing": check["missing"], "outside": check["outside"],
            "closest_name": near.name if near else None, "closest_percent": round(100 * near_score),
            "flagged": near_score >= threshold,
        })
    rows.sort(key=lambda r: (-r["closest_percent"], r["name"]))
    pairs.sort(key=lambda p: -p["percent"])
    return {
        "title": assignment.title, "course": assignment.course, "count": len(subs), "threshold": round(100 * threshold),
        "has_reference": reference is not None, "has_materials": bool(key_terms(materials)),
        "rows": rows, "pairs": pairs,
    }
