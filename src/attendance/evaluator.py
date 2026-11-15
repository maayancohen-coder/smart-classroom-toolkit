"""Combines the results of all checks into one status."""
from .checks import AttendanceCheck, CheckContext
from .models import AttendanceStatus, CheckResult


class AttendanceEvaluator:
    """Rule: one failed strong check, or WEAK_FAILURES_FOR_SUSPECT failed weak checks -> SUSPECT."""

    WEAK_FAILURES_FOR_SUSPECT = 2

    def __init__(self, checks: list[AttendanceCheck]):
        self.checks = checks

    def evaluate(self, ctx: CheckContext) -> tuple[AttendanceStatus, list[CheckResult]]:
        results = [check.run(ctx) for check in self.checks]
        failed = [r for r in results if not r.passed]
        strong_failures = [r for r in failed if r.strong]
        weak_failures = [r for r in failed if not r.strong]
        if strong_failures or len(weak_failures) >= self.WEAK_FAILURES_FOR_SUSPECT:
            return AttendanceStatus.SUSPECT, results
        return AttendanceStatus.PRESENT, results
