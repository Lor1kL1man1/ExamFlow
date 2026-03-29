"""
PDF Export Service
==================
Generates schedule PDFs using ReportLab.

Two modes:
  - Full university schedule (all departments, all dates)
  - Per-department schedule (filtered)
"""

from io import BytesIO
from datetime import date as date_type
from typing import Optional

try:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph,
        Spacer, HRFlowable, PageBreak,
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


UNIVERSITY_NAME = "University Exam Scheduling System"

DEPT_COLORS = {
    "Architecture": colors.HexColor("#7C3AED"),
    "Computer Engineering": colors.HexColor("#2563EB"),
    "AI Engineering": colors.HexColor("#059669"),
    "Civil Engineering": colors.HexColor("#D97706"),
    "Industrial Engineering & Management": colors.HexColor("#DC2626"),
}

HEADER_BG = colors.HexColor("#1E293B")
ALT_ROW = colors.HexColor("#F1F5F9")


def _course_visible_for_department(course, dept_code: str) -> bool:
    if not course or not dept_code:
        return False
    target = dept_code.upper()
    if course.department and (course.department.code or "").upper() == target:
        return True
    shared = [x.strip().upper() for x in str(course.shared_with_departments or "").split(",") if x.strip()]
    return target in shared


def generate_full_schedule_pdf(department_id: Optional[int] = None, workspace_id: Optional[int] = None) -> bytes:
    if not REPORTLAB_AVAILABLE:
        raise RuntimeError("reportlab is not installed. Run: pip install reportlab")

    from app.models.exam import ExamSession, Exam
    from app.models.course import Course
    from app.models.department import Department

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontSize=18,
        spaceAfter=6,
        textColor=HEADER_BG,
    )
    sub_style = ParagraphStyle(
        "Sub",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#64748B"),
        spaceAfter=14,
    )
    cell_style = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=8, leading=11)

    elements = []

    # -- Title block --
    elements.append(Paragraph(UNIVERSITY_NAME, title_style))
    dept_label = "All Departments"
    if department_id:
        dept = Department.query.get(department_id)
        dept_label = dept.name if dept else "Unknown Department"

    elements.append(Paragraph(f"Exam Schedule — {dept_label}", sub_style))
    elements.append(HRFlowable(width="100%", thickness=2, color=HEADER_BG))
    elements.append(Spacer(1, 0.4 * cm))

    # -- Fetch data --
    sessions = (
        ExamSession.query
        .join(Exam)
        .join(Course)
        .order_by(ExamSession.time_slot_id, Course.department_id)
        .all()
    )
    if workspace_id is not None:
        sessions = [s for s in sessions if s.workspace_id == workspace_id]
    else:
        sessions = [s for s in sessions if s.workspace_id is None]

    if department_id and dept:
        sessions = [s for s in sessions if _course_visible_for_department(s.exam.course, dept.code)]

    if not sessions:
        elements.append(Paragraph("No scheduled exams found.", styles["Normal"]))
    else:
        table_data = _build_table_data(sessions, cell_style)
        col_widths = [3 * cm, 2.5 * cm, 2.5 * cm, 4 * cm, 3.5 * cm, 3 * cm, 3 * cm, 3 * cm, 2 * cm]
        tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(_build_table_style(len(table_data)))
        elements.append(tbl)

    doc.build(elements)
    buf.seek(0)
    return buf.read()


def _build_table_data(sessions, cell_style):
    headers = [
        "Date", "Start", "End", "Course", "Department",
        "Classroom(s)", "Instructor", "Observer(s)", "Students",
    ]
    rows = [headers]

    for session in sessions:
        slot = session.time_slot
        exam = session.exam
        course = exam.course

        rooms = ", ".join(a.classroom.name for a in session.assignments if a.classroom)
        instructors = ", ".join(
            a.instructor.name for a in session.assignments if a.instructor
        )
        observers = ", ".join(
            observer.name
            for a in session.assignments
            for observer in a.all_observers
        )

        rows.append([
            str(slot.date) if slot else "—",
            str(slot.start_time)[:5] if slot else "—",
            str(slot.end_time)[:5] if slot else "—",
            f"{course.code}\n{course.name}",
            course.department.name if course.department else "—",
            rooms or "—",
            instructors or "—",
            observers or "—",
            str(session.assigned_students),
        ])
    return rows


def _build_table_style(num_rows: int) -> TableStyle:
    style = [
        # Header row
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        # Body
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, ALT_ROW]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("TOPPADDING", (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    return TableStyle(style)