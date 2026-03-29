import { useCallback, useEffect, useMemo, useState } from "react";
import { del, get, post } from "../utils/api";
import { Icons } from "../utils/constants";
import { Badge, Btn, Card, Icon, Select } from "../components/ui";

const BLANK = { manager_id: "", department_id: "", year: "" };
const YEAR_OPTIONS = ["1", "2", "3", "4", "5", "6"];

export default function ManagerScopesPage({ toast }) {
  const [scopes, setScopes] = useState([]);
  const [managers, setManagers] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [form, setForm] = useState(BLANK);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    const [scopeData, managerData, deptData] = await Promise.all([
      get("/manager-scopes"),
      get("/managers"),
      get("/departments"),
    ]);
    setScopes(scopeData || []);
    setManagers(managerData || []);
    setDepartments(deptData || []);
  }, []);

  useEffect(() => {
    load().catch(() => toast("Failed to load manager scopes", "error"));
  }, [load, toast]);

  const groupedScopes = useMemo(() => {
    const byManager = new Map();
    managers.forEach((manager) => byManager.set(manager.id, { manager, scopes: [] }));
    scopes.forEach((scope) => {
      if (!byManager.has(scope.manager_id)) {
        byManager.set(scope.manager_id, { manager: { id: scope.manager_id, name: scope.manager_name || `Manager ${scope.manager_id}` }, scopes: [] });
      }
      byManager.get(scope.manager_id).scopes.push(scope);
    });
    return Array.from(byManager.values()).sort((a, b) => a.manager.name.localeCompare(b.manager.name));
  }, [managers, scopes]);

  const submit = async () => {
    if (!form.manager_id) {
      toast("Select a manager first", "error");
      return;
    }
    setSaving(true);
    try {
      await post("/manager-scopes", {
        manager_id: +form.manager_id,
        department_id: form.department_id ? +form.department_id : null,
        year: form.year ? +form.year : null,
      });
      setForm(BLANK);
      await load();
      toast("Manager scope added", "success");
    } catch (e) {
      toast(e?.error || "Failed to add manager scope", "error");
    } finally {
      setSaving(false);
    }
  };

  const removeScope = async (scope) => {
    if (!confirm(`Remove scope for ${scope.manager_name}?`)) return;
    try {
      await del(`/manager-scopes/${scope.id}`);
      await load();
      toast("Manager scope removed", "success");
    } catch {
      toast("Failed to remove manager scope", "error");
    }
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <h2 style={{ fontSize: 24, fontWeight: 800, color: "#1E293B", margin: 0 }}>Manager Scopes</h2>
          <div style={{ marginTop: 4, fontSize: 13, color: "#64748B" }}>
            Control which department/year each manager can generate and edit.
          </div>
        </div>
      </div>

      <Card style={{ padding: 20, marginBottom: 20 }}>
        <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr 0.8fr auto", gap: 12, alignItems: "end" }}>
          <Select label="Manager" value={form.manager_id} onChange={(e) => setForm((f) => ({ ...f, manager_id: e.target.value }))}>
            <option value="">Select manager...</option>
            {managers.map((manager) => (
              <option key={manager.id} value={manager.id}>{manager.name}</option>
            ))}
          </Select>
          <Select label="Department" value={form.department_id} onChange={(e) => setForm((f) => ({ ...f, department_id: e.target.value }))}>
            <option value="">All departments</option>
            {departments.map((department) => (
              <option key={department.id} value={department.id}>{department.name}</option>
            ))}
          </Select>
          <Select label="Year" value={form.year} onChange={(e) => setForm((f) => ({ ...f, year: e.target.value }))}>
            <option value="">All years</option>
            {YEAR_OPTIONS.map((year) => (
              <option key={year} value={year}>Year {year}</option>
            ))}
          </Select>
          <Btn onClick={submit} disabled={saving}>
            <Icon d={Icons.plus} size={14} /> {saving ? "Adding..." : "Add Scope"}
          </Btn>
        </div>
        <div style={{ marginTop: 12, fontSize: 12, color: "#94A3B8" }}>
          Leave department or year empty to give broader ownership.
        </div>
      </Card>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: 16 }}>
        {groupedScopes.map(({ manager, scopes: managerScopes }) => (
          <Card key={manager.id} style={{ padding: 18 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
              <div style={{
                width: 42,
                height: 42,
                borderRadius: 12,
                background: "#EDE9FE",
                color: "#7C3AED",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontWeight: 800,
              }}>
                {manager.name?.[0] || "M"}
              </div>
              <div>
                <div style={{ fontSize: 15, fontWeight: 700, color: "#1E293B" }}>{manager.name}</div>
                <div style={{ fontSize: 12, color: "#94A3B8" }}>{managerScopes.length} scope{managerScopes.length !== 1 ? "s" : ""}</div>
              </div>
            </div>

            {managerScopes.length === 0 ? (
              <div style={{ fontSize: 13, color: "#94A3B8" }}>No explicit scopes — this manager can access everything.</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {managerScopes.map((scope) => (
                  <div
                    key={scope.id}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      gap: 12,
                      padding: "10px 12px",
                      border: "1px solid #E2E8F0",
                      borderRadius: 10,
                      background: "#F8FAFC",
                    }}
                  >
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      <Badge color={scope.department_code ? (departments.find((d) => d.code === scope.department_code)?.color || "#2563EB") : "#64748B"}>
                        {scope.department_code || "ALL DEPARTMENTS"}
                      </Badge>
                      <Badge color={scope.year ? "#0EA5E9" : "#64748B"}>
                        {scope.year ? `YEAR ${scope.year}` : "ALL YEARS"}
                      </Badge>
                    </div>
                    <button
                      onClick={() => removeScope(scope)}
                      title="Remove scope"
                      style={{ border: "none", background: "none", color: "#94A3B8", cursor: "pointer", padding: 4 }}
                    >
                      <Icon d={Icons.trash} size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
