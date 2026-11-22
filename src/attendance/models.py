"""Domain model: plain data classes with no web or storage logic."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AttendanceStatus(Enum):
    PRESENT = "present"
    SUSPECT = "suspect"
    ABSENT = "absent"


@dataclass(frozen=True)
class Student:
    student_id: str
    name: str


@dataclass(frozen=True)
class LocationSample:
    lat: float
    lng: float
    accuracy: float  # meters, as reported by the browser
    timestamp: float  # epoch seconds (client clock)


@dataclass
class LocationReport:
    samples: list[LocationSample] = field(default_factory=list)
    denied: bool = False  # user refused permission or the browser failed

    def best(self) -> Optional[LocationSample]:
        return min(self.samples, key=lambda s: s.accuracy) if self.samples else None


@dataclass
class TokenVerdict:
    valid: bool
    age_seconds: float = 0.0
    reason: str = ""


@dataclass
class CheckInTicket:
    """Created when a student opens a valid QR link; consumed by the check-in submit."""
    nonce: str
    session_id: str
    scanned_at: float
    token_age_seconds: float
    ip: str
    used: bool = False


@dataclass(frozen=True)
class CheckResult:
    check_name: str
    passed: bool
    strong: bool  # a failed strong check alone makes the student a suspect
    reason: str = ""


@dataclass
class CheckIn:
    student: Student
    at: float
    device_id: str
    ip: str
    token_age_seconds: float
    location: Optional[LocationSample]
    distance_meters: Optional[float]
    results: list[CheckResult]
    status: AttendanceStatus
    fingerprint: str = ""
    approved_by_lecturer: bool = False   # the lecturer accepted a suspect check-in
    original_status: Optional[AttendanceStatus] = None   # what the checks decided, to undo an approval

    def failed_reasons(self) -> list[str]:
        return [r.reason for r in self.results if not r.passed]


@dataclass
class RejectedAttempt:
    at: float
    ip: str
    reason: str


@dataclass
class LectureSession:
    session_id: str
    course: str
    secret: bytes
    started_at: float
    center_lat: Optional[float] = None
    center_lng: Optional[float] = None
    radius_meters: float = 120
    trusted_networks: list[str] = field(default_factory=list)  # CIDR strings
    closed: bool = False
    checkins: dict[str, CheckIn] = field(default_factory=dict)  # student_id -> CheckIn
    rejected: list[RejectedAttempt] = field(default_factory=list)
    head_count: Optional[int] = None  # number of people counted in the class photo (the photo is never kept)
    head_count_method: str = ""
    head_count_confidence: str = ""
    head_count_note: str = ""
    transcript_raw: str = ""        # what the speech recognition heard
    transcript_corrected: str = ""  # after the glossary correction
    transcript_glossary: str = ""
    course_id: str = ""             # the catalog course this lecture belongs to ("" = free-text course name)
    summary_published: bool = False  # the lecturer decides when students may see the summary
    slides_name: str = ""
    slides_text: str = ""           # text of the uploaded slides (the file itself is not kept)

    @property
    def has_geofence(self) -> bool:
        return self.center_lat is not None and self.center_lng is not None
