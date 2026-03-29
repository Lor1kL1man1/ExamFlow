import { Icons } from "../utils/constants";

export const Icon = ({ d, size = 18, className = "", color }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke={color || "currentColor"} strokeWidth="2" strokeLinecap="round"
    strokeLinejoin="round" className={className}>
    <path d={d} />
  </svg>
);

export const Badge = ({ children, color = "#3B82F6" }) => (
  <span style={{
    background: color + "22", color, border: `1px solid ${color}44`,
    padding: "2px 8px", borderRadius: 99, fontSize: 11, fontWeight: 600,
    letterSpacing: "0.04em", whiteSpace: "nowrap",
  }}>{children}</span>
);

export const Btn = ({ children, onClick, variant = "primary", size = "md", disabled }) => {
  const styles = {
    primary: { background: "#1E293B", color: "#fff", border: "none" },
    secondary: { background: "transparent", color: "#1E293B", border: "1.5px solid #CBD5E1" },
    danger: { background: "#FEE2E2", color: "#DC2626", border: "1.5px solid #FECACA" },
    success: { background: "#D1FAE5", color: "#059669", border: "1.5px solid #A7F3D0" },
  };
  const sizeMap = { sm: "6px 12px", md: "9px 18px", lg: "12px 24px" };
  return (
    <button onClick={onClick} disabled={disabled} style={{
      ...styles[variant], padding: sizeMap[size],
      borderRadius: 8, cursor: disabled ? "not-allowed" : "pointer",
      fontSize: size === "sm" ? 12 : 14, fontWeight: 600,
      display: "inline-flex", alignItems: "center", gap: 6,
      opacity: disabled ? 0.5 : 1, transition: "all 0.15s",
      fontFamily: "inherit",
    }}>{children}</button>
  );
};

export const Card = ({ children, style = {}, ...rest }) => (
  <div style={{
    background: "#fff", borderRadius: 14, border: "1px solid #E2E8F0",
    boxShadow: "0 1px 4px rgba(0,0,0,0.06)", ...style,
  }} {...rest}>{children}</div>
);

export const Input = ({ label, ...props }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
    {label && <label style={{ fontSize: 12, fontWeight: 600, color: "#64748B", letterSpacing: "0.05em" }}>{label.toUpperCase()}</label>}
    <input {...props} style={{
      border: "1.5px solid #E2E8F0", borderRadius: 8, padding: "8px 12px",
      fontSize: 14, fontFamily: "inherit", outline: "none",
      transition: "border-color 0.15s", color: "#1E293B",
      ...(props.style || {}),
    }} />
  </div>
);

export const Select = ({ label, children, ...props }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
    {label && <label style={{ fontSize: 12, fontWeight: 600, color: "#64748B", letterSpacing: "0.05em" }}>{label.toUpperCase()}</label>}
    <select {...props} style={{
      border: "1.5px solid #E2E8F0", borderRadius: 8, padding: "8px 12px",
      fontSize: 14, fontFamily: "inherit", outline: "none", color: "#1E293B",
      background: "#fff", cursor: "pointer",
    }}>{children}</select>
  </div>
);

export const Modal = ({ title, onClose, children }) => (
  <div style={{
    position: "fixed", inset: 0, background: "rgba(15,23,42,0.55)",
    display: "flex", alignItems: "center", justifyContent: "center",
    zIndex: 1000, backdropFilter: "blur(2px)",
  }} onClick={onClose}>
    <Card style={{ width: 520, maxWidth: "95vw", maxHeight: "90vh", overflow: "auto" }}
      onClick={e => e.stopPropagation()}>
      <div style={{ padding: "20px 24px", borderBottom: "1px solid #E2E8F0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: "#1E293B" }}>{title}</h3>
        <button onClick={onClose} style={{ border: "none", background: "none", cursor: "pointer", fontSize: 20, color: "#94A3B8" }}>×</button>
      </div>
      <div style={{ padding: 24 }}>{children}</div>
    </Card>
  </div>
);

export const Toast = ({ message, type, onClose }) => (
  <div style={{
    position: "fixed", bottom: 24, right: 24, zIndex: 2000,
    background: type === "error" ? "#FEF2F2" : type === "warning" ? "#FFFBEB" : "#F0FDF4",
    border: `1.5px solid ${type === "error" ? "#FECACA" : type === "warning" ? "#FDE68A" : "#BBF7D0"}`,
    borderRadius: 12, padding: "12px 18px", display: "flex", alignItems: "center", gap: 10,
    boxShadow: "0 8px 24px rgba(0,0,0,0.12)", maxWidth: 380,
    animation: "slideIn 0.2s ease",
  }}>
    <span style={{ fontSize: 20 }}>{type === "error" ? "⚠️" : type === "warning" ? "⚡" : "✅"}</span>
    <span style={{ fontSize: 13, color: "#1E293B", flex: 1, whiteSpace: "pre-line" }}>{message}</span>
    <button onClick={onClose} style={{ border: "none", background: "none", cursor: "pointer", color: "#94A3B8" }}>×</button>
  </div>
);

export const StatCard = ({ label, value, icon, color = "#3B82F6", sub }) => (
  <Card style={{ padding: 20 }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
      <div>
        <div style={{ fontSize: 12, fontWeight: 600, color: "#94A3B8", letterSpacing: "0.08em", marginBottom: 6 }}>{label.toUpperCase()}</div>
        <div style={{ fontSize: 32, fontWeight: 800, color: "#1E293B", lineHeight: 1 }}>{value}</div>
        {sub && <div style={{ fontSize: 12, color: "#64748B", marginTop: 4 }}>{sub}</div>}
      </div>
      <div style={{ background: color + "18", borderRadius: 10, padding: 10, color }}>
        <Icon d={Icons[icon]} size={22} />
      </div>
    </div>
  </Card>
);
