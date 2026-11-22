"""Head-count gap: how many people checked in versus how many are really in the room."""
from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class HeadCountSummary:
    counted: int
    checkins: int
    gap: int                 # checkins - counted (positive: more check-ins than people in the room)
    allowed: int             # tolerance in people
    verdict: str             # "ok" | "gap" | "more_counted"
    method: str
    confidence: str = ""
    note: str = ""
    highlight_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def allowed_gap(checkins: int, tolerance_percent: float) -> int:
    """Tolerance for people who are hard to count (back rows, partly hidden): a share of the check-ins."""
    return math.floor(checkins * tolerance_percent / 100)


def suspicion_score(checkin) -> tuple[int, int]:
    """Higher = more suspicious. (strong failures, weak failures); used only to rank, never to accuse."""
    failed = [r for r in checkin.results if not r.passed]
    return (sum(1 for r in failed if r.strong), sum(1 for r in failed if not r.strong))


def rank_suspects(checkins: list, how_many: int) -> list[str]:
    """The `how_many` check-ins with the most failed signals (ties: the largest distance first)."""
    scored = [(suspicion_score(c), c.distance_meters or 0, c.student.student_id) for c in checkins]
    scored = [item for item in scored if item[0] != (0, 0)]
    scored.sort(reverse=True)
    return [student_id for _, _, student_id in scored[:max(how_many, 0)]]


def summarize(checkins: list, counted: int, method: str, tolerance_percent: float,
              confidence: str = "", note: str = "") -> HeadCountSummary:
    total = len(checkins)
    gap = total - counted
    allowed = allowed_gap(total, tolerance_percent)
    if gap > allowed:
        verdict, highlights = "gap", rank_suspects(checkins, gap)
    elif gap < 0:
        verdict, highlights = "more_counted", []
    else:
        verdict, highlights = "ok", []
    return HeadCountSummary(counted, total, gap, allowed, verdict, method, confidence, note, highlights)
