/** Dashboard page showing platform-level metrics from live FastAPI endpoints. */

import { api } from "./api.js";
import { mountPage } from "./app.js";
import { setApiIndicator } from "../components/navbar.js";
import { escapeHtml, extractRecords, formatDate, formatNumber, showToast, statusBadge } from "./utils.js";

mountPage({ title:"Dashboard", content:`<div class="page-heading"><div><h1>Operations overview</h1><p>Live delivery forecasting platform health and model activity.</p></div></div><div class="grid metrics" id="metrics-grid"></div><div class="grid two" style="margin-top:18px"><article class="card"><div class="card-header"><h2 class="card-title">Platform services</h2></div><div class="card-body" id="services"><div class="loading"><span class="spinner"></span></div></div></article><article class="card"><div class="card-header"><h2 class="card-title">Active models</h2><a class="mono" href="models.html">View models →</a></div><div class="card-body" id="models-overview"><div class="loading"><span class="spinner"></span></div></div></article></div>` });

/** Render dashboard content from parallel endpoint responses. */
async function loadDashboard() {
  const [healthResult, statusResult, modelsResult] = await Promise.allSettled([api.health(), api.systemStatus(), api.models()]);
  const health = healthResult.status === "fulfilled" ? healthResult.value : null;
  const status = statusResult.status === "fulfilled" ? statusResult.value : {};
  const models = modelsResult.status === "fulfilled" ? extractRecords(modelsResult.value) : [];
  const apiHealthy = Boolean(health);
  setApiIndicator(apiHealthy, apiHealthy ? "API connected" : "API unavailable");
  if (!apiHealthy) showToast("Dashboard metrics are unavailable until the API is running.");

  const metrics = [
    ["Historical orders", status.total_historical_orders ?? status.total_orders, "Orders in the warehouse"],
    ["Delivery zones", status.total_delivery_zones ?? status.zone_count, "Active operational zones"],
    ["Trained models", status.number_of_trained_models ?? models.length, "Registered model versions"],
    ["Latest model", latestModel(models), "Current registered version"],
    ["API status", health?.status ?? health?.api_status, "FastAPI service"],
    ["Database", health?.database ?? status.database?.status, "PostgreSQL connection"],
    ["Redis", health?.redis ?? status.redis?.status, "Feature-cache connection"],
  ];
  document.getElementById("metrics-grid").innerHTML = metrics.map(([label, value, note]) => `<article class="card metric-card"><span class="metric-label">${label}</span><strong class="metric-value">${metricValue(value)}</strong><span class="metric-note">${note}</span></article>`).join("");
  renderServices(health, status);
  renderModels(models);
}

function metricValue(value) {
  if (typeof value === "number") return formatNumber(value);
  return escapeHtml(value ?? "—");
}
function latestModel(models) { return models[0]?.version || models[0]?.model_version || "—"; }
function renderServices(health, status) {
  const services = [["FastAPI", health?.status ?? health?.api_status], ["PostgreSQL", health?.database ?? status.database?.status], ["Redis", health?.redis ?? status.redis?.status]];
  document.getElementById("services").innerHTML = `<div class="service-list">${services.map(([name, state]) => `<div class="service-item"><span>${name}</span>${statusBadge(state || "unknown")}</div>`).join("")}</div>`;
}
function renderModels(models) {
  const target = document.getElementById("models-overview");
  if (!models.length) { target.innerHTML = '<div class="empty-state"><strong>No model registry records</strong><span>Train and register a model to see it here.</span></div>'; return; }
  target.innerHTML = `<div class="overview-list">${models.slice(0, 4).map((model) => `<div class="overview-row"><div><strong>${escapeHtml(model.model_name || model.name || "Model")}</strong><div class="mono">${escapeHtml(model.version || model.model_version || "—")}</div></div><div>${statusBadge(model.stage || model.status || "registered")}</div></div>`).join("")}</div>`;
}

loadDashboard();
