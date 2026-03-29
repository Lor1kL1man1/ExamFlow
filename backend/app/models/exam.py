from ..base import db
from datetime import datetime
import enum
import json


class ExamStatus(enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    CONFLICT = "conflict"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SlotType(enum.Enum):
    MIDTERM = "midterm"
    FINAL   = "final"


class TimeSlot(db.Model):
    """Manager-defined time windows in which exams can be placed."""
    __tablename__ = "time_slots"

    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(80))          # e.g. "Morning Block A"
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    period_id  = db.Column(db.Integer, db.ForeignKey("periods.id"), nullable=True)
    slot_type  = db.Column(db.String(10), nullable=False, default="midterm")  # "midterm"|"final"

    period   = db.relationship("Period", back_populates="time_slots")
    sessions = db.relationship("ExamSession", back_populates="time_slot")

    def to_dict(self):
        return {
            "id": self.id,
            "label": self.label,
            "date": str(self.date),
            "start_time": str(self.start_time),
            "end_time": str(self.end_time),
            "slot_type": self.slot_type or "midterm",
        }


class Exam(db.Model):
    """
    An exam represents a course's examination event.
    It may be split into multiple ExamSessions (one per room/time block).
    """
    __tablename__ = "exams"

    id = db.Column(db.Integer, primary_key=True)
    course_id  = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    period_id  = db.Column(db.Integer, db.ForeignKey("periods.id"), nullable=True)
    duration_minutes = db.Column(db.Integer, default=120)
    student_count = db.Column(db.Integer, nullable=False)  # snapshot at creation
    status = db.Column(db.Enum(ExamStatus), default=ExamStatus.DRAFT)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    course   = db.relationship("Course",  back_populates="exams")
    period   = db.relationship("Period",  back_populates="exams")
    sessions = db.relationship("ExamSession", back_populates="exam", cascade="all, delete-orphan")

    @property
    def is_fully_assigned(self):
        assigned = sum(s.assigned_students for s in self.sessions if s.assigned_students)
        return assigned >= self.student_count

    def to_dict(self, include_sessions=False):
        d = {
            "id": self.id,
            "course_id": self.course_id,
            "course": self.course.to_dict() if self.course else None,
            "duration_minutes": self.duration_minutes,
            "student_count": self.student_count,
            "status": self.status.value,
            "notes": self.notes,
            "is_fully_assigned": self.is_fully_assigned,
        }
        if include_sessions:
            d["sessions"] = [s.to_dict() for s in self.sessions]
        return d


class ExamSession(db.Model):
    """
    One physical sitting of an exam — tied to a time slot.
    One exam can have multiple sessions (split across rooms or time).
    Sessions at the SAME time_slot = parallel rooms for the same exam.
    Sessions at DIFFERENT time_slots = the exam was split across time.
    """
    __tablename__ = "exam_sessions"

    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey("exams.id"), nullable=False)
    workspace_id = db.Column(db.Integer, db.ForeignKey("workspaces.id"), nullable=True)
    time_slot_id = db.Column(db.Integer, db.ForeignKey("time_slots.id"), nullable=False)
    assigned_students = db.Column(db.Integer, default=0)
    session_index = db.Column(db.Integer, default=0)  # ordering within exam

    exam = db.relationship("Exam", back_populates="sessions")
    time_slot = db.relationship("TimeSlot", back_populates="sessions")
    workspace = db.relationship("Workspace")
    # Each session can use one or more room+observer combos
    assignments = db.relationship("SessionAssignment", back_populates="session", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "exam_id": self.exam_id,
            "workspace_id": self.workspace_id,
            "exam": self.exam.to_dict() if self.exam else None,
            "time_slot": self.time_slot.to_dict() if self.time_slot else None,
            "assigned_students": self.assigned_students,
            "session_index": self.session_index,
            "assignments": [a.to_dict() for a in self.assignments],
        }


class SessionAssignment(db.Model):
    """
    Binds one ExamSession to one Classroom + one Observer + optionally an Instructor.
    Multiple rows per session = multiple rooms in parallel.
    """
    __tablename__ = "session_assignments"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("exam_sessions.id"), nullable=False)
    classroom_id = db.Column(db.Integer, db.ForeignKey("classrooms.id"), nullable=False)
    observer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    extra_observer_ids = db.Column(db.Text, nullable=True)
    instructor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    # Students placed in this specific room
    students_in_room = db.Column(db.Integer, default=0)

    session = db.relationship("ExamSession", back_populates="assignments")
    classroom = db.relationship("Classroom", back_populates="session_assignments")
    observer = db.relationship("User", foreign_keys=[observer_id], back_populates="observer_sessions")
    instructor = db.relationship("User", foreign_keys=[instructor_id], back_populates="instructor_sessions")

    def get_extra_observer_ids(self):
        if not self.extra_observer_ids:
            return []
        try:
            ids = json.loads(self.extra_observer_ids)
            return [int(x) for x in ids if x is not None]
        except Exception:
            return []

    def set_extra_observer_ids(self, ids):
        cleaned = []
        for oid in ids or []:
            try:
                val = int(oid)
            except Exception:
                continue
            if val and val != self.observer_id and val not in cleaned:
                cleaned.append(val)
        self.extra_observer_ids = json.dumps(cleaned) if cleaned else None

    @property
    def extra_observers(self):
        from .user import User
        ids = self.get_extra_observer_ids()
        if not ids:
            return []
        users = User.query.filter(User.id.in_(ids)).all()
        by_id = {u.id: u for u in users}
        return [by_id[oid] for oid in ids if oid in by_id]

    @property
    def all_observers(self):
        observers = []
        if self.observer:
            observers.append(self.observer)
        observers.extend(self.extra_observers)
        return observers

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "classroom": self.classroom.to_dict() if self.classroom else None,
            "observer": self.observer.to_dict() if self.observer else None,
            "extra_observers": [u.to_dict() for u in self.extra_observers],
            "observers": [u.to_dict() for u in self.all_observers],
            "instructor": self.instructor.to_dict() if self.instructor else None,
            "students_in_room": self.students_in_room,
        }