"""
ExamFlow Backend — Flask Application
"""
from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
from io import BytesIO
import os
from datetime import datetime, timedelta
from sqlalchemy import or_, func

from app.base import db


def create_app(config: dict = None):
    app = Flask(__name__)

    # ------------------------------------------------------------------ config
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", "sqlite:///examflow.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-me-in-production")
    if config:
        app.config.update(config)

    db.init_app(app)
    CORS(app)

    with app.app_context():
        # Import all models so SQLAlchemy registers them before create_all()
        from . import models as _models  # noqa: F401
        db.create_all()
        # Add period_id columns to existing tables if they were created before
        # this feature was added (idempotent — silently fails if column exists)
        for _sql in [
            "ALTER TABLE exams ADD COLUMN period_id INTEGER REFERENCES periods(id)",
            "ALTER TABLE time_slots ADD COLUMN period_id INTEGER REFERENCES periods(id)",
            "ALTER TABLE courses ADD COLUMN semester_id INTEGER REFERENCES semesters(id)",
            "ALTER TABLE courses ADD COLUMN year INTEGER",
            "ALTER TABLE time_slots ADD COLUMN slot_type VARCHAR(10) DEFAULT 'midterm'",
            "ALTER TABLE periods ADD COLUMN active_slot_type VARCHAR(10) DEFAULT 'midterm'",
            "ALTER TABLE session_assignments ADD COLUMN extra_observer_ids TEXT",
            "ALTER TABLE courses ADD COLUMN shared_with_departments VARCHAR(500)",
            "ALTER TABLE exam_sessions ADD COLUMN workspace_id INTEGER REFERENCES workspaces(id)",
        ]:
            try:
                with db.engine.connect() as _conn:
                    _conn.execute(db.text(_sql))
                    _conn.commit()
            except Exception:
                pass
        _seed_if_empty()
        _migrate_orphan_records()

    # ----------------------------------------------------------------- routes
    _register_routes(app)
    from app.routes.agent_routes import register_agent_routes
    register_agent_routes(app)
    return app


# ===========================================================================
# Route registration
# ===========================================================================

