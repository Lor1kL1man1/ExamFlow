import { useState, useEffect, useCallback } from "react";
import { get, post, put } from "../utils/api";
import { Icons } from "../utils/constants";
import { Btn, Card, Input, Select, Modal, Badge, Icon } from "../components/ui";

const BLANK = { name: "", email: "", role: "instructor", department_id: "", password: "changeme123" };
const roleColor = { instructor: "#2563EB", observer: "#D97706", manager: "#7C3AED" };

export default function StaffPage({ toast }) {
  const [users, setUsers] = useState([]);
  const [depts, setDepts] = useState([]);
  const [roleFilter, setRoleFilter] = useState("instructor");
  const [editUser, setEditUser] = useState(null); // null=closed, false=new, object=editing
  const [form, setForm] = useState(BLANK);

  const load = useCallback(() => get(`/users?role=${roleFilter}`).then(setUsers), [roleFilter]);
  useEffect(() => { load(); get("/departments").then(setDepts); }, [load]);

  const openAdd = () => { setForm({ ...BLANK, role: roleFilter }); setEditUser(false); };
  const openEdit = (u) => {
    setForm({ name: u.name, email: u.email, role: u.role, department_id: u.department_id || "", password: "" });
    setEditUser(u);
  };
  const closeModal = () => setEditUser(null);

  const submit = async () => {
    try {
      if (editUser && editUser.id) {
        await put(`/users/${editUser.id}`, { name: form.name, email: form.email, department_id: form.department_id || null });
        toast("Staff member updated!", "success");
      } else {
        await post("/users", form);
        toast("Staff member added!", "success");
      }
      closeModal();
      load();
    } catch (e) { toast("Error saving staff member", "error"); }
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h2 style={{ fontSize: 24, fontWeight: 800, color: "#1E293B", margin: 0 }}>Staff</h2>
        <div style={{ display: "flex", gap: 10 }}>
          {["instructor", "observer", "manager"].map(r => (
            <button key={r} onClick={() => setRoleFilter(r)} style={{
              border: "none", borderRadius: 8, padding: "8px 14px", cursor: "pointer",
              background: roleFilter === r ? "#1E293B" : "#F1F5F9",
              color: roleFilter === r ? "#fff" : "#64748B",
              fontSize: 13, fontWeight: 600, fontFamily: "inherit", textTransform: "capitalize",
            }}>{r}s</button>
          ))}
          <Btn onClick={openAdd}><Icon d={Icons.plus} size={14} /> Add Staff</Btn>
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 14 }}>
        {users.map(u => (
          <Card key={u.id} style={{ padding: 18 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 10 }}>
              <div style={{
                width: 40, height: 40, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center",
                background: (roleColor[u.role] || "#64748B") + "20", color: roleColor[u.role] || "#64748B",
                fontWeight: 700, fontSize: 16,
              }}>{u.name[0]}</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 700, color: "#1E293B", fontSize: 14 }}>{u.name}</div>
                <div style={{ fontSize: 11, color: "#94A3B8" }}>{u.email}</div>
              </div>
              <button onClick={() => openEdit(u)} title="Edit" style={{ border: "none", background: "none", cursor: "pointer", color: "#94A3B8", padding: 4 }}>
                <Icon d={Icons.edit} size={15} />
              </button>
            </div>
            <Badge color={roleColor[u.role] || "#64748B"}>{u.role}</Badge>
          </Card>
        ))}
        {users.length === 0 && (
          <div style={{ gridColumn: "1/-1", textAlign: "center", color: "#94A3B8", padding: 48, fontSize: 14 }}>
            No {roleFilter}s found
          </div>
        )}
      </div>
      {editUser !== null && (
        <Modal title={editUser && editUser.id ? `Edit ${editUser.name}` : "Add Staff Member"} onClose={closeModal}>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <Input label="Full Name" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
            <Input label="Email" type="email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} />
            {!(editUser && editUser.id) && (
              <Select label="Role" value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value }))}>
                <option value="instructor">Instructor</option>
                <option value="observer">Observer</option>
                <option value="manager">Manager</option>
              </Select>
            )}
            <Select label="Department (optional)" value={form.department_id} onChange={e => setForm(f => ({ ...f, department_id: e.target.value }))}>
              <option value="">No specific department</option>
              {depts.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}
            </Select>
            {!(editUser && editUser.id) && (
              <Input label="Initial Password" type="password" value={form.password} onChange={e => setForm(f => ({ ...f, password: e.target.value }))} />
            )}
            <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
              <Btn onClick={submit}>{editUser && editUser.id ? "Save Changes" : "Add Staff"}</Btn>
              <Btn variant="secondary" onClick={closeModal}>Cancel</Btn>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
