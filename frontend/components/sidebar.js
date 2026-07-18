/** Sidebar navigation component shared by all static application pages. */

const navigation = [
  ["dashboard", "index.html", "▦", "Dashboard"],
  ["forecast", "forecast.html", "⌁", "Demand Forecast"],
  ["eta", "eta.html", "◷", "ETA Prediction"],
  ["models", "models.html", "◇", "Model Management"],
  ["data", "data.html", "▤", "Data Explorer"],
  ["history", "history.html", "◫", "Prediction History"],
  ["status", "status.html", "●", "System Status"],
];

/** Return accessible navigation markup for the selected page. */
export function renderSidebar(activePage) {
  const links = navigation.map(([id, href, icon, label]) => `
    <a class="nav-item ${id === activePage ? "active" : ""}" href="${href}" ${id === activePage ? 'aria-current="page"' : ""}>
      <span class="nav-icon" aria-hidden="true">${icon}</span><span>${label}</span>
    </a>`).join("");
  return `<aside class="sidebar"><a class="brand" href="index.html"><span class="brand-mark">D</span><span>Delivery ML</span></a><nav aria-label="Primary"><div class="nav-label">Workspace</div>${links}</nav><div class="sidebar-footer">Production console<br>v0.1.0</div></aside>`;
}
