"""In-memory storage. Swappable for a database without touching the domain logic."""
from __future__ import annotations

import csv
import hashlib
import hmac
import json
import os
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


class PinStore:
    """Personal PIN per student: chosen on the first check-in, required on every later one.

    Only a salted hash is kept. Repeated wrong guesses lock the student for a while, so a 4-digit PIN
    cannot be brute-forced from another phone or a private window.
    """
    SET, OK, WRONG, LOCKED = "set", "ok", "wrong", "locked"

    def __init__(self, max_attempts: int = 5, lock_seconds: float = 300, path: str = "", keep_plain: bool = False):
        self._hashes: dict[str, tuple[bytes, bytes]] = {}
        self._plain: dict[str, str] = {}     # demo/testing only: lets the lecturer see what was chosen
        self.path, self.keep_plain = path, keep_plain
        self._load()
        self._failures: dict[str, tuple[int, float]] = {}   # student -> (count, locked_until)
        self.max_attempts = max_attempts
        self.lock_seconds = lock_seconds
        self._lock = threading.Lock()

    def _load(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as handle:
                for key, item in json.load(handle).items():
                    self._hashes[key] = (bytes.fromhex(item["salt"]), bytes.fromhex(item["hash"]))
                    if item.get("plain"):
                        self._plain[key] = item["plain"]
        except (OSError, ValueError, KeyError):
            pass    # a damaged file must not stop the server; passwords are simply chosen again

    def _save(self) -> None:
        if not self.path:
            return
        data = {k: {"salt": s.hex(), "hash": h.hex(), **({"plain": self._plain[k]} if k in self._plain else {})}
                for k, (s, h) in self._hashes.items()}
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as handle:
                json.dump(data, handle)
        except OSError:
            pass

    def chosen(self, key: str) -> Optional[str]:
        """The password as chosen (only when keep_plain is on)."""
        return self._plain.get(key) if self.keep_plain else None

    @staticmethod
    def _hash(pin: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 60_000)

    def check_or_set(self, student_id: str, pin: str) -> str:
        with self._lock:
            count, locked_until = self._failures.get(student_id, (0, 0.0))
            if locked_until > time.time():
                return self.LOCKED
            stored = self._hashes.get(student_id)
            if stored is None:
                salt = secrets.token_bytes(16)
                self._hashes[student_id] = (salt, self._hash(pin, salt))
                if self.keep_plain:
                    self._plain[student_id] = pin
                self._save()
                return self.SET
            if hmac.compare_digest(stored[1], self._hash(pin, stored[0])):
                self._failures.pop(student_id, None)
                return self.OK
            count += 1
            until = time.time() + self.lock_seconds if count >= self.max_attempts else 0.0
            self._failures[student_id] = (0 if until else count, until)
            return self.LOCKED if until else self.WRONG

    def has_pin(self, student_id: str) -> bool:
        return student_id in self._hashes

    def reset(self, student_id: str) -> None:
        with self._lock:
            self._hashes.pop(student_id, None)
            self._plain.pop(student_id, None)
            self._failures.pop(student_id, None)
            self._save()


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, LectureSession] = {}
        self._tickets: dict[str, CheckInTicket] = {}
        self._lock = threading.Lock()

    def add(self, session: LectureSession) -> None:
        self._sessions[session.session_id] = session

    def get(self, session_id: str) -> Optional[LectureSession]:
        return self._sessions.get(session_id)

    def all(self) -> list[LectureSession]:
        return sorted(self._sessions.values(), key=lambda s: s.started_at, reverse=True)

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
