import csv
import io
import re
from datetime import datetime

from sqlalchemy import func

from app.base import db
from app.models.classroom import Classroom
from app.models.course import Course
from app.models.department import Department
from app.models.exam import Exam, ExamSession, ExamStatus, SessionAssignment, TimeSlot
from app.models.period import Period
from app.models.semester import Semester
from app.models.user import User, UserRole


HEADER_ALIASES = {
    "course": "course",
    "course_name": "course",
    "instructor": "instructor",
    "instructors": "instructor",
    "date": "date",
    "time": "time",
    "group": "group",
    "room": "room",
    "rooms": "room",
    "observer": "observers",
    "observers": "observers",
    "year": "year",
    "coursecode": "course_code",
    "course_code": "course_code",
    "shared_departments": "shared_departments",
    "shared": "shared_departments",
}


def import_department_dataset(payload):
    csv_text = (payload.get("csv_text") or "").strip()
    if not csv_text:
        raise ValueError("CSV text is required")

    department_name = (payload.get("department_name") or "").strip()
    department_code = (payload.get("department_code") or "").strip().upper()
    if not department_name or not department_code:
        raise ValueError("Department name and code are required")

    default_year = int(payload.get("default_year") or 1)
    default_room_capacity = int(payload.get("default_room_capacity") or 30)
    department_color = (payload.get("department_color") or "#3B82F6").strip()
    overwrite_existing = bool(payload.get("overwrite_existing"))

    semester_id = payload.get("semester_id")
    if not semester_id:
        active_semester = Semester.query.filter_by(is_active=True).first()
        semester_id = active_semester.id if active_semester else None

    period_id = payload.get("period_id")
    if not period_id:
        active_period = Period.query.filter_by(is_active=True).first()
        period_id = active_period.id if active_period else None

    summary = {
        "department_created": False,
        "rooms_created": 0,
        "users_created": 0,
        "users_reused": 0,
        "courses_created": 0,
        "exams_created": 0,
        "overlaps_merged": 0,
        "timeslots_created": 0,
        "courses_deleted": 0,
        "exams_deleted": 0,
        "rows_processed": 0,
        "warnings": [],
    }

    department = _get_or_create_department(department_name, department_code, department_color)
    summary["department_created"] = department.created_at == department.updated_at if hasattr(department, "updated_at") else False

    if overwrite_existing:
        existing_courses = Course.query.filter_by(department_id=department.id).all()
        summary["courses_deleted"] = len(existing_courses)
        summary["exams_deleted"] = sum(len(course.exams) for course in existing_courses)
        for course in existing_courses:
            db.session.delete(course)
        db.session.flush()

    rows = _read_rows(csv_text)
    if not rows:
        raise ValueError("No CSV rows found")

    for index, row in enumerate(rows, start=2):
        course_name = row.get("course", "").strip()
        if not course_name:
            continue

        try:
            exam_date = _parse_date(row.get("date", "").strip())
            start_time, end_time = _parse_time_range(row.get("time", "").strip())
        except ValueError as exc:
            summary["warnings"].append(f"Row {index}: {exc}")
            continue

        room_names = _split_multi_value(row.get("room", ""))
        if not room_names:
            summary["warnings"].append(f"Row {index}: no rooms provided for '{course_name}'")
            continue

        year_value = row.get("year", "").strip()
        try:
            year = int(year_value) if year_value else default_year
        except ValueError:
            year = default_year
            summary["warnings"].append(f"Row {index}: invalid year '{year_value}', defaulted to {default_year}")

        instructors = []
        for name in _split_multi_value(row.get("instructor", "")):
            instructors.append(_get_or_create_user(name, UserRole.INSTRUCTOR, department.id, summary))

        observers = []
        primary_instructor_names = {user.name.casefold() for user in instructors}
        for name in _split_multi_value(row.get("observers", "")):
            if name.casefold() in primary_instructor_names:
                continue
            observers.append(_get_or_create_user(name, UserRole.OBSERVER, department.id, summary))

        rooms = [
            _get_or_create_room(room_name, default_room_capacity, summary)
            for room_name in room_names
        ]
        student_count = sum(room.capacity for room in rooms)
        course_code = _unique_course_code(
            department.code,
            year,
            course_name,
            preferred=row.get("course_code", "").strip() or None,
        )

        # Explicit shared departments from CSV (comma or semicolon separated)
        explicit_shared_codes = _split_dept_codes(row.get("shared_departments", ""))

        # Auto-detect overlap with existing exam (same course + same slot)
        overlap_exam = _find_overlapping_exam(course_name, exam_date, start_time, end_time, period_id)
        if overlap_exam:
            _merge_into_overlapping_exam(
                overlap_exam=overlap_exam,
                importing_department=department,
                instructors=instructors,
                observers=observers,
                rooms=rooms,
                group_label=row.get("group", "").strip(),
                explicit_shared_codes=explicit_shared_codes,
            )
            summary["overlaps_merged"] += 1
            summary["rows_processed"] += 1
            continue

        shared_codes = set(explicit_shared_codes)
        if shared_codes:
            shared_codes.add(department.code.upper())
        shared_with_str = ",".join(sorted(shared_codes)) if shared_codes else None

        course = Course(
            code=course_code,
            name=course_name,
            department_id=department.id,
            student_count=student_count,
            year=year,
            semester_id=semester_id,
            shared_with_departments=shared_with_str,
        )
        for instructor in instructors:
            course.instructors.append(instructor)
        db.session.add(course)
        db.session.flush()
        summary["courses_created"] += 1

        notes = None
        group_label = row.get("group", "").strip()
        if group_label:
            notes = f"Group: {group_label}"

        exam = Exam(
            course_id=course.id,
            duration_minutes=_duration_minutes(start_time, end_time),
            student_count=student_count,
            notes=notes,
            status=ExamStatus.SCHEDULED,
            period_id=period_id,
        )
        db.session.add(exam)
        db.session.flush()
        summary["exams_created"] += 1

        timeslot = _get_or_create_timeslot(exam_date, start_time, end_time, period_id, summary)
        session = ExamSession(
            exam_id=exam.id,
            time_slot_id=timeslot.id,
            assigned_students=student_count,
            session_index=0,
        )
        db.session.add(session)
        db.session.flush()

        overflow_observers = observers[len(rooms):]
        for room_index, room in enumerate(rooms):
            assignment = SessionAssignment(
                session_id=session.id,
                classroom_id=room.id,
                observer_id=observers[room_index].id if room_index < len(observers) else None,
                instructor_id=instructors[0].id if room_index == 0 and instructors else None,
                students_in_room=room.capacity,
            )
            if room_index == 0 and overflow_observers:
                assignment.set_extra_observer_ids([observer.id for observer in overflow_observers])
            db.session.add(assignment)

        summary["rows_processed"] += 1

    db.session.commit()
    return summary


