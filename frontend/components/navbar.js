/** Top navigation component with theme and API-status controls. */

import { getTheme, setTheme } from "../js/utils.js";

/** Render the top bar for a page title. */
export function renderNavbar(title) {
  return `<header class="topbar"><h2 class="topbar-title">${title}</h2><div class="topbar-actions"><div class="api-indicator" title="Backend connectivity"><span class="dot" id="api-dot"></span><span id="api-label">Checking API</span></div><button class="icon-button" id="theme-toggle" type="button" aria-label="Toggle color theme">${getTheme() === "dark" ? "☀" : "◐"}</button></div></header>`;
}

/** Activate the colour-theme button after the shell is mounted. */
export function initializeNavbar() {
  document.getElementById("theme-toggle")?.addEventListener("click", () => {
    const theme = getTheme() === "dark" ? "light" : "dark";
    setTheme(theme);
    const button = document.getElementById("theme-toggle");
    if (button) button.textContent = theme === "dark" ? "☀" : "◐";
  });
}

/** Update the persistent backend connectivity indicator. */
export function setApiIndicator(healthy, label) {
  const dot = document.getElementById("api-dot");
  const text = document.getElementById("api-label");
  if (dot) dot.className = `dot ${healthy ? "healthy" : "failed"}`;
  if (text) text.textContent = label;
}
