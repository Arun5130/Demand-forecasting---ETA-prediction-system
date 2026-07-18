/** Prediction-history page displaying inference audit records from FastAPI. */

import { api } from "./api.js";
import { mountPage } from "./app.js";
import { setApiIndicator } from "../components/navbar.js";
import { extractRecords, formatDate, formatDuration, formatNumber, renderTable, showToast } from "./utils.js";

mountPage({ title:"Prediction History", content:`<div class="page-heading"><div><h1>Prediction history</h1><p>Auditable inference events, model versions, and response times.</p></div></div><article class="card"><div class="card-body"><div class="toolbar"><input class="search" id="history-search" type="search" placeholder="Filter by zone, type, or model version"><button class="button" id="history-refresh" type="button">Refresh</button></div></div><div id="history-table"><div class="loading"><span class="spinner"></span></div></div></article>` });
let records = [];
document.getElementById("history-search").addEventListener("input", render);
document.getElementById("history-refresh").addEventListener("click", loadHistory);
async function loadHistory() { document.getElementById("history-table").innerHTML = '<div class="loading"><span class="spinner"></span></div>'; try { records = extractRecords(await api.history({ limit:100 })); setApiIndicator(true, "API connected"); render(); } catch (error) { setApiIndicator(false, "API unavailable"); document.getElementById("history-table").innerHTML = '<div class="empty-state"><strong>Prediction history unavailable</strong><span>Start the API to retrieve inference logs.</span></div>'; showToast(error.message); } }
function render() { const query = document.getElementById("history-search").value.toLowerCase(); const filtered = records.filter((record) => !query || [record.zone_id, record.prediction_type, record.model_version].some((value) => String(value ?? "").toLowerCase().includes(query))); document.getElementById("history-table").innerHTML = renderTable(filtered, [{ label:"Timestamp", key:"created_at", format:(value, row) => formatDate(value || row.timestamp) }, { label:"Type", key:"prediction_type" }, { label:"Zone", key:"zone_id", format:(value, row) => value || row.zone_name || "—" }, { label:"ETA", key:"eta_seconds", format:(value) => formatDuration(value) }, { label:"Demand", key:"demand", format:(value, row) => formatNumber(value ?? row.predicted_demand) }, { label:"Model version", key:"model_version", format:(value) => `<span class="mono">${value || "—"}</span>` }, { label:"Response time", key:"response_time_ms", format:(value) => Number.isFinite(Number(value)) ? `${formatNumber(value)} ms` : "—" }]); }
loadHistory();
