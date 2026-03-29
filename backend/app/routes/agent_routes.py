"""
AI Agent API Routes — add these to the Flask app in app/__init__.py
"""
from collections import defaultdict

# In-memory sessions (in production use Redis or DB-backed sessions)
_agent_sessions: dict = {}


def register_agent_routes(app):
    from flask import request, jsonify
    from app.services.constraint_agent import ConstraintAgent, apply_constraints_to_scheduler, _name_matches

    def _get_session(session_id: str) -> ConstraintAgent:
        if session_id not in _agent_sessions:
            _agent_sessions[session_id] = ConstraintAgent()
        return _agent_sessions[session_id]

    # -----------------------------------------------------------------------
    # POST /api/agent/chat
    # Body: { "session_id": "mgr1", "message": "Schedule Ervin's courses on Fridays" }
    # -----------------------------------------------------------------------
    @app.post("/api/agent/chat")
    def agent_chat():
        data = request.json
        session_id = data.get("session_id", "default")
        message = data.get("message", "").strip()
        if not message:
            return jsonify({"error": "message is required"}), 400

        agent = _get_session(session_id)
        try:
            result = agent.chat(message)
        except Exception as e:
            err_str = str(e)
            # Surface quota / auth errors as readable JSON
            if "429" in err_str or "rate_limit" in err_str.lower() or "rate limit" in err_str.lower():
                return jsonify({"error": "AI API rate limit reached. Please wait a moment and try again.", "detail": err_str[:300]}), 429
            if "401" in err_str or "403" in err_str or "api_key" in err_str.lower() or "authentication" in err_str.lower():
                return jsonify({"error": "GROQ_API_KEY is invalid or missing.", "detail": err_str[:300]}), 403
            return jsonify({"error": "AI agent error", "detail": err_str[:300]}), 500
        return jsonify(result)

    # -----------------------------------------------------------------------
    # GET /api/agent/constraints?session_id=mgr1
    # -----------------------------------------------------------------------
    @app.get("/api/agent/constraints")
    def agent_get_constraints():
        session_id = request.args.get("session_id", "default")
        agent = _get_session(session_id)
        return jsonify({
            "constraints": [c.to_dict() for c in agent.constraints],
            "count": len(agent.constraints),
        })

    # -----------------------------------------------------------------------
    # DELETE /api/agent/constraints/<index>?session_id=mgr1
    # -----------------------------------------------------------------------
    @app.delete("/api/agent/constraints/<int:index>")
    def agent_remove_constraint(index):
        session_id = request.args.get("session_id", "default")
        agent = _get_session(session_id)
        removed = agent.remove_constraint(index)
        if removed:
            return jsonify({"removed": removed})
        return jsonify({"error": "Index out of range"}), 404

    # -----------------------------------------------------------------------
    # POST /api/agent/clear?session_id=mgr1
    # -----------------------------------------------------------------------
    @app.post("/api/agent/clear")
    def agent_clear():
        data = request.json or {}
        session_id = data.get("session_id") or request.args.get("session_id", "default")
        agent = _get_session(session_id)
        agent.clear()
        return jsonify({"cleared": True})

    # -----------------------------------------------------------------------
    # GET /api/agent/summary?session_id=mgr1
    # -----------------------------------------------------------------------
    @app.get("/api/agent/summary")
    def agent_summary():
        session_id = request.args.get("session_id", "default")
        agent = _get_session(session_id)
        return jsonify({"summary": agent.get_summary()})

    # -----------------------------------------------------------------------
    # POST /api/schedule/generate-with-constraints
    # Body: { "session_id": "mgr1", "exam_ids": null }
    # Runs scheduler with the agent's current constraints applied
    # -----------------------------------------------------------------------
    @app.post("/api/schedule/generate-with-constraints")
    def generate_with_constraints():
        from app.services.scheduler import (
            ExamScheduler, SlotInfo, RoomInfo, PersonInfo, ExamRequest,
            _persist_plans,
        )
        from app.models.exam import Exam, TimeSlot, ExamStatus
        from app.models.period import Period
        from app.models.classroom import Classroom
        from app.models.user import User, UserRole
        from app import db

        data = request.json or {}
        session_id = data.get("session_id", "default")
        exam_ids = data.get("exam_ids")

        agent = _get_session(session_id)
        constraints = agent.constraints

        # Active period + active slot type (same behavior as main scheduler)
        active_period = Period.query.filter_by(is_active=True).first()
        active_slot_type = (active_period.active_slot_type if active_period else "midterm") or "midterm"

        # Load raw data
        slot_q = TimeSlot.query.order_by(TimeSlot.date, TimeSlot.start_time)
        if active_period:
            slot_q = slot_q.filter_by(period_id=active_period.id)
        slot_q = slot_q.filter_by(slot_type=active_slot_type)
        raw_slots = slot_q.all()
        slots = [SlotInfo(s.id, s.date, s.start_time, s.end_time) for s in raw_slots]

        raw_rooms = Classroom.query.filter_by(is_active=True).all()
        rooms = [RoomInfo(r.id, r.capacity, r.name) for r in raw_rooms]

        raw_obs = User.query.filter_by(role=UserRole.OBSERVER, is_active=True).all()
        observers = [PersonInfo(u.id, u.name) for u in raw_obs]

        # Reset all scheduled/conflict exams back to draft so they get re-scheduled
        from app.models.exam import ExamSession, SessionAssignment
        reset_query = Exam.query.filter(
            Exam.status.in_([ExamStatus.SCHEDULED, ExamStatus.CONFLICT])
        )
        if active_period:
            reset_query = reset_query.filter_by(period_id=active_period.id)
        if exam_ids:
            reset_query = reset_query.filter(Exam.id.in_(exam_ids))
        exams_to_reset = reset_query.all()
        for ex in exams_to_reset:
            for sess in list(ex.sessions):
                SessionAssignment.query.filter_by(session_id=sess.id).delete()
                db.session.delete(sess)
            ex.status = ExamStatus.DRAFT
        db.session.commit()

        query = Exam.query.filter(Exam.status.in_([ExamStatus.DRAFT, ExamStatus.CONFLICT]))
        if active_period:
            query = query.filter_by(period_id=active_period.id)
        if exam_ids:
            query = query.filter(Exam.id.in_(exam_ids))
        raw_exams = query.all()

        # Build enriched ExamRequest objects (extra fields needed for constraint matching)
        class EnrichedExamRequest(ExamRequest):
            instructor_names: list = []
            department_code: str = ""

        requests = []
        for e in raw_exams:
            req = ExamRequest(
                exam_id=e.id,
                student_count=e.student_count,
                duration_minutes=e.duration_minutes,
                instructor_ids=[u.id for u in e.course.instructors],
                academic_year=e.course.year,
            )
            req.instructor_names = [u.name for u in e.course.instructors]
            req.department_code = e.course.department.code if e.course.department else ""
            req.course_code = e.course.code
            requests.append(req)

        # Apply constraints (filters slots/rooms per exam)
        slots, rooms, observers, exam_overrides = apply_constraints_to_scheduler(
            constraints, slots, rooms, observers, requests
        )

        # Observer load targets (e.g. "Lorik in 12 exams as observer")
        observer_targets = {}
        extra_warnings = []
        for c in constraints:
            if c.kind != "observer_exam_load" or not c.observer_name or c.target_count is None:
                continue
            matched = [o for o in observers if _name_matches(c.observer_name, [o.name])]
            if not matched:
                extra_warnings.append(f"Observer target ignored: no active observer matched '{c.observer_name}'.")
                continue
            # If multiple match, apply same target to each match
            for o in matched:
                observer_targets[o.id] = max(observer_targets.get(o.id, 0), int(c.target_count))

        # Run scheduler with per-exam slot/room overrides
        from app.models.exam import ExamSession
        from app.services.scheduler import BookingRegistry
        registry = BookingRegistry(slots)
        year_day_counts = defaultdict(lambda: defaultdict(int))
        if active_period:
            existing_sessions = (
                ExamSession.query
                .join(Exam)
                .filter(
                    Exam.period_id == active_period.id,
                    Exam.status == ExamStatus.SCHEDULED,
                )
                .all()
            )
            for sess in existing_sessions:
                if sess.time_slot_id in registry._slots:
                    year = sess.exam.course.year if sess.exam and sess.exam.course else None
                    if year and sess.time_slot and sess.time_slot.date:
                        year_day_counts[year][sess.time_slot.date] += 1
                    for assign in sess.assignments:
                        registry.book_room(assign.classroom_id, sess.time_slot_id)
                        if assign.observer_id:
                            registry.book_person(assign.observer_id, sess.time_slot_id)
                        for extra_id in assign.get_extra_observer_ids():
                            registry.book_person(extra_id, sess.time_slot_id)
                        if assign.instructor_id:
                            registry.book_person(assign.instructor_id, sess.time_slot_id)

        scheduler = ExamScheduler(
            slots,
            rooms,
            observers,
            observer_targets=observer_targets,
            year_day_counts=year_day_counts,
            existing_registry=registry,
        )

        # Temporarily filter slot/room lists per exam using overrides
        all_plans = []
        for req in requests:
            ovr = exam_overrides.get(req.exam_id, {})
            allowed_slot_ids = ovr.get("slot_ids")
            allowed_room_ids = ovr.get("room_ids")

            if allowed_slot_ids is not None:
                scheduler.slots = [s for s in slots if s.id in allowed_slot_ids]
            else:
                scheduler.slots = slots

            if allowed_room_ids is not None:
                scheduler.rooms = [r for r in rooms if r.id in allowed_room_ids]
            else:
                scheduler.rooms = sorted(rooms, key=lambda r: r.capacity, reverse=True)

            plan = scheduler._schedule_exam(req)
            all_plans.append(plan)

        _persist_plans(all_plans, db)

        # Report unmet observer targets (best-effort constraints)
        observer_by_id = {o.id: o.name for o in observers}
        for oid, target in observer_targets.items():
            actual = len(scheduler.observer_exam_ids.get(oid, set()))
            if actual < target:
                extra_warnings.append(
                    f"Observer target not fully met for {observer_by_id.get(oid, oid)}: requested {target}, assigned {actual}."
                )

        constraint_summary = [c.explanation for c in constraints if c.explanation]
        return jsonify({
            "scheduled": len([p for p in all_plans if p.sessions]),
            "warnings": [w for p in all_plans for w in p.warnings] + extra_warnings,
            "applied_constraints": constraint_summary,
        })
