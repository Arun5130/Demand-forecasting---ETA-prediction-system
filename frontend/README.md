# Delivery ML frontend

This is a framework-free dashboard implemented with HTML5, CSS3, and ECMAScript modules.
It has no package manager, bundler, or build step.

## Run

Start the FastAPI service on the same origin as the frontend. The backend will serve this
directory as static files in the API module. During standalone development, use any static
HTTP server and set `api-base-url` in each page's HTML `<meta>` tag to the FastAPI origin.

The UI calls these API contracts:

- `GET /health`, `GET /models`, `GET /system-status`, `GET /prediction-history`, and `GET /orders`
- `POST /forecast` with `zone_id` and `prediction_at`
- `POST /eta` with delivery context features

`GET /orders?dataset=<source>` supports the five Data Explorer tabs. Every page treats
unavailable services as an explicit error state; no fabricated operational data is displayed.

Chart.js is loaded directly from its CDN only on pages that visualize charts.