def _read_rows(csv_text):
    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        raise ValueError("CSV header row is required")
    rows = []
    for raw_row in reader:
        normalized = {}
        for key, value in raw_row.items():
            norm_key = HEADER_ALIASES.get((key or "").strip().lower().replace(" ", "_").replace("-", "_"))
            if norm_key:
                normalized[norm_key] = (value or "").strip()
        rows.append(normalized)
    return rows


def _parse_date(value):
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"invalid date '{value}'")


def _parse_time_range(value):
    normalized = value.replace("–", "-").replace("—", "-")
    parts = [part.strip() for part in normalized.split("-") if part.strip()]
    if len(parts) != 2:
        raise ValueError(f"invalid time range '{value}'")
    try:
        start = datetime.strptime(parts[0], "%H:%M").time()
        end = datetime.strptime(parts[1], "%H:%M").time()
    except ValueError as exc:
        raise ValueError(f"invalid time range '{value}'") from exc
    return start, end


def _split_multi_value(value):
    return [item.strip() for item in (value or "").split(";") if item.strip()]


def _split_dept_codes(value):
    if not value:
        return []
    normalized = value.replace(";", ",")
    return [item.strip().upper() for item in normalized.split(",") if item.strip()]


def _duration_minutes(start_time, end_time):
    return ((end_time.hour * 60 + end_time.minute) - (start_time.hour * 60 + start_time.minute)) or 90


def _get_or_create_department(name, code, color):
    department = Department.query.filter(
        (func.lower(Department.code) == code.lower()) | (func.lower(Department.name) == name.lower())
    ).first()
    if department:
        if name:
            department.name = name
        if code:
            department.code = code
        if color:
            department.color = color
        db.session.flush()
        return department
    department = Department(name=name, code=code, color=color or "#3B82F6")
    db.session.add(department)
    db.session.flush()
    return department


def _get_or_create_user(name, fallback_role, department_id, summary):
    user = User.query.filter(func.lower(User.name) == name.lower()).first()
    if user:
        summary["users_reused"] += 1
        if user.department_id is None:
            user.department_id = department_id
        return user

    user = User(
        name=name,
        email=_make_email(name),
        role=fallback_role,
        department_id=department_id,
        is_active=True,
    )
    user.set_password("changeme123")
    db.session.add(user)
    db.session.flush()
    summary["users_created"] += 1
    return user


def _get_or_create_room(name, default_capacity, summary):
    room = Classroom.query.filter(func.lower(Classroom.name) == name.lower()).first()
    if room:
        return room

    room = Classroom(
        name=name,
        building=_infer_building(name),
        floor=_infer_floor(name),
        capacity=default_capacity,
        is_active=True,
    )
    db.session.add(room)
    db.session.flush()
    summary["rooms_created"] += 1
    return room


