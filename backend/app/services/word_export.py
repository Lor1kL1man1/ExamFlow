"""
Word Export Service
===================
Generates .docx documents using python-docx.

Exports:
  1. generate_schedule_docx()   – Full schedule grouped by academic year
  2. generate_observer_docx()   – Per-observer assignment letter
"""

import re
from io import BytesIO
from typing import Optional
from docx import Document
from docx.shared import Pt, Cm, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

UNIVERSITY_NAME = "University Exam Scheduling System"

YEAR_COLOR_HEX = {
    1: "2563EB",  # blue
    2: "059669",  # green
    3: "D97706",  # amber
    4: "7C3AED",  # purple
}

def _year_rgb(year) -> RGBColor:
    h = YEAR_COLOR_HEX.get(year, "64748B")
    return RGBColor(int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

def _year_hex(year) -> str:
    return YEAR_COLOR_HEX.get(year, "64748B")
HEADER_COLOR = RGBColor(0x1E, 0x29, 0x3B)
ALT_ROW_COLOR = "F1F5F9"
WHITE = "FFFFFF"
HEADER_BG = "1E293B"


# ── helpers ──────────────────────────────────────────────────────────────────

def _set_cell_bg(cell, hex_color: str):
    """Fill a table cell with a hex background colour."""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def _bold_run(para, text: str, size: int = 10, color: Optional[RGBColor] = None):
    run = para.add_run(text)
    run.bold = True
    run.font.size = Pt(size)
    if color:
        run.font.color.rgb = color
    return run


def _fmt_date(d) -> str:
    if d is None:
        return "—"
    s = str(d)
    parts = s.split("-")
    if len(parts) == 3:
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return s


def _fmt_time(t) -> str:
    return str(t)[:5] if t else "—"


def _get_year(code: str) -> Optional[int]:
    m = re.match(r"^Y(\d+)-", code or "")
    return int(m.group(1)) if m else None


def _course_visible_for_department(course, dept_code: str) -> bool:
    if not course or not dept_code:
        return False
    target = dept_code.upper()
    if course.department and (course.department.code or "").upper() == target:
        return True
    shared = [x.strip().upper() for x in str(course.shared_with_departments or "").split(",") if x.strip()]
    return target in shared


def _add_header_row(table, columns: list[str], bg: str = HEADER_BG):
    hdr = table.rows[0]
    for i, text in enumerate(columns):
        cell = hdr.cells[i]
        _set_cell_bg(cell, bg)
        para = cell.paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = para.add_run(text)
        run.bold = True
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER


def _fill_row(row, values: list[str], alt: bool = False, bold_col: Optional[int] = None):
    bg = ALT_ROW_COLOR if alt else WHITE
    for i, val in enumerate(values):
        cell = row.cells[i]
        _set_cell_bg(cell, bg)
        para = cell.paragraphs[0]
        run = para.add_run(str(val) if val else "—")
        run.font.size = Pt(9)
        if bold_col is not None and i == bold_col:
            run.bold = True
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER


def _page_header(doc: Document, title: str, subtitle: str):
    """Add university name + title at top of document."""
    h = doc.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    _bold_run(h, UNIVERSITY_NAME, size=14, color=HEADER_COLOR)

    h2 = doc.add_paragraph()
    h2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = h2.add_run(title)
    run.font.size = Pt(12)
    run.font.color.rgb = HEADER_COLOR

    if subtitle:
        h3 = doc.add_paragraph()
        h3.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run3 = h3.add_run(subtitle)
        run3.font.size = Pt(10)
        run3.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

    doc.add_paragraph()  # spacer


# ── 1. Full schedule by year ──────────────────────────────────────────────────

def generate_schedule_docx(department_id: Optional[int] = None, workspace_id: Optional[int] = None) -> bytes:
    """
    Returns a .docx with one section per academic year.
    Each section has a heading and a table of sessions sorted by date/time.
    """
    from app.models.exam import ExamSession, Exam
    from app.models.course import Course
    from app.models.department import Department
    from app.models.period import Period

    # Active period label
    active_period = Period.query.filter_by(is_active=True).first()
    period_label = active_period.name if active_period else "Current Period"

    dept_label = "All Departments"
    if department_id:
        dept = Department.query.get(department_id)
        dept_label = dept.name if dept else "Unknown"

    # Fetch all sessions for active period
    sessions = (
        ExamSession.query
        .join(Exam)
        .join(Course)
        .filter(Exam.period_id == active_period.id if active_period else True)
        .all()
    )
    if workspace_id is not None:
        sessions = [s for s in sessions if s.workspace_id == workspace_id]
    else:
        sessions = [s for s in sessions if s.workspace_id is None]

    if department_id and dept:
        sessions = [s for s in sessions if _course_visible_for_department(s.exam.course, dept.code)]

    # Group by year
    by_year: dict[int | str, list] = {}
    for s in sessions:
        yr = s.exam.course.year or _get_year(s.exam.course.code or "")
        key = yr if yr else 0  # 0 = Other
        by_year.setdefault(key, []).append(s)

    year_order = sorted(k for k in by_year if k != 0) + ([0] if 0 in by_year else [])

    doc = Document()

    # Page margins
    section = doc.sections[0]
    section.page_width = Inches(11.69)   # A4 landscape
    section.page_height = Inches(8.27)
    section.left_margin = Cm(1.8)
    section.right_margin = Cm(1.8)
    section.top_margin = Cm(2)
    section.bottom_margin = Cm(2)

    from datetime import date
    _page_header(
        doc,
        f"Exam Schedule — {period_label}",
        f"{dept_label}  ·  Generated {date.today().strftime('%d/%m/%Y')}",
    )

    COL_NAMES = ["Date", "Time", "Code", "Course", "Students", "Classroom(s)", "Instructor(s)", "Observer(s)"]
    COL_WIDTHS = [Cm(2.8), Cm(2.4), Cm(2.4), Cm(5.0), Cm(1.8), Cm(3.2), Cm(4.2), Cm(4.2)]

    for key in year_order:
        year_sessions = sorted(
            by_year[key],
            key=lambda s: (
                str(s.time_slot.date) if s.time_slot else "",
                str(s.time_slot.start_time) if s.time_slot else "",
            ),
        )

        year_label = f"Year {key}" if key != 0 else "Other"
        yr_rgb   = _year_rgb(key)
        yr_hex   = _year_hex(key)

        # Year heading
        heading = doc.add_paragraph()
        _bold_run(heading, f"  {year_label}  ", size=11, color=RGBColor(0xFF, 0xFF, 0xFF))
        # Color the heading paragraph background via shading
        pPr = heading._p.get_or_add_pPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), yr_hex)
        pPr.append(shd)
        heading.paragraph_format.space_before = Pt(6)
        heading.paragraph_format.space_after = Pt(2)

        # Count badge
        count_p = doc.add_paragraph()
        run = count_p.add_run(f"  {len(year_sessions)} session{'s' if len(year_sessions) != 1 else ''}")
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)
        count_p.paragraph_format.space_after = Pt(4)

        # Table
        table = doc.add_table(rows=1 + len(year_sessions), cols=len(COL_NAMES))
        table.style = "Table Grid"
        for i, w in enumerate(COL_WIDTHS):
            for row in table.rows:
                row.cells[i].width = w

        _add_header_row(table, COL_NAMES)

        for idx, s in enumerate(year_sessions):
            slot = s.time_slot
            course = s.exam.course
            rooms = ", ".join(a.classroom.name for a in s.assignments if a.classroom) or "—"
            instructors = ", ".join(a.instructor.name for a in s.assignments if a.instructor) or "—"
            observers = ", ".join(
                observer.name
                for a in s.assignments
                for observer in a.all_observers
            ) or "—"

            _fill_row(
                table.rows[idx + 1],
                [
                    _fmt_date(slot.date if slot else None),
                    f"{_fmt_time(slot.start_time if slot else None)}–{_fmt_time(slot.end_time if slot else None)}",
                    course.code or "—",
                    course.name or "—",
                    str(s.assigned_students),
                    rooms,
                    instructors,
                    observers,
                ],
                alt=(idx % 2 == 1),
                bold_col=2,
            )

        doc.add_paragraph()  # spacing between year sections

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


