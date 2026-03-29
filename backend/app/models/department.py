from ..base import db


class Department(db.Model):
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    code = db.Column(db.String(10), unique=True, nullable=False)
    color = db.Column(db.String(7), default="#3B82F6")

    members = db.relationship("User", back_populates="department")
    courses = db.relationship("Course", back_populates="department", cascade="all, delete-orphan")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "code": self.code, "color": self.color}