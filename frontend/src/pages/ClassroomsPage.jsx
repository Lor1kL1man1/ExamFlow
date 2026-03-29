import { useState, useEffect, useCallback } from "react";
import { get, post, put, del } from "../utils/api";
import { Icons } from "../utils/constants";
import { Btn, Card, Input, Modal, Badge, Icon } from "../components/ui";

const BLANK = { name: "", building: "", floor: 0, capacity: 30, has_projector: false, has_computers: false };

export default function ClassroomsPage({ toast }) {
  const [rooms, setRooms] = useState([]);
  const [editRoom, setEditRoom] = useState(null); // null = closed, object = editing
  const [form, setForm] = useState(BLANK);

  const load = useCallback(() => get("/classrooms").then(setRooms), []);
  useEffect(() => { load(); }, [load]);

  const openAdd = () => { setForm(BLANK); setEditRoom(false); };
  const openEdit = (r) => {
    setForm({ name: r.name, building: r.building, floor: r.floor, capacity: r.capacity, has_projector: r.has_projector, has_computers: r.has_computers });
    setEditRoom(r);
  };
  const closeModal = () => setEditRoom(null);

  const submit = async () => {
    try {
      if (editRoom && editRoom.id) {
        await put(`/classrooms/${editRoom.id}`, form);
        toast("Classroom updated!", "success");
      } else {
        await post("/classrooms", form);
        toast("Classroom created!", "success");
      }
      closeModal();
      load();
    } catch (e) { toast("Failed to save classroom", "error"); }
  };

  const remove = async (id) => {
    if (!confirm("Deactivate this classroom?")) return;
    await del(`/classrooms/${id}`);
    load();
    toast("Classroom deactivated", "success");
  };

  const isOpen = editRoom !== null;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <h2 style={{ fontSize: 24, fontWeight: 800, color: "#1E293B", margin: 0 }}>Classrooms</h2>
        <Btn onClick={openAdd}><Icon d={Icons.plus} size={14} /> Add Classroom</Btn>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 16 }}>
        {rooms.map(r => (
          <Card key={r.id} style={{ padding: 18 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
              <div>
                <div style={{ fontSize: 17, fontWeight: 700, color: "#1E293B" }}>{r.name}</div>
                <div style={{ fontSize: 12, color: "#64748B" }}>{r.building}{r.floor ? `, Floor ${r.floor}` : ""}</div>
              </div>
              <div style={{ fontSize: 22, fontWeight: 800, color: "#7C3AED" }}>{r.capacity}</div>
            </div>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
              {r.has_projector && <Badge color="#2563EB">Projector</Badge>}
              {r.has_computers && <Badge color="#059669">Computers</Badge>}
              <Badge color="#64748B">Cap: {r.capacity}</Badge>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <Btn variant="secondary" size="sm" onClick={() => openEdit(r)}>
                <Icon d={Icons.edit} size={12} /> Edit
              </Btn>
              <Btn variant="danger" size="sm" onClick={() => remove(r.id)}>
                <Icon d={Icons.trash} size={12} /> Remove
              </Btn>
            </div>
          </Card>
        ))}
      </div>
      {isOpen && (
        <Modal title={editRoom && editRoom.id ? `Edit ${editRoom.name}` : "New Classroom"} onClose={closeModal}>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <Input label="Room Name / ID" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} placeholder="e.g. A-101" />
            <Input label="Building" value={form.building} onChange={e => setForm(f => ({ ...f, building: e.target.value }))} placeholder="e.g. Engineering Block" />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <Input label="Floor" type="number" value={form.floor} onChange={e => setForm(f => ({ ...f, floor: +e.target.value }))} />
              <Input label="Capacity" type="number" value={form.capacity} onChange={e => setForm(f => ({ ...f, capacity: +e.target.value }))} />
            </div>
            <div style={{ display: "flex", gap: 16 }}>
              {["has_projector", "has_computers"].map(k => (
                <label key={k} style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", fontSize: 13, color: "#374151" }}>
                  <input type="checkbox" checked={form[k]} onChange={e => setForm(f => ({ ...f, [k]: e.target.checked }))} />
                  {k === "has_projector" ? "Projector" : "Computers"}
                </label>
              ))}
            </div>
            <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
              <Btn onClick={submit}>{editRoom && editRoom.id ? "Save Changes" : "Create Classroom"}</Btn>
              <Btn variant="secondary" onClick={closeModal}>Cancel</Btn>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
