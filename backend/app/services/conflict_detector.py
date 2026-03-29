"""
Conflict Detection Service
===========================
Provides real-time conflict checks BEFORE inserting/updating schedule data.
Returns structured ConflictResult objects that the frontend can display.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import date, time


@dataclass
class ConflictResult:
    has_conflict: bool
    conflicts: List[dict] = field(default_factory=list)

    def add(self, kind: str, message: str, entity_ids: Optional[dict] = None):
        self.conflicts.append({"kind": kind, "message": message, "entities": entity_ids or {}})
        self.has_conflict = True


def check_classroom_conflict(
    classroom_id: int,
    slot_id: int,
    exclude_assignment_id: Optional[int] = None,
) -> ConflictResult:
    from app.models.exam import SessionAssignment, ExamSession, TimeSlot

    result = ConflictResult(has_conflict=False)
    target_slot = TimeSlot.query.get(slot_id)
    if not target_slot:
        return result

    # Find all assignments for this classroom
    query = (
        SessionAssignment.query
        .filter_by(classroom_id=classroom_id)
        .join(ExamSession)
    )
    if exclude_assignment_id:
        query = query.filter(SessionAssignment.id != exclude_assignment_id)

    for assignment in query.all():
        other_slot = assignment.session.time_slot
        if _slots_overlap(target_slot, other_slot):
            conflict_ctx = _describe_assignment_context(assignment)
            result.add(
                "classroom_double_booking",
                f"{conflict_ctx['department']} is already using classroom {assignment.classroom.name} for "
                f"{conflict_ctx['course']} on {other_slot.date} {other_slot.start_time}–{other_slot.end_time}. "
                "Choose a different classroom or a different time slot.",
                {"classroom_id": classroom_id, "conflicting_assignment_id": assignment.id},
            )
    return result


def check_observer_conflict(
    observer_id: int,
    slot_id: int,
    exclude_assignment_id: Optional[int] = None,
) -> ConflictResult:
    from app.models.exam import SessionAssignment, ExamSession, TimeSlot

    result = ConflictResult(has_conflict=False)
    target_slot = TimeSlot.query.get(slot_id)
    if not target_slot:
        return result

    query = SessionAssignment.query.join(ExamSession)
    if exclude_assignment_id:
        query = query.filter(SessionAssignment.id != exclude_assignment_id)

    for assignment in query.all():
        assigned_ids = []
        if assignment.observer_id:
            assigned_ids.append(assignment.observer_id)
        assigned_ids.extend(assignment.get_extra_observer_ids())
        if observer_id not in assigned_ids:
            continue
        other_slot = assignment.session.time_slot
        if _slots_overlap(target_slot, other_slot):
            conflict_ctx = _describe_assignment_context(assignment)
            observer_name = assignment.observer.name if assignment.observer and assignment.observer_id == observer_id else f"Observer {observer_id}"
            if assignment.observer_id != observer_id:
                extra = next((o for o in assignment.extra_observers if o.id == observer_id), None)
                if extra:
                    observer_name = extra.name
            result.add(
                "observer_double_booking",
                f"{conflict_ctx['department']} is already using observer {observer_name} for "
                f"{conflict_ctx['course']} on {other_slot.date} {other_slot.start_time}–{other_slot.end_time}. "
                "Choose a different observer or a different time slot.",
                {"observer_id": observer_id, "conflicting_assignment_id": assignment.id},
            )
    return result


def check_instructor_conflict(
    instructor_id: int,
    slot_id: int,
    exclude_assignment_id: Optional[int] = None,
) -> ConflictResult:
    from app.models.exam import SessionAssignment, ExamSession, TimeSlot

    result = ConflictResult(has_conflict=False)
    target_slot = TimeSlot.query.get(slot_id)
    if not target_slot:
        return result

    query = (
        SessionAssignment.query
        .filter_by(instructor_id=instructor_id)
        .join(ExamSession)
    )
    if exclude_assignment_id:
        query = query.filter(SessionAssignment.id != exclude_assignment_id)

    for assignment in query.all():
        other_slot = assignment.session.time_slot
        if _slots_overlap(target_slot, other_slot):
            conflict_ctx = _describe_assignment_context(assignment)
            result.add(
                "instructor_double_booking",
                f"{conflict_ctx['department']} is already using instructor {assignment.instructor.name} for "
                f"{conflict_ctx['course']} on {other_slot.date} {other_slot.start_time}–{other_slot.end_time}. "
                "Choose a different instructor or a different time slot.",
                {"instructor_id": instructor_id, "conflicting_assignment_id": assignment.id},
            )
    return result


def check_all_conflicts_for_assignment(
    classroom_id: int,
    observer_id: Optional[int],
    extra_observer_ids: Optional[List[int]],
    instructor_id: Optional[int],
    slot_id: int,
    exclude_assignment_id: Optional[int] = None,
) -> ConflictResult:
    """Convenience: run all three checks in one call."""
    result = ConflictResult(has_conflict=False)

    r1 = check_classroom_conflict(classroom_id, slot_id, exclude_assignment_id)
    observer_checks = []
    if observer_id:
        observer_checks.append(check_observer_conflict(observer_id, slot_id, exclude_assignment_id))
    for extra_id in extra_observer_ids or []:
        if not observer_id or extra_id != observer_id:
            observer_checks.append(check_observer_conflict(extra_id, slot_id, exclude_assignment_id))
    r3 = check_instructor_conflict(instructor_id, slot_id, exclude_assignment_id) if instructor_id else ConflictResult(False)

    for r in (r1, *observer_checks, r3):
        result.conflicts.extend(r.conflicts)
    result.has_conflict = bool(result.conflicts)
    return result


def check_session_move_conflicts(session, target_slot_id: int) -> ConflictResult:
    """Validate that moving a session to a new slot will not conflict with existing assignments."""
    result = ConflictResult(has_conflict=False)

    if not session or not target_slot_id or session.time_slot_id == target_slot_id:
        return result

    for assignment in session.assignments:
        assignment_result = check_all_conflicts_for_assignment(
            classroom_id=assignment.classroom_id,
            observer_id=assignment.observer_id,
            extra_observer_ids=assignment.get_extra_observer_ids(),
            instructor_id=assignment.instructor_id,
            slot_id=target_slot_id,
            exclude_assignment_id=assignment.id,
        )
        if assignment_result.conflicts:
            result.conflicts.extend(assignment_result.conflicts)

    result.has_conflict = bool(result.conflicts)
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slots_overlap(a, b) -> bool:
    """True if two TimeSlot ORM objects overlap in time."""
    if a.date != b.date:
        return False
    return a.start_time < b.end_time and b.start_time < a.end_time


def _describe_assignment_context(assignment) -> dict:
    course = assignment.session.exam.course if assignment.session and assignment.session.exam else None
    department = course.department if course else None
    department_name = department.code if department and department.code else (department.name if department else "Another department")
    course_name = course.name if course and course.name else "another exam"
    return {
        "department": department_name,
        "course": course_name,
    }