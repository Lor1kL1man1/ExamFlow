"""
AI Scheduling Constraint Agent
================================
Uses Groq (free tier) to parse free-text scheduling instructions into structured
SchedulingConstraint objects that the scheduler engine can enforce.
"""

from __future__ import annotations
import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Literal
from groq import Groq

def _make_client():
    key = os.getenv("GROQ_API_KEY", "")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set. Add it to your .env file.")
    return Groq(api_key=key)

_client = None  # lazy-initialised on first use

def _get_client():
    global _client
    if _client is None:
        _client = _make_client()
    return _client

# llama-3.3-70b-versatile — free tier, fast, excellent for structured extraction
_EXTRACT_MODEL = "llama-3.3-70b-versatile"
_REPLY_MODEL   = "llama-3.3-70b-versatile"

# ---------------------------------------------------------------------------
# Constraint data model
# ---------------------------------------------------------------------------

ConstraintKind = Literal[
    "instructor_day",         # exam must be on a specific weekday
    "instructor_time_range",  # exam must start within a time range
    "instructor_unavailable", # instructor unavailable on a date
    "department_day",         # all dept exams on a weekday
    "department_time_range",  # dept exams within a time range
    "department_no_overlap",  # two departments must not have simultaneous exams
    "exam_room",              # specific exam must use a specific room
    "observer_unavailable",   # observer unavailable on a date
    "exam_day",               # specific exam must be on a weekday
    "exam_time_range",        # specific exam must be within a time range
    "course_day",             # specific course exam must be on a weekday
    "observer_exam_load",     # target observer to invigilate N exams
]

WEEKDAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


@dataclass
class SchedulingConstraint:
    kind: ConstraintKind
    # Targets (use whichever are relevant to the kind)
    instructor_name: Optional[str] = None   # fuzzy matched against DB
    department_code: Optional[str] = None
    course_code: Optional[str] = None
    observer_name: Optional[str] = None
    room_name: Optional[str] = None
    # Constraint values
    weekday: Optional[int] = None           # 0=Mon … 6=Sun
    date_str: Optional[str] = None          # "YYYY-MM-DD" for unavailability
    start_time: Optional[str] = None        # "HH:MM"
    end_time: Optional[str] = None          # "HH:MM"
    department_code_b: Optional[str] = None # for no_overlap constraints
    target_count: Optional[int] = None      # e.g. observer should invigilate N exams
    # Human-readable explanation produced by the agent
    explanation: str = ""
    # Confidence 0-1 (agent self-assessed)
    confidence: float = 1.0

    def to_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}


# ---------------------------------------------------------------------------
# Constraint Agent
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are a university exam scheduling assistant. Your job is to parse natural
language scheduling instructions into structured JSON constraints.

For each instruction you receive, output a JSON array of constraint objects.
Each object must include a "kind" field from this list:
  instructor_day         - exam for this instructor locked to a weekday
  instructor_time_range  - exam for this instructor must be within a time range
  instructor_unavailable - instructor unavailable on a specific date
  department_day         - all exams of this department on a weekday
  department_time_range  - all exams of this department within a time range
  department_no_overlap  - two departments must not have simultaneous exams
  exam_room              - this exam must use this classroom
  observer_unavailable   - observer unavailable on a specific date
  exam_day               - a specific exam must be on a weekday
  exam_time_range        - a specific exam must be within a time range
  course_day             - course exam must be on a weekday
    observer_exam_load     - observer should invigilate a target number of exams

Additional fields (include only what is relevant):
  instructor_name    - full or partial instructor name (string)
  department_code    - e.g. "CE", "ARCH", "AIE", "CIVIL", "IEM"
  course_code        - course code, e.g. "CS401"
  observer_name      - full or partial observer name
  room_name          - room ID/name, e.g. "A-101"
  weekday            - integer 0=Monday … 6=Sunday
  date_str           - "YYYY-MM-DD"
  start_time         - "HH:MM" (24h)
  end_time           - "HH:MM" (24h)
  department_code_b  - second department for no_overlap constraint
    target_count       - integer target count (e.g. 12 exams)
  explanation        - one sentence explaining the constraint
  confidence         - float 0.0-1.0 (how certain you are about the parse)

Department codes available:
  ARCH  = Architecture
  CE    = Computer Engineering
  AIE   = AI Engineering
  CIVIL = Civil Engineering
  IEM   = Industrial Engineering & Management

