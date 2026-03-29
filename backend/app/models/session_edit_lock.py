from datetime import datetime

from ..base import db


class SessionEditLock(db.Model):
    __tablename__ = "session_edit_locks"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("exam_sessions.id"), nullable=False, unique=True)
    manager_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    session = db.relationship("ExamSession")
    manager = db.relationship("User", foreign_keys=[manager_id])

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "manager_id": self.manager_id,
            "manager_name": self.manager.name if self.manager else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
