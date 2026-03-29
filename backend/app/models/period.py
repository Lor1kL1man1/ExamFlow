from ..base import db
from datetime import datetime


class Period(db.Model):
    """
    An exam period groups a set of Exams and TimeSlots together.
    e.g. "Midterm 2026" or "Final 2026".
    Only one period is active at a time — that is the one shown in the app.
    A maximum of 2 periods are kept; the oldest is deleted when a 3rd is created.
    """
    __tablename__ = "periods"

    id                = db.Column(db.Integer, primary_key=True)
    name              = db.Column(db.String(100), nullable=False)   # "Midterm 2026"
    is_active         = db.Column(db.Boolean, default=False)
    active_slot_type  = db.Column(db.String(10), default="midterm")  # "midterm" | "final"
    created_at        = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships — back_populates defined in Exam / TimeSlot
    exams      = db.relationship("Exam",     back_populates="period", lazy="dynamic")
    time_slots = db.relationship("TimeSlot", back_populates="period", lazy="dynamic")

    def to_dict(self):
        midterm_count = self.time_slots.filter_by(slot_type="midterm").count()
        final_count   = self.time_slots.filter_by(slot_type="final").count()
        return {
            "id":               self.id,
            "name":             self.name,
            "is_active":        self.is_active,
            "active_slot_type": self.active_slot_type or "midterm",
            "created_at":       self.created_at.isoformat() if self.created_at else None,
            "exam_count":       self.exams.count(),
            "slot_count":       self.time_slots.count(),
            "midterm_count":    midterm_count,
            "final_count":      final_count,
        }
