import { useState, useEffect, useCallback } from "react";
import { get, post, put, del as removeReq, API } from "../../utils/api";
import { Icons } from "../../utils/constants";
import { Btn, Card, Badge, Icon, Modal, Select } from "../ui";

// ── helpers ──────────────────────────────────────────────────────────────────
const getYear = (code) => {
  const m = (code || "").match(/^Y(\d+)-/i);
  return m ? parseInt(m[1], 10) : null;
};

const YEAR_LABELS = { 1: "Year 1", 2: "Year 2", 3: "Year 3", 4: "Year 4" };
const YEAR_COLORS = { 1: "#2563EB", 2: "#059669", 3: "#D97706", 4: "#7C3AED" };
const YEAR_ORDER  = [1, 2, 3, 4, null];

const fmt = (t) => (t || "").slice(0, 5);
const fmtDate = (d) => {
  if (!d) return "—";
  const [y, m, day] = d.split("-");
  return `${day}/${m}/${y}`;
};

const parseSharedCodes = (value) =>
  String(value || "")
    .split(",")
    .map((x) => x.trim().toUpperCase())
    .filter(Boolean);

const CONFLICT_KIND_META = {
  classroom_double_booking: { label: "Classroom", color: "#DC2626", suggestion: "Suggested fix: choose a different classroom or move this exam to another time slot." },
  observer_double_booking: { label: "Observer", color: "#D97706", suggestion: "Suggested fix: choose another available observer or move this exam to another time slot." },
  instructor_double_booking: { label: "Instructor", color: "#2563EB", suggestion: "Suggested fix: assign a different instructor or move this exam to another time slot." },
};

const getConflictItems = (err, fallback) => {
  const items = Array.isArray(err?.conflicts)
    ? err.conflicts
        .filter((conflict) => conflict?.message)
        .map((conflict) => ({
          kind: conflict.kind || "generic_conflict",
          message: conflict.message,
        }))
    : [];
  if (items.length) {
    return items.filter((item, index, all) => all.findIndex((entry) => entry.message === item.message) === index);
  }
  if (err?.error) return [{ kind: "generic_conflict", message: err.error }];
  return [{ kind: "generic_conflict", message: fallback }];
};

const summarizeConflictMessages = (conflictItems, fallback) => {
  const items = (conflictItems || []).map((item) => item?.message).filter(Boolean);
  if (!items.length) return fallback;
  return [
    items[0],
    ...(items.length > 1 ? [`+${items.length - 1} more conflict${items.length > 2 ? "s" : ""}`] : []),
  ].join("\n");
};

