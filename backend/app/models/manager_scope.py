from datetime import datetime

from ..base import db


class ManagerScope(db.Model):
    __tablename__ = "manager_scopes"

    id = db.Column(db.Integer, primary_key=True)
    manager_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)
    year = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    manager = db.relationship("User", foreign_keys=[manager_id])
    department = db.relationship("Department", foreign_keys=[department_id])

    __table_args__ = (
        db.UniqueConstraint("manager_id", "department_id", "year", name="uq_manager_scope"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "manager_id": self.manager_id,
            "manager_name": self.manager.name if self.manager else None,
            "department_id": self.department_id,
            "department_code": self.department.code if self.department else None,
            "year": self.year,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
