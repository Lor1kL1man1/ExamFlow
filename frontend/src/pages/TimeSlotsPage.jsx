import { useState, useEffect, useCallback } from "react";
import { get, post, put, del } from "../utils/api";
import { Icons } from "../utils/constants";
import { Btn, Card, Input, Modal, Icon, Badge } from "../components/ui";

const TYPE_CONFIG = {
  midterm: { label: "Midterm",  color: "#2563EB", bg: "#EFF6FF", border: "#BFDBFE" },
  final:   { label: "Final",    color: "#7C3AED", bg: "#F5F3FF", border: "#DDD6FE" },
};

const BLANK_FORM = { label: "", date: "", start_time: "09:00", end_time: "12:00" };

const DEFAULT_SESSIONS = {
  midterm: [
    { start_time: "08:30", end_time: "10:00", label: "" },
    { start_time: "10:15", end_time: "11:45", label: "" },
    { start_time: "12:00", end_time: "13:30", label: "" },
    { start_time: "13:45", end_time: "15:15", label: "" },
  ],
  final: [
    { start_time: "08:30", end_time: "10:00", label: "" },
    { start_time: "10:15", end_time: "11:45", label: "" },
    { start_time: "12:00", end_time: "13:30", label: "" },
    { start_time: "13:45", end_time: "15:15", label: "" },
    { start_time: "15:30", end_time: "17:00", label: "" },
    { start_time: "17:15", end_time: "18:45", label: "" },
  ],
};

const BLANK_BULK = (type) => ({
  start_date: "",
  end_date: "",
  sessions: DEFAULT_SESSIONS[type].map(s => ({ ...s })),
});