def _register_routes(app: Flask):

    def _shared_code_filter(column, dept_code: str):
        code = (dept_code or "").upper()
        shared = func.replace(func.upper(func.coalesce(column, "")), " ", "")
        return or_(
            shared == code,
            shared.like(f"{code},%"),
            shared.like(f"%,{code},%"),
            shared.like(f"%,{code}"),
        )

    def _normalize_shared_departments(raw_value, owner_department_id: int | None = None):
        from app.models.department import Department

        if raw_value is None:
            return None

        tokens = []
        if isinstance(raw_value, str):
            tokens = [x.strip() for x in raw_value.replace(";", ",").split(",") if x.strip()]
        elif isinstance(raw_value, list):
            tokens = [str(x).strip() for x in raw_value if str(x).strip()]
        else:
            tokens = [str(raw_value).strip()]

        if not tokens:
            return None

        owner_code = None
        if owner_department_id:
            owner = Department.query.get(owner_department_id)
            owner_code = owner.code.upper() if owner and owner.code else None

        normalized_codes = set()
        for token in tokens:
            dept = None
            if token.isdigit():
                dept = Department.query.get(int(token))
            if not dept:
                dept = Department.query.filter(func.upper(Department.code) == token.upper()).first()
            if dept and dept.code:
                code = dept.code.upper()
                if owner_code and code == owner_code:
                    continue
                normalized_codes.add(code)

        return ",".join(sorted(normalized_codes)) if normalized_codes else None

    def _resolve_workspace(manager_id: int | None):
        from app.models.user import User, UserRole
        from app.models.period import Period
        from app.models.workspace import Workspace

        if not manager_id:
            return None
        manager = User.query.get(manager_id)
        if not manager or manager.role != UserRole.MANAGER:
            return None

        active_period = Period.query.filter_by(is_active=True).first()
        period_id = active_period.id if active_period else None
        workspace = Workspace.query.filter_by(manager_id=manager.id, period_id=period_id).first()
        if workspace:
            if not workspace.is_active:
                workspace.is_active = True
                db.session.commit()
            return workspace

        workspace = Workspace(
            name=f"{manager.name} — {(active_period.name if active_period else 'Current Period')}",
            manager_id=manager.id,
            period_id=period_id,
            is_active=True,
        )
        db.session.add(workspace)
        db.session.commit()
        return workspace

    @app.get("/api/managers")
    def list_managers():
        from app.models.user import User, UserRole
        managers = User.query.filter_by(role=UserRole.MANAGER, is_active=True).all()
        return jsonify([m.to_dict() for m in managers])

    def _manager_scopes(manager_id: int):
        from app.models.manager_scope import ManagerScope
        return ManagerScope.query.filter_by(manager_id=manager_id, is_active=True).all()

    def _manager_can_access_exam(manager_id: int | None, exam) -> bool:
        from app.models.user import User, UserRole

        if not manager_id:
            return True
        manager = User.query.get(manager_id)
        if not manager or manager.role != UserRole.MANAGER:
            return False

        scopes = _manager_scopes(manager_id)
        if not scopes:
            return True  # no scope rows => unrestricted manager

        course = exam.course if exam else None
        dept_id = course.department_id if course else None
        year = course.year if course else None
        for scope in scopes:
            dept_ok = scope.department_id is None or scope.department_id == dept_id
            year_ok = scope.year is None or scope.year == year
            if dept_ok and year_ok:
                return True
        return False

    def _manager_allowed_exam_ids(manager_id: int | None, period_id: int | None):
        from app.models.exam import Exam

        exams_q = Exam.query
        if period_id:
            exams_q = exams_q.filter_by(period_id=period_id)
        return [e.id for e in exams_q.all() if _manager_can_access_exam(manager_id, e)]

    @app.get("/api/manager-scopes")
    def list_manager_scopes():
        from app.models.manager_scope import ManagerScope

        manager_id = request.args.get("manager_id", type=int)
        q = ManagerScope.query.filter_by(is_active=True)
        if manager_id:
            q = q.filter_by(manager_id=manager_id)
        return jsonify([s.to_dict() for s in q.all()])

    @app.post("/api/manager-scopes")
    def create_manager_scope():
        from app.models.manager_scope import ManagerScope
        from sqlalchemy.exc import IntegrityError

        data = request.json or {}
        scope = ManagerScope(
            manager_id=data["manager_id"],
            department_id=data.get("department_id"),
            year=data.get("year"),
            is_active=data.get("is_active", True),
        )
        db.session.add(scope)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            return jsonify({"error": "That manager scope already exists."}), 409
        return jsonify(scope.to_dict()), 201

    @app.delete("/api/manager-scopes/<int:scope_id>")
    def delete_manager_scope(scope_id):
        from app.models.manager_scope import ManagerScope

        scope = ManagerScope.query.get_or_404(scope_id)
        db.session.delete(scope)
        db.session.commit()
        return jsonify({"deleted": True})

    @app.get("/api/workspaces/current")
    def current_workspace():
        manager_id = request.args.get("manager_id", type=int)
        ws = _resolve_workspace(manager_id)
        if not ws:
            return jsonify({"error": "manager_id is required and must be a manager"}), 400
        return jsonify(ws.to_dict())

    # ---- Health ----
    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    # ================================================================
    # PERIODS
    # ================================================================

    @app.get("/api/periods")
    def list_periods():
        from app.models.period import Period
        periods = Period.query.order_by(Period.created_at.desc()).all()
        return jsonify([p.to_dict() for p in periods])

    @app.post("/api/periods")
    def create_period():
        from app.models.period import Period
        from app.models.exam import Exam, ExamStatus, TimeSlot
        data = request.json
        # Remember the previous active period so we can copy its exams
        prev = Period.query.filter_by(is_active=True).first()
        prev_exams = prev.exams.all() if prev else []
        # Deactivate all existing periods
        Period.query.update({"is_active": False})
        # Create the new active period
        period = Period(name=data["name"], is_active=True)
        db.session.add(period)
        db.session.flush()
        # Copy exams from previous period as DRAFT (no sessions / time slots)
        for old in prev_exams:
            new_exam = Exam(
                course_id=old.course_id,
                duration_minutes=old.duration_minutes,
                student_count=old.student_count,
                notes=old.notes,
                status=ExamStatus.DRAFT,
                period_id=period.id,
            )
            db.session.add(new_exam)
        # Enforce max 2 periods — delete oldest when over limit
        all_periods = Period.query.order_by(Period.created_at).all()
        while len(all_periods) > 2:
            oldest = all_periods.pop(0)
            for exam in oldest.exams.all():
                db.session.delete(exam)
            oldest.time_slots.delete(synchronize_session=False)
            db.session.delete(oldest)
        db.session.commit()
        return jsonify(period.to_dict()), 201

    @app.put("/api/periods/<int:period_id>/activate")
    def activate_period(period_id):
        from app.models.period import Period
        Period.query.update({"is_active": False})
        period = Period.query.get_or_404(period_id)
        period.is_active = True
        db.session.commit()
        return jsonify(period.to_dict())

    # ================================================================
    # SEMESTERS
    # ================================================================

    @app.get("/api/semesters")
    def list_semesters():
        from app.models.semester import Semester
        sems = Semester.query.order_by(Semester.created_at.desc()).all()
        return jsonify([s.to_dict() for s in sems])

    @app.post("/api/semesters")
    def create_semester():
        from app.models.semester import Semester
        data = request.json
        # If first semester, make it active automatically
        make_active = Semester.query.count() == 0
        sem = Semester(name=data["name"], is_active=make_active)
        db.session.add(sem)
        db.session.commit()
        return jsonify(sem.to_dict()), 201

    @app.put("/api/semesters/<int:sem_id>")
    def update_semester(sem_id):
        from app.models.semester import Semester
        sem = Semester.query.get_or_404(sem_id)
        data = request.json
        if "name" in data:
            sem.name = data["name"]
        db.session.commit()
        return jsonify(sem.to_dict())

    @app.put("/api/semesters/<int:sem_id>/activate")
    def activate_semester(sem_id):
        from app.models.semester import Semester
        Semester.query.update({"is_active": False})
        sem = Semester.query.get_or_404(sem_id)
        sem.is_active = True
        db.session.commit()
        return jsonify(sem.to_dict())
    # ================================================================

    @app.get("/api/departments")
    def list_departments():
        from app.models.department import Department
        return jsonify([d.to_dict() for d in Department.query.all()])

    @app.post("/api/departments")
    def create_department():
        from app.models.department import Department
        data = request.json
        dept = Department(name=data["name"], code=data["code"], color=data.get("color", "#3B82F6"))
        db.session.add(dept)
        db.session.commit()
        return jsonify(dept.to_dict()), 201

    @app.post("/api/departments/import")
    def import_department_dataset_route():
        from app.services.dataset_import import import_department_dataset
        data = request.json or {}
        try:
            summary = import_department_dataset(data)
        except ValueError as exc:
            db.session.rollback()
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:
            db.session.rollback()
            return jsonify({"error": "Import failed", "detail": str(exc)[:300]}), 500
        return jsonify(summary), 201

    @app.put("/api/departments/<int:dept_id>")
    def update_department(dept_id):
        from app.models.department import Department
        dept = Department.query.get_or_404(dept_id)
        data = request.json
        for key in ("name", "code", "color"):
            if key in data:
                setattr(dept, key, data[key])
        db.session.commit()
        return jsonify(dept.to_dict())

    @app.delete("/api/departments/<int:dept_id>")
    def delete_department(dept_id):
        from app.models.department import Department
        dept = Department.query.get_or_404(dept_id)
        db.session.delete(dept)
        db.session.commit()
        return jsonify({"deleted": dept_id})

    # ================================================================
    # CLASSROOMS
    # ================================================================

    @app.get("/api/classrooms")
    def list_classrooms():
        from app.models.classroom import Classroom
        rooms = Classroom.query.filter_by(is_active=True).all()
        return jsonify([r.to_dict() for r in rooms])

    @app.post("/api/classrooms")
    def create_classroom():
        from app.models.classroom import Classroom
        data = request.json
        room = Classroom(
            name=data["name"],
            building=data["building"],
            floor=data.get("floor", 0),
            capacity=data["capacity"],
            has_projector=data.get("has_projector", False),
            has_computers=data.get("has_computers", False),
            notes=data.get("notes"),
        )
        db.session.add(room)
        db.session.commit()
        return jsonify(room.to_dict()), 201

    @app.put("/api/classrooms/<int:room_id>")
    def update_classroom(room_id):
        from app.models.classroom import Classroom
        room = Classroom.query.get_or_404(room_id)
        data = request.json
        for key in ("name", "building", "floor", "capacity", "has_projector", "has_computers", "notes", "is_active"):
            if key in data:
                setattr(room, key, data[key])
        db.session.commit()
        return jsonify(room.to_dict())

    @app.delete("/api/classrooms/<int:room_id>")
    def delete_classroom(room_id):
        from app.models.classroom import Classroom
        room = Classroom.query.get_or_404(room_id)
        room.is_active = False
        db.session.commit()
        return jsonify({"deleted": True})

    # ================================================================
    # USERS (Instructors / Observers / Managers)
    # ================================================================

    @app.get("/api/users")
    def list_users():
        from app.models.user import User
        role = request.args.get("role")
        q = User.query.filter_by(is_active=True)
        if role:
            from app.models.user import UserRole
            q = q.filter_by(role=UserRole(role))
        return jsonify([u.to_dict() for u in q.all()])

    @app.post("/api/users")
    def create_user():
        from app.models.user import User, UserRole
        data = request.json
        user = User(
            name=data["name"],
            email=data["email"],
            role=UserRole(data["role"]),
            department_id=data.get("department_id"),
        )
        user.set_password(data.get("password", "changeme123"))
        db.session.add(user)
        db.session.commit()
        return jsonify(user.to_dict()), 201

    @app.put("/api/users/<int:user_id>")
    def update_user(user_id):
        from app.models.user import User
        user = User.query.get_or_404(user_id)
        data = request.json
        for key in ("name", "email", "department_id", "is_active"):
            if key in data:
                setattr(user, key, data[key])
        db.session.commit()
        return jsonify(user.to_dict())

    # ================================================================
    # COURSES
    # ================================================================

    @app.get("/api/courses")
    def list_courses():
        from app.models.course import Course
        from app.models.department import Department
        dept_id = request.args.get("department_id", type=int)
        q = Course.query
        if dept_id:
            dept = Department.query.get(dept_id)
            if dept:
                q = q.filter(or_(
                    Course.department_id == dept_id,
                    _shared_code_filter(Course.shared_with_departments, dept.code),
                ))
            else:
                q = q.filter_by(department_id=dept_id)
        return jsonify([c.to_dict() for c in q.all()])

    @app.post("/api/courses")
    def create_course():
        from app.models.course import Course
        from app.models.user import User
        from app.models.exam import Exam, ExamStatus
        from app.models.semester import Semester
        data = request.json
        # Resolve semester_id: use provided value or fall back to active semester
        sem_id = data.get("semester_id")
        if not sem_id:
            active_sem = Semester.query.filter_by(is_active=True).first()
            sem_id = active_sem.id if active_sem else None

        shared_raw = data.get("shared_with_departments", data.get("shared_department_ids"))
        shared_with_departments = _normalize_shared_departments(shared_raw, owner_department_id=data["department_id"])

        course = Course(
            code=data["code"],
            name=data["name"],
            department_id=data["department_id"],
            student_count=data["student_count"],
            semester_id=sem_id,
            year=data.get("year"),
            shared_with_departments=shared_with_departments,
        )
        for uid in data.get("instructor_ids", []):
            u = User.query.get(uid)
            if u:
                course.instructors.append(u)
        db.session.add(course)
        db.session.flush()  # get course.id before creating exam

        # Auto-create a draft exam for every new course, in the active period
        from app.models.period import Period
        active_period = Period.query.filter_by(is_active=True).first()
        exam = Exam(
            course_id=course.id,
            duration_minutes=120,
            student_count=course.student_count,
            status=ExamStatus.DRAFT,
            period_id=active_period.id if active_period else None,
        )
        db.session.add(exam)
        db.session.commit()
        return jsonify(course.to_dict()), 201

    @app.put("/api/courses/<int:course_id>")
    def update_course(course_id):
        from app.models.course import Course
        from app.models.user import User
        course = Course.query.get_or_404(course_id)
        data = request.json
        for key in ("code", "name", "department_id", "student_count", "semester_id", "year"):
            if key in data:
                setattr(course, key, data[key])
        if "shared_with_departments" in data or "shared_department_ids" in data:
            raw_shared = data.get("shared_with_departments", data.get("shared_department_ids"))
            owner_department_id = data.get("department_id", course.department_id)
            course.shared_with_departments = _normalize_shared_departments(raw_shared, owner_department_id=owner_department_id)
        if "instructor_ids" in data:
            course.instructors = [User.query.get(uid) for uid in data["instructor_ids"] if User.query.get(uid)]
        db.session.commit()
        return jsonify(course.to_dict())

    @app.delete("/api/courses/<int:course_id>")
    def delete_course(course_id):
        from app.models.course import Course
        course = Course.query.get_or_404(course_id)
        db.session.delete(course)
        db.session.commit()
        return jsonify({"deleted": True})

    # ================================================================
    # TIME SLOTS
    # ================================================================

    @app.get("/api/timeslots")
    def list_timeslots():
        from app.models.exam import TimeSlot
        from app.models.period import Period
        active = Period.query.filter_by(is_active=True).first()
        q = TimeSlot.query
        if active:
            q = q.filter_by(period_id=active.id)
        slot_type = request.args.get("type")  # "midterm" | "final" | None (all)
        if slot_type in ("midterm", "final"):
            q = q.filter_by(slot_type=slot_type)
        slots = q.order_by(TimeSlot.date, TimeSlot.start_time).all()
        return jsonify([s.to_dict() for s in slots])

    @app.post("/api/timeslots")
    def create_timeslot():
        from app.models.exam import TimeSlot
        from app.models.period import Period
        from datetime import datetime
        data = request.json
        active = Period.query.filter_by(is_active=True).first()
        # slot_type sent from frontend ("midterm" or "final"), default to period's active type
        slot_type = data.get("slot_type") or (active.active_slot_type if active else "midterm")
        if slot_type not in ("midterm", "final"):
            slot_type = "midterm"
        slot = TimeSlot(
            label=data.get("label"),
            date=datetime.strptime(data["date"], "%Y-%m-%d").date(),
            start_time=datetime.strptime(data["start_time"], "%H:%M").time(),
            end_time=datetime.strptime(data["end_time"], "%H:%M").time(),
            period_id=active.id if active else None,
            slot_type=slot_type,
        )
        db.session.add(slot)
        db.session.commit()
        return jsonify(slot.to_dict()), 201

    @app.delete("/api/timeslots/<int:slot_id>")
    def delete_timeslot(slot_id):
        from app.models.exam import TimeSlot
        slot = TimeSlot.query.get_or_404(slot_id)
        db.session.delete(slot)
        db.session.commit()
        return jsonify({"deleted": True})

    @app.put("/api/periods/<int:period_id>/active-slot-type")
    def set_active_slot_type(period_id):
        """Switch the active slot type (midterm <-> final) for a period."""
        from app.models.period import Period
        period = Period.query.get_or_404(period_id)
        data = request.json
        slot_type = data.get("slot_type", "midterm")
        if slot_type not in ("midterm", "final"):
            return jsonify({"error": "slot_type must be 'midterm' or 'final'"}), 400
        period.active_slot_type = slot_type
        db.session.commit()
        return jsonify(period.to_dict())

    @app.post("/api/timeslots/bulk")
    def bulk_create_timeslots():
        """
        Generate time slots for every calendar day in a date range.

        Body:
            slot_type    "midterm" | "final"
            start_date   "YYYY-MM-DD"
            end_date     "YYYY-MM-DD"
            sessions     [{"start_time": "HH:MM", "end_time": "HH:MM", "label": "..."}, ...]
        """
        from app.models.exam import TimeSlot
        from app.models.period import Period
        from datetime import datetime, timedelta, date as date_type
        data = request.json

        slot_type = data.get("slot_type", "midterm")
        if slot_type not in ("midterm", "final"):
            return jsonify({"error": "slot_type must be 'midterm' or 'final'"}), 400

        try:
            start = datetime.strptime(data["start_date"], "%Y-%m-%d").date()
            end   = datetime.strptime(data["end_date"],   "%Y-%m-%d").date()
        except (KeyError, ValueError) as e:
            return jsonify({"error": f"Invalid date: {e}"}), 400

        if end < start:
            return jsonify({"error": "end_date must be >= start_date"}), 400
        if (end - start).days > 60:
            return jsonify({"error": "Date range must be 60 days or fewer"}), 400

        sessions = data.get("sessions", [])
        if not sessions:
            return jsonify({"error": "At least one session is required"}), 400

        active = Period.query.filter_by(is_active=True).first()
        period_id = active.id if active else None

        # Delete all existing slots of this type in the active period
        # (must delete referencing ExamSessions first – time_slot_id is NOT NULL)
        existing = TimeSlot.query.filter_by(period_id=period_id, slot_type=slot_type).all()
        deleted_count = len(existing)
        existing_ids = [s.id for s in existing]
        if existing_ids:
            from app.models.exam import ExamSession
            ExamSession.query.filter(ExamSession.time_slot_id.in_(existing_ids)).delete(synchronize_session=False)
        for s in existing:
            db.session.delete(s)
        db.session.flush()

        created = []
        current = start
        while current <= end:
            d_str = current.strftime("%Y-%m-%d")
            for sess in sessions:
                try:
                    st = datetime.strptime(sess["start_time"], "%H:%M").time()
                    et = datetime.strptime(sess["end_time"],   "%H:%M").time()
                except (KeyError, ValueError):
                    continue
                label = sess.get("label") or f"{d_str} {sess['start_time']}–{sess['end_time']}"
                slot = TimeSlot(
                    date=current,
                    start_time=st,
                    end_time=et,
                    label=label,
                    period_id=period_id,
                    slot_type=slot_type,
                )
                db.session.add(slot)
                created.append(slot)
            current += timedelta(days=1)

        db.session.commit()
        return jsonify({"created": len(created), "deleted": deleted_count, "slots": [s.to_dict() for s in created]}), 201

    # ================================================================
    # EXAMS
    # ================================================================

    @app.get("/api/exams")
    def list_exams():
        from app.models.exam import Exam
        from app.models.period import Period
        from app.models.department import Department
        dept_id = request.args.get("department_id", type=int)
        active = Period.query.filter_by(is_active=True).first()
        q = Exam.query
        if active:
            q = q.filter_by(period_id=active.id)
        if dept_id:
            from app.models.course import Course
            q = q.join(Course)
            dept = Department.query.get(dept_id)
            if dept:
                q = q.filter(or_(
                    Course.department_id == dept_id,
                    _shared_code_filter(Course.shared_with_departments, dept.code),
                ))
            else:
                q = q.filter(Course.department_id == dept_id)
        return jsonify([e.to_dict(include_sessions=True) for e in q.all()])

    @app.post("/api/exams")
    def create_exam():
        from app.models.exam import Exam
        from app.models.period import Period
        data = request.json
        active = Period.query.filter_by(is_active=True).first()
        exam = Exam(
            course_id=data["course_id"],
            duration_minutes=data.get("duration_minutes", 120),
            student_count=data["student_count"],
            notes=data.get("notes"),
            period_id=active.id if active else None,
        )
        db.session.add(exam)
        db.session.commit()
        return jsonify(exam.to_dict()), 201

    @app.put("/api/exams/<int:exam_id>")
    def update_exam(exam_id):
        from app.models.exam import Exam
        exam = Exam.query.get_or_404(exam_id)
        data = request.json
        for key in ("duration_minutes", "student_count", "notes"):
            if key in data:
                setattr(exam, key, data[key])
        db.session.commit()
        return jsonify(exam.to_dict())

    @app.delete("/api/exams/<int:exam_id>")
    def delete_exam(exam_id):
        from app.models.exam import Exam
        exam = Exam.query.get_or_404(exam_id)
        db.session.delete(exam)
        db.session.commit()
        return jsonify({"deleted": True})

    # ================================================================
    # SCHEDULING
    # ================================================================

    @app.post("/api/schedule/generate")
    def generate_schedule():
        from app.services.scheduler import build_schedule_from_db
        from app.models.exam import Exam, ExamSession, ExamStatus
        from app.models.period import Period
        data = request.json or {}
        exam_ids = data.get("exam_ids")  # None = schedule all
        manager_id = data.get("manager_id") or request.args.get("manager_id", type=int)
        active_period = Period.query.filter_by(is_active=True).first()
        if manager_id and active_period:
            allowed_ids = set(_manager_allowed_exam_ids(manager_id, active_period.id))
            if not allowed_ids:
                return jsonify({
                    "scheduled": 0,
                    "warnings": ["No owned exams in current period for this manager scope."],
                })
            if exam_ids:
                exam_ids = [eid for eid in exam_ids if eid in allowed_ids]
            else:
                exam_ids = list(allowed_ids)

        # Reset SCHEDULED (and CONFLICT) exams back to DRAFT so the scheduler
        # can re-process them.  Clear their existing sessions first.
        reset_q = Exam.query.filter(
            Exam.status.in_([ExamStatus.SCHEDULED, ExamStatus.CONFLICT])
        )
        if active_period:
            reset_q = reset_q.filter_by(period_id=active_period.id)
        if exam_ids:
            reset_q = reset_q.filter(Exam.id.in_(exam_ids))
        exams_to_reset = reset_q.all()
        for exam in exams_to_reset:
            old_session_ids = [s.id for s in ExamSession.query.filter_by(exam_id=exam.id).all()]
            if old_session_ids:
                from app.models.exam import SessionAssignment
                SessionAssignment.query.filter(
                    SessionAssignment.session_id.in_(old_session_ids)
                ).delete(synchronize_session=False)
            ExamSession.query.filter_by(exam_id=exam.id).delete(synchronize_session=False)
            exam.status = ExamStatus.DRAFT
        db.session.commit()

        plans = build_schedule_from_db(exam_ids, workspace_id=None)
        return jsonify({
            "scheduled": len([p for p in plans if p.sessions]),
            "warnings": [w for p in plans for w in p.warnings],
        })

    @app.get("/api/schedule")
    def get_schedule():
        """Returns full schedule as JSON grouped by date, for the active period."""
        from app.models.exam import ExamSession, Exam
        from app.models.period import Period
        active = Period.query.filter_by(is_active=True).first()
        q = ExamSession.query.join(Exam)
        if active:
            q = q.filter(Exam.period_id == active.id)
        q = q.filter(ExamSession.workspace_id.is_(None))
        result = {}
        for s in q.all():
            date_key = str(s.time_slot.date) if s.time_slot else "unscheduled"
            result.setdefault(date_key, []).append(s.to_dict())
        return jsonify(result)

    # ================================================================
    # CONFLICT CHECKING
    # ================================================================

    @app.post("/api/conflicts/check")
    def check_conflicts():
        from app.services.conflict_detector import check_all_conflicts_for_assignment
        data = request.json
        result = check_all_conflicts_for_assignment(
            classroom_id=data["classroom_id"],
            observer_id=data.get("observer_id"),
            instructor_id=data.get("instructor_id"),
            slot_id=data["slot_id"],
            exclude_assignment_id=data.get("exclude_assignment_id"),
        )
        return jsonify({"has_conflict": result.has_conflict, "conflicts": result.conflicts})

    # ================================================================
    # WORD / DOCX EXPORT
    # ================================================================

    @app.get("/api/export/schedule")
    def export_schedule_docx():
        from app.services.word_export import generate_schedule_docx
        dept_id = request.args.get("department_id", type=int)
        docx_bytes = generate_schedule_docx(
            department_id=dept_id,
            workspace_id=None,
        )
        return send_file(
            BytesIO(docx_bytes),
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True,
            download_name="exam_schedule.docx",
        )

    @app.get("/api/export/observer/<int:observer_id>")
    def export_observer_docx(observer_id):
        from app.services.word_export import generate_observer_docx
        docx_bytes = generate_observer_docx(observer_id=observer_id)
        from app.models.user import User
        observer = User.query.get_or_404(observer_id)
        import re
        safe = re.sub(r"[^\w\-]", "_", observer.name)
        return send_file(
            BytesIO(docx_bytes),
            mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            as_attachment=True,
            download_name=f"observer_{safe}.docx",
        )

    @app.get("/api/export/observers")
    def export_all_observers_zip():
        from app.services.word_export import generate_all_observers_zip
        zip_bytes = generate_all_observers_zip()
        return send_file(
            BytesIO(zip_bytes),
            mimetype="application/zip",
            as_attachment=True,
            download_name="observer_assignments.zip",
        )

    # ================================================================
    # PDF EXPORT (legacy – kept for backwards compat)
    # ================================================================

    @app.get("/api/export/pdf")
    def export_pdf():
        from app.services.pdf_export import generate_full_schedule_pdf
        dept_id = request.args.get("department_id", type=int)
        pdf_bytes = generate_full_schedule_pdf(
            department_id=dept_id,
            workspace_id=None,
        )
        return send_file(
            BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name="exam_schedule.pdf",
        )

    # ================================================================
    # SESSIONS & ASSIGNMENTS (manual editing)
    # ================================================================

    def _active_lock_for_session(session_id: int):
        from app.models.session_edit_lock import SessionEditLock
        lock = SessionEditLock.query.filter_by(session_id=session_id).first()
        if not lock:
            return None
        if lock.expires_at <= datetime.utcnow():
            db.session.delete(lock)
            db.session.commit()
            return None
        return lock

    def _check_edit_permission(session, manager_id: int | None):
        if manager_id is None:
            return False, (jsonify({"error": "manager_id is required"}), 400)
        if not _manager_can_access_exam(manager_id, session.exam):
            return False, (jsonify({"error": "Manager is not allowed to edit this exam scope"}), 403)

        lock = _active_lock_for_session(session.id)
        if not lock or lock.manager_id != manager_id:
            holder = lock.manager.name if lock and lock.manager else None
            return False, (
                jsonify({
                    "error": "Session is locked by another manager",
                    "holder": holder,
                    "expires_at": lock.expires_at.isoformat() if lock else None,
                }),
                409,
            )
        return True, None

    @app.post("/api/sessions/<int:session_id>/lock")
    def acquire_session_lock(session_id):
        from app.models.exam import ExamSession
        from app.models.session_edit_lock import SessionEditLock
        from app.models.user import User, UserRole

        data = request.json or {}
        manager_id = data.get("manager_id") if isinstance(data, dict) else None
        try:
            manager_id = int(manager_id)
        except Exception:
            return jsonify({"error": "manager_id is required"}), 400

        manager = User.query.get(manager_id)
        if not manager or manager.role != UserRole.MANAGER:
            return jsonify({"error": "Invalid manager_id"}), 400

        session = ExamSession.query.get_or_404(session_id)
        if not _manager_can_access_exam(manager_id, session.exam):
            return jsonify({"error": "Manager is not allowed to edit this exam scope"}), 403

        ttl = int(data.get("ttl_minutes", 15))
        ttl = min(max(ttl, 1), 60)
        expires_at = datetime.utcnow() + timedelta(minutes=ttl)

        lock = _active_lock_for_session(session_id)
        if lock and lock.manager_id != manager_id:
            return jsonify({
                "error": "Session already locked",
                "holder": lock.manager.name if lock.manager else None,
                "expires_at": lock.expires_at.isoformat(),
            }), 409

        if lock:
            lock.expires_at = expires_at
        else:
            lock = SessionEditLock(session_id=session_id, manager_id=manager_id, expires_at=expires_at)
            db.session.add(lock)
        db.session.commit()
        return jsonify(lock.to_dict())

    @app.delete("/api/sessions/<int:session_id>/lock")
    def release_session_lock(session_id):
        from app.models.session_edit_lock import SessionEditLock

        manager_id = request.args.get("manager_id", type=int)
        lock = SessionEditLock.query.filter_by(session_id=session_id).first()
        if not lock:
            return jsonify({"released": True})

        if lock.expires_at <= datetime.utcnow() or (manager_id and lock.manager_id == manager_id):
            db.session.delete(lock)
            db.session.commit()
            return jsonify({"released": True})

        return jsonify({"error": "Only lock owner can release active lock"}), 403

    @app.post("/api/sessions/<int:session_id>/assignments")
    def add_assignment(session_id):
        from app.models.exam import SessionAssignment, ExamSession
        from app.services.conflict_detector import check_all_conflicts_for_assignment
        session = ExamSession.query.get_or_404(session_id)
        data = request.json

        manager_id = data.get("manager_id") if isinstance(data, dict) else None
        try:
            manager_id = int(manager_id)
        except Exception:
            manager_id = None
        ok, err = _check_edit_permission(session, manager_id)
        if not ok:
            return err

        extra_observer_ids = data.get("extra_observer_ids") or []

        conflicts = check_all_conflicts_for_assignment(
            classroom_id=data["classroom_id"],
            observer_id=data.get("observer_id"),
            extra_observer_ids=extra_observer_ids,
            instructor_id=data.get("instructor_id"),
            slot_id=session.time_slot_id,
        )
        if conflicts.has_conflict:
            return jsonify({"error": "Conflict detected", "conflicts": conflicts.conflicts}), 409

        sa = SessionAssignment(
            session_id=session_id,
            classroom_id=data["classroom_id"],
            observer_id=data.get("observer_id"),
            instructor_id=data.get("instructor_id"),
            students_in_room=data.get("students_in_room", 0),
        )
        sa.set_extra_observer_ids(extra_observer_ids)
        db.session.add(sa)
        db.session.commit()
        return jsonify(sa.to_dict()), 201

    @app.put("/api/sessions/<int:session_id>")
    def update_session(session_id):
        from app.models.exam import ExamSession
        from app.services.conflict_detector import check_session_move_conflicts
        session = ExamSession.query.get_or_404(session_id)
        data = request.json
        manager_id = data.get("manager_id") if isinstance(data, dict) else None
        try:
            manager_id = int(manager_id)
        except Exception:
            manager_id = None
        ok, err = _check_edit_permission(session, manager_id)
        if not ok:
            return err
        if "time_slot_id" in data:
            conflicts = check_session_move_conflicts(session, data["time_slot_id"])
            if conflicts.has_conflict:
                return jsonify({"error": "Conflict detected", "conflicts": conflicts.conflicts}), 409
            session.time_slot_id = data["time_slot_id"]
        if "assigned_students" in data:
            session.assigned_students = data["assigned_students"]
        db.session.commit()
        return jsonify(session.to_dict())

    @app.get("/api/sessions/<int:session_id>/available-observers")
    def get_available_observers(session_id):
        from app.models.exam import ExamSession
        from app.models.user import User, UserRole
        from app.services.conflict_detector import check_observer_conflict

        session = ExamSession.query.get_or_404(session_id)
        exclude_assignment_id = request.args.get("exclude_assignment_id", type=int)

        available = []
        for observer in User.query.filter_by(role=UserRole.OBSERVER, is_active=True).order_by(User.name).all():
            conflict = check_observer_conflict(observer.id, session.time_slot_id, exclude_assignment_id)
            if not conflict.has_conflict:
                available.append(observer.to_dict())

        return jsonify(available)

    @app.get("/api/sessions/<int:session_id>/available-classrooms")
    def get_available_classrooms(session_id):
        from app.models.exam import ExamSession
        from app.models.classroom import Classroom
        from app.services.conflict_detector import check_classroom_conflict

        session = ExamSession.query.get_or_404(session_id)
        exclude_assignment_id = request.args.get("exclude_assignment_id", type=int)

        available = []
        for classroom in Classroom.query.filter_by(is_active=True).order_by(Classroom.name).all():
            conflict = check_classroom_conflict(classroom.id, session.time_slot_id, exclude_assignment_id)
            if not conflict.has_conflict:
                available.append(classroom.to_dict())

        return jsonify(available)

    @app.put("/api/assignments/<int:assignment_id>")
    def update_assignment(assignment_id):
        from app.models.exam import SessionAssignment
        from app.services.conflict_detector import check_all_conflicts_for_assignment

        sa = SessionAssignment.query.get_or_404(assignment_id)
        data = request.json
        manager_id = data.get("manager_id") if isinstance(data, dict) else None
        try:
            manager_id = int(manager_id)
        except Exception:
            manager_id = None
        ok, err = _check_edit_permission(sa.session, manager_id)
        if not ok:
            return err

        classroom_id = data.get("classroom_id", sa.classroom_id)
        observer_id = data.get("observer_id", sa.observer_id)
        extra_observer_ids = data.get("extra_observer_ids", sa.get_extra_observer_ids())
        instructor_id = data.get("instructor_id", sa.instructor_id)

        conflicts = check_all_conflicts_for_assignment(
            classroom_id=classroom_id,
            observer_id=observer_id,
            extra_observer_ids=extra_observer_ids,
            instructor_id=instructor_id,
            slot_id=sa.session.time_slot_id,
            exclude_assignment_id=assignment_id,
        )
        if conflicts.has_conflict:
            return jsonify({"error": "Conflict detected", "conflicts": conflicts.conflicts}), 409

        for key in ("classroom_id", "observer_id", "instructor_id", "students_in_room"):
            if key in data:
                setattr(sa, key, data[key] if data[key] != "" else None)
        if "extra_observer_ids" in data:
            sa.set_extra_observer_ids(extra_observer_ids)
        db.session.commit()
        return jsonify(sa.to_dict())

    @app.delete("/api/assignments/<int:assignment_id>")
    def delete_assignment(assignment_id):
        from app.models.exam import SessionAssignment
        sa = SessionAssignment.query.get_or_404(assignment_id)
        manager_id = request.args.get("manager_id", type=int)
        ok, err = _check_edit_permission(sa.session, manager_id)
        if not ok:
            return err
        db.session.delete(sa)
        db.session.commit()
        return jsonify({"deleted": True})

    @app.delete("/api/exams/<int:exam_id>/sessions")
    def reset_exam_sessions(exam_id):
        from app.models.exam import Exam, ExamSession, ExamStatus
        exam = Exam.query.get_or_404(exam_id)
        ExamSession.query.filter_by(exam_id=exam_id).delete()
        exam.status = ExamStatus.DRAFT
        db.session.commit()
        return jsonify({"reset": True, "exam_id": exam_id})


