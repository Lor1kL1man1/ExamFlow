from datetime import datetime

from ..base import db


class Workspace(db.Model):
    __tablename__ = "workspaces"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    manager_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    period_id = db.Column(db.Integer, db.ForeignKey("periods.id"), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    manager = db.relationship("User", foreign_keys=[manager_id])
    period = db.relationship("Period", foreign_keys=[period_id])

    __table_args__ = (
        db.UniqueConstraint("manager_id", "period_id", name="uq_workspace_manager_period"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "manager_id": self.manager_id,
            "period_id": self.period_id,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
