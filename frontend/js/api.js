/** Typed-by-convention HTTP client for the FastAPI delivery ML endpoints. */

const timeoutMilliseconds = 15000;

/** Resolve the API URL for browser-served and file-opened dashboard pages. */
function resolveBaseUrl() {
  const configured = document.querySelector('meta[name="api-base-url"]')?.content.trim();
  if (configured) return configured.replace(/\/$/, "");
  return window.location.protocol.startsWith("http") ? window.location.origin : "http://localhost:8000";
}

/** HTTP error retaining a safe status and backend-provided message. */
export class ApiError extends Error {
  constructor(message, status = 0) { super(message); this.name = "ApiError"; this.status = status; }
}

/** Fetch API wrapper with timeout, JSON parsing, and endpoint-specific methods. */
export class DeliveryApi {
  constructor(baseUrl = resolveBaseUrl()) { this.baseUrl = baseUrl; }

  async request(path, options = {}) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), timeoutMilliseconds);
    try {
      const response = await fetch(`${this.baseUrl}${path}`, { ...options, headers:{ Accept:"application/json", ...options.headers }, signal:controller.signal });
      const contentType = response.headers.get("content-type") || "";
      const payload = contentType.includes("application/json") ? await response.json() : null;
      if (!response.ok) throw new ApiError(payload?.detail || `Request failed with HTTP ${response.status}.`, response.status);
      return payload;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (error.name === "AbortError") throw new ApiError("The API request timed out.");
      throw new ApiError("Unable to reach the API. Confirm that FastAPI is running and CORS is configured.");
    } finally { window.clearTimeout(timeout); }
  }

  health() { return this.request("/health"); }
  forecast(request) { return this.request("/forecast", { method:"POST", headers:{ "Content-Type":"application/json" }, body:JSON.stringify(request) }); }
  eta(request) { return this.request("/eta", { method:"POST", headers:{ "Content-Type":"application/json" }, body:JSON.stringify(request) }); }
  models() { return this.request("/models"); }
  history(query = {}) { return this.request(`/prediction-history${toQuery(query)}`); }
  systemStatus() { return this.request("/system-status"); }
  orders(query = {}) { return this.request(`/orders${toQuery(query)}`); }
}

/** Build an encoded optional query string. */
function toQuery(query) {
  const params = new URLSearchParams(Object.entries(query).filter(([, value]) => value !== undefined && value !== null && value !== ""));
  return params.size ? `?${params}` : "";
}

export const api = new DeliveryApi();
