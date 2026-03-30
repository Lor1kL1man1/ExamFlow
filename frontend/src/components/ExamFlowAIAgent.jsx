import { useState, useRef, useEffect } from "react";
import { API } from "../utils/api";

const SESSION_STORAGE_KEY = "examflow_ai_session_id";
const makeSessionId = () => "sess_" + Math.random().toString(36).slice(2);
const getOrCreateSessionId = () => {
  try {
    const existing = localStorage.getItem(SESSION_STORAGE_KEY);
    if (existing) return existing;
    const created = makeSessionId();
    localStorage.setItem(SESSION_STORAGE_KEY, created);
    return created;
  } catch {
    return makeSessionId();
  }
};
const constraintsStorageKey = (sessionId) => `examflow_ai_constraints_${sessionId}`;

// ── Constraint kind metadata ──────────────────────────────────────────────────
const KIND_META = {
  instructor_day:         { label: "Instructor Day Lock",     color: "#7C3AED", icon: "👨\u200d🏫" },
  instructor_time_range:  { label: "Instructor Time Window",  color: "#2563EB", icon: "⏰" },
  instructor_unavailable: { label: "Instructor Unavailable",  color: "#DC2626", icon: "🚫" },
  department_day:         { label: "Dept Day Lock",           color: "#059669", icon: "🏛️" },
  department_time_range:  { label: "Dept Time Window",        color: "#D97706", icon: "⏱️" },
  department_no_overlap:  { label: "No Dept Overlap",         color: "#EC4899", icon: "⛔" },
  exam_room:              { label: "Room Assignment",         color: "#0891B2", icon: "🏫" },
  observer_unavailable:   { label: "Observer Unavailable",    color: "#9333EA", icon: "👁️\u200d🗨️" },
  observer_exam_load:     { label: "Observer Exam Target",    color: "#0EA5E9", icon: "🎯" },
  course_day:             { label: "Course Day Lock",         color: "#16A34A", icon: "📚" },
  course_time_range:      { label: "Course Time Window",      color: "#CA8A04", icon: "📋" },
};

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

const QUICK_PROMPTS = [
  "All exams by Professor Ervin should be on Fridays",
  "Architecture department exams must start after 10:00",
  "Observer Amira is unavailable on 2025-06-15",
  "AI Engineering and Civil Engineering exams must not overlap",
  "The Database Systems exam must be in room A-101",
  "All Computer Engineering exams should be on Tuesdays",
];

// ── Sub-components ────────────────────────────────────────────────────────────
const ConstraintChip = ({ constraint, index, onRemove }) => {
  const meta = KIND_META[constraint.kind] || { label: constraint.kind, color: "#64748B", icon: "📌" };
  const parts = [];
  if (constraint.instructor_name) parts.push(`Prof. ${constraint.instructor_name}`);
  if (constraint.department_code) parts.push(constraint.department_code);
  if (constraint.course_code) parts.push(constraint.course_code);
  if (constraint.observer_name) parts.push(constraint.observer_name);
  if (constraint.target_count !== undefined && constraint.target_count !== null) parts.push(`${constraint.target_count} exams`);
  if (constraint.weekday !== undefined && constraint.weekday !== null) parts.push(WEEKDAYS[constraint.weekday]);
  if (constraint.date_str) parts.push(constraint.date_str);
  if (constraint.room_name) parts.push(`Room ${constraint.room_name}`);
  if (constraint.start_time) parts.push(`${constraint.start_time}–${constraint.end_time || "?"}`);

  return (
    <div style={{
      display: "flex", alignItems: "flex-start", gap: 8, padding: "10px 12px",
      background: meta.color + "0d", border: `1px solid ${meta.color}30`,
      borderRadius: 10, position: "relative",
    }}>
      <span style={{ fontSize: 16, lineHeight: 1.4 }}>{meta.icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: meta.color, letterSpacing: "0.05em", marginBottom: 2 }}>
          {meta.label.toUpperCase()}
        </div>
        <div style={{ fontSize: 13, color: "#1E293B", fontWeight: 600 }}>
          {parts.join(" · ")}
        </div>
        {constraint.explanation && (
          <div style={{ fontSize: 11, color: "#64748B", marginTop: 2 }}>{constraint.explanation}</div>
        )}
        {constraint.confidence !== undefined && constraint.confidence < 0.8 && (
          <div style={{ fontSize: 10, color: "#D97706", marginTop: 2 }}>
            ⚠ Low confidence ({Math.round(constraint.confidence * 100)}%) — please verify
          </div>
        )}
      </div>
      <button onClick={() => onRemove(index)} style={{
        border: "none", background: "none", cursor: "pointer", color: "#CBD5E1",
        fontSize: 16, lineHeight: 1, padding: "0 2px", flexShrink: 0,
        transition: "color 0.15s",
      }} onMouseEnter={e => e.target.style.color = "#DC2626"}
         onMouseLeave={e => e.target.style.color = "#CBD5E1"}>×</button>
    </div>
  );
};

