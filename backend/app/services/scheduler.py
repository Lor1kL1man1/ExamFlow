"""
ExamFlow Scheduling Engine
==========================

Algorithm overview
------------------
Input:
  - A list of Exam objects (each with student_count, duration_minutes, course)
  - Available TimeSlots (manager-defined date/time windows)
  - Available Classrooms (with capacities)
  - Available Observers and Instructors

Output:
  - ExamSession + SessionAssignment rows written to the database

Strategy (greedy with constraint propagation)
---------------------------------------------
1. Sort exams by student_count DESC (largest first — hardest to place).
2. For each exam, try to fit ALL students into a single time slot
   using multiple rooms in parallel (preferred — "minimize sessions").
3. If no single slot fits (no combination of rooms has enough total capacity),
   split the exam across the minimum number of time slots required.
4. Within each slot, greedily assign rooms largest-first.
5. After room assignment, assign observers (round-robin from available pool,
   checking no double-booking within that time slot).
6. Attach the exam's primary instructor to each session (also double-booking checked).

Conflict definitions
--------------------
- Classroom conflict  : same classroom, overlapping time slots
- Observer conflict   : same observer, overlapping time slots
- Instructor conflict : same instructor, overlapping time slots
Two time slots overlap when their date is the same AND their time ranges intersect.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from datetime import date, time
from collections import defaultdict


# ---------------------------------------------------------------------------
# Pure-Python conflict checker (no DB dependency — testable in isolation)
# ---------------------------------------------------------------------------

@dataclass
class SlotInfo:
    id: int
    date: date
    start: time
    end: time

    def overlaps(self, other: "SlotInfo") -> bool:
        if self.date != other.date:
            return False
        # Two intervals [s1,e1] and [s2,e2] overlap iff s1 < e2 AND s2 < e1
        return self.start < other.end and other.start < self.end


@dataclass
class RoomInfo:
    id: int
    capacity: int
    name: str


@dataclass
class PersonInfo:
    id: int
    name: str


@dataclass
class ExamRequest:
    exam_id: int
    student_count: int
    duration_minutes: int
    instructor_ids: List[int]   # primary instructors (from course)
    academic_year: Optional[int] = None
    priority: int = 0           # higher = schedule first


@dataclass
class RoomAssignment:
    room_id: int
    observer_id: Optional[int]
    instructor_id: Optional[int]
    students_in_room: int


@dataclass
class SessionPlan:
    slot_id: int
    session_index: int          # 0-based, >0 means exam was split
    assignments: List[RoomAssignment]
    assigned_students: int


@dataclass
class SchedulePlan:
    exam_id: int
    sessions: List[SessionPlan]
    warnings: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Booking registries — track what is already booked
# ---------------------------------------------------------------------------

class BookingRegistry:
    """In-memory registry used during a single scheduling run."""

    def __init__(self, slots: List[SlotInfo]):
        self._slots: Dict[int, SlotInfo] = {s.id: s for s in slots}
        # room_id -> list of slot_ids already booked
        self._room_bookings: Dict[int, List[int]] = {}
        # person_id -> list of slot_ids already booked
        self._person_bookings: Dict[int, List[int]] = {}

    def _slot_conflicts(self, slot_id: int, booked_slot_ids: List[int]) -> bool:
        candidate = self._slots[slot_id]
        return any(candidate.overlaps(self._slots[sid]) for sid in booked_slot_ids)

    def room_available(self, room_id: int, slot_id: int) -> bool:
        booked = self._room_bookings.get(room_id, [])
        return not self._slot_conflicts(slot_id, booked)

    def person_available(self, person_id: int, slot_id: int) -> bool:
        booked = self._person_bookings.get(person_id, [])
        return not self._slot_conflicts(slot_id, booked)

    def book_room(self, room_id: int, slot_id: int):
        self._room_bookings.setdefault(room_id, []).append(slot_id)

    def book_person(self, person_id: int, slot_id: int):
        self._person_bookings.setdefault(person_id, []).append(slot_id)

    def snapshot(self) -> Tuple[Dict, Dict]:
        """Return a deep-copy snapshot for backtracking."""
        import copy
        return (copy.deepcopy(self._room_bookings), copy.deepcopy(self._person_bookings))

    def restore(self, snapshot: Tuple[Dict, Dict]):
        self._room_bookings, self._person_bookings = snapshot


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------

class ExamScheduler:
    def __init__(
        self,
        slots: List[SlotInfo],
        rooms: List[RoomInfo],
        observers: List[PersonInfo],
        observer_targets: Optional[Dict[int, int]] = None,
        year_day_counts: Optional[Dict[int, Dict[date, int]]] = None,
        existing_registry: Optional[BookingRegistry] = None,
    ):
        self.slots = slots
        # Rooms sorted by capacity DESC for greedy filling
        self.rooms = sorted(rooms, key=lambda r: r.capacity, reverse=True)
        self.observers = observers
        self.observer_targets = observer_targets or {}
        self.observer_assignment_counts = {o.id: 0 for o in observers}
        self.observer_exam_ids = {o.id: set() for o in observers}
        self.year_day_counts = defaultdict(lambda: defaultdict(int))
        for year, counts in (year_day_counts or {}).items():
            for day, value in counts.items():
                self.year_day_counts[year][day] = value
        self.registry = existing_registry or BookingRegistry(slots)

    def _ordered_slots_for_exam(self, exam: ExamRequest) -> List[SlotInfo]:
        """Prefer dates not yet used by the same academic year; otherwise maximize spacing."""
        year = getattr(exam, "academic_year", None)
        if not year:
            return list(self.slots)

        year_counts = self.year_day_counts.get(year, {})
        used_dates = list(year_counts.keys())

        def sort_key(slot: SlotInfo):
            same_day_count = year_counts.get(slot.date, 0)
            min_gap = min((abs((slot.date - d).days) for d in used_dates), default=9999)
            return (same_day_count, -min_gap, slot.date, slot.start)

        return sorted(self.slots, key=sort_key)

    def _record_exam_dates(self, exam: ExamRequest, sessions: List[SessionPlan]):
        year = getattr(exam, "academic_year", None)
        if not year:
            return
        seen_dates = set()
        for session in sessions:
            slot = self.registry._slots.get(session.slot_id)
            if slot and slot.date not in seen_dates:
                self.year_day_counts[year][slot.date] += 1
                seen_dates.add(slot.date)

    def _pick_observer(self, slot_id: int) -> Optional[int]:
        """Pick an available observer, prioritizing unmet target counts when provided."""
        available = [o for o in self.observers if self.registry.person_available(o.id, slot_id)]
        if not available:
            return None

        if self.observer_targets:
            with_deficit = []
            for o in available:
                target = self.observer_targets.get(o.id, 0)
                current = len(self.observer_exam_ids.get(o.id, set()))
                deficit = target - current
                if deficit > 0:
                    with_deficit.append((deficit, -current, o.id))
            if with_deficit:
                with_deficit.sort(reverse=True)
                return with_deficit[0][2]

        # Fallback: least-used available observer first
        available.sort(key=lambda o: (self.observer_assignment_counts.get(o.id, 0), o.id))
        return available[0].id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def schedule(self, exams: List[ExamRequest]) -> List[SchedulePlan]:
        """Schedule all exams and return a list of SchedulePlans."""
        # Sort: largest exams first, then by explicit priority
        sorted_exams = sorted(exams, key=lambda e: (-e.student_count, -e.priority))
        results = []
        for exam in sorted_exams:
            plan = self._schedule_exam(exam)
            results.append(plan)
        return results

    # ------------------------------------------------------------------
    # Internal logic
    # ------------------------------------------------------------------

    def _schedule_exam(self, exam: ExamRequest) -> SchedulePlan:
        warnings = []
        candidate_slots = self._ordered_slots_for_exam(exam)

        # ---- Try to fit in ONE slot (parallel rooms) ----
        for slot in candidate_slots:
            plan = self._try_single_slot(exam, slot)
            if plan:
                result = SchedulePlan(exam_id=exam.exam_id, sessions=[plan], warnings=warnings)
                self._record_exam_dates(exam, result.sessions)
                return result

        # ---- Fallback: split across minimum number of slots ----
        warnings.append(
            f"Exam {exam.exam_id}: could not fit in a single slot — splitting across sessions."
        )
        sessions = self._split_across_slots(exam, warnings, candidate_slots)
        result = SchedulePlan(exam_id=exam.exam_id, sessions=sessions, warnings=warnings)
        self._record_exam_dates(exam, result.sessions)
        return result

    def _try_single_slot(
        self, exam: ExamRequest, slot: SlotInfo
    ) -> Optional[SessionPlan]:
        """
        Try to cover exam.student_count students using available rooms in `slot`.
        Returns a SessionPlan if successful, else None.
        Modifies registry only on success.
        """
        available_rooms = [
            r for r in self.rooms if self.registry.room_available(r.id, slot.id)
        ]
        total_capacity = sum(r.capacity for r in available_rooms)
        if total_capacity < exam.student_count:
            return None  # Not enough room even if we use all

        snapshot = self.registry.snapshot()
        assignments, remaining = self._assign_rooms_greedy(
            available_rooms, exam.student_count, slot.id, exam.instructor_ids, exam.exam_id
        )
        if remaining > 0:
            self.registry.restore(snapshot)
            return None

        return SessionPlan(
            slot_id=slot.id,
            session_index=0,
            assignments=assignments,
            assigned_students=exam.student_count,
        )

    def _split_across_slots(
        self, exam: ExamRequest, warnings: List[str], candidate_slots: List[SlotInfo]
    ) -> List[SessionPlan]:
        """
        Split exam.student_count across multiple time slots.
        Greedy: fill as many students as possible per slot.
        """
        remaining = exam.student_count
        sessions = []
        idx = 0

        for slot in candidate_slots:
            if remaining <= 0:
                break
            available_rooms = [
                r for r in self.rooms if self.registry.room_available(r.id, slot.id)
            ]
            if not available_rooms:
                continue

            batch = min(remaining, sum(r.capacity for r in available_rooms))
            if batch == 0:
                continue

            assignments, leftover = self._assign_rooms_greedy(
                available_rooms, batch, slot.id, exam.instructor_ids, exam.exam_id
            )
            placed = batch - leftover
            remaining -= placed
            sessions.append(
                SessionPlan(
                    slot_id=slot.id,
                    session_index=idx,
                    assignments=assignments,
                    assigned_students=placed,
                )
            )
            idx += 1

        if remaining > 0:
            warnings.append(
                f"Exam {exam.exam_id}: {remaining} students could NOT be scheduled — "
                "insufficient capacity across all slots."
            )
        return sessions

    def _assign_rooms_greedy(
        self,
        rooms: List[RoomInfo],
        students_needed: int,
        slot_id: int,
        instructor_ids: List[int],
        exam_id: int,
    ) -> Tuple[List[RoomAssignment], int]:
        """
        Fill rooms largest-first until students_needed is covered.
        Returns (list_of_assignments, students_still_unplaced).
        Side-effect: updates registry for rooms, observers, instructors booked.
        """
        assignments = []
        remaining = students_needed
        primary_instructor = instructor_ids[0] if instructor_ids else None

        for room in rooms:
            if remaining <= 0:
                break

            # Skip rooms already booked (should already be filtered, defensive check)
            if not self.registry.room_available(room.id, slot_id):
                continue

            in_room = min(room.capacity, remaining)

            # --- Observer assignment ---
            observer_id = self._pick_observer(slot_id)
            if observer_id is not None:
                self.registry.book_person(observer_id, slot_id)
                self.observer_assignment_counts[observer_id] = self.observer_assignment_counts.get(observer_id, 0) + 1
                self.observer_exam_ids.setdefault(observer_id, set()).add(exam_id)
            # (If all observers are booked, observer_id stays None — flagged as warning)

            # --- Instructor conflict check ---
            assigned_instructor = None
            if primary_instructor and self.registry.person_available(primary_instructor, slot_id):
                assigned_instructor = primary_instructor
                self.registry.book_person(primary_instructor, slot_id)

            self.registry.book_room(room.id, slot_id)
            assignments.append(
                RoomAssignment(
                    room_id=room.id,
                    observer_id=observer_id,
                    instructor_id=assigned_instructor,
                    students_in_room=in_room,
                )
            )
            remaining -= in_room

        return assignments, remaining


# ---------------------------------------------------------------------------
# DB-backed scheduler runner (Flask app context required)
# ---------------------------------------------------------------------------

def build_schedule_from_db(
    exam_ids: Optional[List[int]] = None,
    workspace_id: Optional[int] = None,
    include_all_exams: bool = False,
    update_exam_status: bool = True,
) -> List[SchedulePlan]:
    """
    Load data from DB, run scheduler, persist results.
    Call from within a Flask app context.
    Only operates on the currently active period.
    """
    from app.models import db, Exam, ExamSession, SessionAssignment, TimeSlot, Classroom, User
    from app.models.user import UserRole
    from app.models.exam import ExamStatus
    from app.models.period import Period

    # ---- Active period ----
    active_period = Period.query.filter_by(is_active=True).first()

    # ---- Load slots (active period + active slot type only) ----
    slot_q = TimeSlot.query.order_by(TimeSlot.date, TimeSlot.start_time)
    if active_period:
        slot_q = slot_q.filter_by(period_id=active_period.id)
        active_type = active_period.active_slot_type or "midterm"
        slot_q = slot_q.filter_by(slot_type=active_type)
    raw_slots = slot_q.all()
    slots = [SlotInfo(s.id, s.date, s.start_time, s.end_time) for s in raw_slots]

    # ---- Load rooms ----
    raw_rooms = Classroom.query.filter_by(is_active=True).all()
    rooms = [RoomInfo(r.id, r.capacity, r.name) for r in raw_rooms]

    # ---- Load observers ----
    raw_obs = User.query.filter_by(role=UserRole.OBSERVER, is_active=True).all()
    observers = [PersonInfo(u.id, u.name) for u in raw_obs]

    # ---- Load exams ----
    query = Exam.query
    if not include_all_exams:
        query = query.filter(Exam.status.in_([ExamStatus.DRAFT, ExamStatus.CONFLICT]))
    if active_period:
        query = query.filter_by(period_id=active_period.id)
    if exam_ids:
        query = query.filter(Exam.id.in_(exam_ids))
    raw_exams = query.all()

    # ---- Pre-load existing bookings + same-year day usage into registry ----
    # (so re-scheduling doesn't double-book already-placed sessions in this period)
    registry = BookingRegistry(slots)
    year_day_counts = defaultdict(lambda: defaultdict(int))
    if active_period:
        existing_sessions = (
            ExamSession.query
            .join(Exam)
            .filter(Exam.period_id == active_period.id)
            .all()
        )
        if workspace_id is not None:
            existing_sessions = [s for s in existing_sessions if s.workspace_id == workspace_id]
        else:
            existing_sessions = [s for s in existing_sessions if s.workspace_id is None and s.exam.status == ExamStatus.SCHEDULED]
        for sess in existing_sessions:
            if sess.time_slot_id in registry._slots:
                year = sess.exam.course.year if sess.exam and sess.exam.course else None
                if year and sess.time_slot and sess.time_slot.date:
                    year_day_counts[year][sess.time_slot.date] += 1
                for assign in sess.assignments:
                    registry.book_room(assign.classroom_id, sess.time_slot_id)
                    if assign.observer_id:
                        registry.book_person(assign.observer_id, sess.time_slot_id)
                    if assign.instructor_id:
                        registry.book_person(assign.instructor_id, sess.time_slot_id)

    requests = [
        ExamRequest(
            exam_id=e.id,
            student_count=e.student_count,
            duration_minutes=e.duration_minutes,
            instructor_ids=[u.id for u in e.course.instructors],
            academic_year=e.course.year,
        )
        for e in raw_exams
    ]

    if not slots:
        # No timeslots — reset all target exams back to DRAFT (not CONFLICT)
        for e in raw_exams:
            e.status = ExamStatus.DRAFT
        db.session.commit()
        return [SchedulePlan(
            exam_id=0,
            sessions=[],
            warnings=["No time slots found for the active period. Add time slots first."]
        )]

    # ---- Run scheduler ----
    scheduler = ExamScheduler(slots, rooms, observers, year_day_counts=year_day_counts, existing_registry=registry)
    plans = scheduler.schedule(requests)

    # ---- Persist ----
    _persist_plans(plans, db, workspace_id=workspace_id, update_exam_status=update_exam_status)

    return plans


def _persist_plans(
    plans: List[SchedulePlan],
    db,
    workspace_id: Optional[int] = None,
    update_exam_status: bool = True,
):
    from app.models.exam import ExamSession, SessionAssignment, ExamStatus, Exam

    for plan in plans:
        if plan.exam_id == 0:
            continue  # sentinel plan (e.g. "no timeslots" notice)
        exam = Exam.query.get(plan.exam_id)
        if not exam:
            continue
        # Remove old assignments then sessions (bulk delete bypasses ORM cascade)
        old_sessions_q = ExamSession.query.filter_by(exam_id=plan.exam_id)
        if workspace_id is None:
            old_sessions_q = old_sessions_q.filter(ExamSession.workspace_id.is_(None))
        else:
            old_sessions_q = old_sessions_q.filter_by(workspace_id=workspace_id)

        old_session_ids = [s.id for s in old_sessions_q.all()]
        if old_session_ids:
            SessionAssignment.query.filter(
                SessionAssignment.session_id.in_(old_session_ids)
            ).delete(synchronize_session=False)
        old_sessions_q.delete(synchronize_session=False)

        if not plan.sessions:
            # Could not place a single student — true conflict
            if update_exam_status:
                exam.status = ExamStatus.CONFLICT
        else:
            for sp in plan.sessions:
                session = ExamSession(
                    exam_id=plan.exam_id,
                    workspace_id=workspace_id,
                    time_slot_id=sp.slot_id,
                    assigned_students=sp.assigned_students,
                    session_index=sp.session_index,
                )
                db.session.add(session)
                db.session.flush()  # get session.id

                for ra in sp.assignments:
                    sa = SessionAssignment(
                        session_id=session.id,
                        classroom_id=ra.room_id,
                        observer_id=ra.observer_id,
                        instructor_id=ra.instructor_id,
                        students_in_room=ra.students_in_room,
                    )
                    db.session.add(sa)

            # Only mark CONFLICT if students could genuinely not be placed
            # "splitting" warnings are informational — exam is still fully scheduled
            has_unplaced = any("could NOT be scheduled" in w for w in plan.warnings)
            if update_exam_status:
                exam.status = ExamStatus.CONFLICT if has_unplaced else ExamStatus.SCHEDULED

    db.session.commit()