# ── 2. Per-observer assignment letter ────────────────────────────────────────

def generate_observer_docx(observer_id: int) -> bytes:
    """
    Returns a .docx assignment letter for a single observer:
    - Header with observer name
    - Table of every session they're assigned to
    """
    from app.models.user import User
    from app.models.exam import SessionAssignment, ExamSession, Exam
    from app.models.course import Course
    from app.models.period import Period
    from datetime import date

    observer = User.query.get_or_404(observer_id)
    active_period = Period.query.filter_by(is_active=True).first()
    period_label = active_period.name if active_period else "Current Period"

    assignments = (
        SessionAssignment.query
        .join(ExamSession)
        .join(Exam)
        .join(Course)
        .all()
    )

    assignments = [
        a for a in assignments
        if observer_id in [o.id for o in a.all_observers]
    ]

    # Filter to active period if set
    if active_period:
        assignments = [a for a in assignments if a.session.exam.period_id == active_period.id]

    assignments.sort(
        key=lambda a: (
            str(a.session.time_slot.date) if a.session.time_slot else "",
            str(a.session.time_slot.start_time) if a.session.time_slot else "",
        )
    )

    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.27)   # A4 portrait
    section.page_height = Inches(11.69)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2.5)

    _page_header(
        doc,
        f"Observer Assignment — {observer.name}",
        f"Period: {period_label}  ·  Generated {date.today().strftime('%d/%m/%Y')}",
    )

    # Greeting paragraph
    greeting = doc.add_paragraph()
    greeting.add_run("Dear ").font.size = Pt(11)
    _bold_run(greeting, observer.name, size=11)
    run = greeting.add_run(
        f",\n\nYou have been assigned as an exam observer for the "
        f"following session(s) during {period_label}. "
        f"Please be present at the designated classroom at least "
        f"10 minutes before the exam starts.\n"
    )
    run.font.size = Pt(11)
    greeting.paragraph_format.space_after = Pt(12)

    if not assignments:
        p = doc.add_paragraph("You have no observer assignments for this period.")
        p.runs[0].font.size = Pt(11)
        p.runs[0].font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)
    else:
        COL_NAMES = ["#", "Date", "Time", "Course Code", "Course Name", "Classroom", "Students", "Instructor"]
        COL_WIDTHS = [Cm(1.0), Cm(2.6), Cm(2.8), Cm(2.6), Cm(4.8), Cm(2.6), Cm(2.0), Cm(3.6)]

        table = doc.add_table(rows=1 + len(assignments), cols=len(COL_NAMES))
        table.style = "Table Grid"
        for i, w in enumerate(COL_WIDTHS):
            for row in table.rows:
                row.cells[i].width = w

        _add_header_row(table, COL_NAMES)

        for idx, a in enumerate(assignments):
            slot = a.session.time_slot
            course = a.session.exam.course
            _fill_row(
                table.rows[idx + 1],
                [
                    str(idx + 1),
                    _fmt_date(slot.date if slot else None),
                    f"{_fmt_time(slot.start_time if slot else None)}–{_fmt_time(slot.end_time if slot else None)}",
                    course.code or "—",
                    course.name or "—",
                    a.classroom.name if a.classroom else "—",
                    str(a.students_in_room),
                    a.instructor.name if a.instructor else "—",
                ],
                alt=(idx % 2 == 1),
                bold_col=3,
            )

        doc.add_paragraph()

    # Signature block
    sig = doc.add_paragraph()
    sig.paragraph_format.space_before = Pt(24)
    sig.add_run("Scheduling Office\n").bold = True
    sig.runs[0].font.size = Pt(11)
    run = sig.add_run(UNIVERSITY_NAME)
    run.font.size = Pt(10)
    run.font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.read()


# ── 3. All-observers bundle ───────────────────────────────────────────────────

def generate_all_observers_zip() -> bytes:
    """
    Returns a ZIP archive containing one .docx per observer who has assignments.
    """
    import zipfile
    from app.models.user import User
    from app.models.exam import SessionAssignment
    from app.models.period import Period

    active_period = Period.query.filter_by(is_active=True).first()

    # Find all distinct observers who have assignments in the active period
    query = SessionAssignment.query
    if active_period:
        from app.models.exam import ExamSession, Exam
        query = (
            query
            .join(ExamSession, SessionAssignment.session_id == ExamSession.id)
            .join(Exam, ExamSession.exam_id == Exam.id)
            .filter(Exam.period_id == active_period.id)
        )
    observer_ids = set()
    for assignment in query.all():
        observer_ids.update(o.id for o in assignment.all_observers)

    zip_buf = BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for oid in sorted(observer_ids):
            observer = User.query.get(oid)
            if not observer:
                continue
            docx_bytes = generate_observer_docx(oid)
            safe_name = re.sub(r"[^\w\-]", "_", observer.name)
            zf.writestr(f"observer_{safe_name}.docx", docx_bytes)

    zip_buf.seek(0)
    return zip_buf.read()