const Message = ({ msg }) => {
  const isUser = msg.role === "user";
  return (
    <div style={{
      display: "flex", justifyContent: isUser ? "flex-end" : "flex-start",
      marginBottom: 12,
    }}>
      {!isUser && (
        <div style={{
          width: 30, height: 30, borderRadius: "50%", background: "linear-gradient(135deg, #7C3AED, #2563EB)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 14, marginRight: 8, flexShrink: 0, marginTop: 2,
        }}>🤖</div>
      )}
      <div style={{
        maxWidth: "80%", padding: "10px 14px", borderRadius: isUser ? "14px 14px 4px 14px" : "14px 14px 14px 4px",
        background: isUser ? "#1E293B" : "#F8FAFC",
        color: isUser ? "#fff" : "#1E293B",
        fontSize: 13, lineHeight: 1.6,
        border: isUser ? "none" : "1px solid #E2E8F0",
        boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
      }}>
        {msg.content}
        {msg.newConstraints?.length > 0 && (
          <div style={{
            marginTop: 8, padding: "6px 10px",
            background: "#D1FAE5", borderRadius: 6,
            fontSize: 11, color: "#065F46", fontWeight: 600,
          }}>
            ✓ {msg.newConstraints.length} constraint{msg.newConstraints.length > 1 ? "s" : ""} added
          </div>
        )}
      </div>
    </div>
  );
};

const TypingIndicator = () => (
  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
    <div style={{
      width: 30, height: 30, borderRadius: "50%", background: "linear-gradient(135deg, #7C3AED, #2563EB)",
      display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14,
    }}>🤖</div>
    <div style={{
      padding: "10px 16px", background: "#F8FAFC", border: "1px solid #E2E8F0",
      borderRadius: "14px 14px 14px 4px", display: "flex", gap: 4, alignItems: "center",
    }}>
      {[0, 1, 2].map(i => (
        <div key={i} style={{
          width: 6, height: 6, borderRadius: "50%", background: "#94A3B8",
          animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
        }} />
      ))}
    </div>
  </div>
);