export default function TimeSlotsPage({ toast }) {
  const [slots,       setSlots]       = useState([]);
  const [period,      setPeriod]      = useState(null);  // active period (with active_slot_type)
  const [activeTab,   setActiveTab]   = useState("midterm");
  const [showModal,     setShowModal]     = useState(false);
  const [form,          setForm]          = useState(BLANK_FORM);
  const [switching,     setSwitching]     = useState(false);
  const [showBulkModal, setShowBulkModal] = useState(false);
  const [bulkForm,      setBulkForm]      = useState(BLANK_BULK("midterm"));
  const [bulkLoading,   setBulkLoading]   = useState(false);

  const loadAll = useCallback(async () => {
    const [allSlots, periods] = await Promise.all([
      get("/timeslots"),                   // all slots for active period
      get("/periods"),
    ]);
    setSlots(allSlots);
    const activePeriod = periods.find(p => p.is_active);
    if (activePeriod) {
      setPeriod(activePeriod);
      setActiveTab(activePeriod.active_slot_type || "midterm");
    }
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  const submit = async () => {
    try {
      await post("/timeslots", { ...form, slot_type: activeTab });
      setShowModal(false);
      setForm(BLANK_FORM);
      loadAll();
      toast(`${TYPE_CONFIG[activeTab].label} time slot created!`, "success");
    } catch { toast("Error creating slot", "error"); }
  };

  const remove = async (id) => {
    await del(`/timeslots/${id}`);
    loadAll();
    toast("Time slot removed", "success");
  };

  const switchActiveType = async (type) => {
    if (!period || switching) return;
    setSwitching(true);
    try {
      const updated = await put(`/periods/${period.id}/active-slot-type`, { slot_type: type });
      setPeriod(updated);
      toast(`${TYPE_CONFIG[type].label} slots are now active for scheduling`, "success");
    } catch { toast("Failed to switch slot type", "error"); }
    setSwitching(false);
  };

  const openBulkModal = () => {
    setBulkForm(BLANK_BULK(activeTab));
    setShowBulkModal(true);
  };

  const submitBulk = async () => {
    if (!bulkForm.start_date || !bulkForm.end_date) {
      toast("Please set start and end dates", "error"); return;
    }
    if (bulkForm.sessions.length === 0) {
      toast("Add at least one session", "error"); return;
    }
    setBulkLoading(true);
    try {
      const res = await post("/timeslots/bulk", { ...bulkForm, slot_type: activeTab });
      setShowBulkModal(false);
      loadAll();
      const msg = res.deleted > 0
        ? `Replaced ${res.deleted} old slots with ${res.created} new ${TYPE_CONFIG[activeTab].label.toLowerCase()} slots`
        : `${res.created} ${TYPE_CONFIG[activeTab].label.toLowerCase()} slots created`;
      toast(msg, "success");
    } catch { toast("Error generating slots", "error"); }
    setBulkLoading(false);
  };

  const updateSession = (i, field, val) =>
    setBulkForm(f => ({ ...f, sessions: f.sessions.map((s, idx) => idx === i ? { ...s, [field]: val } : s) }));
  const addSession = () =>
    setBulkForm(f => ({ ...f, sessions: [...f.sessions, { start_time: "", end_time: "", label: "" }] }));
  const removeSession = (i) =>
    setBulkForm(f => ({ ...f, sessions: f.sessions.filter((_, idx) => idx !== i) }));

  const dayCount = (bulkForm.start_date && bulkForm.end_date)
    ? Math.max(0, Math.round((new Date(bulkForm.end_date) - new Date(bulkForm.start_date)) / 86400000) + 1)
    : 0;
  const totalSlots = dayCount * bulkForm.sessions.length;

  // Filter visible slots by the active tab
  const tabSlots = slots.filter(s => (s.slot_type || "midterm") === activeTab);

  const grouped = tabSlots.reduce((acc, s) => {
    acc[s.date] = acc[s.date] || [];
    acc[s.date].push(s);
    return acc;
  }, {});

  const cfg = TYPE_CONFIG[activeTab];
  const activeCfg = TYPE_CONFIG[period?.active_slot_type || "midterm"];

  return (
    <div>
      {/* header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h2 style={{ fontSize: 24, fontWeight: 800, color: "#1E293B", margin: 0 }}>Time Slots</h2>
          {period && (
            <p style={{ margin: "4px 0 0", fontSize: 13, color: "#94A3B8" }}>
              Period: <strong>{period.name}</strong> &nbsp;·&nbsp;
              {period.midterm_count ?? 0} midterm · {period.final_count ?? 0} final
            </p>
          )}
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          <Btn variant="secondary" onClick={openBulkModal}>
            <Icon d={Icons.slot} size={14} /> Generate from Date Range
          </Btn>
          <Btn onClick={() => setShowModal(true)}>
            <Icon d={Icons.plus} size={14} /> Add {cfg.label} Slot
          </Btn>
        </div>
      </div>

      {/* active slot type banner */}
      {period && (
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          background: activeCfg.bg, border: `1.5px solid ${activeCfg.border}`,
          borderRadius: 12, padding: "12px 18px", marginBottom: 20,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 10, height: 10, borderRadius: "50%", background: activeCfg.color }} />
            <span style={{ fontSize: 13, fontWeight: 700, color: activeCfg.color }}>
              {activeCfg.label} slots are active for scheduling
            </span>
            <span style={{ fontSize: 12, color: "#64748B" }}>
              — the scheduler will only use <strong>{activeCfg.label.toLowerCase()}</strong> time slots
            </span>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            {["midterm", "final"].map(type => (
              <button
                key={type}
                disabled={switching || (period.active_slot_type || "midterm") === type}
                onClick={() => switchActiveType(type)}
                style={{
                  border: `1.5px solid ${(period.active_slot_type || "midterm") === type ? TYPE_CONFIG[type].color : "#E2E8F0"}`,
                  borderRadius: 8, background: (period.active_slot_type || "midterm") === type ? TYPE_CONFIG[type].color : "#fff",
                  color: (period.active_slot_type || "midterm") === type ? "#fff" : "#374151",
                  padding: "6px 14px", fontSize: 12, fontWeight: 600, cursor: switching ? "not-allowed" : "pointer",
                  fontFamily: "inherit", opacity: switching ? 0.7 : 1, transition: "all 0.15s",
                }}
              >
                {(period.active_slot_type || "midterm") === type ? "✓ " : ""}{TYPE_CONFIG[type].label} Active
              </button>
            ))}
          </div>
        </div>
      )}

      {/* tabs */}
      <div style={{ display: "flex", gap: 0, marginBottom: 24, borderBottom: "2px solid #E2E8F0" }}>
        {["midterm", "final"].map(type => {
          const c = TYPE_CONFIG[type];
          const count = slots.filter(s => (s.slot_type || "midterm") === type).length;
          const isActive = activeTab === type;
          return (
            <button
              key={type}
              onClick={() => setActiveTab(type)}
              style={{
                border: "none", background: "none", cursor: "pointer",
                padding: "10px 24px", fontSize: 14, fontWeight: isActive ? 700 : 500,
                color: isActive ? c.color : "#94A3B8",
                borderBottom: `3px solid ${isActive ? c.color : "transparent"}`,
                marginBottom: -2, fontFamily: "inherit", transition: "all 0.15s",
                display: "flex", alignItems: "center", gap: 8,
              }}
            >
              {c.label} Slots
              <span style={{
                background: isActive ? c.color : "#E2E8F0",
                color: isActive ? "#fff" : "#64748B",
                borderRadius: 999, padding: "1px 8px", fontSize: 11, fontWeight: 700,
              }}>{count}</span>
            </button>
          );
        })}
      </div>

      {/* slots grid */}
      {Object.keys(grouped).length === 0 ? (
        <Card style={{ padding: 48, textAlign: "center" }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>🕐</div>
          <div style={{ color: "#94A3B8", marginBottom: 16 }}>
            No <strong>{cfg.label.toLowerCase()}</strong> time slots defined yet.
          </div>
          <div style={{ display: "flex", gap: 10, justifyContent: "center" }}>
            <Btn variant="secondary" onClick={openBulkModal}>
              <Icon d={Icons.slot} size={14} /> Generate from Date Range
            </Btn>
            <Btn onClick={() => setShowModal(true)}>
              <Icon d={Icons.plus} size={14} /> Add First {cfg.label} Slot
            </Btn>
          </div>
        </Card>
      ) : (
        Object.entries(grouped).sort().map(([date, daySlots]) => (
          <div key={date} style={{ marginBottom: 20 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "#64748B", marginBottom: 8, letterSpacing: "0.06em", textTransform: "uppercase" }}>
              {new Date(date + "T12:00:00").toLocaleDateString("en-US", { weekday: "long", year: "numeric", month: "long", day: "numeric" })}
            </div>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              {daySlots.map(s => (
                <Card key={s.id} style={{ padding: "12px 16px", display: "flex", alignItems: "center", gap: 14, borderLeft: `3px solid ${cfg.color}` }}>
                  <Icon d={Icons.slot} size={16} color={cfg.color} />
                  <div>
                    {s.label && <div style={{ fontSize: 11, fontWeight: 700, color: cfg.color, marginBottom: 2 }}>{s.label}</div>}
                    <div style={{ fontSize: 14, fontWeight: 700, color: "#1E293B" }}>
                      {s.start_time?.slice(0, 5)} — {s.end_time?.slice(0, 5)}
                    </div>
                  </div>
                  <Badge color={cfg.color} style={{ fontSize: 10 }}>{cfg.label}</Badge>
                  <button
                    onClick={() => remove(s.id)}
                    style={{ border: "none", background: "none", cursor: "pointer", color: "#CBD5E1", fontSize: 18, marginLeft: 4, lineHeight: 1 }}
                  >×</button>
                </Card>
              ))}
            </div>
          </div>
        ))
      )}

      {/* add single slot modal */}
      {showModal && (
        <Modal title={`New ${cfg.label} Time Slot`} onClose={() => { setShowModal(false); setForm(BLANK_FORM); }}>
          <div style={{ marginBottom: 14, padding: "8px 12px", background: cfg.bg, border: `1px solid ${cfg.border}`, borderRadius: 8, fontSize: 12, color: cfg.color, fontWeight: 600 }}>
            This slot will be saved as a <strong>{cfg.label}</strong> time slot
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <Input label="Label (optional)" value={form.label} onChange={e => setForm(f => ({ ...f, label: e.target.value }))} placeholder="e.g. Morning Block A" />
            <Input label="Date" type="date" value={form.date} onChange={e => setForm(f => ({ ...f, date: e.target.value }))} />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
              <Input label="Start Time" type="time" value={form.start_time} onChange={e => setForm(f => ({ ...f, start_time: e.target.value }))} />
              <Input label="End Time" type="time" value={form.end_time} onChange={e => setForm(f => ({ ...f, end_time: e.target.value }))} />
            </div>
            <div style={{ display: "flex", gap: 10, marginTop: 8 }}>
              <Btn onClick={submit}>Create Slot</Btn>
              <Btn variant="secondary" onClick={() => { setShowModal(false); setForm(BLANK_FORM); }}>Cancel</Btn>
            </div>
          </div>
        </Modal>
      )}

      {/* bulk generate modal */}
      {showBulkModal && (
        <Modal title={`Generate ${cfg.label} Slots from Date Range`} onClose={() => setShowBulkModal(false)}>
          <div style={{ marginBottom: 18, padding: "10px 14px", background: cfg.bg, border: `1px solid ${cfg.border}`, borderRadius: 8, fontSize: 12, color: cfg.color, fontWeight: 600 }}>
            Creates one slot per session for every day in the selected range
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginBottom: 18 }}>
            <Input label="Start Date" type="date" value={bulkForm.start_date}
              onChange={e => setBulkForm(f => ({ ...f, start_date: e.target.value }))} />
            <Input label="End Date" type="date" value={bulkForm.end_date}
              onChange={e => setBulkForm(f => ({ ...f, end_date: e.target.value }))} />
          </div>

          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "#475569", marginBottom: 8, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <span>Sessions per day</span>
              <button onClick={addSession} style={{ border: `1.5px solid ${cfg.color}`, background: "none", color: cfg.color, borderRadius: 6, padding: "3px 10px", fontSize: 11, fontWeight: 700, cursor: "pointer", fontFamily: "inherit" }}>
                + Add Session
              </button>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 260, overflowY: "auto", paddingRight: 4 }}>
              {bulkForm.sessions.map((s, i) => (
                <div key={i} style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1.4fr auto", gap: 8, alignItems: "end" }}>
                  <Input label={i === 0 ? "Start Time" : undefined} type="time" value={s.start_time}
                    onChange={e => updateSession(i, "start_time", e.target.value)} />
                  <Input label={i === 0 ? "End Time" : undefined} type="time" value={s.end_time}
                    onChange={e => updateSession(i, "end_time", e.target.value)} />
                  <Input label={i === 0 ? "Label (opt.)" : undefined} value={s.label}
                    onChange={e => updateSession(i, "label", e.target.value)} placeholder="e.g. Morning" />
                  <button onClick={() => removeSession(i)} disabled={bulkForm.sessions.length <= 1}
                    style={{ border: "none", background: "none", cursor: bulkForm.sessions.length <= 1 ? "not-allowed" : "pointer", color: "#CBD5E1", fontSize: 20, lineHeight: 1, paddingBottom: 6, opacity: bulkForm.sessions.length <= 1 ? 0.3 : 1 }}>
                    ×
                  </button>
                </div>
              ))}
            </div>
          </div>

          <div style={{ padding: "10px 14px", background: totalSlots > 0 ? "#F0FDF4" : "#F8FAFC", border: `1px solid ${totalSlots > 0 ? "#BBF7D0" : "#E2E8F0"}`, borderRadius: 8, marginBottom: 18, fontSize: 13 }}>
            {dayCount > 0 && bulkForm.sessions.length > 0 ? (
              <span style={{ fontWeight: 700, color: totalSlots > 0 ? "#15803D" : "#475569" }}>
                Will create <strong>{totalSlots}</strong> slots &nbsp;·&nbsp; {dayCount} day{dayCount !== 1 ? "s" : ""} × {bulkForm.sessions.length} session{bulkForm.sessions.length !== 1 ? "s" : ""}
              </span>
            ) : (
              <span style={{ color: "#94A3B8" }}>Select a date range to see a preview</span>
            )}
          </div>

          <div style={{ padding: "10px 14px", background: "#FFF1F2", border: "1px solid #FECDD3", borderRadius: 8, marginBottom: 14, fontSize: 12, color: "#BE123C", fontWeight: 600, display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 16 }}>⚠️</span>
            All existing <strong>{cfg.label.toLowerCase()}</strong> slots and any scheduled exam sessions using them will be deleted and replaced with the newly generated slots.
          </div>

          <div style={{ display: "flex", gap: 10 }}>
            <Btn onClick={submitBulk} disabled={bulkLoading || totalSlots === 0}>
              {bulkLoading ? "Generating…" : `Generate ${totalSlots > 0 ? totalSlots + " " : ""}Slots`}
            </Btn>
            <Btn variant="secondary" onClick={() => setShowBulkModal(false)}>Cancel</Btn>
          </div>
        </Modal>
      )}
    </div>
  );
}

