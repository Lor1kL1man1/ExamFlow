import { useState, useEffect, useCallback } from "react";
import { get, post, put, del } from "../utils/api";
import { Icons } from "../utils/constants";
import { Btn, Card, Input, Select, Modal, Badge, Icon } from "../components/ui";

const statusColor = { draft: "#64748B", scheduled: "#059669", conflict: "#DC2626", completed: "#7C3AED", cancelled: "#94A3B8" };
const BLANK_NEW  = { course_id: "", student_count: 0, duration_minutes: 120, notes: "" };
const BLANK_EDIT = { student_count: 0, duration_minutes: 120, notes: "" };

const parseSharedCodes = (value) =>
  String(value || "")
    .split(",")
    .map((x) => x.trim().toUpperCase())
    .filter(Boolean);

export default function ExamsPage({ toast }) {
  const [exams, setExams] = useState([]);
  const [courses, setCourses] = useState([]);
  const [depts, setDepts] = useState([]);
  const [filter, setFilter] = useState("");
  const [editExam, setEditExam] = useState(null); // null=closed, false=new, object=editing
  const [form, setForm] = useState(BLANK_NEW);

  const load = useCallback(() => get("/exams").then(setExams), []);

  useEffect(() => {
    load();
    get("/courses").then(setCourses);
    get("/departments").then(setDepts);
  }, [load]);

  const openAdd = () => { setForm(BLANK_NEW); setEditExam(false); };
  const openEdit = (e) => {
    setForm({ student_count: e.student_count, duration_minutes: e.duration_minutes, notes: e.notes || "" });
    setEditExam(e);
  };
  const closeModal = () => setEditExam(null);

  const submit = async () => {
    try {
      if (editExam && editExam.id) {
        await put(`/exams/${editExam.id}`, form);
        toast("Exam updated!", "success");
      } else {
        const course = courses.find(c => c.id === +form.course_id);
        await post("/exams", { ...form, course_id: +form.course_id, student_count: form.student_count || (course?.student_count ?? 0) });
        toast("Exam created!", "success");
      }
      closeModal();
      load();
    } catch (e) { toast("Error saving exam", "error"); }
  };

  const remove = async (id) => {
    if (!confirm("Delete this exam?")) return;
    await del(`/exams/${id}`);
    load();
    toast("Exam deleted", "success");
  };

  const filtered = filter
    ? exams.filter((e) => {
        const course = e.course;
        if (!course) return false;
        if (course.department?.code === filter) return true;
        return parseSharedCodes(course.shared_with_departments).includes(filter.toUpperCase());
      })
    : exams;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h2 style={{ fontSize: 24, fontWeight: 800, color: "#1E293B", margin: 0 }}>Exams</h2>
        <div style={{ display: "flex", gap: 10 }}>
          <select value={filter} onChange={e => setFilter(e.target.value)} style={{ border: "1.5px solid #E2E8F0", borderRadius: 8, padding: "8px 12px", fontSize: 13, fontFamily: "inherit", color: "#374151" }}>
            <option value="">All Departments</option>
            {depts.map(d => <option key={d.id} value={d.code}>{d.name}</option>)}
          </select>
          <Btn onClick={openAdd}><Icon d={Icons.plus} size={14} /> Create Exam</Btn>
        </div>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {filtered.map(e => (
          <Card key={e.id} style={{ padding: 18 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
                  <span style={{ fontSize: 16, fontWeight: 700, color: "#1E293B" }}>
                    {e.course?.code} — {e.course?.name}
                  </span>
                  <Badge color={statusColor[e.status] || "#64748B"}>{e.status}</Badge>
                  {e.course?.department && <Badge color={e.course.department.color || "#64748B"}>{e.course.department.code}</Badge>}
                </div>
                <div style={{ display: "flex", gap: 16, fontSize: 13, color: "#64748B" }}>
                  <span>👥 {e.student_count} students</span>
                  <span>⏱ {e.duration_minutes} min</span>
                  <span>📋 {(e.sessions || []).length} sessions</span>
                </div>
                {e.status === "conflict" && (
                  <div style={{ marginTop: 8, background: "#FEF2F2", border: "1px solid #FECACA", borderRadius: 8, padding: "6px 10px", fontSize: 12, color: "#DC2626", display: "flex", alignItems: "center", gap: 6 }}>
                    <Icon d={Icons.alert} size={13} /> Scheduling conflict detected
                  </div>
                )}
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <Btn variant="secondary" size="sm" onClick={() => openEdit(e)}>
                  <Icon d={Icons.edit} size={12} /> Edit
                </Btn>
                <Btn variant="danger" size="sm" onClick={() => remove(e.id)}>
                  <Icon d={Icons.trash} size={12} />
                </Btn>
              </div>
            </div>
          </Card>
        ))}
        {filtered.length === 0 && (
          <Card style={{ padding: 48, textAlign: "center" }}>
            <div style={{ fontSize: 40, marginBottom: 12 }}>📋</div>
            <div style={{ color: "#94A3B8", fontSize: 14 }}>No exams found.</div>
          </Card>
        )}
      </div>
      {editExam !== null && (
        <Modal
          title={editExam && editExam.id ? `Edit — ${editExam.course?.code} ${editExam.course?.name}` : "Create Exam"}
          onClose={closeModal}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {!(editExam && editExam.id) && (
              <Select label="Course" value={form.course_id} onChange={e => {
                const c = courses.find(cc => cc.id === +e.target.value);
                setForm(f => ({ ...f, course_id: e.target.value, student_count: c?.student_count || 0 }));
              }}>
                <option value="">Select course...</option>
                {courses.map(c => <option key={c.id} value={c.id}>{c.code} — {c.name}</option>)}
              </Select>
            )}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <Input label="Students" type="number" value={form.student_count} onChange={e => setForm(f => ({ ...f, student_count: +e.target.value }))} />
              <Input label="Duration (min)" type="number" value={form.duration_minutes} onChange={e => setForm(f => ({ ...f, duration_minutes: +e.target.value }))} />
            </div>
            <Input label="Notes (optional)" value={form.notes} onChange={e => setForm(f => ({ ...f, notes: e.target.value }))} placeholder="Any special requirements..." />
            <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
              <Btn onClick={submit}>{editExam && editExam.id ? "Save Changes" : "Create Exam"}</Btn>
              <Btn variant="secondary" onClick={closeModal}>Cancel</Btn>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