// ── Main Component ────────────────────────────────────────────────────────────
export default function ExamFlowAIAgent({ toast }) {
  const sessionIdRef = useRef(getOrCreateSessionId());
  const [messages, setMessages] = useState([{
    role: "assistant",
    content: "Hi! I'm ExamBot — your AI scheduling assistant. Tell me any scheduling preferences or constraints you want applied before generating the exam schedule. For example: \"All exams taught by Professor Ervin should be scheduled on Fridays.\"",
    newConstraints: [],
  }]);
  const [constraints, setConstraints] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState("chat");
  const [generating, setGenerating] = useState(false);
  const [genResult, setGenResult] = useState(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    const sessionId = sessionIdRef.current;

    // 1) Restore quickly from local storage for better UX
    try {
      const raw = localStorage.getItem(constraintsStorageKey(sessionId));
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) setConstraints(parsed);
      }
    } catch {
      // ignore local storage parse errors
    }

    // 2) Sync from backend session (source of truth while backend is alive)
    (async () => {
      try {
        const res = await fetch(`${API}/agent/constraints?session_id=${encodeURIComponent(sessionId)}`);
        const data = await res.json();
        const next = Array.isArray(data?.constraints) ? data.constraints : [];
        setConstraints(next);
        try {
          localStorage.setItem(constraintsStorageKey(sessionId), JSON.stringify(next));
        } catch {
          // ignore local storage write errors
        }
      } catch {
        // keep local copy if backend fetch fails
      }
    })();
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(constraintsStorageKey(sessionIdRef.current), JSON.stringify(constraints));
    } catch {
      // ignore local storage write errors
    }
  }, [constraints]);

  const send = async (text) => {
    const userText = text || input.trim();
    if (!userText || loading) return;
    setInput("");
    setLoading(true);
    setMessages(prev => [...prev, { role: "user", content: userText, newConstraints: [] }]);

    try {
      const res = await fetch(`${API}/agent/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionIdRef.current, message: userText }),
      });
      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error || "Server error");
      }

      setConstraints(data.all_constraints || []);
      setMessages(prev => [...prev, {
        role: "assistant",
        content: data.reply,
        newConstraints: data.new_constraints || [],
      }]);
    } catch (err) {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: `⚠️ ${err.message || "Could not reach the AI agent. Make sure the backend is running."}`,
        newConstraints: [],
      }]);
    }

    setLoading(false);
    inputRef.current?.focus();
  };

  const removeConstraint = async (index) => {
    try {
      await fetch(`${API}/agent/constraints/${index}?session_id=${sessionIdRef.current}`, { method: "DELETE" });
      setConstraints(prev => prev.filter((_, i) => i !== index));
    } catch (_) {
      setConstraints(prev => prev.filter((_, i) => i !== index));
    }
  };

  const clearAll = async () => {
    try {
      await fetch(`${API}/agent/clear`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionIdRef.current }),
      });
    } catch (_) {}
    setConstraints([]);
    setGenResult(null);
    setMessages([{
      role: "assistant",
      content: "All constraints cleared! Start fresh by telling me your scheduling requirements.",
      newConstraints: [],
    }]);
  };

  const handleGenerate = async () => {
    if (generating) return;
    setGenerating(true);
    setGenResult(null);
    try {
      const res = await fetch(`${API}/schedule/generate-with-constraints`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionIdRef.current }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Generation failed");
      setGenResult({ ok: true, ...data });
      toast?.(`Schedule generated: ${data.scheduled ?? 0} exams placed.`, "success");
    } catch (err) {
      setGenResult({ ok: false, error: err.message });
      toast?.(err.message, "error");
    }
    setGenerating(false);
  };

  const kindCounts = constraints.reduce((acc, c) => {
    acc[c.kind] = (acc[c.kind] || 0) + 1;
    return acc;
  }, {});

  return (
    <div style={{
      fontFamily: "'IBM Plex Sans', system-ui, sans-serif",
      display: "flex", flexDirection: "column", height: 680,
      background: "#fff", borderRadius: 16,
      border: "1px solid #E2E8F0", overflow: "hidden",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
        @keyframes pulse { 0%,100%{opacity:.3;transform:scale(0.85)} 50%{opacity:1;transform:scale(1)} }
        * { box-sizing: border-box; }
        textarea:focus { outline: none; border-color: #7C3AED !important; }
        button:focus { outline: 2px solid #7C3AED; outline-offset: 2px; }
      `}</style>

      {/* Header */}
      <div style={{
        padding: "16px 20px", borderBottom: "1px solid #E2E8F0",
        background: "linear-gradient(135deg, #0F172A 0%, #1E293B 100%)",
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{
            width: 36, height: 36, borderRadius: "50%",
            background: "linear-gradient(135deg, #7C3AED, #2563EB)",
            display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18,
          }}>🤖</div>
          <div>
            <div style={{ color: "#fff", fontWeight: 700, fontSize: 15 }}>ExamBot</div>
            <div style={{ color: "#64748B", fontSize: 11 }}>AI Scheduling Constraint Agent · Powered by Groq</div>
          </div>
        </div>
        {constraints.length > 0 && (
          <div style={{
            background: "#7C3AED", color: "#fff", borderRadius: 99,
            padding: "2px 10px", fontSize: 12, fontWeight: 700,
          }}>{constraints.length} constraint{constraints.length > 1 ? "s" : ""}</div>
        )}
      </div>

      {/* Tabs */}
      <div style={{ display: "flex", borderBottom: "1px solid #E2E8F0", background: "#F8FAFC" }}>
        {[["chat", "💬 Chat"], ["constraints", `📋 Constraints (${constraints.length})`]].map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)} style={{
            flex: 1, padding: "10px", border: "none", cursor: "pointer",
            background: tab === id ? "#fff" : "transparent",
            color: tab === id ? "#7C3AED" : "#64748B",
            fontWeight: tab === id ? 700 : 500, fontSize: 13,
            borderBottom: tab === id ? "2px solid #7C3AED" : "2px solid transparent",
            fontFamily: "inherit", transition: "all 0.15s",
          }}>{label}</button>
        ))}
      </div>

      {/* Chat Tab */}
      {tab === "chat" && (
        <>
          <div style={{ flex: 1, overflow: "auto", padding: "16px 16px 8px" }}>
            {messages.map((msg, i) => <Message key={i} msg={msg} />)}
            {loading && <TypingIndicator />}
            <div ref={messagesEndRef} />
          </div>

          {messages.length <= 1 && !loading && (
            <div style={{ padding: "0 16px 8px" }}>
              <div style={{ fontSize: 11, color: "#94A3B8", fontWeight: 600, marginBottom: 6, letterSpacing: "0.05em" }}>QUICK EXAMPLES</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {QUICK_PROMPTS.map((p, i) => (
                  <button key={i} onClick={() => send(p)} style={{
                    border: "1px solid #E2E8F0", background: "#F8FAFC",
                    borderRadius: 20, padding: "5px 12px", fontSize: 11,
                    cursor: "pointer", color: "#374151", fontFamily: "inherit",
                    transition: "all 0.15s",
                  }}
                    onMouseEnter={e => { e.currentTarget.style.background = "#EDE9FE"; e.currentTarget.style.borderColor = "#7C3AED"; e.currentTarget.style.color = "#7C3AED"; }}
                    onMouseLeave={e => { e.currentTarget.style.background = "#F8FAFC"; e.currentTarget.style.borderColor = "#E2E8F0"; e.currentTarget.style.color = "#374151"; }}
                  >{p}</button>
                ))}
              </div>
            </div>
          )}

          <div style={{ padding: "12px 16px", borderTop: "1px solid #E2E8F0", background: "#fff" }}>
            <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
              <textarea
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                placeholder="Type a scheduling constraint... (Enter to send, Shift+Enter for newline)"
                rows={2}
                style={{
                  flex: 1, border: "1.5px solid #E2E8F0", borderRadius: 10,
                  padding: "10px 12px", fontSize: 13, fontFamily: "inherit",
                  resize: "none", lineHeight: 1.5, color: "#1E293B",
                }}
              />
              <button onClick={() => send()} disabled={!input.trim() || loading} style={{
                background: input.trim() && !loading ? "#7C3AED" : "#E2E8F0",
                color: input.trim() && !loading ? "#fff" : "#94A3B8",
                border: "none", borderRadius: 10, padding: "10px 16px",
                cursor: input.trim() && !loading ? "pointer" : "not-allowed",
                fontSize: 18, transition: "all 0.15s", flexShrink: 0, height: 56,
              }}>➤</button>
            </div>
          </div>
        </>
      )}

      {/* Constraints Tab */}
      {tab === "constraints" && (
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
          <div style={{ flex: 1, overflow: "auto", padding: 16 }}>
            {constraints.length === 0 ? (
              <div style={{ textAlign: "center", padding: "40px 20px", color: "#94A3B8" }}>
                <div style={{ fontSize: 40, marginBottom: 12 }}>📋</div>
                <div style={{ fontWeight: 600, color: "#374151", marginBottom: 4 }}>No constraints yet</div>
                <div style={{ fontSize: 13 }}>Switch to the chat tab and tell ExamBot your scheduling requirements.</div>
              </div>
            ) : (
              <>
                <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 16 }}>
                  {Object.entries(kindCounts).map(([kind, count]) => {
                    const meta = KIND_META[kind] || { color: "#64748B", icon: "📌" };
                    return (
                      <div key={kind} style={{
                        background: meta.color + "12", border: `1px solid ${meta.color}30`,
                        borderRadius: 8, padding: "4px 10px", fontSize: 11, fontWeight: 700, color: meta.color,
                        display: "flex", alignItems: "center", gap: 4,
                      }}>
                        {meta.icon} {count}×
                      </div>
                    );
                  })}
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {constraints.map((c, i) => (
                    <ConstraintChip key={i} constraint={c} index={i} onRemove={removeConstraint} />
                  ))}
                </div>
              </>
            )}
          </div>

          <div style={{ padding: "12px 16px", borderTop: "1px solid #E2E8F0", background: "#F8FAFC" }}>
            {genResult && (
              <div style={{
                marginBottom: 12, padding: "10px 14px",
                background: genResult.ok ? "#D1FAE5" : "#FEF2F2",
                border: `1px solid ${genResult.ok ? "#A7F3D0" : "#FECACA"}`,
                borderRadius: 10, fontSize: 12,
              }}>
                <div style={{ fontWeight: 700, color: genResult.ok ? "#065F46" : "#991B1B", marginBottom: 4 }}>
                  {genResult.ok ? "✅ Schedule generated successfully!" : "❌ Generation failed"}
                </div>
                {genResult.ok && (
                  <div style={{ color: "#374151" }}>
                    {genResult.scheduled ?? 0} exams scheduled · {genResult.conflicts ?? 0} conflicts
                  </div>
                )}
                {!genResult.ok && (
                  <div style={{ color: "#DC2626" }}>{genResult.error}</div>
                )}
              </div>
            )}
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={handleGenerate} disabled={generating} style={{
                flex: 1, padding: "11px", borderRadius: 10, border: "none",
                background: generating ? "#E2E8F0" : "linear-gradient(135deg, #7C3AED, #2563EB)",
                color: generating ? "#94A3B8" : "#fff",
                fontWeight: 700, fontSize: 14, cursor: generating ? "not-allowed" : "pointer",
                fontFamily: "inherit", transition: "all 0.2s",
              }}>
                {generating ? "⏳ Generating schedule..." : `▶ Generate Schedule${constraints.length > 0 ? ` with ${constraints.length} Constraint${constraints.length !== 1 ? "s" : ""}` : ""}`}
              </button>
              {constraints.length > 0 && (
                <button onClick={clearAll} style={{
                  padding: "11px 14px", borderRadius: 10, border: "1.5px solid #FECACA",
                  background: "#FEF2F2", color: "#DC2626", fontWeight: 600, fontSize: 13,
                  cursor: "pointer", fontFamily: "inherit",
                }}>Clear All</button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
