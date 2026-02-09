# Cursor-oriented README: MBTA Red Line Tracker (Shiny App)

Context for AI-assisted editing and code generation. This folder contains the runnable Shiny for Python app that queries the MBTA V3 API and displays Red Line alerts, Alewife departures/arrivals, and a live map (all branches per route, Eastern time, train markers with direction). Use this file together with [`.cursor/rules/`](../.cursor/rules/) when generating or modifying code here.

## Table of Contents

- [Project summary](#project-summary)
- [Project structure](#project-structure)
- [Tech stack & environment](#tech-stack--environment)
- [Entry points](#entry-points)
- [Conventions & patterns](#conventions--patterns)
- [APIs and libraries](#apis-and-libraries)
- [Code example: refresh and map data](#code-example-refresh-and-map-data)
- [Reference links](#reference-links)

## Project summary

Single Shiny for Python app in `Shiny App/`: fetches MBTA V3 API (alerts, predictions, vehicles, shapes), parses with pure functions in `api/parsers.py`, and renders tables (alerts, departures, near-term/future arrivals) and a Plotly map (route lines by branch, train positions with direction). All displayed datetimes are Eastern. Map layers are toggled via sidebar checkboxes only (no route traces in plot legend). Auto-refresh supports fractional minutes (min 0.5 to avoid freezing). Rules: [`.cursor/rules/coding_style.mdc`](../.cursor/rules/coding_style.mdc), [`.cursor/rules/cursor_readme_format.mdc`](../.cursor/rules/cursor_readme_format.mdc), [`.cursor/rules/developer_readme_format.mdc`](../.cursor/rules/developer_readme_format.mdc).

## Project structure

Paths below are relative to the **Shiny App** folder unless noted.

- **`app.py`** — Main entry point. UI (sidebar: Run API query, auto-refresh minutes, last API call, map layer checkboxes), tabs (alerts, departures, near-term, future, live map). Server: reactive state (`df_alerts`, `df_departures`, `df_near_term`, `df_future`, `vehicles_map`, `shapes_by_route`, `last_api_call_time`, `skip_next_timer_refresh`), `_do_refresh()`, `_auto_refresh_timer()` (min interval 0.5 min), `_fetch_extra_map_layers()` (per-route shapes as list of geometries). Map: route lines with `showlegend=False`; trains = circle markers + direction line segment, `legendgroup="Trains"`. Run: `shiny run app.py` from this directory.
- **`api/`** — API client and parsers.
  - **`api/mbta_client.py`** — Loads `.env`; `fetch_alerts()`, `fetch_predictions()`, `fetch_predictions_all_stops()`, `fetch_vehicles()`, `fetch_shapes(route_id)`, `fetch_shapes_for_routes(route_ids)`. Returns JSON or dict with `error` and `message`.
  - **`api/parsers.py`** — Pure functions: `parse_alerts`, `parse_departures`, `parse_near_term_arrivals`, `parse_future_arrivals`, `parse_vehicles_for_map`, `parse_vehicles_for_map_enriched` (hover + Eastern next_stop_time), `parse_red_line_shape` (returns list of `(lons, lats)` per branch), `parse_route_shapes_merged`, `parse_merged_shapes_by_route`. Datetimes normalized to UTC (naive → America/New_York); display conversion to Eastern is done in `app.py` for tables and in parsers for hover time.
- **`api/__init__.py`** — Re-exports client and parser functions; `__all__` lists them.
- **`requirements.txt`** — shiny, pandas, requests, python-dotenv, plotly, shinywidgets, polyline.
- **`.env.example`** — Template for `MBTA_API_KEY`; copy to `.env` (do not commit).
- **`README.md`** — Developer/user doc (overview, install, run, usage).
- **`.cursor/rules/`** (repo root) — `coding_style.mdc` (Python/R), `cursor_readme_format.mdc`, `developer_readme_format.mdc`. Apply when editing `.py` or `README*.md`.

## Tech stack & environment

- **Python**: 3.9+. Install deps: `pip install -r requirements.txt` from `Shiny App/`.
- **Shiny for Python**: UI and server in `app.py`; reactive values and effects; `reactive.invalidate_later(seconds)` for auto-refresh.
- **Map**: Plotly `go.Scattermapbox` via shinywidgets; route geometries from MBTA `/shapes` (polyline decode in parsers).
- **Environment**: Copy `.env.example` to `.env`; set `MBTA_API_KEY`. No secrets in README or code.

## Entry points

- **Run app**: From `Shiny App/`, run `shiny run app.py` (default port 8000). Optional: `shiny run app.py --reload --launch-browser`.
- **Refresh data**: User clicks "Run API query" or auto-refresh timer fires (interval ≥ 0.5 min). `_do_refresh()` runs; first four API calls update tables and base map; then predictions-all-stops and map enrichment.

## Conventions & patterns

- **Style**: Follow [`.cursor/rules/coding_style.mdc`](../.cursor/rules/coding_style.mdc) for Python (section headers with `# 0. Setup ##`, comments, pandas, variable naming).
- **Layout**: API and parsing in `api/`; app UI and reactivity in `app.py`. Parsers are pure (no side effects).
- **Map**: `shapes_by_route` is `dict[route_name, list of (lons, lats)]`. Red set on initial refresh via `parse_red_line_shape(shapes_resp)`; Green/Blue/Orange/Silver set in `_fetch_extra_map_layers()` per branch with `fetch_shapes(rid)` and `parse_red_line_shape(resp)`. Route traces use `showlegend=False`. Train icon: one circle trace (hover) + one line trace (direction), both `legendgroup="Trains"`.
- **Time**: Store and filter in UTC; display in Eastern (`ZoneInfo("America/New_York")`) in tables and hover.

## APIs and libraries

- **MBTA V3 API**: [Swagger](https://api-v3.mbta.com/docs/swagger/index.html). Endpoints: `/alerts`, `/predictions`, `/vehicles`, `/shapes`. Used in [`api/mbta_client.py`](api/mbta_client.py).
- **Shiny for Python**: [Install & run](https://shiny.posit.co/py/docs/install-create-run.html), [Layouts](https://shiny.posit.co/py/layouts/).
- **Plotly**: [Plotly Python](https://plotly.com/python/); [shinywidgets](https://shiny.posit.co/py/packages/shinywidgets/) for `output_widget` / `render_widget`.
- **Python**: [Requests](https://requests.readthedocs.io/en/latest/), pandas, python-dotenv, polyline (decode encoded polyline from shapes).

## Code example: refresh and map data

Refresh runs shared logic and updates reactive state; map uses cached shapes and vehicle list:

```python
# _do_refresh() in app.py: after main API calls, set last_api_call_time, then fetch predictions_all_stops and enrich vehicles_map
last_api_call_time.set(datetime.now(EASTERN))
# ...
vehicles_map.set(parse_vehicles_for_map_enriched(vehicles_response, predictions_all_stops, ...))

# map_widget: route traces from shapes_by_route(); each route has list of (lons, lats)
for name in selected:
    geoms = cache[name]
    if not isinstance(geoms, list):
        geoms = [geoms]
    for lons, lats in geoms:
        fig.add_trace(go.Scattermapbox(..., showlegend=False))
```

See [`app.py`](app.py) for full `_do_refresh()` and `map_widget`; [`api/parsers.py`](api/parsers.py) for `parse_red_line_shape` and `parse_vehicles_for_map_enriched`.

## Reference links

| Resource | URL |
|----------|-----|
| MBTA V3 API | https://api-v3.mbta.com/docs/swagger/index.html |
| MBTA API key | https://api-v3.mbta.com/portal |
| Shiny for Python | https://shiny.posit.co/py/docs/install-create-run.html |
| Plotly Python | https://plotly.com/python/ |
| shinywidgets | https://shiny.posit.co/py/packages/shinywidgets/ |
| Requests | https://requests.readthedocs.io/en/latest/ |
| Coding style (rules) | [.cursor/rules/coding_style.mdc](../.cursor/rules/coding_style.mdc) |
