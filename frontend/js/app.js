/** Shared application-shell bootstrapper for all frontend pages. */

import { renderNavbar, initializeNavbar } from "../components/navbar.js";
import { renderSidebar } from "../components/sidebar.js";
import { initializeTheme } from "./utils.js";

/** Mount a page inside the shared sidebar/topbar shell. */
export function mountPage({ title, content }) {
  initializeTheme();
  const activePage = document.body.dataset.page || "dashboard";
  const root = document.getElementById("app");
  if (!root) throw new Error("Application root is missing.");
  root.innerHTML = `<div class="app-shell">${renderSidebar(activePage)}<main class="main">${renderNavbar(title)}<section class="content">${content}</section></main></div><div class="toast-container" id="toast-container" aria-live="polite"></div>`;
  initializeNavbar();
}
