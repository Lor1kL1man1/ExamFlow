const rawApiBase = import.meta.env.VITE_API_URL || "/api";
export const API = rawApiBase.replace(/\/+$/, "");

const fetcher = async (path, opts = {}) => {
  const suffix = String(path || "").startsWith("/") ? path : `/${path || ""}`;
  const res = await fetch(`${API}${suffix}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw await res.json();
  return res.json();
};

export const get = (path) => fetcher(path);
export const post = (path, body) => fetcher(path, { method: "POST", body: JSON.stringify(body) });
export const put = (path, body) => fetcher(path, { method: "PUT", body: JSON.stringify(body) });
export const del = (path) => fetcher(path, { method: "DELETE" });
