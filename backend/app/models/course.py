from ..base import db
from datetime import datetime

# courses table for the many-to-many between Course and instructor (User)
course_instructors = db.Table(
    "course_instructors",
    db.Column("course_id", db.Integer, db.ForeignKey("courses.id"), primary_key=True),
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
)


class Course(db.Model):
    __tablename__ = "courses"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(150), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=False)
    student_count = db.Column(db.Integer, nullable=False, default=0)
    year = db.Column(db.Integer, nullable=True)  # study year: 1, 2, 3, 4
    semester = db.Column(db.String(20))  # legacy text field, kept for compat
    semester_id = db.Column(db.Integer, db.ForeignKey("semesters.id"), nullable=True)
    shared_with_departments = db.Column(db.String(500), nullable=True)  # comma-separated dept codes, e.g. "CE,ARCH"
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    department   = db.relationship("Department", back_populates="courses")
    semester_obj = db.relationship("Semester", back_populates="courses")
    instructors  = db.relationship("User", secondary=course_instructors, backref="courses")
    exams        = db.relationship("Exam", back_populates="course", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "department_id": self.department_id,
            "department": self.department.to_dict() if self.department else None,
            "student_count": self.student_count,
            "year": self.year,
            "semester_id": self.semester_id,
            "semester": self.semester_obj.name if self.semester_obj else (self.semester or ""),
            "shared_with_departments": self.shared_with_departments,
            "instructors": [u.to_dict() for u in self.instructors],
        }