// ── ManageModal ───────────────────────────────────────────────────────────────
function ManageModal({ session, timeslots, onClose, onSaved, toast, managerId }) {
  const ts = session.time_slot;
  const [slotId, setSlotId] = useState(ts?.id ?? "");
  const [saving, setSaving] = useState(false);
  const [assignments, setAssignments] = useState(session.assignments || []);
  const [observerOptions, setObserverOptions] = useState({});
  const [classroomOptions, setClassroomOptions] = useState({});
  const [newObservers, setNewObservers] = useState([]);
  const [newClassrooms, setNewClassrooms] = useState([]);
  const [observerByAssignment, setObserverByAssignment] = useState(() =>
    Object.fromEntries((session.assignments || []).map((a) => [a.id, a.observer?.id ? String(a.observer.id) : ""]))
  );
  const [extraObserversByAssignment, setExtraObserversByAssignment] = useState(() =>
    Object.fromEntries((session.assignments || []).map((a) => [a.id, (a.extra_observers || []).map((o) => String(o.id))]))
  );
  const [studentsByAssignment, setStudentsByAssignment] = useState(() =>
    Object.fromEntries((session.assignments || []).map((a) => [a.id, String(a.students_in_room ?? 0)]))
  );
  const [newAssignment, setNewAssignment] = useState({ classroom_id: "", observer_id: "", students_in_room: "0" });
  const [lockStatus, setLockStatus] = useState({ acquired: false, holder: null });
  const [conflictItems, setConflictItems] = useState([]);

  useEffect(() => {
    let released = false;
    const acquire = async () => {
      if (!managerId) {
        toast("Select a manager first", "error");
        onClose();
        return;
      }
      try {
        const res = await post(`/sessions/${session.id}/lock`, { manager_id: managerId, ttl_minutes: 15 });
        if (!released) setLockStatus({ acquired: true, holder: res.manager_name || null });
      } catch (e) {
        if (!released) {
          setLockStatus({ acquired: false, holder: e?.holder || null });
          toast(e?.holder ? `Session is locked by ${e.holder}` : (e?.error || "Could not acquire edit lock"), "error");
          onClose();
        }
      }
    };
    acquire();

    return () => {
      released = true;
      if (managerId) {
        removeReq(`/sessions/${session.id}/lock?manager_id=${managerId}`).catch(() => {});
      }
    };
  }, [session.id, managerId]);

  useEffect(() => {
    let cancelled = false;

    const loadAvailability = async () => {
      const observerEntries = await Promise.all(
        assignments.map(async (assignment) => {
          try {
            const available = await get(`/sessions/${session.id}/available-observers?exclude_assignment_id=${assignment.id}`);
            const current = assignment.observer;
            const merged = current && !available.some((o) => o.id === current.id)
              ? [current, ...available]
              : available;
            return [assignment.id, merged];
          } catch {
            return [assignment.id, assignment.observer ? [assignment.observer] : []];
          }
        })
      );

      const classroomEntries = await Promise.all(
        assignments.map(async (assignment) => {
          try {
            const available = await get(`/sessions/${session.id}/available-classrooms?exclude_assignment_id=${assignment.id}`);
            const current = assignment.classroom;
            const merged = current && !available.some((r) => r.id === current.id)
              ? [current, ...available]
              : available;
            return [assignment.id, merged];
          } catch {
            return [assignment.id, assignment.classroom ? [assignment.classroom] : []];
          }
        })
      );

      let newObserverList = [];
      let newClassroomList = [];
      try {
        newObserverList = await get(`/sessions/${session.id}/available-observers`);
      } catch {}
      try {
        newClassroomList = await get(`/sessions/${session.id}/available-classrooms`);
      } catch {}

      if (!cancelled) {
        setObserverOptions(Object.fromEntries(observerEntries));
        setClassroomOptions(Object.fromEntries(classroomEntries));
        setNewObservers(newObserverList);
        setNewClassrooms(newClassroomList);
      }
    };

    loadAvailability();
    return () => {
      cancelled = true;
    };
  }, [session, assignments]);

  const removeAssignment = async (assignmentId) => {
    try {
      setConflictItems([]);
      await removeReq(`/assignments/${assignmentId}?manager_id=${managerId}`);
      setAssignments((prev) => prev.filter((a) => a.id !== assignmentId));
      setObserverByAssignment((prev) => {
        const next = { ...prev };
        delete next[assignmentId];
        return next;
      });
      setExtraObserversByAssignment((prev) => {
        const next = { ...prev };
        delete next[assignmentId];
        return next;
      });
      setStudentsByAssignment((prev) => {
        const next = { ...prev };
        delete next[assignmentId];
        return next;
      });
      toast("Assignment removed", "success");
    } catch {
      toast("Failed to remove assignment", "error");
    }
  };

  const addAssignment = async () => {
    if (!newAssignment.classroom_id) {
      toast("Select a classroom first", "error");
      return;
    }

    try {
      setConflictItems([]);
      const created = await post(`/sessions/${session.id}/assignments`, {
        classroom_id: +newAssignment.classroom_id,
        observer_id: newAssignment.observer_id ? +newAssignment.observer_id : null,
        extra_observer_ids: [],
        instructor_id: assignments[0]?.instructor?.id || null,
        students_in_room: +(newAssignment.students_in_room || 0),
        manager_id: managerId,
      });
      setAssignments((prev) => [...prev, created]);
      setObserverByAssignment((prev) => ({ ...prev, [created.id]: created.observer?.id ? String(created.observer.id) : "" }));
      setExtraObserversByAssignment((prev) => ({ ...prev, [created.id]: (created.extra_observers || []).map((o) => String(o.id)) }));
      setStudentsByAssignment((prev) => ({ ...prev, [created.id]: String(created.students_in_room ?? 0) }));
      setNewAssignment({ classroom_id: "", observer_id: "", students_in_room: "0" });
      toast("Assignment added", "success");
    } catch (err) {
      const items = getConflictItems(err, "Failed to add assignment");
      setConflictItems(items);
      toast(summarizeConflictMessages(items, "Failed to add assignment"), "error");
    }
  };

  const save = async () => {
    if (!slotId) return;
    setSaving(true);
    try {
      setConflictItems([]);
      if (+slotId !== (ts?.id ?? null)) {
        await put(`/sessions/${session.id}`, { time_slot_id: +slotId, manager_id: managerId });
      }

      for (const assignment of assignments) {
        const nextObserverId = observerByAssignment[assignment.id] ?? "";
        const nextExtraObserverIds = extraObserversByAssignment[assignment.id] || [];
        const currentObserverId = assignment.observer?.id ? String(assignment.observer.id) : "";
        const currentExtraObserverIds = (assignment.extra_observers || []).map((o) => String(o.id));
        const nextStudents = studentsByAssignment[assignment.id] ?? String(assignment.students_in_room ?? 0);
        const currentStudents = String(assignment.students_in_room ?? 0);
        if (
          nextObserverId === currentObserverId &&
          nextStudents === currentStudents &&
          nextExtraObserverIds.join(",") === currentExtraObserverIds.join(",")
        ) continue;

        await put(`/assignments/${assignment.id}`, {
          observer_id: nextObserverId ? +nextObserverId : "",
          extra_observer_ids: nextExtraObserverIds.map((id) => +id),
          students_in_room: +(nextStudents || 0),
          manager_id: managerId,
        });
      }

      toast("Session updated", "success");
      onSaved();
    } catch (err) {
      const items = getConflictItems(err, "Failed to save");
      setConflictItems(items);
      toast(summarizeConflictMessages(items, "Failed to save"), "error");
    }
    setSaving(false);
  };

  const course = session.exam?.course;

  return (
    <Modal
      title={`Manage Session — ${course?.code ?? "?"}: ${course?.name ?? ""}`}
      onClose={onClose}
    >
      {/* current rooms */}
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: "#94A3B8", textTransform: "uppercase", letterSpacing: 1, marginBottom: 10 }}>
          Room Assignments & Observers
        </div>
        {lockStatus.acquired && (
          <div style={{ fontSize: 11, color: "#059669", marginBottom: 8 }}>
            🔒 Edit lock acquired{lockStatus.holder ? ` by ${lockStatus.holder}` : ""}
          </div>
        )}
        {assignments.length === 0 ? (
          <p style={{ color: "#94A3B8", fontSize: 13 }}>No room assignments</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {assignments.map((a) => (
              <div key={a.id} style={{ background: "#F8FAFC", border: "1.5px solid #E2E8F0", borderRadius: 8, padding: "10px 14px", fontSize: 13 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
                  <div style={{ minWidth: 220, flex: "1 1 220px" }}>
                    <div style={{ fontWeight: 700, color: "#1E293B", marginBottom: 6 }}>🏛 {a.classroom?.name}</div>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#94A3B8", textTransform: "uppercase", letterSpacing: 0.8, marginBottom: 6 }}>
                      Students in room
                    </div>
                    <input
                      type="number"
                      min="0"
                      value={studentsByAssignment[a.id] ?? "0"}
                      onChange={(e) => setStudentsByAssignment((prev) => ({ ...prev, [a.id]: e.target.value }))}
                      style={{ width: 120, border: "1.5px solid #E2E8F0", borderRadius: 8, padding: "8px 10px", fontSize: 13, fontFamily: "inherit" }}
                    />
                    {a.instructor && <span style={{ color: "#2563EB" }}> · 👨‍🏫 {a.instructor.name}</span>}
                  </div>
                  <div style={{ minWidth: 240, flex: "1 1 240px" }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: "#94A3B8", textTransform: "uppercase", letterSpacing: 0.8, marginBottom: 6 }}>
                      Observer
                    </div>
                    <Select
                      value={observerByAssignment[a.id] ?? ""}
                      onChange={(e) => {
                        const nextValue = e.target.value;
                        setObserverByAssignment((prev) => ({ ...prev, [a.id]: nextValue }));
                        setExtraObserversByAssignment((prev) => ({
                          ...prev,
                          [a.id]: (prev[a.id] || []).filter((id) => id !== nextValue),
                        }));
                      }}
                      style={{ width: "100%" }}
                    >
                      <option value="">— No observer —</option>
                      {(observerOptions[a.id] || []).map((observer) => (
                        <option key={observer.id} value={observer.id}>{observer.name}</option>
                      ))}
                    </Select>
                    <div style={{ marginTop: 10 }}>
                      <div style={{ fontSize: 11, fontWeight: 700, color: "#94A3B8", textTransform: "uppercase", letterSpacing: 0.8, marginBottom: 6 }}>
                        Additional observers
                      </div>
                      <div style={{ display: "flex", flexDirection: "column", gap: 6, maxHeight: 120, overflow: "auto" }}>
                        {(observerOptions[a.id] || [])
                          .filter((observer) => String(observer.id) !== (observerByAssignment[a.id] ?? ""))
                          .map((observer) => {
                            const checked = (extraObserversByAssignment[a.id] || []).includes(String(observer.id));
                            return (
                              <label key={observer.id} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "#475569" }}>
                                <input
                                  type="checkbox"
                                  checked={checked}
                                  onChange={(e) => {
                                    setExtraObserversByAssignment((prev) => {
                                      const current = prev[a.id] || [];
                                      return {
                                        ...prev,
                                        [a.id]: e.target.checked
                                          ? [...current, String(observer.id)]
                                          : current.filter((id) => id !== String(observer.id)),
                                      };
                                    });
                                  }}
                                />
                                {observer.name}
                              </label>
                            );
                          })}
                      </div>
                    </div>
                    <div style={{ fontSize: 11, color: "#94A3B8", marginTop: 6 }}>
                      Only observers free at this time are listed.
                    </div>
                  </div>
                  <div>
                    <Btn variant="secondary" onClick={() => removeAssignment(a.id)} style={{ padding: "8px 12px", fontSize: 12 }}>
                      Remove
                    </Btn>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={{ marginBottom: 24, padding: "14px", border: "1.5px dashed #CBD5E1", borderRadius: 10, background: "#FCFCFD" }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: "#94A3B8", textTransform: "uppercase", letterSpacing: 1, marginBottom: 10 }}>
          Add Room Assignment
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 10, alignItems: "end" }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#94A3B8", marginBottom: 6 }}>Classroom</div>
            <Select value={newAssignment.classroom_id} onChange={(e) => setNewAssignment((prev) => ({ ...prev, classroom_id: e.target.value }))} style={{ width: "100%" }}>
              <option value="">— Select classroom —</option>
              {newClassrooms.map((room) => (
                <option key={room.id} value={room.id}>{room.name} ({room.capacity})</option>
              ))}
            </Select>
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#94A3B8", marginBottom: 6 }}>Observer</div>
            <Select value={newAssignment.observer_id} onChange={(e) => setNewAssignment((prev) => ({ ...prev, observer_id: e.target.value }))} style={{ width: "100%" }}>
              <option value="">— No observer —</option>
              {newObservers.map((observer) => (
                <option key={observer.id} value={observer.id}>{observer.name}</option>
              ))}
            </Select>
          </div>
          <div>
            <div style={{ fontSize: 11, fontWeight: 700, color: "#94A3B8", marginBottom: 6 }}>Students</div>
            <input
              type="number"
              min="0"
              value={newAssignment.students_in_room}
              onChange={(e) => setNewAssignment((prev) => ({ ...prev, students_in_room: e.target.value }))}
              style={{ width: "100%", border: "1.5px solid #E2E8F0", borderRadius: 8, padding: "8px 10px", fontSize: 13, fontFamily: "inherit" }}
            />
          </div>
          <div>
            <Btn onClick={addAssignment} disabled={!newAssignment.classroom_id}>Add Assignment</Btn>
          </div>
        </div>
        <div style={{ fontSize: 11, color: "#94A3B8", marginTop: 8 }}>
          Add another classroom + observer for this same exam session when you need more observers.
        </div>
      </div>

      {/* change timeslot */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: "#94A3B8", textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>
          Time Slot
        </div>
        <Select
          value={slotId}
          onChange={(e) => setSlotId(e.target.value)}
          style={{ width: "100%" }}
        >
          <option value="">— select time slot —</option>
          {timeslots.map((t) => (
            <option key={t.id} value={t.id}>
              {fmtDate(t.date)} · {fmt(t.start_time)}–{fmt(t.end_time)}
            </option>
          ))}
        </Select>
      </div>

      {conflictItems.length > 0 && (
        <div style={{ marginBottom: 20, padding: "14px 16px", borderRadius: 10, border: "1.5px solid #FECACA", background: "#FEF2F2" }}>
          <div style={{ fontSize: 12, fontWeight: 800, color: "#B91C1C", textTransform: "uppercase", letterSpacing: 0.8, marginBottom: 8 }}>
            Conflict detected
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {conflictItems.map((item, index) => {
              const meta = CONFLICT_KIND_META[item.kind] || { label: "Conflict", color: "#B91C1C", suggestion: "Suggested fix: review the conflicting resource or pick a different time slot." };
              return (
                <div key={`${index}-${item.message}`} style={{ display: "flex", gap: 10, alignItems: "flex-start", padding: "10px 12px", borderRadius: 8, background: "rgba(255,255,255,0.55)", border: "1px solid #FECACA" }}>
                  <div style={{ paddingTop: 1 }}>
                    <Badge color={meta.color}>{meta.label}</Badge>
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 13, lineHeight: 1.45, color: "#7F1D1D" }}>
                      {item.message}
                    </div>
                    <div style={{ fontSize: 12, lineHeight: 1.4, color: "#991B1B", marginTop: 6, fontWeight: 600 }}>
                      {meta.suggestion}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
        <Btn variant="secondary" onClick={onClose}>Cancel</Btn>
        <Btn onClick={save} disabled={saving || !slotId}>
          {saving ? "Saving…" : "Save Changes"}
        </Btn>
      </div>
    </Modal>
  );
}

// ── YearTable ─────────────────────────────────────────────────────────────────
function YearTable({ year, sessions, onManage }) {
  const color  = year ? YEAR_COLORS[year] : "#64748B";
  const label  = year ? YEAR_LABELS[year] : "Other";
  const sorted = [...sessions].sort((a, b) => {
    const da = a.time_slot?.date ?? "";
    const db = b.time_slot?.date ?? "";
    if (da !== db) return da < db ? -1 : 1;
    return (a.time_slot?.start_time ?? "") < (b.time_slot?.start_time ?? "") ? -1 : 1;
  });

  const TH = ({ children, align = "left" }) => (
    <th style={{ padding: "10px 14px", textAlign: align, fontSize: 11, fontWeight: 700, color: "#94A3B8", textTransform: "uppercase", letterSpacing: 0.8, borderBottom: "2px solid #E2E8F0", background: "#F8FAFC" }}>
      {children}
    </th>
  );
  const TD = ({ children, muted, align }) => (
    <td style={{ padding: "12px 14px", fontSize: 13, color: muted ? "#94A3B8" : "#1E293B", borderBottom: "1px solid #F1F5F9", verticalAlign: "top", textAlign: align || "left" }}>
      {children}
    </td>
  );

  return (
    <div style={{ marginBottom: 32 }}>
      {/* heading */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <div style={{ width: 4, height: 24, borderRadius: 2, background: color }} />
        <h3 style={{ margin: 0, fontSize: 17, fontWeight: 800, color: "#1E293B" }}>{label}</h3>
        <Badge color={color}>{sorted.length} session{sorted.length !== 1 ? "s" : ""}</Badge>
      </div>

      {/* table */}
      <div style={{ border: "1.5px solid #E2E8F0", borderRadius: 12, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <TH>Date</TH>
              <TH>Time</TH>
              <TH>Code</TH>
              <TH>Course</TH>
              <TH align="right">Students</TH>
              <TH>Rooms</TH>
              <TH>Observers / Instructors</TH>
              <TH align="center">Actions</TH>
            </tr>
          </thead>
          <tbody>
            {sorted.map((s) => {
              const course = s.exam?.course;
              const rooms = s.assignments || [];
              return (
                <tr key={s.id}
                    onMouseEnter={e => (e.currentTarget.style.background = "#F8FAFC")}
                    onMouseLeave={e => (e.currentTarget.style.background = "")}>
                  <TD>
                    <span style={{ fontWeight: 600 }}>{fmtDate(s.time_slot?.date)}</span>
                  </TD>
                  <TD muted>
                    {fmt(s.time_slot?.start_time)}–{fmt(s.time_slot?.end_time)}
                  </TD>
                  <TD>
                    <span style={{ fontWeight: 700, color, fontFamily: "monospace", fontSize: 12 }}>
                      {course?.code ?? "—"}
                    </span>
                    {s.session_index > 0 && (
                      <Badge color="#D97706" style={{ marginLeft: 6 }}>Split {s.session_index + 1}</Badge>
                    )}
                  </TD>
                  <TD>{course?.name ?? <span style={{ color: "#CBD5E1" }}>Unknown</span>}</TD>
                  <TD align="right">
                    <span style={{ fontWeight: 700 }}>{s.assigned_students}</span>
                  </TD>
                  <TD>
                    {rooms.length === 0 ? (
                      <span style={{ color: "#CBD5E1" }}>—</span>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                        {rooms.map((a) => (
                          <span key={a.id} style={{ display: "flex", alignItems: "center", gap: 4 }}>
                            <span style={{ fontWeight: 600, color: "#475569" }}>🏛 {a.classroom?.name}</span>
                            <span style={{ color: "#94A3B8", fontSize: 12 }}>({a.students_in_room})</span>
                          </span>
                        ))}
                      </div>
                    )}
                  </TD>
                  <TD>
                    {rooms.length === 0 ? (
                      <span style={{ color: "#CBD5E1" }}>—</span>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                        {rooms.map((a) => (
                          <span key={a.id} style={{ fontSize: 12, color: "#64748B" }}>
                            {(a.observers || (a.observer ? [a.observer] : [])).length > 0
                              ? `👁 ${(a.observers || (a.observer ? [a.observer] : [])).map((o) => o.name).join(", ")}`
                              : ""}
                            {(a.observers || (a.observer ? [a.observer] : [])).length > 0 && a.instructor ? " · " : ""}
                            {a.instructor ? `👨‍🏫 ${a.instructor.name}` : ""}
                            {!(a.observers || (a.observer ? [a.observer] : [])).length && !a.instructor ? "—" : ""}
                          </span>
                        ))}
                      </div>
                    )}
                  </TD>
                  <TD align="center">
                    <Btn variant="secondary" onClick={() => onManage(s)} style={{ padding: "5px 14px", fontSize: 12 }}>
                      <Icon d={Icons.edit} size={12} /> Manage
                    </Btn>
                  </TD>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── ScheduleView ──────────────────────────────────────────────────────────────
export default function ScheduleView({ toast, managerId }) {
  const [schedule,   setSchedule]   = useState({});
  const [timeslots,  setTimeslots]  = useState([]);
  const [observers,  setObservers]  = useState([]);
  const [generating, setGenerating] = useState(false);
  const [depts,      setDepts]      = useState([]);
  const [deptFilter, setDeptFilter] = useState("");
  const [managing,   setManaging]   = useState(null);

  const load = useCallback(
    () => Promise.all([
      get(`/schedule${managerId ? `?manager_id=${managerId}` : ""}`).then(setSchedule),
      get("/timeslots").then(setTimeslots),
    ]),
    [managerId]
  );

  useEffect(() => {
    load();
    get("/departments").then(setDepts);
    get("/users?role=observer").then(setObservers);
  }, [load]);

  const generate = async () => {
    if (!managerId) {
      toast("Select a manager first", "error");
      return;
    }
    setGenerating(true);
    try {
      const result = await post("/schedule/generate", { manager_id: managerId });
      await load();
      if (result.warnings?.length) {
        toast(`Schedule generated with ${result.warnings.length} warnings`, "warning");
      } else {
        toast(`✓ ${result.scheduled} exams scheduled successfully!`, "success");
      }
    } catch {
      toast("Failed to generate schedule", "error");
    }
    setGenerating(false);
  };

  const exportSchedule = () => {
    const query = new URLSearchParams();
    if (deptFilter) query.set("department_id", deptFilter);
    if (managerId) query.set("manager_id", String(managerId));
    const url = `${API}/export/schedule${query.toString() ? `?${query.toString()}` : ""}`;
    window.open(url, "_blank");
  };

  const exportObserver = (id) => window.open(`${API}/export/observer/${id}`, "_blank");
  const exportAllObservers = () => window.open(`${API}/export/observers`, "_blank");

  const allSessions = Object.values(schedule).flat();
  const selectedDept = depts.find((d) => d.id === +deptFilter);
  const visible = deptFilter
    ? allSessions.filter((s) => {
        const course = s.exam?.course;
        if (!course) return false;
        if (course.department_id === +deptFilter) return true;
        const shared = parseSharedCodes(course.shared_with_departments);
        return selectedDept ? shared.includes((selectedDept.code || "").toUpperCase()) : false;
      })
    : allSessions;

  // group by year
  const byYear = {};
  visible.forEach((s) => {
    const yr = s.exam?.course?.year ?? getYear(s.exam?.course?.code);
    const key = yr ?? "other";
    (byYear[key] = byYear[key] || []).push(s);
  });
  const yearKeys = YEAR_ORDER.map((y) => (y === null ? "other" : y)).filter((k) => byYear[k]);

  return (
    <div>
      {/* header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <div>
          <h2 style={{ fontSize: 24, fontWeight: 800, color: "#1E293B", margin: 0 }}>Schedule</h2>
          {visible.length > 0 && (
            <p style={{ margin: "4px 0 0", fontSize: 13, color: "#94A3B8" }}>
              {visible.length} session{visible.length !== 1 ? "s" : ""} across {yearKeys.length} year group{yearKeys.length !== 1 ? "s" : ""}
            </p>
          )}
        </div>
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <select
            value={deptFilter}
            onChange={(e) => setDeptFilter(e.target.value)}
            style={{ border: "1.5px solid #E2E8F0", borderRadius: 8, padding: "8px 12px", fontSize: 13, fontFamily: "inherit", color: "#374151", background: "#fff" }}
          >
            <option value="">All Departments</option>
            {depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
          </select>
          <Btn onClick={exportSchedule} variant="secondary">
            <Icon d={Icons.word} size={14} /> Export Schedule (.docx)
          </Btn>
          <Btn onClick={generate} disabled={generating}>
            <Icon d={Icons.generate} size={14} /> {generating ? "Generating…" : "Generate Schedule"}
          </Btn>
        </div>
      </div>

      {/* observer export bar */}
      {observers.length > 0 && (
        <Card style={{ padding: "14px 18px", marginBottom: 24, background: "#F8FAFC" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Icon d={Icons.observer} size={15} color="#7C3AED" />
              <span style={{ fontSize: 13, fontWeight: 700, color: "#1E293B" }}>Observer Assignment Letters</span>
              <span style={{ fontSize: 12, color: "#94A3B8" }}>— download individual .docx per observer</span>
            </div>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
              {observers.map((o) => (
                <button
                  key={o.id}
                  onClick={() => exportObserver(o.id)}
                  title={`Download assignment for ${o.name}`}
                  style={{
                    border: "1.5px solid #E2E8F0", borderRadius: 8, background: "#fff",
                    padding: "5px 12px", fontSize: 12, fontFamily: "inherit", cursor: "pointer",
                    display: "flex", alignItems: "center", gap: 5, color: "#374151",
                    transition: "border-color 0.15s",
                  }}
                  onMouseEnter={e => (e.currentTarget.style.borderColor = "#7C3AED")}
                  onMouseLeave={e => (e.currentTarget.style.borderColor = "#E2E8F0")}
                >
                  <Icon d={Icons.download} size={12} color="#7C3AED" />
                  {o.name}
                </button>
              ))}
              <Btn variant="secondary" onClick={exportAllObservers} style={{ fontSize: 12, padding: "5px 14px" }}>
                <Icon d={Icons.download} size={12} /> Download All (.zip)
              </Btn>
            </div>
          </div>
        </Card>
      )}

      {/* empty state */}
      {visible.length === 0 ? (
        <Card style={{ padding: 64, textAlign: "center" }}>
          <div style={{ fontSize: 48, marginBottom: 16 }}>📅</div>
          <h3 style={{ color: "#1E293B", marginBottom: 8 }}>No schedule yet</h3>
          <p style={{ color: "#94A3B8", fontSize: 14, marginBottom: 24 }}>
            Make sure you have time slots, classrooms, and exams — then click{" "}
            <strong>Generate Schedule</strong>.
          </p>
          <Btn onClick={generate} disabled={generating}>
            <Icon d={Icons.generate} size={14} /> Generate Now
          </Btn>
        </Card>
      ) : (
        yearKeys.map((key) => (
          <YearTable
            key={key}
            year={key === "other" ? null : key}
            sessions={byYear[key]}
            onManage={setManaging}
          />
        ))
      )}

      {/* manage modal */}
      {managing && (
        <ManageModal
          session={managing}
          timeslots={timeslots}
          toast={toast}
          managerId={managerId}
          onClose={() => setManaging(null)}
          onSaved={async () => {
            setManaging(null);
            await load();
          }}
        />
      )}
    </div>
  );
}

