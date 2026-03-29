import { useState, useEffect } from "react";
import { get, post, put } from "./utils/api";
import { Icons } from "./utils/constants";
import { Icon, Toast } from "./components/ui";
import { useToast } from "./hooks/useToast";
import Dashboard from "./components/dashboard/Dashboard";
import ScheduleView from "./components/schedule/ScheduleView";
import ClassroomsPage from "./pages/ClassroomsPage";
import CoursesPage from "./pages/CoursesPage";
import ExamsPage from "./pages/ExamsPage";
import StaffPage from "./pages/StaffPage";
import TimeSlotsPage from "./pages/TimeSlotsPage";
import SemestersPage from "./pages/SemestersPage";
import ExamFlowAIAgent from "./components/ExamFlowAIAgent";
import DepartmentsPage from "./pages/DepartmentsPage";
import ManagerScopesPage from "./pages/ManagerScopesPage";

const NAV = [
  { id: "dashboard",    label: "Dashboard",    icon: "dashboard" },
  { id: "semesters",    label: "Semesters",    icon: "semester" },
  { id: "departments",  label: "Departments",  icon: "department" },
  { id: "managerScopes", label: "Manager Scopes", icon: "users" },
  { id: "classrooms",   label: "Classrooms",   icon: "classroom" },
  { id: "courses",    label: "Courses",     icon: "course" },
  { id: "exams",      label: "Exams",       icon: "exam" },
  { id: "staff",      label: "Staff",       icon: "users" },
  { id: "timeslots",  label: "Time Slots",  icon: "slot" },
  { id: "schedule",   label: "Schedule",    icon: "schedule" },
  { id: "agent",     label: "AI Agent",    icon: "agent" },
];

