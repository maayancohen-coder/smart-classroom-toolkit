"""Application service: the use cases (open session, scan QR, check in, report)."""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Optional

from .checks import (CheckContext, DeviceBindingCheck, DuplicateCoordinatesCheck, FrozenLocationCheck,
                     GeofenceCheck, LocationSpoofCheck, NetworkCheck, RapidRepeatCheck,
                     SharedFingerprintCheck, StaleLocationCheck, TokenFreshnessCheck)
from .cluster import ClassCluster, build_cluster
from .config import Config
from .evaluator import AttendanceEvaluator
from .counting import CountResult, PeopleCounter
from .geo import haversine_meters, ip_in_networks, network_of
from .headcount import HeadCountSummary, summarize
from .models import (AttendanceStatus, CheckIn, CheckInTicket, LectureSession, LocationReport,
                     RejectedAttempt, Student)
from .repository import DeviceRegistry, PinStore, Roster, SessionStore
from .tokens import TokenService


class CheckInError(Exception):
    """A check-in that is refused outright (not merely suspicious)."""


@dataclass
class CheckInOutcome:
    student: Student
    already_checked_in: bool


class AttendanceService:
    def __init__(self, config: type[Config], roster: Roster, registry: DeviceRegistry,
                 store: SessionStore, tokens: TokenService, counter: Optional[PeopleCounter] = None):
        self.config = config
        self.roster = roster
        self.registry = registry
        self.store = store
        self.tokens = tokens
        self.counter = counter
        self.pins = PinStore(config.PIN_MAX_ATTEMPTS, config.PIN_LOCK_SECONDS)
        self.evaluator = AttendanceEvaluator([
            TokenFreshnessCheck(config.MAX_TOKEN_AGE_SECONDS),
            DeviceBindingCheck(registry),
            GeofenceCheck(config.MAX_LOCATION_ACCURACY_METERS),
            LocationSpoofCheck(config.MIN_PLAUSIBLE_ACCURACY_METERS),
            FrozenLocationCheck(),
            DuplicateCoordinatesCheck(),
            StaleLocationCheck(config.STALE_FIX_SECONDS),
            SharedFingerprintCheck(),
            RapidRepeatCheck(config.RAPID_REPEAT_SECONDS),
            NetworkCheck(),
        ])

    # ---- lecturer ----------------------------------------------------------------
    def open_session(self, course: str, lecturer_ip: str, lat: Optional[float],
                     lng: Optional[float], radius: Optional[float]) -> LectureSession:
        trusted = list(self.config.CAMPUS_NETWORKS)
        # The lecturer opens the session from the classroom, so their network is the campus network.
        # Private/loopback addresses (local testing) are skipped - they say nothing about the campus.
        if lecturer_ip and not ip_in_networks(lecturer_ip, ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
                                                            "127.0.0.0/8", "::1/128", "fc00::/7"]):
            trusted.append(network_of(lecturer_ip))
        session = LectureSession(
            session_id=secrets.token_urlsafe(6),
            course=course.strip() or "Lecture",
            secret=self.tokens.new_secret(),
            started_at=time.time(),
            center_lat=lat, center_lng=lng,
            radius_meters=radius or self.config.DEFAULT_RADIUS_METERS,
            trusted_networks=trusted,
        )
        self.store.add(session)
        return session

    def close_session(self, session: LectureSession) -> None:
        session.closed = True

    def current_qr_path(self, session: LectureSession) -> tuple[str, float]:
        slot, signature, expires_in = self.tokens.current(session.secret, session.session_id)
        return f"/c/{session.session_id}/{slot}/{signature}", expires_in

    # ---- student -----------------------------------------------------------------
    def scan(self, session_id: str, slot: int, signature: str, ip: str) -> CheckInTicket:
        session = self.store.get(session_id)
        if session is None or session.closed:
            raise CheckInError("השיעור לא פעיל")
        verdict = self.tokens.verify(session.secret, session_id, slot, signature)
        if not verdict.valid:
            session.rejected.append(RejectedAttempt(time.time(), ip, verdict.reason))
            raise CheckInError("הקוד פג תוקף. סרקו שוב את הקוד שעל המסך.")
        return self.store.new_ticket(session_id, verdict.age_seconds, ip)

    def check_in(self, nonce: str, device_id: str, student_id: Optional[str],
                 location: LocationReport, ip: str, fingerprint: str = "",
                 client_now: Optional[float] = None, pin: Optional[str] = None) -> CheckInOutcome:
        ticket = self.store.consume_ticket(nonce, self.config.TICKET_TTL_SECONDS)
        if ticket is None:
            raise CheckInError("פג הזמן לסימון. סרקו שוב את הקוד שעל המסך.")
        session = self.store.get(ticket.session_id)
        if session is None or session.closed:
            raise CheckInError("השיעור לא פעיל")

        student_id = student_id or self.registry.student_for_device(device_id)
        student = self.roster.get(student_id) if student_id else None
        if student is None:
            ticket.used = False  # let them fix a typo without rescanning
            raise CheckInError("מספר הסטודנט לא נמצא ברשימת הכיתה")

        if self.config.BLOCK_WITHOUT_LOCATION and session.has_geofence \
                and (location.denied or not location.samples):
            ticket.used = False
            raise CheckInError("יש לאשר גישה למיקום בדפדפן כדי לסמן נוכחות. אשרו ונסו שוב.")

        pin_verified = False
        if self.config.REQUIRE_PIN:
            pin = (pin or "").strip()
            if not (pin.isdigit() and 4 <= len(pin) <= 6):
                ticket.used = False
                raise CheckInError("יש להזין קוד אישי של 4 עד 6 ספרות")
            verdict = self.pins.check_or_set(student.student_id, pin)
            if verdict == PinStore.LOCKED:
                ticket.used = False
                raise CheckInError("יותר מדי ניסיונות שגויים. נסו שוב בעוד כמה דקות או פנו למרצה.")
            if verdict == PinStore.WRONG:
                ticket.used = False
                raise CheckInError("קוד אישי שגוי")
            pin_verified = True

        if student.student_id in session.checkins:
            return CheckInOutcome(student, already_checked_in=True)

        ctx = CheckContext(session, student, device_id, ticket, location, ip, fingerprint, client_now,
                           pin_verified)
        status, results = self.evaluator.evaluate(ctx)

        best = location.best()
        distance = (haversine_meters(session.center_lat, session.center_lng, best.lat, best.lng)
                    if best and session.has_geofence else None)
        session.checkins[student.student_id] = CheckIn(
            student=student, at=time.time(), device_id=device_id, ip=ip,
            token_age_seconds=ticket.token_age_seconds, location=best,
            distance_meters=distance, results=results, status=status, fingerprint=fingerprint,
        )
        # Register the phone only after evaluation, and only if nobody owns it yet.
        self.registry.bind_if_free(student.student_id, device_id)
        return CheckInOutcome(student, already_checked_in=False)

    def reset_student(self, student_id: str) -> None:
        """Lecturer action: forget the phone and the PIN (new phone, forgotten PIN)."""
        self.registry.reset_student(student_id)
        self.pins.reset(student_id)

    def student_for_device(self, device_id: str) -> Optional[Student]:
        sid = self.registry.student_for_device(device_id)
        return self.roster.get(sid) if sid else None

    # ---- head count --------------------------------------------------------------
    def count_photo(self, session: LectureSession, image: bytes, mime: str) -> CountResult:
        """Count people in the photo. The image bytes are not stored anywhere; only the number is kept."""
        if self.counter is None:
            raise CheckInError("לא הוגדר שירות ספירה. אפשר להזין את המספר ידנית.")
        result = self.counter.count(image, mime)
        self.record_head_count(session, result)
        return result

    def record_head_count(self, session: LectureSession, result: CountResult) -> None:
        session.head_count = result.count
        session.head_count_method = result.method
        session.head_count_confidence = result.confidence
        session.head_count_note = result.note

    def head_count_summary(self, session: LectureSession) -> Optional[HeadCountSummary]:
        if session.head_count is None:
            return None
        return summarize(list(session.checkins.values()), session.head_count, session.head_count_method,
                         self.config.HEADCOUNT_TOLERANCE_PERCENT, session.head_count_confidence,
                         session.head_count_note)

    # ---- class group -------------------------------------------------------------
    def class_cluster(self, session: LectureSession) -> Optional[ClassCluster]:
        fixes = [(c.location.lat, c.location.lng, c.location.accuracy)
                 for c in session.checkins.values() if c.location]
        return build_cluster(fixes, self.config.CLUSTER_MIN_POINTS, self.config.CLUSTER_MIN_RADIUS_METERS)

    # ---- report ------------------------------------------------------------------
    def report_rows(self, session: LectureSession) -> list[dict]:
        rows = []
        cluster = self.class_cluster(session)
        for student in self.roster.all():
            checkin = session.checkins.get(student.student_id)
            if checkin is None:
                rows.append({"student_id": student.student_id, "name": student.name,
                             "status": AttendanceStatus.ABSENT.value, "time": None,
                             "distance_m": None, "token_age_s": None, "notes": "", "zone": ""})
                continue
            rows.append({
                "student_id": student.student_id, "name": student.name,
                "status": checkin.status.value, "time": checkin.at,
                "distance_m": round(checkin.distance_meters) if checkin.distance_meters is not None else None,
                "token_age_s": round(checkin.token_age_seconds, 1),
                "notes": "; ".join(checkin.failed_reasons()), "zone": "",
            })
            loc = checkin.location
            if cluster and loc and cluster.is_outside(loc.lat, loc.lng, loc.accuracy):
                # Inside the building radius but away from where the class actually sits.
                row = rows[-1]
                where = "nearby" if (checkin.distance_meters is None
                                     or checkin.distance_meters - loc.accuracy <= session.radius_meters) else "far"
                row["zone"] = where
                extra = f"outside the class group ({cluster.distance_to(loc.lat, loc.lng):.0f}m from its centre)"
                row["notes"] = (row["notes"] + "; " if row["notes"] else "") + extra
                if row["status"] == AttendanceStatus.PRESENT.value:
                    row["status"] = AttendanceStatus.SUSPECT.value
        order = {"suspect": 0, "absent": 1, "present": 2}
        return sorted(rows, key=lambda r: (order[r["status"]], r["name"]))
