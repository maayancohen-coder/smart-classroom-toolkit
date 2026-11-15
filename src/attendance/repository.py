"""In-memory storage. Swappable for a database without touching the domain logic."""
from __future__ import annotations

import csv
import secrets
import threading
import time
from typing import Optional

from .models import CheckInTicket, LectureSession, Student


class Roster:
    """The official class list (CSV with columns: student_id,name)."""

    def __init__(self, students: list[Student]):
        self._by_id = {s.student_id: s for s in students}

    @classmethod
    def from_csv(cls, path: str) -> "Roster":
        with open(path, newline="", encoding="utf-8-sig") as f:
            rows = csv.DictReader(f)
            return cls([Student(r["student_id"].strip(), r["name"].strip()) for r in rows if r.get("student_id")])

    def get(self, student_id: str) -> Optional[Student]:
        return self._by_id.get(student_id)

    def all(self) -> list[Student]:
        return sorted(self._by_id.values(), key=lambda s: s.name)


class DeviceRegistry:
    """Binds each phone (a random id kept in the browser) to exactly one student."""

    def __init__(self):
        self._device_to_student: dict[str, str] = {}
        self._student_to_device: dict[str, str] = {}
        self._lock = threading.Lock()

    def student_for_device(self, device_id: str) -> Optional[str]:
        return self._device_to_student.get(device_id)

    def device_for_student(self, student_id: str) -> Optional[str]:
        return self._student_to_device.get(student_id)

    def bind_if_free(self, student_id: str, device_id: str) -> bool:
        with self._lock:
            if device_id in self._device_to_student or student_id in self._student_to_device:
                return False
            self._device_to_student[device_id] = student_id
            self._student_to_device[student_id] = device_id
            return True

    def reset_student(self, student_id: str) -> None:
        """Lecturer action when a student legitimately changes phone."""
        with self._lock:
            device = self._student_to_device.pop(student_id, None)
            if device:
                self._device_to_student.pop(device, None)


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, LectureSession] = {}
        self._tickets: dict[str, CheckInTicket] = {}
        self._lock = threading.Lock()

    def add(self, session: LectureSession) -> None:
        self._sessions[session.session_id] = session

    def get(self, session_id: str) -> Optional[LectureSession]:
        return self._sessions.get(session_id)

    def new_ticket(self, session_id: str, token_age: float, ip: str) -> CheckInTicket:
        ticket = CheckInTicket(secrets.token_urlsafe(16), session_id, time.time(), token_age, ip)
        self._tickets[ticket.nonce] = ticket
        return ticket

    def consume_ticket(self, nonce: str, ttl_seconds: float) -> Optional[CheckInTicket]:
        """Single use: a ticket can complete exactly one check-in."""
        with self._lock:
            ticket = self._tickets.get(nonce)
            if ticket is None or ticket.used or time.time() - ticket.scanned_at > ttl_seconds:
                return None
            ticket.used = True
            return ticket

    def peek_ticket(self, nonce: str) -> Optional[CheckInTicket]:
        return self._tickets.get(nonce)
