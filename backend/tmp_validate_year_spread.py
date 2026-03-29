import sys
from collections import defaultdict

sys.path.insert(0, ".")

from app import create_app
from app.base import db
from app.services.scheduler import build_schedule_from_db
from app.models.exam import Exam, ExamStatus, ExamSession, SessionAssignment
from app.models.period import Period

app = create_app()

with app.app_context():
    active = Period.query.filter_by(is_active=True).first()
    reset_query = Exam.query.filter(Exam.status.in_([ExamStatus.SCHEDULED, ExamStatus.CONFLICT]))
    if active:
        reset_query = reset_query.filter_by(period_id=active.id)
    exams = reset_query.all()

    for exam in exams:
        session_ids = [session.id for session in exam.sessions]
        if session_ids:
            SessionAssignment.query.filter(SessionAssignment.session_id.in_(session_ids)).delete(synchronize_session=False)
        ExamSession.query.filter_by(exam_id=exam.id).delete(synchronize_session=False)
        exam.status = ExamStatus.DRAFT
    db.session.commit()

    plans = build_schedule_from_db()
    print(f"scheduled: {len([p for p in plans if p.sessions])}")

    per_year = defaultdict(lambda: defaultdict(list))
    sessions = ExamSession.query.join(Exam).all()
    for session in sessions:
        course = session.exam.course if session.exam else None
        if not course or not course.year or not session.time_slot:
            continue
        per_year[course.year][str(session.time_slot.date)].append(course.code)

    for year in sorted(per_year):
        print(f"YEAR {year}")
        for day in sorted(per_year[year]):
            codes = sorted(per_year[year][day])
            print(f"  {day} {len(codes)} {codes}")