def _get_or_create_timeslot(exam_date, start_time, end_time, period_id, summary):
    timeslot = TimeSlot.query.filter_by(
        date=exam_date,
        start_time=start_time,
        end_time=end_time,
        period_id=period_id,
        slot_type="midterm",
    ).first()
    if timeslot:
        return timeslot

    timeslot = TimeSlot(
        label=f"{exam_date.isoformat()} {start_time.strftime('%H:%M')}–{end_time.strftime('%H:%M')}",
        date=exam_date,
        start_time=start_time,
        end_time=end_time,
        period_id=period_id,
        slot_type="midterm",
    )
    db.session.add(timeslot)
    db.session.flush()
    summary["timeslots_created"] += 1
    return timeslot


def _find_overlapping_exam(course_name, exam_date, start_time, end_time, period_id):
    q = (
        Exam.query
        .join(Course, Exam.course_id == Course.id)
        .join(ExamSession, ExamSession.exam_id == Exam.id)
        .join(TimeSlot, TimeSlot.id == ExamSession.time_slot_id)
        .filter(func.lower(Course.name) == course_name.lower())
        .filter(TimeSlot.date == exam_date)
        .filter(TimeSlot.start_time == start_time)
        .filter(TimeSlot.end_time == end_time)
    )
    if period_id is not None:
        q = q.filter(Exam.period_id == period_id)
    return q.order_by(Exam.id.asc()).first()


def _merge_into_overlapping_exam(
    overlap_exam,
    importing_department,
    instructors,
    observers,
    rooms,
    group_label,
    explicit_shared_codes,
):
    course = overlap_exam.course
    session = overlap_exam.sessions[0] if overlap_exam.sessions else None
    if not session:
        return

    # Merge shared department flags
    shared_codes = set(_split_dept_codes(course.shared_with_departments))
    if course.department and course.department.code:
        shared_codes.add(course.department.code.upper())
    shared_codes.add(importing_department.code.upper())
    shared_codes.update(explicit_shared_codes)
    course.shared_with_departments = ",".join(sorted(shared_codes)) if shared_codes else None

    # Merge instructors
    existing_instructor_ids = {u.id for u in course.instructors}
    for instructor in instructors:
        if instructor.id not in existing_instructor_ids:
            course.instructors.append(instructor)
            existing_instructor_ids.add(instructor.id)

    # Merge notes with group label if present
    if group_label:
        group_note = f"Group: {group_label}"
        if overlap_exam.notes:
            if group_note not in overlap_exam.notes:
                overlap_exam.notes = f"{overlap_exam.notes}; {group_note}"
        else:
            overlap_exam.notes = group_note

    # Add only new rooms to the existing session
    existing_room_ids = {a.classroom_id for a in session.assignments}
    new_rooms = [room for room in rooms if room.id not in existing_room_ids]
    if not new_rooms:
        return

    add_students = sum(room.capacity for room in new_rooms)
    course.student_count += add_students
    overlap_exam.student_count += add_students
    session.assigned_students += add_students

    has_instructor_assigned = any(a.instructor_id for a in session.assignments)
    overflow_observers = observers[len(new_rooms):]
    for i, room in enumerate(new_rooms):
        assignment = SessionAssignment(
            session_id=session.id,
            classroom_id=room.id,
            observer_id=observers[i].id if i < len(observers) else None,
            instructor_id=(instructors[0].id if (i == 0 and instructors and not has_instructor_assigned) else None),
            students_in_room=room.capacity,
        )
        if i == 0 and overflow_observers:
            assignment.set_extra_observer_ids([u.id for u in overflow_observers])
        db.session.add(assignment)


def _unique_course_code(department_code, year, course_name, preferred=None):
    base = preferred or f"{department_code}-Y{year}-{_slugify(course_name)}"
    candidate = base[:20]
    suffix = 2
    while Course.query.filter_by(code=candidate).first():
        trimmed = base[: max(1, 20 - len(str(suffix)) - 1)]
        candidate = f"{trimmed}-{suffix}"
        suffix += 1
    return candidate


def _slugify(value):
    slug = re.sub(r"[^A-Z0-9]+", "", value.upper())
    return (slug or "COURSE")[:10]


def _make_email(name):
    clean = (name.lower()
             .replace("ı", "i").replace("ğ", "g").replace("ş", "s")
             .replace("ç", "c").replace("ö", "o").replace("ü", "u")
             .replace(" ", ".").replace("/", ""))
    return clean + "@university.edu"


def _infer_building(room_name):
    parts = room_name.split("-")
    prefix = parts[0] if parts else "Main"
    return f"{prefix} Block"


def _infer_floor(room_name):
    try:
        return int(room_name.split("-")[1][0])
    except Exception:
        return 0