/** DOM, formatting, presentation, and theme helpers for the vanilla-JS UI. */

const themeKey = "delivery-ml-theme";

/** Escape untrusted API text before inserting it into HTML. */
export function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", "'":"&#39;", '"':"&quot;" })[character]);
}

/** Format nullable numbers for metric cards and tables. */
export function formatNumber(value, maximumFractionDigits = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? new Intl.NumberFormat(undefined, { maximumFractionDigits }).format(number) : "—";
}

/** Format an ISO timestamp with the user's locale. */
export function formatDate(value) {
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? "—" : new Intl.DateTimeFormat(undefined, { dateStyle:"medium", timeStyle:"short" }).format(date);
}

/** Format a duration in seconds into a concise customer-facing ETA. */
export function formatDuration(seconds) {
  const value = Number(seconds);
  if (!Number.isFinite(value)) return "—";
  const minutes = Math.round(value / 60);
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)}h ${minutes % 60}m`;
}

/** Display a transient, accessible toast message. */
export function showToast(message, variant = "error") {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = `toast ${variant}`;
  toast.setAttribute("role", "status");
  toast.textContent = message;
  container.append(toast);
  window.setTimeout(() => toast.remove(), 4500);
}

/** Apply the persisted colour theme or the user's system preference. */
export function getTheme() {
  return localStorage.getItem(themeKey) || (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}

/** Persist and apply a requested colour theme. */
export function setTheme(theme) {
  localStorage.setItem(themeKey, theme);
  document.documentElement.dataset.theme = theme;
}

/** Initialize the document's theme before rendering rich content. */
export function initializeTheme() { setTheme(getTheme()); }

/** Return a semantic status badge based on a service or model state. */
export function statusBadge(status) {
  const text = String(status || "unknown");
  const normalized = text.toLowerCase();
  const variant = ["healthy", "active", "ok", "success", "connected"].includes(normalized) ? "healthy" : ["failed", "error", "down", "unhealthy"].includes(normalized) ? "failed" : normalized === "warning" ? "warning" : "";
  return `<span class="status-badge ${variant}">${escapeHtml(text)}</span>`;
}

/** Render a safe table from API records and declared columns. */
export function renderTable(records, columns) {
  if (!records.length) return '<div class="empty-state"><strong>No records found</strong><span>Adjust filters or load a different data source.</span></div>';
  const header = columns.map(({ label }) => `<th>${escapeHtml(label)}</th>`).join("");
  const rows = records.map((record) => `<tr>${columns.map(({ key, format }) => `<td>${format ? format(record[key], record) : escapeHtml(record[key] ?? "—")}</td>`).join("")}</tr>`).join("");
  return `<div class="table-wrap"><table class="data-table"><thead><tr>${header}</tr></thead><tbody>${rows}</tbody></table></div>`;
}

/** Convert inconsistent paginated API responses into a stable records array. */
export function extractRecords(payload) {
  if (Array.isArray(payload)) return payload;
  return payload?.items || payload?.data || payload?.results || [];
}
