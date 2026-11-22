"""The course catalog: which courses exist, who teaches them and who studies them.

It is read from data/courses.json when the server starts, so it lives in Git and survives every deployment.
A course lists its lecturers by id, and its students either as a list of student ids or as "all" (the whole roster).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from .repository import Roster


@dataclass
class Course:
    course_id: str
    name: str
    lecturer_ids: list[str] = field(default_factory=list)
    student_ids: Optional[list[str]] = None      # None = everyone in the roster

    def has_student(self, student_id: str) -> bool:
        return self.student_ids is None or student_id in self.student_ids


@dataclass
class Lecturer:
    lecturer_id: str
    name: str


class Catalog:
    def __init__(self, courses: list[Course], lecturers: list[Lecturer], roster: Roster):
        self._courses = {c.course_id: c for c in courses}
        self._lecturers = {l.lecturer_id: l for l in lecturers}
        self._roster = roster

    @classmethod
    def from_json(cls, path: str, roster: Roster) -> "Catalog":
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, ValueError):
            raw = {}
        courses = []
        for item in raw.get("courses", []):
            students = item.get("students", "all")
            courses.append(Course(str(item["id"]), str(item["name"]), [str(x) for x in item.get("lecturers", [])],
                                  None if students == "all" else [str(s) for s in students]))
        lecturers = [Lecturer(str(l["id"]), str(l["name"])) for l in raw.get("lecturers", [])]
        return cls(courses, lecturers, roster)

    def get(self, course_id: str) -> Optional[Course]:
        return self._courses.get(course_id)

    def by_name(self, name: str) -> Optional[Course]:
        return next((c for c in self._courses.values() if c.name == name.strip()), None)

    def all(self) -> list[Course]:
        return list(self._courses.values())

    def lecturers(self) -> list[Lecturer]:
        return list(self._lecturers.values())

    def lecturer(self, lecturer_id: str) -> Optional[Lecturer]:
        return self._lecturers.get(lecturer_id)

    def for_lecturer(self, lecturer_id: str) -> list[Course]:
        return [c for c in self._courses.values() if lecturer_id in c.lecturer_ids]

    def for_student(self, student_id: str) -> list[Course]:
        if self._roster.get(student_id) is None:
            return []
        return [c for c in self._courses.values() if c.has_student(student_id)]
