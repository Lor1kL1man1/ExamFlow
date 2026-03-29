import { Badge, Card, StatCard } from "../ui";

export default function Dashboard({ stats }) {
  return (
    <div>
      <h2 style={{ fontSize: 24, fontWeight: 800, color: "#1E293B", marginBottom: 4 }}>Overview</h2>
      <p style={{ color: "#64748B", marginBottom: 24, fontSize: 14 }}>University Exam Scheduling System</p>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 16, marginBottom: 32 }}>
        <StatCard label="Classrooms" value={stats.classrooms} icon="classroom" color="#7C3AED" />
        <StatCard label="Courses" value={stats.courses} icon="course" color="#2563EB" />
        <StatCard label="Exams" value={stats.exams} icon="exam" color="#059669" />
        <StatCard label="Instructors" value={stats.instructors} icon="users" color="#D97706" />
        <StatCard label="Observers" value={stats.observers} icon="users" color="#EC4899" />
        <StatCard label="Scheduled" value={stats.scheduled} icon="check" color="#10B981"
          sub={`of ${stats.exams} exams`} />
      </div>
      <Card style={{ padding: 20 }}>
        <h3 style={{ fontSize: 15, fontWeight: 700, color: "#1E293B", marginBottom: 12 }}>Departments</h3>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
          {(stats.departments || []).map(d => (
            <div key={d.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "8px 14px", background: d.color + "10", borderRadius: 8, border: `1px solid ${d.color}30` }}>
              <div style={{ width: 10, height: 10, borderRadius: 3, background: d.color }} />
              <span style={{ fontSize: 13, fontWeight: 600, color: "#1E293B" }}>{d.name}</span>
              <Badge color={d.color}>{d.code}</Badge>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
