"""Attendance checks (Strategy pattern).

Each check looks at one signal and returns a CheckResult. Adding a new signal
means adding a class here - the evaluator and the rest of the system do not change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from .geo import haversine_meters, ip_in_networks
from .models import CheckInTicket, CheckResult, LectureSession, LocationReport, Student
from .repository import DeviceRegistry


@dataclass
class CheckContext:
    session: LectureSession
    student: Student
    device_id: str
    ticket: CheckInTicket
    location: LocationReport
    ip: str


class AttendanceCheck(ABC):
    name: str = "check"
    strong: bool = True

    @abstractmethod
    def run(self, ctx: CheckContext) -> CheckResult: ...

    def _ok(self, reason: str = "") -> CheckResult:
        return CheckResult(self.name, True, self.strong, reason)

    def _fail(self, reason: str) -> CheckResult:
        return CheckResult(self.name, False, self.strong, reason)


class TokenFreshnessCheck(AttendanceCheck):
    """Valid but old token -> the QR may have been photographed or streamed."""
    name = "token_freshness"
    strong = False

    def __init__(self, max_age_seconds: float):
        self.max_age = max_age_seconds

    def run(self, ctx: CheckContext) -> CheckResult:
        age = ctx.ticket.token_age_seconds
        if age > self.max_age:
            return self._fail(f"slow QR scan ({age:.1f}s) - possible relay")
        return self._ok()


class DeviceBindingCheck(AttendanceCheck):
    """One phone = one student."""
    name = "device_binding"
    strong = True

    def __init__(self, registry: DeviceRegistry):
        self.registry = registry

    def run(self, ctx: CheckContext) -> CheckResult:
        owner = self.registry.student_for_device(ctx.device_id)
        if owner is not None and owner != ctx.student.student_id:
            return self._fail(f"phone already registered to student {owner}")
        bound_device = self.registry.device_for_student(ctx.student.student_id)
        if bound_device is not None and bound_device != ctx.device_id:
            return self._fail("checked in from a different phone than registered")
        return self._ok()


class GeofenceCheck(AttendanceCheck):
    """The reported location must be inside the classroom's radius."""
    name = "geofence"
    strong = True

    def __init__(self, max_accuracy_meters: float):
        self.max_accuracy = max_accuracy_meters

    def run(self, ctx: CheckContext) -> CheckResult:
        if not ctx.session.has_geofence:
            return self._ok("geofence not configured")
        best = ctx.location.best()
        if ctx.location.denied or best is None:
            return self._fail("location not shared")
        if best.accuracy > self.max_accuracy:
            return self._fail(f"location too imprecise (±{best.accuracy:.0f}m)")
        distance = haversine_meters(ctx.session.center_lat, ctx.session.center_lng, best.lat, best.lng)
        # Give the benefit of the doubt up to the reported accuracy.
        if distance - best.accuracy > ctx.session.radius_meters:
            return self._fail(f"{distance:.0f}m from the classroom")
        return self._ok()


class LocationSpoofCheck(AttendanceCheck):
    """Fake-GPS heuristics: real indoor fixes are imprecise and jitter between readings."""
    name = "location_spoofing"
    strong = True

    def __init__(self, min_plausible_accuracy: float):
        self.min_accuracy = min_plausible_accuracy

    def run(self, ctx: CheckContext) -> CheckResult:
        samples = ctx.location.samples
        if not samples:
            return self._ok()  # missing location is the geofence's concern
        if any(s.accuracy < self.min_accuracy for s in samples):
            return self._fail("unrealistically precise location for indoors")
        if len(samples) >= 3 and len({(s.lat, s.lng) for s in samples}) == 1:
            return self._fail("location frozen across readings")
        return self._ok()


class NetworkCheck(AttendanceCheck):
    """Was the request sent from the campus network? Weak: students on mobile data are legit."""
    name = "campus_network"
    strong = False

    def run(self, ctx: CheckContext) -> CheckResult:
        if not ctx.session.trusted_networks:
            return self._ok("campus network not configured")
        if ip_in_networks(ctx.ip, ctx.session.trusted_networks):
            return self._ok()
        return self._fail("not on the campus network")
