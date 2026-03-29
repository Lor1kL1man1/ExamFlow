#!/usr/bin/env python3
"""
Seed script — Spring 2026 exam schedule.
Run from the backend/ directory:
    /Users/lorik/examflow/backend/venv/bin/python3 seed.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from datetime import date, time as dtime
from app import create_app
from app.base import db
from app.models.department import Department
from app.models.classroom import Classroom
from app.models.user import User, UserRole
from app.models.course import Course
from app.models.exam import Exam, ExamStatus, ExamSession, TimeSlot, SessionAssignment
from app.models.period import Period
from app.models.semester import Semester
from app.models.manager_scope import ManagerScope
from app.models.session_edit_lock import SessionEditLock
from app.models.workspace import Workspace

app = create_app()

with app.app_context():
    print("Clearing existing data...")
    SessionEditLock.query.delete()
    SessionAssignment.query.delete()
    ExamSession.query.delete()
    Exam.query.delete()
    db.session.execute(db.text("DELETE FROM course_instructors"))
    Course.query.delete()
    ManagerScope.query.delete()
    Workspace.query.delete()
    TimeSlot.query.delete()
    User.query.delete()
    Classroom.query.delete()
    Department.query.delete()
    Period.query.delete()
    Semester.query.delete()
    db.session.commit()

    # ── Semester ─────────────────────────────────────────────────────────────
    semester = Semester(name="Spring 2026", is_active=True)
    db.session.add(semester)
    db.session.flush()

    # ── Period ──────────────────────────────────────────────────────────────
    period = Period(name="Midterm 2026", is_active=True, active_slot_type="midterm")
    db.session.add(period)
    db.session.flush()

    # ── Departments ─────────────────────────────────────────────────────────
    ce_dept = Department(name="Computer Engineering", code="CE", color="#2563EB")
    arch_dept = Department(name="Architecture", code="ARCH", color="#7C3AED")
    db.session.add_all([ce_dept, arch_dept])
    db.session.flush()

    # ── Helpers ─────────────────────────────────────────────────────────────
    def make_email(name):
        clean = (name.lower()
                 .replace("ı", "i").replace("ğ", "g").replace("ş", "s")
                 .replace("ç", "c").replace("ö", "o").replace("ü", "u")
                 .replace(" ", ".").replace("/", ""))
        return clean + "@university.edu"

    def infer_building(room_name):
        return f"{room_name.split('-')[0]} Block"

    def infer_floor(room_name):
        try:
            return int(room_name.split("-")[1][0])
        except Exception:
            return 0

    def compute_duration_minutes(start_str, end_str):
        sh, sm = map(int, start_str.split(":"))
        eh, em = map(int, end_str.split(":"))
        return (eh * 60 + em) - (sh * 60 + sm)

    U = {}
    R = {}
    TS = {}

    def ensure_user(name, role, department_id=None):
        existing = U.get(name)
        if existing:
            if existing.department_id is None and department_id is not None:
                existing.department_id = department_id
            return existing

        user = User(
            name=name,
            email=make_email(name),
            role=role,
            department_id=department_id,
            is_active=True,
        )
        user.set_password("changeme123")
        db.session.add(user)
        db.session.flush()
        U[name] = user
        return user

    def ensure_room(name, capacity):
        existing = R.get(name)
        if existing:
            return existing
        room = Classroom(
            name=name,
            building=infer_building(name),
            floor=infer_floor(name),
            capacity=capacity,
            is_active=True,
        )
        db.session.add(room)
        db.session.flush()
        R[name] = room
        return room

    def ensure_timeslot(d_str, s_str, e_str, slot_type="midterm"):
        key = (d_str, s_str, e_str, slot_type)
        existing = TS.get(key)
        if existing:
            return existing
        y, m, day = map(int, d_str.split("-"))
        sh, sm = map(int, s_str.split(":"))
        eh, em = map(int, e_str.split(":"))
        slot = TimeSlot(
            date=date(y, m, day),
            start_time=dtime(sh, sm),
            end_time=dtime(eh, em),
            label=f"{d_str} {s_str}–{e_str}",
            period_id=period.id,
            slot_type=slot_type,
        )
        db.session.add(slot)
        db.session.flush()
        TS[key] = slot
        return slot

    def seed_exam_entry(department, year, cname, ccode, instructor_names, dt, start, end, room_names, people, shared_with_departments=None):
        student_count = sum(R[r].capacity for r in room_names if r in R)

        course = Course(
            code=ccode,
            name=cname,
            department_id=department.id,
            student_count=student_count,
            semester_id=semester.id,
            year=year,
            shared_with_departments=shared_with_departments,
        )
        db.session.add(course)
        for iname in instructor_names:
            course.instructors.append(ensure_user(iname, UserRole.INSTRUCTOR, department.id))
        db.session.flush()

        exam = Exam(
            course_id=course.id,
            duration_minutes=compute_duration_minutes(start, end),
            student_count=student_count,
            status=ExamStatus.SCHEDULED,
            period_id=period.id,
        )
        db.session.add(exam)
        db.session.flush()

        slot = ensure_timeslot(dt, start, end, slot_type="midterm")
        session = ExamSession(
            exam_id=exam.id,
            time_slot_id=slot.id,
            assigned_students=student_count,
            session_index=0,
        )
        db.session.add(session)
        db.session.flush()

        primary_set = set(instructor_names)
        observer_users = [
            ensure_user(person, UserRole.OBSERVER, department.id)
            for person in people
            if person and person not in primary_set
        ]
        primary_instructor = ensure_user(instructor_names[0], UserRole.INSTRUCTOR, department.id) if instructor_names else None
        overflow_observers = observer_users[len(room_names):]

        for i, room_name in enumerate(room_names):
            if room_name not in R:
                print(f"  WARNING: room {room_name} not found, skipping")
                continue
            room = R[room_name]
            observer = observer_users[i] if i < len(observer_users) else None
            assignment = SessionAssignment(
                session_id=session.id,
                classroom_id=room.id,
                observer_id=observer.id if observer else None,
                instructor_id=primary_instructor.id if i == 0 and primary_instructor else None,
                students_in_room=room.capacity,
            )
            if i == 0 and overflow_observers:
                assignment.set_extra_observer_ids([user.id for user in overflow_observers])
            db.session.add(assignment)

    # ── Classrooms ──────────────────────────────────────────────────────────
    room_capacities = {
        "A-207": 42,
        "A-208": 36,
        "A-209": 34,
        "A-301": 32,
        "A-302": 28,
        "A-303": 40,
        "A-304": 30,
        "A-305": 26,
        "A-307": 24,
        "A-309": 80,
        "B-203": 60,
        "B-208": 60,
        "B-209": 45,
        "B-301": 35,
        "B-303": 90,
        "B-304": 30,
        "B-306": 45,
    }
    for room_name, capacity in room_capacities.items():
        ensure_room(room_name, capacity)

    # ── Users ───────────────────────────────────────────────────────────────
    ce_instructors = [
        "Renata Todorovska",
        "Afan Hasan",
        "Damir Rahmani",
        "Zhilbert Tafa",
        "Hiqmet Kamberaj",
        "Jana Mihajlovska Ivanov",
        "Cuneyt Nur",
        "Ahmet Lokce",
        "Delcho Leshkovski",
        "Aleksandra Porjazoska Kujundziski",
        "Neslihan Ademi",
        "Edmond Jajaga",
        "Andrej Stefanov",
        "Ervin Domazet",
    ]
    ce_observers = [
        "Amra Abazi",
        "Fisnik Sopi",
        "Done Nikolovski",
        "Enis Ramani",
        "Lorik Limani",
        "Mia Dimova",
        "Vrull Selmani",
        "Amra Feta",
    ]
    managers = [
        "Manager 1",
        "Manager 2",
        "Manager 3",
        "Manager 4",
        "Manager 5",
    ]

    for name in ce_instructors:
        ensure_user(name, UserRole.INSTRUCTOR, ce_dept.id)
    for name in ce_observers:
        ensure_user(name, UserRole.OBSERVER, ce_dept.id)
    for name in managers:
        ensure_user(name, UserRole.MANAGER, None)

    # Default ownership scopes (department + year partitions)
    manager_scopes = [
        ("Manager 1", ce_dept.id, 1),
        ("Manager 2", ce_dept.id, 2),
        ("Manager 3", ce_dept.id, 3),
        ("Manager 3", ce_dept.id, 4),
        ("Manager 4", arch_dept.id, 1),
        ("Manager 4", arch_dept.id, 2),
        ("Manager 5", arch_dept.id, None),
    ]
    for manager_name, dept_id, year in manager_scopes:
        mgr = U.get(manager_name)
        if not mgr:
            continue
        db.session.add(ManagerScope(manager_id=mgr.id, department_id=dept_id, year=year, is_active=True))

    # ── Final exam time slots (Jan 12–17, 2026 · 6 sessions/day) ─────────────
    _final_sessions = [
        ("08:30", "10:00"), ("10:15", "11:45"), ("12:00", "13:30"),
        ("13:45", "15:15"), ("15:30", "17:00"), ("17:15", "18:45"),
    ]
    _final_dates = [
        "2026-01-12", "2026-01-13", "2026-01-14",
        "2026-01-15", "2026-01-16", "2026-01-17",
    ]
    for d_str in _final_dates:
        for s_str, e_str in _final_sessions:
            y, m, day = map(int, d_str.split("-"))
            sh, sm = map(int, s_str.split(":"))
            eh, em = map(int, e_str.split(":"))
            ensure_timeslot(d_str, s_str, e_str, slot_type="final")
    db.session.flush()

    # ── Computer Engineering exam data ──────────────────────────────────────
    # (year, course_name, course_code, [instructor_names], date, start_time,
    #  end_time, [room_names], [all_present_people_in_order])
    ce_exams_data = [
        # ── Year 1 ────────────────────────────────────────────────────────
        (1, "English Language II", "Y1-ENG2",
         ["Renata Todorovska"],
         "2026-03-23", "12:00", "13:30",
         ["B-208", "B-203", "B-303", "B-304"],
         ["Renata Todorovska", "Amra Abazi", "Fisnik Sopi", "Done Nikolovski", "Enis Ramani"]),

        (1, "Introduction to Programming", "Y1-PROG",
         ["Afan Hasan"],
         "2026-03-24", "10:15", "11:45",
         ["B-209", "B-306"],
         ["Afan Hasan", "Amra Abazi", "Fisnik Sopi", "Lorik Limani"]),

        (1, "Mathematics 2", "Y1-MATH2",
         ["Damir Rahmani"],
         "2026-03-25", "13:45", "15:15",
         ["B-303", "B-203", "B-209", "B-306"],
         ["Damir Rahmani", "Amra Abazi", "Lorik Limani", "Fisnik Sopi", "Mia Dimova", "Vrull Selmani"]),

        (1, "Information Technology", "Y1-IT",
         ["Zhilbert Tafa"],
         "2026-03-26", "08:30", "10:00",
         ["A-309"],
         ["Zhilbert Tafa", "Lorik Limani", "Vrull Selmani", "Fisnik Sopi"]),

        (1, "Physics 2", "Y1-PHY2",
         ["Hiqmet Kamberaj"],
         "2026-03-27", "10:15", "11:45",
         ["B-203", "B-303"],
         ["Hiqmet Kamberaj", "Fisnik Sopi", "Lorik Limani", "Done Nikolovski"]),

        (1, "Macedonian Language II", "Y1-MKD2",
         ["Jana Mihajlovska Ivanov"],
         "2026-03-28", "08:30", "10:00",
         ["B-303", "B-304"],
         ["Jana Mihajlovska Ivanov", "Done Nikolovski"]),

        (1, "Turkish Language II", "Y1-TUR2",
         ["Cuneyt Nur"],
         "2026-03-28", "10:15", "11:45",
         ["B-304", "B-301"],
         ["Cuneyt Nur", "Vrull Selmani"]),

        # ── Year 2 ────────────────────────────────────────────────────────
        (2, "Entrepreneurship", "Y2-ENTR",
         ["Ahmet Lokce"],
         "2026-03-23", "17:15", "18:45",
         ["B-303", "B-304"],
         ["Ahmet Lokce", "Enis Ramani"]),

        (2, "Differential Equations", "Y2-DIFF",
         ["Delcho Leshkovski"],
         "2026-03-24", "15:30", "17:00",
         ["B-303", "B-209", "B-306", "B-203"],
         ["Delcho Leshkovski", "Damir Rahmani", "Amra Abazi", "Lorik Limani", "Fisnik Sopi", "Mia Dimova", "Vrull Selmani"]),

        (2, "Numerical Methods", "Y2-NUMT",
         ["Aleksandra Porjazoska Kujundziski", "Damir Rahmani"],
         "2026-03-25", "08:30", "10:00",
         ["B-303", "B-203"],
         ["Aleksandra Porjazoska Kujundziski", "Damir Rahmani", "Lorik Limani"]),

        (2, "Probability and Statistics", "Y2-PROB",
         ["Delcho Leshkovski"],
         "2026-03-26", "10:15", "11:45",
         ["B-303", "B-209", "B-306", "B-203"],
         ["Delcho Leshkovski", "Damir Rahmani", "Amra Abazi", "Lorik Limani", "Fisnik Sopi", "Mia Dimova", "Vrull Selmani"]),

        (2, "Logic Design", "Y2-LOGD",
         ["Neslihan Ademi"],
         "2026-03-27", "13:45", "15:15",
         ["B-303"],
         ["Neslihan Ademi", "Lorik Limani"]),

        (2, "Algorithms", "Y2-ALGO",
         ["Hiqmet Kamberaj"],
         "2026-03-28", "12:00", "13:30",
         ["B-303", "B-203"],
         ["Hiqmet Kamberaj", "Amra Abazi", "Lorik Limani", "Fisnik Sopi"]),

        # ── Year 3 ────────────────────────────────────────────────────────
        (3, "System Modeling", "Y3-SYSM",
         ["Edmond Jajaga"],
         "2026-03-23", "13:45", "15:15",
         ["B-203", "B-209"],
         ["Edmond Jajaga", "Lorik Limani", "Fisnik Sopi"]),

        (3, "Computer Architecture", "Y3-ARCH",
         ["Neslihan Ademi"],
         "2026-03-24", "13:45", "15:15",
         ["B-203"],
         ["Neslihan Ademi", "Damir Rahmani"]),

        (3, "Artificial Intelligence", "Y3-AI",
         ["Afan Hasan"],
         "2026-03-25", "12:00", "13:30",
         ["B-209", "B-306"],
         ["Afan Hasan", "Amra Abazi", "Vrull Selmani"]),

        (3, "Operating Systems", "Y3-OS",
         ["Andrej Stefanov"],
         "2026-03-26", "12:00", "13:30",
         ["B-203", "B-209"],
         ["Andrej Stefanov", "Damir Rahmani", "Amra Abazi"]),

        (3, "Multimedia and Web Design", "Y3-MMWD",
         ["Edmond Jajaga"],
         "2026-03-27", "08:30", "10:00",
         ["B-203", "B-209"],
         ["Edmond Jajaga", "Lorik Limani", "Amra Feta"]),

        (3, "Software Quality and Testing", "Y3-SQTE",
         ["Edmond Jajaga"],
         "2026-03-28", "10:15", "11:45",
         ["B-209", "B-306"],
         ["Edmond Jajaga", "Lorik Limani", "Amra Feta"]),

        # ── Year 4 ────────────────────────────────────────────────────────
        (4, "Wireless Information Networks", "Y4-WIN",
         ["Andrej Stefanov"],
         "2026-03-23", "10:15", "11:45",
         ["B-203"],
         ["Andrej Stefanov", "Lorik Limani"]),

        (4, "Human Computer Interface", "Y4-HCI",
         ["Ervin Domazet"],
         "2026-03-24", "12:00", "13:30",
         ["B-203"],
         ["Ervin Domazet", "Vrull Selmani", "Enis Ramani"]),

        (4, "Telecommunications", "Y4-TELE",
         ["Andrej Stefanov"],
         "2026-03-25", "10:15", "11:45",
         ["B-203"],
         ["Andrej Stefanov", "Damir Rahmani"]),

        (4, "Internet of Things", "Y4-IOT",
         ["Ervin Domazet"],
         "2026-03-26", "13:45", "15:15",
         ["B-203"],
         ["Ervin Domazet", "Amra Abazi"]),
    ]

    # ── Architecture exam data ──────────────────────────────────────────────
    arch_exams_data = [
        # ── Year 1 ────────────────────────────────────────────────────────
        (1, "English Language II", "ARCH-Y1-01", ["Marija Stevkovska"], "2026-03-23", "12:00", "13:30", ["A-303", "A-304", "A-305"], ["Marija Stevkovska", "Isra Asani", "Anastasija Dimitrievska"]),
        (1, "Architectural Design and Studio I", "ARCH-Y1-02", ["Kefajet Edip"], "2026-03-25", "10:15", "13:30", ["A-207", "A-209"], ["Kefajet Edip", "Blerta Imeri", "Sema Ebibi"]),
        (1, "Visualization and Perspective", "ARCH-Y1-03", ["Aleksandar Andovski"], "2026-03-24", "10:15", "11:45", ["A-207", "A-208"], ["Aleksandar Andovski", "Blerta Imeri", "Isra Asani"]),
        (1, "Critical Thinking and Academic Writing", "ARCH-Y1-04", ["Marija Stevkovska"], "2026-03-26", "15:30", "17:00", ["A-309", "A-305", "A-307"], ["Marija Stevkovska", "Isra Asani", "Harika Shehabi"]),
        (1, "Balkan Societies and Cultures", "ARCH-Y1-05", ["Muhammed Jashar"], "2026-03-27", "15:30", "17:00", ["B-303", "B-304", "A-309", "A-305", "A-307"], ["Muhammed Jashar", "Isra Asani", "Harika Shehabi"]),
        (1, "Macedonian Language I", "ARCH-Y1-06", ["Jana Mihajlovska Ivanov"], "2026-03-28", "08:30", "10:00", ["B-303", "B-304"], ["Jana Mihajlovska Ivanov", "Damir Rahmani"]),
        (1, "Turkish Language I", "ARCH-Y1-07", ["Cuneyt Nur"], "2026-03-28", "10:15", "11:45", ["B-304", "B-301"], ["Cuneyt Nur", "Isra Asani"]),
        (1, "Mathematics II", "ARCH-Y1-08", ["Daniela Mechkaroska"], "2026-03-28", "13:45", "15:15", ["A-207"], ["Daniela Mechkaroska"]),

        # ── Year 2 ────────────────────────────────────────────────────────
        (2, "Architectural Design I", "ARCH-Y2-01", ["Marko Icev"], "2026-03-23", "13:45", "15:15", ["A-209"], ["Marko Icev"]),
        (2, "Architectural Studio I", "ARCH-Y2-02", ["Aleksandar Andovski"], "2026-03-26", "08:30", "10:00", ["A-209"], ["Aleksandar Andovski"]),
        (2, "History of Architecture and Art I", "ARCH-Y2-03", ["Marko Icev"], "2026-03-25", "13:45", "15:15", ["A-207"], ["Marko Icev", "Isra Asani", "Nadica Angova Kolevska"]),

        # ── Year 3 ────────────────────────────────────────────────────────
        (3, "Architectural Studio III", "ARCH-Y3-01", ["Marija Miloshevska Janakievska"], "2026-03-25", "12:00", "13:30", ["A-208"], ["Marija Miloshevska Janakievska", "Faton Kalisi", "Harika Shehabi"]),
        (3, "Entrepreneurship", "ARCH-Y3-02", [], "2026-03-23", "15:30", "17:00", ["B-303", "B-304"], ["Blerta Imeri", "Sema Ebibi"]),
        (3, "Computer Aided Design II", "ARCH-Y3-03", ["Kefajet Edip"], "2026-03-24", "13:45", "15:15", ["B-306", "B-209"], ["Kefajet Edip", "Isra Asani", "Blerta Imeri"]),
        (3, "Strength of Materials", "ARCH-Y3-04", ["Vesna Grujoska"], "2026-03-27", "13:45", "15:15", ["B-203", "A-207"], ["Vesna Grujoska", "Harika Shehabi", "Blerta Imeri"]),
        (3, "Architectural Structures II", "ARCH-Y3-05", ["Marija Miloshevska Janakievska"], "2026-03-28", "10:15", "11:45", ["A-207", "A-209"], ["Marija Miloshevska Janakievska", "Faton Kalisi", "Sema Ebibi"]),
        (3, "Architectural Design III", "ARCH-Y3-06", ["Viktorija Mangaroska"], "2026-03-26", "10:15", "11:45", ["A-207", "A-208"], ["Viktorija Mangaroska", "Harika Shehabi", "Sema Ebibi"]),

        # ── Year 4 ────────────────────────────────────────────────────────
        (4, "Urban Planning I", "ARCH-Y4-01", ["Aleksandar Andovski"], "2026-03-27", "10:15", "11:45", ["A-207"], ["Aleksandar Andovski", "Harika Shehabi", "Nadica Angova Kolevska"]),
        (4, "Interior Design I", "ARCH-Y4-02", ["Viktorija Mangaroska"], "2026-03-26", "12:00", "13:30", ["A-207"], ["Viktorija Mangaroska", "Faton Kalisi", "Blerta Imeri"]),
        (4, "Architectural Studio V", "ARCH-Y4-03", ["Arbresha Ibrahimi"], "2026-03-24", "12:00", "15:15", ["A-207"], ["Arbresha Ibrahimi", "Jasna Grujoska Kuneska", "Faton Kalisi"]),
        (4, "Reinforced Concrete", "ARCH-Y4-04", ["Jordan Bojadziev"], "2026-03-25", "12:00", "13:30", ["B-303"], ["Jordan Bojadziev"]),
        (4, "Architectural Design V", "ARCH-Y4-05", ["Arbresha Ibrahimi"], "2026-03-28", "12:00", "13:30", ["A-207"], ["Arbresha Ibrahimi", "Harika Shehabi"]),

        # ── Year 5 ────────────────────────────────────────────────────────
        (5, "Energy Efficiency of Buildings", "ARCH-Y5-01", ["Jasna Grujoska Kuneska"], "2026-03-23", "12:00", "13:30", ["A-207"], ["Jasna Grujoska Kuneska", "Sema Ebibi"]),
        (5, "Steel Structure", "ARCH-Y5-02", ["Vesna Grujoska"], "2026-03-24", "12:00", "13:30", ["B-303"], ["Vesna Grujoska"]),
        (5, "Architectural Theory and Methods", "ARCH-Y5-03", ["Jasna Grujoska Kuneska"], "2026-03-28", "10:15", "11:45", ["A-208"], ["Jasna Grujoska Kuneska", "Harika Shehabi"]),
        (5, "Sustainable Architecture", "ARCH-Y5-04", ["Marija Miloshevska Janakievska"], "2026-03-26", "13:45", "15:15", ["A-207"], ["Marija Miloshevska Janakievska", "Faton Kalisi"]),

        # ── Additional data ────────────────────────────────────────────────
        (6, "Introduction to Architecture", "ARCH-Y6-01", ["Arbresha Ibrahimi"], "2026-03-24", "08:30", "10:00", ["A-208"], ["Arbresha Ibrahimi"]),
        (6, "Research Methods in Natural Sciences", "ARCH-Y6-02", ["Aleksandar Anastasovski"], "2026-03-23", "12:00", "13:30", ["A-302"], ["Aleksandar Anastasovski"]),
        (6, "Prestressed Concrete", "ARCH-Y6-03", ["Vesna Grujoska"], "2026-03-26", "12:00", "13:30", ["A-301"], ["Vesna Grujoska"]),
        (6, "Theory of Architecture", "ARCH-Y6-04", ["Viktorija Mangaroska"], "2026-03-27", "13:45", "15:15", ["A-208"], ["Viktorija Mangaroska"]),
        (6, "Infrastructure Structures", "ARCH-Y6-05", ["Done Nikolovski"], "2026-03-23", "08:30", "10:00", ["B-203"], ["Done Nikolovski"]),
        (6, "Planning Studio", "ARCH-Y6-06", ["Jasna Grujoska Kuneska"], "2026-03-25", "10:15", "11:45", ["A-208"], ["Jasna Grujoska Kuneska"]),
        (6, "Urban Planning", "ARCH-Y6-07", ["Marko Icev"], "2028-03-27", "10:15", "11:45", ["A-208"], ["Marko Icev"]),
    ]

    def normalize_key(entry):
        # key: same course name + same slot => shared mixed-cohort exam
        return (entry[1].strip().lower(), entry[4], entry[5], entry[6])

    def slug_shared_code(course_name, used_codes):
        import re as _re
        base = "GEN-" + (_re.sub(r"[^A-Z0-9]+", "", course_name.upper())[:12] or "COURSE")
        code = base[:20]
        i = 2
        while code in used_codes:
            suffix = f"-{i}"
            code = (base[: max(1, 20 - len(suffix))] + suffix)
            i += 1
        used_codes.add(code)
        return code

    # ── Create shared courses first (single record for mixed cohorts) ──────
    used_codes = {entry[2] for entry in ce_exams_data + arch_exams_data}
    arch_by_key = {}
    for idx, entry in enumerate(arch_exams_data):
        arch_by_key.setdefault(normalize_key(entry), []).append((idx, entry))

    shared_pairs = []
    ce_remaining = []
    arch_used_idx = set()

    for ce_entry in ce_exams_data:
        key = normalize_key(ce_entry)
        bucket = arch_by_key.get(key, [])
        match = None
        for idx, arch_entry in bucket:
            if idx not in arch_used_idx:
                match = (idx, arch_entry)
                break
        if match:
            arch_used_idx.add(match[0])
            shared_pairs.append((ce_entry, match[1]))
        else:
            ce_remaining.append(ce_entry)

    arch_remaining = [entry for idx, entry in enumerate(arch_exams_data) if idx not in arch_used_idx]

    for ce_entry, arch_entry in shared_pairs:
        ce_year, ce_name, _, ce_instr, ce_dt, ce_start, ce_end, ce_rooms, ce_people = ce_entry
        arch_year, _, _, arch_instr, _, _, _, arch_rooms, arch_people = arch_entry

        merged_instructors = list(dict.fromkeys(ce_instr + arch_instr))
        merged_rooms = list(dict.fromkeys(ce_rooms + arch_rooms))
        merged_people = list(dict.fromkeys(ce_people + arch_people))

        seed_exam_entry(
            ce_dept,
            min(ce_year, arch_year),
            ce_name,
            slug_shared_code(ce_name, used_codes),
            merged_instructors,
            ce_dt,
            ce_start,
            ce_end,
            merged_rooms,
            merged_people,
            shared_with_departments="CE,ARCH",
        )

    # Courses that should be visible for both CE and ARCH even when only
    # one department provided the row (general shared courses).
    forced_shared_names = {
        "English Language II",
        "Introduction to Programming",
    }

    # ── Create department-specific courses, exams, sessions, assignments ───
    for entry in ce_remaining:
        shared_flag = "CE,ARCH" if entry[1] in forced_shared_names else None
        seed_exam_entry(ce_dept, *entry, shared_with_departments=shared_flag)
    for entry in arch_remaining:
        shared_flag = "CE,ARCH" if entry[1] in forced_shared_names else None
        seed_exam_entry(arch_dept, *entry, shared_with_departments=shared_flag)

    db.session.commit()

    print(f"\nSeeded successfully!")
    print(f"  Semester    : {semester.name} (active)")
    print(f"  Period      : {period.name} (active)")
    print(f"  Departments : {Department.query.count()}")
    print(f"  Classrooms  : {len(R)}")
    print(f"  Users       : {User.query.count()}  ({User.query.filter_by(role=UserRole.INSTRUCTOR).count()} instructors, {User.query.filter_by(role=UserRole.OBSERVER).count()} observers)")
    print(f"  Time slots  : {TimeSlot.query.count()}")
    print(f"  Exams       : {Exam.query.count()}")
