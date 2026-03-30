import { useState, useEffect } from "react";
import { get, post, put } from "../utils/api";
import { Icons } from "../utils/constants";
import { Btn, Card, Input, Select, Modal, Badge, Icon } from "../components/ui";

const YEAR_COLORS = { 1: "#2563EB", 2: "#059669", 3: "#D97706", 4: "#7C3AED" };
const BLANK = { code: "", name: "", department_id: "", student_count: 30, semester_id: "", year: "", instructor_ids: [], shared_department_ids: [] };

const parseSharedCodes = (value) =>
  String(value || "")
    .split(",")
    .map((x) => x.trim().toUpperCase())
    .filter(Boolean);

export default function CoursesPage({ toast }) {
  const [courses, setCourses]       = useState([]);
  const [depts, setDepts]           = useState([]);
  const [instructors, setInstructors] = useState([]);
  const [semesters, setSemesters]   = useState([]);
  const [filterDept, setFilterDept] = useState("");
  const [filterSem, setFilterSem]   = useState("");
  const [editCourse, setEditCourse] = useState(null);
  const [form, setForm]             = useState(BLANK);

  const reload = () => get("/courses").then(setCourses);

  useEffect(() => {
    reload();
    get("/departments").then(setDepts);
    get("/users?role=instructor").then(setInstructors);
    get("/semesters").then(data => {
      setSemesters(data);
      // Pre-select the active semester for new courses
      const active = data.find(s => s.is_active);
      if (active) setForm(f => ({ ...f, semester_id: active.id }));
    });
  }, []);

  const openAdd = () => {
    const active = semesters.find(s => s.is_active);
    setForm({ ...BLANK, semester_id: active ? active.id : "" });
    setEditCourse(false);
  };
  const openEdit = (c) => {
    const sharedCodes = parseSharedCodes(c.shared_with_departments);
    const sharedDepartmentIds = depts
      .filter((d) => sharedCodes.includes(String(d.code || "").toUpperCase()))
      .map((d) => d.id);

    setForm({
      code: c.code, name: c.name,
      department_id: c.department_id || "",
      student_count: c.student_count,
      semester_id: c.semester_id || "",
      year: c.year || "",
      instructor_ids: (c.instructors || []).map(u => u.id),
      shared_department_ids: sharedDepartmentIds,
    });
    setEditCourse(c);
  };
  const closeModal = () => setEditCourse(null);

  const submit = async () => {
    try {
      const payload = {
        ...form,
        department_id: +form.department_id,
        semester_id: form.semester_id ? +form.semester_id : null,
        year: form.year ? +form.year : null,
        shared_department_ids: (form.shared_department_ids || []).filter((id) => +id !== +form.department_id).map((id) => +id),
      };
      if (editCourse && editCourse.id) {
        await put(`/courses/${editCourse.id}`, payload);
        toast("Course updated!", "success");
      } else {
        await post("/courses", payload);
        toast("Course created and exam added to draft!", "success");
      }
      closeModal(); reload();
    } catch { toast("Error saving course", "error"); }
  };

  let filtered = courses;
  if (filterDept) {
    filtered = filtered.filter((c) =>
      c.department?.code === filterDept ||
      parseSharedCodes(c.shared_with_departments).includes(filterDept.toUpperCase())
    );
  }
  if (filterSem)  filtered = filtered.filter(c => c.semester_id === +filterSem);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h2 style={{ fontSize: 24, fontWeight: 800, color: "#1E293B", margin: 0 }}>Courses</h2>
        <div style={{ display: "flex", gap: 10 }}>
          <select value={filterSem} onChange={e => setFilterSem(e.target.value)} style={{ border: "1.5px solid #E2E8F0", borderRadius: 8, padding: "8px 12px", fontSize: 13, fontFamily: "inherit", color: "#374151" }}>
            <option value="">All Semesters</option>
            {semesters.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <select value={filterDept} onChange={e => setFilterDept(e.target.value)} style={{ border: "1.5px solid #E2E8F0", borderRadius: 8, padding: "8px 12px", fontSize: 13, fontFamily: "inherit", color: "#374151" }}>
            <option value="">All Departments</option>
            {depts.map(d => <option key={d.id} value={d.code}>{d.name}</option>)}
          </select>
          <Btn onClick={openAdd}><Icon d={Icons.plus} size={14} /> Add Course</Btn>
        </div>
      </div>
      <Card>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "2px solid #F1F5F9" }}>
              {["Code", "Name", "Year", "Semester", "Department", "Students", "Instructors", ""].map((h, i) => (
                <th key={i} style={{ padding: "12px 16px", textAlign: "left", fontSize: 11, fontWeight: 700, color: "#94A3B8", letterSpacing: "0.06em" }}>{h.toUpperCase()}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filtered.map((c, i) => (
              <tr key={c.id} style={{ borderBottom: "1px solid #F8FAFC", background: i % 2 ? "#FAFBFF" : "#fff" }}>
                <td style={{ padding: "12px 16px", fontWeight: 700, color: "#1E293B", fontSize: 13 }}>{c.code}</td>
                <td style={{ padding: "12px 16px", color: "#374151", fontSize: 13 }}>{c.name}</td>
                <td style={{ padding: "12px 16px" }}>
                  {c.year ? <Badge color={YEAR_COLORS[c.year] || "#64748B"}>Y{c.year}</Badge> : <span style={{ color: "#CBD5E1", fontSize: 12 }}>—</span>}
                </td>
                <td style={{ padding: "12px 16px" }}>
                  {c.semester ? <Badge color="#0369A1">{c.semester}</Badge> : <span style={{ color: "#CBD5E1", fontSize: 12 }}>—</span>}
                </td>
                <td style={{ padding: "12px 16px" }}>
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                    {c.department && <Badge color={c.department.color || "#64748B"}>{c.department.code}</Badge>}
                    {parseSharedCodes(c.shared_with_departments)
                      .filter(code => code !== String(c.department?.code || "").toUpperCase())
                      .map(code => <Badge key={`${c.id}-${code}`} color="#334155">{code}</Badge>)}
                  </div>
                </td>
                <td style={{ padding: "12px 16px", color: "#374151", fontSize: 13 }}>{c.student_count}</td>
                <td style={{ padding: "12px 16px" }}>
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                    {(c.instructors || []).map(u => (
                      <Badge key={u.id} color="#7C3AED">{u.name}</Badge>
                    ))}
                  </div>
                </td>
                <td style={{ padding: "12px 16px" }}>
                  <button onClick={() => openEdit(c)} style={{ border: "none", background: "none", cursor: "pointer", color: "#64748B", display: "flex", alignItems: "center", gap: 4, fontSize: 12, fontFamily: "inherit", fontWeight: 600 }}>
                    <Icon d={Icons.edit} size={13} /> Edit
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && <div style={{ padding: 32, textAlign: "center", color: "#94A3B8", fontSize: 14 }}>No courses found</div>}
      </Card>
      {editCourse !== null && (
        <Modal title={editCourse && editCourse.id ? `Edit ${editCourse.code}` : "New Course"} onClose={closeModal}>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 12 }}>
              <Input label="Code" value={form.code} onChange={e => setForm(f => ({ ...f, code: e.target.value }))} placeholder="CS401" />
              <Input label="Name" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="Algorithms" />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <Select label="Department" value={form.department_id} onChange={e => setForm(f => ({ ...f, department_id: e.target.value }))}>
                <option value="">Select department...</option>
                {depts.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
              </Select>
              <Select label="Semester" value={form.semester_id} onChange={e => setForm(f => ({ ...f, semester_id: e.target.value }))}>
                <option value="">Select semester...</option>
                {semesters.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
              </Select>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: "#64748B", letterSpacing: "0.05em" }}>SHARED WITH DEPARTMENTS (OPTIONAL)</label>
              <div style={{ border: "1.5px solid #E2E8F0", borderRadius: 8, padding: 8, maxHeight: 110, overflowY: "auto", display: "flex", flexWrap: "wrap", gap: 6 }}>
                {depts
                  .filter((d) => +d.id !== +form.department_id)
                  .map((d) => (
                    <label key={d.id} style={{ display: "flex", alignItems: "center", gap: 4, cursor: "pointer", padding: "4px 8px", borderRadius: 6, background: form.shared_department_ids.includes(d.id) ? "#E0E7FF" : "#F8FAFC", fontSize: 12, color: "#374151" }}>
                      <input
                        type="checkbox"
                        checked={form.shared_department_ids.includes(d.id)}
                        onChange={e => setForm(f => ({
                          ...f,
                          shared_department_ids: e.target.checked
                            ? [...f.shared_department_ids, d.id]
                            : f.shared_department_ids.filter(id => id !== d.id),
                        }))}
                      />
                      {d.name}
                    </label>
                  ))}
                {depts.filter((d) => +d.id !== +form.department_id).length === 0 && <span style={{ fontSize: 12, color: "#94A3B8" }}>No other departments available</span>}
              </div>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <Select label="Year" value={form.year} onChange={e => setForm(f => ({ ...f, year: e.target.value }))}>
                <option value="">Select year...</option>
                <option value="1">Year 1</option>
                <option value="2">Year 2</option>
                <option value="3">Year 3</option>
                <option value="4">Year 4</option>
              </Select>
              <Input label="Students" type="number" value={form.student_count} onChange={e => setForm(f => ({ ...f, student_count: +e.target.value }))} />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: "#64748B", letterSpacing: "0.05em" }}>INSTRUCTORS</label>
              <div style={{ border: "1.5px solid #E2E8F0", borderRadius: 8, padding: 8, maxHeight: 120, overflowY: "auto", display: "flex", flexWrap: "wrap", gap: 6 }}>
                {instructors.map(u => (
                  <label key={u.id} style={{ display: "flex", alignItems: "center", gap: 4, cursor: "pointer", padding: "4px 8px", borderRadius: 6, background: form.instructor_ids.includes(u.id) ? "#EDE9FE" : "#F8FAFC", fontSize: 12, color: "#374151" }}>
                    <input type="checkbox" checked={form.instructor_ids.includes(u.id)}
                      onChange={e => setForm(f => ({
                        ...f, instructor_ids: e.target.checked
                          ? [...f.instructor_ids, u.id]
                          : f.instructor_ids.filter(id => id !== u.id)
                      }))} />
                    {u.name}
                  </label>
                ))}
                {instructors.length === 0 && <span style={{ fontSize: 12, color: "#94A3B8" }}>No instructors yet — add in Staff page</span>}
              </div>
            </div>
            {!(editCourse && editCourse.id) && (
              <div style={{ background: "#F0FDF4", border: "1px solid #BBF7D0", borderRadius: 8, padding: "10px 14px", fontSize: 12, color: "#15803D" }}>
                ✅ A draft exam will be created automatically for this course.
              </div>
            )}
            <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
              <Btn onClick={submit}>{editCourse && editCourse.id ? "Save Changes" : "Create Course"}</Btn>
              <Btn variant="secondary" onClick={closeModal}>Cancel</Btn>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
