/** Reusable accessible loading and empty-state fragments. */

/** Return a centered progress indicator. */
export function loadingMarkup(label = "Loading") {
  return `<div class="loading" role="status" aria-live="polite"><span class="spinner" aria-hidden="true"></span><span class="sr-only">${label}</span></div>`;
}

/** Return a descriptive empty state without inventing application data. */
export function emptyMarkup(title, detail) {
  return `<div class="empty-state"><strong>${title}</strong><span>${detail}</span></div>`;
}
