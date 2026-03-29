import { useState, useEffect, useCallback } from "react";
import { get, post, put, del } from "../utils/api";
import { Icons } from "../utils/constants";
import { Btn, Card, Input, Modal, Icon } from "../components/ui";

const BLANK = { name: "", code: "", color: "#3B82F6" };

const PRESET_COLORS = [
  "#2563EB", "#7C3AED", "#059669", "#D97706",
  "#DC2626", "#0891B2", "#9333EA", "#EA580C",
];

export default function DepartmentsPage({ toast }) {
  const [depts, setDepts] = useState([]);
  const [editDept, setEditDept] = useState(null); // null=closed, false=new, object=editing
  const [form, setForm] = useState(BLANK);
  const [showImport, setShowImport] = useState(false);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState(null);
  const [importForm, setImportForm] = useState({
    department_name: "",
    department_code: "",
    department_color: "#3B82F6",
    default_year: 1,
    default_room_capacity: 30,
    overwrite_existing: false,
    csv_text: "Course,Instructor,Date,Time,Group,Room,Observers,Year,CourseCode\nEnglish Language II,Marija Stevkovska,23.03.2026,12:00-13:30,Group 5,A-303;A-304;A-305,Isra Asani;Anastasija Dimitrievska,1,ARCH-Y1-01",
  });

  const load = useCallback(() => get("/departments").then(setDepts), []);
  useEffect(() => { load(); }, [load]);

  const openAdd = () => { setForm(BLANK); setEditDept(false); };
  const openEdit = (d) => {
    setForm({ name: d.name, code: d.code, color: d.color || "#3B82F6" });
    setEditDept(d);
  };
  const closeModal = () => setEditDept(null);
  const closeImport = () => {
    setShowImport(false);
    setImportResult(null);
  };

  const submit = async () => {
    if (!form.name.trim() || !form.code.trim()) {
      toast("Name and code are required", "error");
      return;
    }
    try {
      if (editDept && editDept.id) {
        await put(`/departments/${editDept.id}`, form);
        toast("Department updated!", "success");
      } else {
        await post("/departments", form);
        toast("Department created!", "success");
      }
      closeModal();
      load();
    } catch (e) { toast("Error saving department", "error"); }
  };

  const remove = async (d) => {
    if (!confirm(`Delete "${d.name}"? This will also remove all its courses and staff assignments.`)) return;
    try {
      await del(`/departments/${d.id}`);
      toast("Department deleted", "success");
      load();
    } catch (e) { toast("Failed to delete department", "error"); }
  };

  const submitImport = async () => {
    if (!importForm.department_name.trim() || !importForm.department_code.trim() || !importForm.csv_text.trim()) {
      toast("Department fields and CSV text are required", "error");
      return;
    }
    setImporting(true);
    try {
      const result = await post("/departments/import", {
        ...importForm,
        department_code: importForm.department_code.trim().toUpperCase(),
        default_year: Number(importForm.default_year) || 1,
        default_room_capacity: Number(importForm.default_room_capacity) || 30,
      });
      setImportResult(result);
      load();
      toast(`Imported ${result.courses_created} courses for ${importForm.department_code.trim().toUpperCase()}`, "success");
    } catch (e) {
      toast(e?.error || "Import failed", "error");
    } finally {
      setImporting(false);
    }
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h2 style={{ fontSize: 24, fontWeight: 800, color: "#1E293B", margin: 0 }}>Departments</h2>
        <div style={{ display: "flex", gap: 10 }}>
          <Btn variant="secondary" onClick={() => setShowImport(true)}><Icon d={Icons.download} size={14} /> Import Dataset</Btn>
          <Btn onClick={openAdd}><Icon d={Icons.plus} size={14} /> Add Department</Btn>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 16 }}>
        {depts.map(d => (
          <Card key={d.id} style={{ padding: 20 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 14, marginBottom: 14 }}>
              {/* Color swatch */}
              <div style={{
                width: 48, height: 48, borderRadius: 12,
                background: d.color || "#3B82F6",
                display: "flex", alignItems: "center", justifyContent: "center",
                flexShrink: 0,
              }}>
                <span style={{ fontSize: 16, fontWeight: 800, color: "#fff", letterSpacing: "-0.03em" }}>
                  {d.code}
                </span>
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 15, fontWeight: 700, color: "#1E293B", marginBottom: 2 }}>{d.name}</div>
                <div style={{ fontSize: 12, color: "#94A3B8" }}>Code: {d.code}</div>
              </div>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <Btn variant="secondary" size="sm" onClick={() => openEdit(d)}>
                <Icon d={Icons.edit} size={12} /> Edit
              </Btn>
              <Btn variant="danger" size="sm" onClick={() => remove(d)}>
                <Icon d={Icons.trash} size={12} /> Delete
              </Btn>
            </div>
          </Card>
        ))}
        {depts.length === 0 && (
          <div style={{ gridColumn: "1/-1", textAlign: "center", color: "#94A3B8", padding: 48, fontSize: 14 }}>
            No departments yet. Add your first one!
          </div>
        )}
      </div>

      {editDept !== null && (
        <Modal
          title={editDept && editDept.id ? `Edit ${editDept.name}` : "New Department"}
          onClose={closeModal}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <Input
              label="Department Name"
              value={form.name}
              onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="e.g. Computer Engineering"
            />
            <Input
              label="Short Code"
              value={form.code}
              onChange={e => setForm(f => ({ ...f, code: e.target.value.toUpperCase() }))}
              placeholder="e.g. CE"
            />

            {/* Color picker */}
            <div>
              <div style={{ fontSize: 12, fontWeight: 600, color: "#374151", marginBottom: 8 }}>Color</div>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
                {PRESET_COLORS.map(c => (
                  <button
                    key={c}
                    onClick={() => setForm(f => ({ ...f, color: c }))}
                    style={{
                      width: 28, height: 28, borderRadius: 8, background: c, border: "none",
                      cursor: "pointer", outline: form.color === c ? `3px solid ${c}` : "none",
                      outlineOffset: 2, boxShadow: form.color === c ? "0 0 0 2px #fff, 0 0 0 4px " + c : "none",
                    }}
                  />
                ))}
                {/* Custom hex input */}
                <input
                  type="color"
                  value={form.color}
                  onChange={e => setForm(f => ({ ...f, color: e.target.value }))}
                  title="Custom color"
                  style={{ width: 28, height: 28, padding: 0, border: "none", borderRadius: 8, cursor: "pointer" }}
                />
              </div>
              {/* Preview */}
              <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 10 }}>
                <div style={{
                  width: 40, height: 40, borderRadius: 10, background: form.color,
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  <span style={{ fontWeight: 800, color: "#fff", fontSize: 13 }}>
                    {form.code || "??"}
                  </span>
                </div>
                <span style={{ fontSize: 13, color: "#64748B" }}>{form.name || "Department Name"}</span>
              </div>
            </div>

            <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
              <Btn onClick={submit}>
                {editDept && editDept.id ? "Save Changes" : "Create Department"}
              </Btn>
              <Btn variant="secondary" onClick={closeModal}>Cancel</Btn>
            </div>
          </div>
        </Modal>
      )}

      {showImport && (
        <Modal title="Import Department Dataset" onClose={closeImport}>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div style={{ fontSize: 13, color: "#64748B", lineHeight: 1.5 }}>
              Paste CSV with a header row. Supported columns: <strong>Course</strong>, <strong>Instructor</strong>, <strong>Date</strong>, <strong>Time</strong>, <strong>Group</strong>, <strong>Room</strong>, <strong>Observers</strong>, optional <strong>Year</strong>, <strong>CourseCode</strong>, and <strong>SharedDepartments</strong> (e.g., "CE,ARCH" for mixed cohorts).
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
              <Input
                label="Department Name"
                value={importForm.department_name}
                onChange={e => setImportForm(f => ({ ...f, department_name: e.target.value }))}
                placeholder="e.g. Civil Engineering"
              />
              <Input
                label="Department Code"
                value={importForm.department_code}
                onChange={e => setImportForm(f => ({ ...f, department_code: e.target.value.toUpperCase() }))}
                placeholder="e.g. CIVIL"
              />
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: "#64748B", letterSpacing: "0.05em", marginBottom: 4 }}>COLOR</div>
                <input
                  type="color"
                  value={importForm.department_color}
                  onChange={e => setImportForm(f => ({ ...f, department_color: e.target.value }))}
                  style={{ width: "100%", height: 40, border: "1.5px solid #E2E8F0", borderRadius: 8, background: "#fff", cursor: "pointer" }}
                />
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <Input
                label="Default Year"
                type="number"
                min="1"
                value={importForm.default_year}
                onChange={e => setImportForm(f => ({ ...f, default_year: e.target.value }))}
              />
              <Input
                label="Default Room Capacity"
                type="number"
                min="1"
                value={importForm.default_room_capacity}
                onChange={e => setImportForm(f => ({ ...f, default_room_capacity: e.target.value }))}
              />
            </div>

            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#374151" }}>
              <input
                type="checkbox"
                checked={importForm.overwrite_existing}
                onChange={e => setImportForm(f => ({ ...f, overwrite_existing: e.target.checked }))}
              />
              Replace existing courses for this department before importing
            </label>

            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <label style={{ fontSize: 12, fontWeight: 600, color: "#64748B", letterSpacing: "0.05em" }}>CSV DATA</label>
              <textarea
                value={importForm.csv_text}
                onChange={e => setImportForm(f => ({ ...f, csv_text: e.target.value }))}
                spellCheck={false}
                rows={12}
                style={{
                  width: "100%", resize: "vertical", border: "1.5px solid #E2E8F0", borderRadius: 10,
                  padding: 12, fontSize: 13, fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", color: "#1E293B",
                }}
              />
            </div>

            {importResult && (
              <div style={{ background: "#F8FAFC", border: "1px solid #E2E8F0", borderRadius: 10, padding: 14 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: "#0F172A", marginBottom: 8 }}>Last Import Summary</div>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8, fontSize: 12, color: "#475569" }}>
                  <div>Courses: <strong>{importResult.courses_created}</strong></div>
                  <div>Exams: <strong>{importResult.exams_created}</strong></div>
                  <div>Rows: <strong>{importResult.rows_processed}</strong></div>
                  <div>Rooms: <strong>{importResult.rooms_created}</strong></div>
                  <div>Users: <strong>{importResult.users_created}</strong></div>
                  <div>Reused: <strong>{importResult.users_reused}</strong></div>
                </div>
                {importResult.warnings?.length > 0 && (
                  <div style={{ marginTop: 10, fontSize: 12, color: "#92400E" }}>
                    {importResult.warnings.length} warning(s): {importResult.warnings.slice(0, 3).join(" • ")}
                  </div>
                )}
              </div>
            )}

            <div style={{ display: "flex", gap: 10, marginTop: 4 }}>
              <Btn onClick={submitImport} disabled={importing}>{importing ? "Importing..." : "Import Dataset"}</Btn>
              <Btn variant="secondary" onClick={closeImport}>Close</Btn>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
