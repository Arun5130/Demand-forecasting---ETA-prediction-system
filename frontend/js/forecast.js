/** Demand-forecast page with validated input, live API inference, and Chart.js output. */

import { api } from "./api.js";
import { mountPage } from "./app.js";
import { setApiIndicator } from "../components/navbar.js";
import { extractRecords, formatNumber, showToast } from "./utils.js";

let forecastChart;
mountPage({ title:"Demand Forecast", content:`<div class="page-heading"><div><h1>Zone demand forecast</h1><p>Generate point-in-time forecasts for the next one, three, and six hours.</p></div></div><div class="prediction-layout"><article class="card"><div class="card-header"><h2 class="card-title">Forecast request</h2></div><div class="card-body"><form class="form-grid" id="forecast-form"><div class="form-field"><label for="zone">Delivery zone</label><select id="zone" required disabled><option value="">Loading zones…</option></select></div><div class="form-field"><label for="forecast-date">Date</label><input id="forecast-date" type="date" required></div><div class="form-field"><label for="forecast-time">Time</label><input id="forecast-time" type="time" required></div><button class="button" id="forecast-submit" type="submit">Predict demand</button></form></div></article><section class="grid"><article class="card"><div class="card-header"><h2 class="card-title">Prediction</h2><span id="forecast-confidence" class="status-badge">Awaiting request</span></div><div class="card-body" id="forecast-result"><div class="empty-state"><strong>No prediction yet</strong><span>Select a zone and prediction time to run the active model.</span></div></div></article><article class="card"><div class="card-header"><h2 class="card-title">Historical demand and forecast</h2></div><div class="chart-container"><canvas id="forecast-chart" aria-label="Demand forecast chart"></canvas></div></article></section></div>` });

function setDefaultTime() { const now = new Date(); document.getElementById("forecast-date").value = now.toISOString().slice(0, 10); document.getElementById("forecast-time").value = now.toTimeString().slice(0, 5); }
async function loadZones() {
  try {
    const records = extractRecords(await api.orders({ page_size:1000 }));
    const zones = [...new Map(records.map((order) => [order.zone_id ?? order.zone?.id ?? order.zone_name, order.zone_name ?? order.zone?.name ?? order.zone_id])).entries()].filter(([id]) => id !== undefined && id !== null);
    const select = document.getElementById("zone");
    select.innerHTML = `<option value="">Select a zone</option>${zones.map(([id, name]) => `<option value="${String(id)}">${String(name)}</option>`).join("")}`;
    select.disabled = !zones.length;
    if (!zones.length) showToast("No delivery zones were returned by the orders endpoint.");
  } catch (error) { document.getElementById("zone").innerHTML = '<option value="">Zones unavailable</option>'; showToast(error.message); }
}
document.getElementById("forecast-form").addEventListener("submit", async (event) => {
  event.preventDefault(); const button = document.getElementById("forecast-submit"); button.disabled = true; button.textContent = "Predicting…";
  try { const zoneId = document.getElementById("zone").value; const date = document.getElementById("forecast-date").value; const time = document.getElementById("forecast-time").value; const result = await api.forecast({ zone_id:zoneId, prediction_at:new Date(`${date}T${time}`).toISOString() }); renderForecast(result); setApiIndicator(true, "API connected"); showToast("Demand forecast generated.", "success"); }
  catch (error) { setApiIndicator(false, "API unavailable"); showToast(error.message); }
  finally { button.disabled = false; button.textContent = "Predict demand"; }
});
function renderForecast(result) {
  const one = result.next_1_hour ?? result.next_1h ?? result.forecast_1h;
  const three = result.next_3_hours ?? result.next_3h ?? result.forecast_3h;
  const six = result.next_6_hours ?? result.next_6h ?? result.forecast_6h;
  const confidence = result.confidence ?? result.prediction_confidence;
  document.getElementById("forecast-confidence").textContent = Number.isFinite(Number(confidence)) ? `${Math.round(Number(confidence) * 100)}% confidence` : "Prediction ready";
  document.getElementById("forecast-result").innerHTML = `<div class="result-hero"><div><span class="result-label">Next one hour demand</span><strong class="result-value">${formatNumber(one)}</strong></div><span class="status-badge healthy">Active model</span></div><div class="result-grid"><div class="result-item"><span>Next 1 hour</span><strong>${formatNumber(one)} orders</strong></div><div class="result-item"><span>Next 3 hours</span><strong>${formatNumber(three)} orders</strong></div><div class="result-item"><span>Next 6 hours</span><strong>${formatNumber(six)} orders</strong></div></div>`;
  renderChart(result.historical_trend || result.history || [], [one, three, six]);
}
function renderChart(history, forecast) {
  const canvas = document.getElementById("forecast-chart"); if (!window.Chart) return;
  forecastChart?.destroy(); const historic = Array.isArray(history) ? history.map((point) => Number(point.demand ?? point.value ?? point)) : [];
  forecastChart = new Chart(canvas, { type:"line", data:{ labels:[...historic.map((_, index) => `History ${index + 1}`), "+1h", "+3h", "+6h"], datasets:[{ label:"Demand", data:[...historic, ...forecast], borderColor:"#2563eb", backgroundColor:"rgba(37,99,235,.12)", pointRadius:3, tension:.35, fill:true }] }, options:{ responsive:true, maintainAspectRatio:false, plugins:{ legend:{ display:false } }, scales:{ y:{ beginAtZero:true, grid:{ color:"rgba(100,116,139,.15)" } }, x:{ grid:{ display:false } } } } });
}
setDefaultTime(); loadZones();
