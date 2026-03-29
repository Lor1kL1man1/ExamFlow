from ..base import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import enum


class UserRole(enum.Enum):
    MANAGER = "manager"
    INSTRUCTOR = "instructor"
    OBSERVER = "observer"


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.Enum(UserRole), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    department = db.relationship("Department", back_populates="members")
    # Availability windows for observers
    availability = db.relationship("ObserverAvailability", back_populates="observer", cascade="all, delete-orphan")
    # Sessions where this user is an instructor
    instructor_sessions = db.relationship(
        "SessionAssignment",
        foreign_keys="SessionAssignment.instructor_id",
        back_populates="instructor",
    )
    # Sessions where this user is an observer
    observer_sessions = db.relationship(
        "SessionAssignment",
        foreign_keys="SessionAssignment.observer_id",
        back_populates="observer",
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role.value,
            "department_id": self.department_id,
            "is_active": self.is_active,
        }


class ObserverAvailability(db.Model):
    """Optional availability windows for observers (used to prefer assignments)."""
    __tablename__ = "observer_availability"

    id = db.Column(db.Integer, primary_key=True)
    observer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)

    observer = db.relationship("User", back_populates="availability")