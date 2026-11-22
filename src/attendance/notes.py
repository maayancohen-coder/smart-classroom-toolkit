"""Live notes from students during a lecture, and messages from students to the lecturer of a course.

Both are kept in memory. Simple limits keep one phone from flooding the lecturer's screen.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

MAX_CHARS = 500
MIN_SECONDS_BETWEEN = 3.0
MAX_PER_LIST = 500


@dataclass
class Note:
    note_id: int
    student_id: str
    name: str            # empty when the student chose to stay anonymous
    text: str
    at: float = field(default_factory=time.time)


class TooFast(Exception):
    pass


class NoteBoard:
    """One board for notes (key = session id) and one for messages (key = course id)."""

    def __init__(self):
        self._items: dict[str, list[Note]] = {}
        self._last: dict[tuple[str, str], float] = {}
        self._lock = threading.Lock()

    def add(self, key: str, student_id: str, name: str, text: str, anonymous: bool = False) -> Note:
        text = (text or "").strip()[:MAX_CHARS]
        if not text:
            raise ValueError("empty")
        with self._lock:
            now = time.time()
            if now - self._last.get((key, student_id), 0.0) < MIN_SECONDS_BETWEEN:
                raise TooFast()
            items = self._items.setdefault(key, [])
            if len(items) >= MAX_PER_LIST:
                raise ValueError("full")
            self._last[(key, student_id)] = now
            note = Note(len(items) + 1, student_id, "" if anonymous else name, text, now)
            items.append(note)
            return note

    def list(self, key: str, after: int = 0) -> list[Note]:
        return [n for n in self._items.get(key, []) if n.note_id > after]

    def by_student(self, key: str, student_id: str) -> list[Note]:
        return [n for n in self._items.get(key, []) if n.student_id == student_id]
