from ..base import db
from datetime import datetime


class Semester(db.Model):
    """
    A semester groups a set of courses for a given term.
    e.g. "Spring 2026", "Fall 2026".
    Only one semester is active at a time — that one is pre-selected
    when creating new courses.
    """
    __tablename__ = "semesters"

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(100), nullable=False)  # "Spring 2026"
    is_active  = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    courses = db.relationship("Course", back_populates="semester_obj", lazy="dynamic")

    def to_dict(self):
        return {
            "id":           self.id,
            "name":         self.name,
            "is_active":    self.is_active,
            "created_at":   self.created_at.isoformat() if self.created_at else None,
            "course_count": self.courses.count(),
        }
