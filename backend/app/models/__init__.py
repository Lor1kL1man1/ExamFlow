# models/__init__.py
from ..base import db
from .user import User
from .department import Department
from .classroom import Classroom
from .course import Course
from .semester import Semester      # must be before course.py (FK dependency)
from .period import Period          # must be before exam.py (FK dependency)
from .workspace import Workspace
from .manager_scope import ManagerScope
from .session_edit_lock import SessionEditLock
from .exam import Exam, ExamSession, SessionAssignment
from .timeslot import TimeSlot
