"""Where the class really is: the centre of the check-ins, not a single GPS fix from the lecturer.

A phone's indoor GPS fix is off by tens of metres, and so is the lecturer's. The *group* of students
is a much better reference: its centre is the median of many fixes, and its spread tells how far from
the group a student can honestly be. Someone who is inside the building's radius but clearly away from
the group (another room, the corridor, the cafeteria) stands out.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Optional

from .geo import haversine_meters


@dataclass(frozen=True)
class ClassCluster:
    lat: float
    lng: float
    radius_m: float     # how far from the centre a student may honestly be (accuracy not included)
    points: int

    def distance_to(self, lat: float, lng: float) -> float:
        return haversine_meters(self.lat, self.lng, lat, lng)

    def is_outside(self, lat: float, lng: float, accuracy: float) -> bool:
        """Outside only if even the best case (the true spot is `accuracy` closer) is beyond the radius."""
        return self.distance_to(lat, lng) - accuracy > self.radius_m


def build_cluster(fixes: list[tuple[float, float, float]], min_points: int,
                  min_radius_m: float, max_accuracy_m: float = 100.0) -> Optional[ClassCluster]:
    """fixes: (lat, lng, accuracy_m) of each student's best reading. None until there are enough points."""
    usable = [f for f in fixes if f[2] <= max_accuracy_m]
    if len(usable) < min_points:
        return None
    lat = statistics.median(f[0] for f in usable)
    lng = statistics.median(f[1] for f in usable)
    typical = statistics.median(haversine_meters(lat, lng, f[0], f[1]) for f in usable)
    # Three times the typical spread plus a margin: tight in a small room, wider in a big hall.
    return ClassCluster(lat, lng, max(min_radius_m, 3 * typical + 15), len(usable))