export default function App() {
  const [view, setView]   = useState("dashboard");
  const [stats, setStats] = useState({ classrooms: 0, courses: 0, exams: 0, instructors: 0, observers: 0, scheduled: 0, departments: [] });
  const [managers, setManagers] = useState([]);
  const [managerId, setManagerId] = useState(() => {
    const v = localStorage.getItem("manager_id");
    return v ? Number(v) : "";
  });
  const { toastMsg, toast, clearToast } = useToast();

  // ---- Period state ----
  const [periods, setPeriods]           = useState([]);
  const [activePeriod, setActivePeriod] = useState(null);
  const [showPeriodMenu, setShowPeriodMenu] = useState(false);
  const [showNewPeriod, setShowNewPeriod]   = useState(false);
  const [newPeriodName, setNewPeriodName]   = useState("");
  const [refreshKey, setRefreshKey]         = useState(0);

  // Fetch periods whenever refreshKey changes
  useEffect(() => {
    get("/periods").then(data => {
      setPeriods(data);
      setActivePeriod(data.find(p => p.is_active) || null);
    }).catch(() => {});
  }, [refreshKey]);

  // Fetch dashboard stats (period-filtered by backend)
  useEffect(() => {
    Promise.all([
      get("/classrooms"), get("/courses"), get("/exams"),
      get("/users?role=instructor"), get("/users?role=observer"), get("/departments"),
    ]).then(([rooms, courses, exams, instr, obs, depts]) => {
      setStats({
        classrooms: rooms.length, courses: courses.length,
        exams: exams.length, instructors: instr.length, observers: obs.length,
        scheduled: exams.filter(e => e.status === "scheduled").length,
        departments: depts,
      });
    }).catch(() => {});
  }, [view, refreshKey]);

  useEffect(() => {
    get("/managers")
      .then((data) => {
        setManagers(data || []);
        if (!managerId && data?.length) {
          setManagerId(data[0].id);
          localStorage.setItem("manager_id", String(data[0].id));
        }
      })
      .catch(() => {});
  }, []);

  const handleActivatePeriod = (id) => {
    put(`/periods/${id}/activate`, {}).then(() => {
      setRefreshKey(k => k + 1);
      setShowPeriodMenu(false);
      toast({ type: "success", message: "Period switched!" });
    }).catch(() => toast({ type: "error", message: "Failed to switch period." }));
  };

  const handleCreatePeriod = () => {
    const name = newPeriodName.trim();
    if (!name) return;
    post("/periods", { name }).then(() => {
      setRefreshKey(k => k + 1);
      setShowNewPeriod(false);
      setNewPeriodName("");
      toast({ type: "success", message: `Period "${name}" created!` });
    }).catch(() => toast({ type: "error", message: "Failed to create period." }));
  };

  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: "'IBM Plex Sans', system-ui, sans-serif", background: "#F8FAFC" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700;800&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { margin: 0; }
        ::-webkit-scrollbar { width: 6px; } ::-webkit-scrollbar-thumb { background: #CBD5E1; border-radius: 3px; }
        @keyframes slideIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
      `}</style>

      {/* ── Sidebar ── */}
      <aside style={{ width: 230, background: "#0F172A", display: "flex", flexDirection: "column", padding: "0 0 16px", flexShrink: 0 }}>

        {/* Logo */}
        <div style={{ padding: "22px 20px 18px", borderBottom: "1px solid #1E293B" }}>
          <div style={{ fontSize: 18, fontWeight: 800, color: "#fff", letterSpacing: "-0.02em" }}>ExamFlow</div>
          <div style={{ fontSize: 11, color: "#475569", marginTop: 2, letterSpacing: "0.06em" }}>SCHEDULING SYSTEM</div>
        </div>

        {/* Period selector */}
        <div style={{ padding: "10px 10px 12px", borderBottom: "1px solid #1E293B", position: "relative" }}>
          <div style={{ fontSize: 10, color: "#475569", fontWeight: 700, letterSpacing: "0.08em", marginBottom: 6, paddingLeft: 2 }}>EXAM PERIOD</div>
          <div style={{ display: "flex", gap: 5 }}>
            <button
              onClick={() => setShowPeriodMenu(v => !v)}
              style={{
                flex: 1, background: "#1E293B", border: "none", borderRadius: 7, padding: "7px 10px",
                color: "#E2E8F0", fontSize: 12, fontWeight: 600, cursor: "pointer",
                fontFamily: "inherit", textAlign: "left",
                display: "flex", justifyContent: "space-between", alignItems: "center",
              }}
            >
              <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {activePeriod?.name || "No Period"}
              </span>
              <span style={{ color: "#475569", fontSize: 10, flexShrink: 0, marginLeft: 4 }}>▾</span>
            </button>
            <button
              onClick={() => { setShowPeriodMenu(false); setShowNewPeriod(true); }}
              title="New Period"
              style={{
                width: 30, background: "#1E3A5F", border: "none", borderRadius: 7,
                color: "#60A5FA", fontSize: 18, fontWeight: 700, cursor: "pointer", fontFamily: "inherit",
                display: "flex", alignItems: "center", justifyContent: "center",
              }}
            >+</button>
          </div>

          {/* Period dropdown */}
          {showPeriodMenu && (
            <div style={{
              position: "absolute", top: "calc(100% - 4px)", left: 10, right: 10,
              background: "#1E293B", borderRadius: 8, padding: "4px 0",
              zIndex: 200, boxShadow: "0 6px 20px rgba(0,0,0,0.5)",
            }}>
              {periods.length === 0 && (
                <div style={{ padding: "8px 12px", color: "#475569", fontSize: 12 }}>No periods yet</div>
              )}
              {periods.map(p => (
                <button key={p.id} onClick={() => handleActivatePeriod(p.id)} style={{
                  width: "100%", background: "none", border: "none", padding: "8px 12px",
                  color: p.is_active ? "#60A5FA" : "#94A3B8",
                  fontSize: 12, fontWeight: p.is_active ? 700 : 500,
                  cursor: "pointer", textAlign: "left", fontFamily: "inherit",
                  display: "flex", alignItems: "center", gap: 6,
                }}>
                  <span style={{ fontSize: 7 }}>{p.is_active ? "●" : "○"}</span>
                  <span style={{ flex: 1 }}>{p.name}</span>
                  <span style={{ fontSize: 10, color: "#475569" }}>{p.exam_count ?? 0} exams</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Nav links */}
        <nav style={{ flex: 1, padding: "12px 10px" }}>
          {NAV.map(n => (
            <button key={n.id} onClick={() => { setView(n.id); setShowPeriodMenu(false); }} style={{
              width: "100%", display: "flex", alignItems: "center", gap: 10,
              padding: "10px 12px", borderRadius: 8, border: "none", cursor: "pointer",
              background: view === n.id ? "#1E3A5F" : "transparent",
              color: view === n.id ? "#60A5FA" : "#94A3B8",
              fontSize: 13, fontWeight: view === n.id ? 700 : 500,
              marginBottom: 2, fontFamily: "inherit", transition: "all 0.15s", textAlign: "left",
            }}>
              <Icon d={Icons[n.icon]} size={15} />
              {n.label}
            </button>
          ))}
        </nav>

        <div style={{ padding: "12px 20px", borderTop: "1px solid #1E293B" }}>
          <div style={{ fontSize: 11, color: "#334155", fontWeight: 600 }}>LOGGED IN AS</div>
          <select
            value={managerId}
            onChange={(e) => {
              const id = Number(e.target.value);
              setManagerId(id);
              localStorage.setItem("manager_id", String(id));
            }}
            style={{
              width: "100%", marginTop: 6, background: "#0B1220", color: "#60A5FA",
              border: "1px solid #1E293B", borderRadius: 6, padding: "6px 8px",
              fontSize: 12, fontWeight: 700, fontFamily: "inherit",
            }}
          >
            {managers.map((m) => (
              <option key={m.id} value={m.id}>{m.name}</option>
            ))}
          </select>
        </div>
      </aside>

      {/* ── Main content (key=refreshKey forces remount on period switch) ── */}
      <main style={{ flex: 1, overflow: "auto", padding: 32 }} onClick={() => setShowPeriodMenu(false)}>
        {view === "dashboard"  && <Dashboard key={refreshKey} stats={stats} />}
        {view === "semesters"  && <SemestersPage  key={refreshKey} toast={toast} />}
        {view === "departments" && <DepartmentsPage key={refreshKey} toast={toast} />}
        {view === "managerScopes" && <ManagerScopesPage key={refreshKey} toast={toast} />}
        {view === "classrooms" && <ClassroomsPage key={refreshKey} toast={toast} />}
        {view === "courses"    && <CoursesPage    key={refreshKey} toast={toast} />}
        {view === "exams"      && <ExamsPage      key={refreshKey} toast={toast} />}
        {view === "staff"      && <StaffPage      key={refreshKey} toast={toast} />}
        {view === "timeslots"  && <TimeSlotsPage  key={refreshKey} toast={toast} />}
        {view === "schedule"   && <ScheduleView       key={refreshKey} toast={toast} managerId={managerId} />}
        {view === "agent"     && <ExamFlowAIAgent     key={refreshKey} toast={toast} />}
      </main>

      {/* ── New Period modal ── */}
      {showNewPeriod && (
        <div
          onClick={() => setShowNewPeriod(false)}
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", zIndex: 999, display: "flex", alignItems: "center", justifyContent: "center" }}
        >
          <div onClick={e => e.stopPropagation()} style={{ background: "#fff", borderRadius: 16, padding: 32, width: 420, boxShadow: "0 20px 60px rgba(0,0,0,0.25)" }}>
            <div style={{ fontSize: 20, fontWeight: 800, color: "#0F172A", marginBottom: 8 }}>New Exam Period</div>
            <div style={{ fontSize: 13, color: "#64748B", marginBottom: 20, lineHeight: 1.6 }}>
              Starting a new period keeps your current <strong>{activePeriod?.name || "period"}</strong> data intact — exams and time slots are separate per period.
              Only <strong>2 periods</strong> are stored; creating a third will delete the oldest.
            </div>
            <input
              autoFocus
              value={newPeriodName}
              onChange={e => setNewPeriodName(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleCreatePeriod()}
              placeholder="e.g. Final 2026"
              style={{
                width: "100%", padding: "10px 14px", border: "2px solid #E2E8F0",
                borderRadius: 8, fontSize: 14, outline: "none", fontFamily: "inherit",
              }}
            />
            <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
              <button onClick={() => setShowNewPeriod(false)} style={{
                flex: 1, padding: "11px 0", background: "#F1F5F9", border: "none",
                borderRadius: 8, cursor: "pointer", fontSize: 14, fontWeight: 600, fontFamily: "inherit",
              }}>Cancel</button>
              <button onClick={handleCreatePeriod} disabled={!newPeriodName.trim()} style={{
                flex: 2, padding: "11px 0", background: newPeriodName.trim() ? "#3B82F6" : "#CBD5E1",
                color: newPeriodName.trim() ? "#fff" : "#94A3B8",
                border: "none", borderRadius: 8, cursor: newPeriodName.trim() ? "pointer" : "default",
                fontSize: 14, fontWeight: 700, fontFamily: "inherit",
              }}>Create Period</button>
            </div>
          </div>
        </div>
      )}

      {toastMsg && <Toast {...toastMsg} onClose={clearToast} />}
    </div>
  );
}