# ===========================================================================
# Seed data
# ===========================================================================

def _seed_if_empty():
    from app.models.department import Department
    from app.models.user import User, UserRole
    from app.models.period import Period
    from app.models.semester import Semester
    from app.models.manager_scope import ManagerScope

    # Ensure a default semester exists
    if Semester.query.count() == 0:
        s = Semester(name="Spring 2026", is_active=True)
        db.session.add(s)
        db.session.commit()
        print("✔ Created default semester: Spring 2026")

    # Ensure a default period exists
    if Period.query.count() == 0:
        p = Period(name="Midterm 2026", is_active=True)
        db.session.add(p)
        db.session.commit()
        print("✔ Created default period: Midterm 2026")

    if Department.query.count() > 0:
        return  # already seeded

    depts = [
        Department(name="Architecture", code="ARCH", color="#7C3AED"),
        Department(name="Computer Engineering", code="CE", color="#2563EB"),
        Department(name="AI Engineering", code="AIE", color="#059669"),
        Department(name="Civil Engineering", code="CIVIL", color="#D97706"),
        Department(name="Industrial Engineering & Management", code="IEM", color="#DC2626"),
    ]
    for d in depts:
        db.session.add(d)
    db.session.flush()

    # 5 managers
    for i in range(1, 6):
        m = User(name=f"Manager {i}", email=f"manager{i}@uni.edu", role=UserRole.MANAGER)
        m.set_password("admin123")
        db.session.add(m)

    db.session.flush()

    managers = {u.name: u for u in User.query.filter_by(role=UserRole.MANAGER).all()}
    dept_by_code = {d.code: d for d in Department.query.all()}
    defaults = [
        ("Manager 1", "CE", 1),
        ("Manager 2", "CE", 2),
        ("Manager 3", "CE", None),
        ("Manager 4", "ARCH", 1),
        ("Manager 5", "ARCH", None),
    ]
    for m_name, d_code, year in defaults:
        m = managers.get(m_name)
        d = dept_by_code.get(d_code)
        if m and d:
            db.session.add(ManagerScope(manager_id=m.id, department_id=d.id, year=year, is_active=True))

    db.session.commit()
    print("✔ Seeded departments and default managers.")


def _migrate_orphan_records():
    """Assign exams/timeslots/courses that have no period_id/semester_id to the active ones."""
    from app.models.period import Period
    from app.models.semester import Semester
    from app.models.exam import Exam, TimeSlot
    from app.models.course import Course

    active_period = Period.query.filter_by(is_active=True).first()
    if active_period:
        orphan_exams = Exam.query.filter_by(period_id=None).count()
        orphan_slots = TimeSlot.query.filter_by(period_id=None).count()
        if orphan_exams or orphan_slots:
            Exam.query.filter_by(period_id=None).update({"period_id": active_period.id})
            TimeSlot.query.filter_by(period_id=None).update({"period_id": active_period.id})
            db.session.commit()
            print(f"✔ Migrated {orphan_exams} exams and {orphan_slots} time slots → period '{active_period.name}'")

    active_sem = Semester.query.filter_by(is_active=True).first()
    if active_sem:
        orphan_courses = Course.query.filter_by(semester_id=None).count()
        if orphan_courses:
            Course.query.filter_by(semester_id=None).update({"semester_id": active_sem.id})
            db.session.commit()
            print(f"✔ Migrated {orphan_courses} courses → semester '{active_sem.name}'")


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5000)