from ..base import db


class Classroom(db.Model):
    __tablename__ = "classrooms"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    building = db.Column(db.String(100), nullable=False)
    floor = db.Column(db.Integer, default=0)
    capacity = db.Column(db.Integer, nullable=False)
    has_projector = db.Column(db.Boolean, default=False)
    has_computers = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)

    # Sessions assigned to this room
    session_assignments = db.relationship("SessionAssignment", back_populates="classroom")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "building": self.building,
            "floor": self.floor,
            "capacity": self.capacity,
            "has_projector": self.has_projector,
            "has_computers": self.has_computers,
            "notes": self.notes,
            "is_active": self.is_active,
        }