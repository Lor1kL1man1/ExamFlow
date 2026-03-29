import { useState, useEffect } from "react";
import { get, post, put } from "../utils/api";
import { Icons } from "../utils/constants";
import { Btn, Card, Input, Modal, Icon } from "../components/ui";

export default function SemestersPage({ toast }) {
  const [semesters, setSemesters] = useState([]);
  const [editSem, setEditSem]     = useState(null); // null=closed, false=new, obj=editing
  const [form, setForm]           = useState({ name: "" });

  const reload = () => get("/semesters").then(setSemesters);
  useEffect(() => { reload(); }, []);

  const openAdd  = () => { setForm({ name: "" }); setEditSem(false); };
  const openEdit = (s) => { setForm({ name: s.name }); setEditSem(s); };
  const close    = () => setEditSem(null);

  const submit = async () => {
    try {
      if (editSem && editSem.id) {
        await put(`/semesters/${editSem.id}`, form);
        toast("Semester updated!", "success");
      } else {
        await post("/semesters", form);
        toast("Semester created!", "success");
      }
      close(); reload();
    } catch { toast("Error saving semester", "error"); }
  };

  const activate = async (id) => {
    try {
      await put(`/semesters/${id}/activate`, {});
      toast("Semester activated!", "success");
      reload();
    } catch { toast("Error activating semester", "error"); }
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h2 style={{ fontSize: 24, fontWeight: 800, color: "#1E293B", margin: 0 }}>Semesters</h2>
        <Btn onClick={openAdd}><Icon d={Icons.plus} size={14} /> Add Semester</Btn>
      </div>

      <div style={{ background: "#EFF6FF", border: "1px solid #BFDBFE", borderRadius: 10, padding: "12px 16px", marginBottom: 20, fontSize: 13, color: "#1D4ED8", lineHeight: 1.6 }}>
        💡 Each semester has its own set of courses. The <strong>active semester</strong> is pre-selected when you add a new course.
        Classrooms and staff are always shared across all semesters.
      </div>

      <Card>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "2px solid #F1F5F9" }}>
              {["Semester", "Courses", "Status", ""].map((h, i) => (
                <th key={i} style={{ padding: "12px 16px", textAlign: "left", fontSize: 11, fontWeight: 700, color: "#94A3B8", letterSpacing: "0.06em" }}>{h.toUpperCase()}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {semesters.map((s, i) => (
              <tr key={s.id} style={{ borderBottom: "1px solid #F8FAFC", background: i % 2 ? "#FAFBFF" : "#fff" }}>
                <td style={{ padding: "14px 16px" }}>
                  <div style={{ fontWeight: 700, color: "#1E293B", fontSize: 14 }}>{s.name}</div>
                  {s.is_active && (
                    <span style={{ fontSize: 10, background: "#DCFCE7", color: "#15803D", borderRadius: 4, padding: "2px 7px", fontWeight: 700, marginTop: 4, display: "inline-block" }}>
                      ACTIVE
                    </span>
                  )}
                </td>
                <td style={{ padding: "14px 16px", color: "#374151", fontSize: 13 }}>
                  {s.course_count ?? 0} courses
                </td>
                <td style={{ padding: "14px 16px" }}>
                  {!s.is_active && (
                    <button onClick={() => activate(s.id)} style={{
                      border: "1.5px solid #3B82F6", background: "none", borderRadius: 6,
                      padding: "5px 14px", fontSize: 12, fontWeight: 700, color: "#3B82F6",
                      cursor: "pointer", fontFamily: "inherit",
                    }}>
                      Set Active
                    </button>
                  )}
                </td>
                <td style={{ padding: "14px 16px" }}>
                  <button onClick={() => openEdit(s)} style={{
                    border: "none", background: "none", cursor: "pointer", color: "#64748B",
                    display: "flex", alignItems: "center", gap: 4, fontSize: 12, fontFamily: "inherit", fontWeight: 600,
                  }}>
                    <Icon d={Icons.edit} size={13} /> Edit
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {semesters.length === 0 && (
          <div style={{ padding: 32, textAlign: "center", color: "#94A3B8", fontSize: 14 }}>
            No semesters yet — create one to get started
          </div>
        )}
      </Card>

      {editSem !== null && (
        <Modal title={editSem && editSem.id ? `Edit ${editSem.name}` : "New Semester"} onClose={close}>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <Input
              label="Semester Name"
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              onKeyDown={e => e.key === "Enter" && submit()}
              placeholder="e.g. Fall 2026"
              autoFocus
            />
            <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
              <Btn onClick={submit}>{editSem && editSem.id ? "Save Changes" : "Create Semester"}</Btn>
              <Btn variant="secondary" onClick={close}>Cancel</Btn>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