IMPORTANT: Return ONLY the raw JSON array with no markdown fences, no prose.
If you cannot parse the instruction, return an empty array [].
""".strip()


class ConstraintAgent:
    """
    Stateful multi-turn agent that accumulates constraints from a conversation.
    Users can correct misunderstandings and the agent maintains context.
    """

    def __init__(self):
        self.history: List[dict] = []
        self.constraints: List[SchedulingConstraint] = []
        self.pending_review: List[SchedulingConstraint] = []

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def chat(self, user_message: str) -> dict:
        """
        Send a user message to the agent. Returns:
          {
            "reply": str,               # conversational response
            "new_constraints": [...],    # newly parsed constraints
            "all_constraints": [...],    # accumulated so far
            "needs_clarification": bool
          }
        """
        self.history.append({"role": "user", "content": user_message})

        # Step 1: extract structured constraints
        new_constraints = self._extract_constraints(user_message)

        # Step 2: generate a natural conversational reply
        reply = self._generate_reply(user_message, new_constraints)

        self.constraints.extend(new_constraints)
        self.history.append({"role": "assistant", "content": reply})

        low_confidence = [c for c in new_constraints if c.confidence < 0.75]

        return {
            "reply": reply,
            "new_constraints": [c.to_dict() for c in new_constraints],
            "all_constraints": [c.to_dict() for c in self.constraints],
            "needs_clarification": len(low_confidence) > 0,
        }

    def remove_constraint(self, index: int):
        """Remove a constraint by index (0-based)."""
        if 0 <= index < len(self.constraints):
            removed = self.constraints.pop(index)
            return removed.to_dict()
        return None

    def clear(self):
        self.constraints.clear()
        self.history.clear()

    def get_summary(self) -> str:
        """Ask the agent to summarise all active constraints."""
        if not self.constraints:
            return "No constraints have been set yet."

        constraint_list = "\n".join(
            f"- [{c.kind}] {c.explanation}" for c in self.constraints
        )
        resp = _get_client().chat.completions.create(
            model=_REPLY_MODEL,
            messages=[
                {"role": "system", "content": "You are a university exam scheduling assistant. Summarise the following scheduling constraints clearly and concisely in plain English, grouped by type."},
                {"role": "user", "content": f"Active constraints:\n{constraint_list}\n\nProvide a clear summary."},
            ],
        )
        return resp.choices[0].message.content.strip()

    # -----------------------------------------------------------------------
    # Internal: constraint extraction
    # -----------------------------------------------------------------------

    def _extract_constraints(self, user_message: str) -> List[SchedulingConstraint]:
        """Call Gemini to parse user message into constraint objects."""
        history_text = ""
        for msg in self.history[:-1]:
            role = "User" if msg["role"] == "user" else "Assistant"
            history_text += f"{role}: {msg['content']}\n"

        prompt = (
            f"{history_text}"
            f"Parse this scheduling instruction into JSON:\n\n{user_message}"
        )
        resp = _get_client().chat.completions.create(
            model=_EXTRACT_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        raw = resp.choices[0].message.content.strip()
        raw = re.sub(r"^```(?:json)?", "", raw).rstrip("```").strip()

        try:
            data = json.loads(raw)
            if not isinstance(data, list):
                data = [data]
            parsed = [
                SchedulingConstraint(**{k: v for k, v in item.items() if k in SchedulingConstraint.__dataclass_fields__})
                for item in data
            ]
            parsed = [self._normalize_constraint(c, user_message) for c in parsed]

            # Rule-based fallback for observer load target phrasing
            if not any(c.kind == "observer_exam_load" for c in parsed):
                fallback = self._fallback_observer_load(user_message)
                if fallback:
                    parsed.append(fallback)

            return parsed
        except Exception:
            fallback = self._fallback_observer_load(user_message)
            return [fallback] if fallback else []

    def _fallback_observer_load(self, user_message: str) -> Optional[SchedulingConstraint]:
        text = user_message.strip()

        patterns = [
            r"(?i)put\s+(.+?)\s+in\s+(\d+)\s+exams?\s+as\s+observers?",
            r"(?i)assign\s+(.+?)\s+to\s+(\d+)\s+exams?\s+as\s+observers?",
            r"(?i)(.+?)\s+should\s+be\s+in\s+(\d+)\s+exams?\s+as\s+observers?",
            r"(?i)(.+?)\s+in\s+(\d+)\s+exams?\s+as\s+observers?",
        ]
        for p in patterns:
            m = re.search(p, text)
            if m:
                name = m.group(1).strip(" .,!?")
                try:
                    count = int(m.group(2))
                except Exception:
                    continue
                return SchedulingConstraint(
                    kind="observer_exam_load",
                    observer_name=name,
                    target_count=max(0, count),
                    explanation=f"Assign observer {name} to about {count} exams",
                    confidence=0.9,
                )
        return None

    def _normalize_constraint(self, c: SchedulingConstraint, user_message: str) -> SchedulingConstraint:
        """Normalize model output to our canonical formats."""
        # Remove titles from instructor names (UI already prefixes with "Prof.")
        if c.instructor_name:
            c.instructor_name = re.sub(r"^\s*(professor|prof\.?|dr\.?|mr\.?|ms\.?|mrs\.?)\s+", "", c.instructor_name, flags=re.IGNORECASE).strip()

        # Weekday normalization:
        # 1) If text explicitly mentions a weekday, trust that text.
        # 2) Else if model returned 1..7, treat it as 1-based and convert to 0..6.
        if c.weekday is not None:
            text = f"{user_message} {c.explanation or ''}".lower()
            explicit = next((idx for name, idx in WEEKDAY_MAP.items() if name in text), None)
            if explicit is not None:
                c.weekday = explicit
            elif isinstance(c.weekday, int) and 1 <= c.weekday <= 7:
                c.weekday = c.weekday - 1

            # Guard against invalid values
            if not isinstance(c.weekday, int) or c.weekday < 0 or c.weekday > 6:
                c.weekday = None

        # Time-range normalization:
        # If user says "start at/from HH:MM" and no end time is provided,
        # treat it as an exact start-time lock.
        if c.kind in ("instructor_time_range", "department_time_range", "exam_time_range", "course_time_range"):
            if c.start_time and not c.end_time:
                text = f"{user_message} {c.explanation or ''}".lower()
                if re.search(r"\bstart(?:ing)?\s+(?:at|from)\b", text):
                    c.end_time = c.start_time

        # Observer load normalization
        if c.kind == "observer_exam_load":
            if c.observer_name:
                c.observer_name = re.sub(r"^\s*(observer|proctor)\s+", "", c.observer_name, flags=re.IGNORECASE).strip()
            if c.target_count is None:
                text = f"{user_message} {c.explanation or ''}"
                m = re.search(r"\b(\d+)\s+exams?\b", text, flags=re.IGNORECASE)
                if m:
                    c.target_count = int(m.group(1))
            if c.target_count is not None:
                c.target_count = max(0, int(c.target_count))

        return c

    def _generate_reply(self, user_message: str, parsed: List[SchedulingConstraint]) -> str:
        """Generate a friendly conversational acknowledgment."""
        if not parsed:
            context = "You could not parse any constraints from the message. Politely ask for clarification."
        else:
            descriptions = "; ".join(c.explanation for c in parsed if c.explanation)
            context = f"You successfully parsed these constraints: {descriptions}. Confirm them clearly and ask if anything should be adjusted."

        history_text = ""
        for msg in self.history[:-1]:
            role = "User" if msg["role"] == "user" else "Assistant"
            history_text += f"{role}: {msg['content']}\n"

        prompt = (
            f"{history_text}"
            f"User: {user_message}\n"
            f"[Internal note: {context}]\n"
            f"Now write your actual conversational reply to the user based on the internal note."
        )
        resp = _get_client().chat.completions.create(
            model=_REPLY_MODEL,
            messages=[
                {"role": "system", "content": (
                    "You are a friendly, concise university exam scheduling assistant. "
                    "Respond in 2-3 sentences max. Be specific about what you understood. "
                    "Don't use bullet points."
                )},
                {"role": "user", "content": prompt},
            ],
        )
        return resp.choices[0].message.content.strip()


# ---------------------------------------------------------------------------
# Constraint application — filters slots/rooms/people in the scheduler
# ---------------------------------------------------------------------------

def apply_constraints_to_scheduler(
    constraints: List[SchedulingConstraint],
    slots,         # List[SlotInfo]
    rooms,         # List[RoomInfo]
    observers,     # List[PersonInfo]
    exams,         # List[ExamRequest] (enriched with dept/instructor names)
) -> tuple:
    """
    Filters and annotates slots/rooms/observers based on constraints.
    Returns (filtered_slots, filtered_rooms, filtered_observers, exam_overrides)
    where exam_overrides is a dict: exam_id -> {slot_ids, room_ids}

    Multiple constraints on the same exam INTERSECT (e.g. "Ervin on Fridays"
    AND "Ervin from 8:30" → only Friday slots that start at/after 8:30).
    """
    exam_overrides = {}

    def _ovr(exam_id):
        return exam_overrides.setdefault(exam_id, {"slot_ids": None, "room_ids": None})

    def _restrict_slots(exam_id, allowed_ids):
        """Intersect new allowed_ids with whatever is already set (None = all)."""
        allowed_set = set(allowed_ids)
        ovr = _ovr(exam_id)
        if ovr["slot_ids"] is None:
            ovr["slot_ids"] = list(allowed_set)
        else:
            ovr["slot_ids"] = [sid for sid in ovr["slot_ids"] if sid in allowed_set]

    def _restrict_rooms(exam_id, allowed_ids):
        allowed_set = set(allowed_ids)
        ovr = _ovr(exam_id)
        if ovr["room_ids"] is None:
            ovr["room_ids"] = list(allowed_set)
        else:
            ovr["room_ids"] = [rid for rid in ovr["room_ids"] if rid in allowed_set]

    for c in constraints:

        # ── instructor_day: lock instructor's exams to one weekday ──────────
        if c.kind == "instructor_day" and c.instructor_name and c.weekday is not None:
            allowed = [s.id for s in slots if s.date.weekday() == c.weekday]
            for exam in exams:
                if _name_matches(c.instructor_name, getattr(exam, "instructor_names", [])):
                    _restrict_slots(exam.exam_id, allowed)

        # ── department_day ──────────────────────────────────────────────────
        elif c.kind == "department_day" and c.department_code and c.weekday is not None:
            allowed = [s.id for s in slots if s.date.weekday() == c.weekday]
            for exam in exams:
                if getattr(exam, "department_code", "") == c.department_code:
                    _restrict_slots(exam.exam_id, allowed)

        # ── instructor_time_range: exams must start within a window ─────────
        elif c.kind == "instructor_time_range" and c.instructor_name:
            s_t = _parse_time(c.start_time)
            e_t = _parse_time(c.end_time)
            allowed = [s.id for s in slots
                       if (not s_t or s.start >= s_t) and (not e_t or s.start <= e_t)]
            for exam in exams:
                if _name_matches(c.instructor_name, getattr(exam, "instructor_names", [])):
                    _restrict_slots(exam.exam_id, allowed)

        # ── department_time_range ───────────────────────────────────────────
        elif c.kind == "department_time_range" and c.department_code:
            s_t = _parse_time(c.start_time)
            e_t = _parse_time(c.end_time)
            allowed = [s.id for s in slots
                       if (not s_t or s.start >= s_t) and (not e_t or s.start <= e_t)]
            for exam in exams:
                if getattr(exam, "department_code", "") == c.department_code:
                    _restrict_slots(exam.exam_id, allowed)

        # ── instructor_unavailable: exclude a specific date ─────────────────
        elif c.kind == "instructor_unavailable" and c.instructor_name and c.date_str:
            try:
                from datetime import date as _date
                unavail = _date.fromisoformat(c.date_str)
                allowed = [s.id for s in slots if s.date != unavail]
                for exam in exams:
                    if _name_matches(c.instructor_name, getattr(exam, "instructor_names", [])):
                        _restrict_slots(exam.exam_id, allowed)
            except Exception:
                pass

        # ── exam_day / course_day: specific course on a weekday ─────────────
        elif c.kind in ("exam_day", "course_day") and c.course_code and c.weekday is not None:
            allowed = [s.id for s in slots if s.date.weekday() == c.weekday]
            for exam in exams:
                if getattr(exam, "course_code", None) == c.course_code:
                    _restrict_slots(exam.exam_id, allowed)

        # ── exam_time_range / course_time_range ─────────────────────────────
        elif c.kind in ("exam_time_range", "course_time_range") and c.course_code:
            s_t = _parse_time(c.start_time)
            e_t = _parse_time(c.end_time)
            allowed = [s.id for s in slots
                       if (not s_t or s.start >= s_t) and (not e_t or s.start <= e_t)]
            for exam in exams:
                if getattr(exam, "course_code", None) == c.course_code:
                    _restrict_slots(exam.exam_id, allowed)

        # ── exam_room: specific course must use a specific room ─────────────
        elif c.kind == "exam_room" and c.room_name:
            matched = [r.id for r in rooms if c.room_name.lower() in r.name.lower()]
            for exam in exams:
                if getattr(exam, "course_code", None) == c.course_code:
                    _restrict_rooms(exam.exam_id, matched)

        # ── observer_unavailable: remove observer from all slots on that date
        elif c.kind == "observer_unavailable" and c.observer_name:
            observers = [
                o for o in observers
                if not _name_matches(c.observer_name, [o.name])
            ]

    return slots, rooms, observers, exam_overrides


def _name_matches(query: str, names: List[str]) -> bool:
    """
    Fuzzy name match — strips academic prefixes, then checks substring
    or any shared word between query and each candidate name.
    """
    q = query.lower().strip()
    # Strip common academic prefixes so "Professor Ervin" → "Ervin"
    for prefix in ("professor ", "prof. ", "prof ", "dr. ", "dr ", "assoc. prof. ", "asst. prof. "):
        if q.startswith(prefix):
            q = q[len(prefix):]
            break
    if not q:
        return False
    # Substring match
    if any(q in n.lower() for n in names):
        return True
    # Word-level match: any word in the query appears in any candidate name
    q_words = {w for w in q.split() if len(w) > 2}
    for n in names:
        n_words = set(n.lower().split())
        if q_words & n_words:
            return True
    return False


def _parse_time(t_str: Optional[str]):
    if not t_str:
        return None
    from datetime import time
    try:
        h, m = t_str.split(":")
        return time(int(h), int(m))
    except Exception:
        return None
