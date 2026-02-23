# Cursor-oriented README: Shiny App V3 (MBTA Red Line Tracker)

Context for AI-assisted editing and code generation. This folder contains the Shiny for Python app (V3) that queries the MBTA V3 API for Red Line data, displays tables and a live map for a selected departure station, and generates an AI Commuter Report via Ollama Cloud from cached API data. Use this file with [`.cursor/rules/`](../.cursor/rules/) when generating or modifying code here.

## Table of Contents

- [Project summary](#project-summary)
- [Project structure](#project-structure)
- [Tech stack & environment](#tech-stack--environment)
- [Entry points](#entry-points)
- [Conventions & patterns](#conventions--patterns)
- [APIs and libraries](#apis-and-libraries)
- [Key flows](#key-flows)
- [Reference links](#reference-links)

## Project summary

Single Shiny for Python app in `Shiny App V3/`: fetches MBTA V3 API (alerts, predictions at dep and arr stops, vehicles, shapes, predictions all stops), parses with `api/parsers.py`, and renders tables + Plotly map on the **left** and an **AI Commuter Report** (Markdown with grid-lined tables) on the **right**. One "Run API query" fetches all data for both dashboard and reporter; "Run AI Commuter Report" uses cached responses — but if the user has changed dep/arr since the last refresh, the app runs a refresh for the current stations first, then invokes the report task so the report always matches the selected stations. **Station dropdowns** use `RED_LINE_STOPS_GROUPED` (optgroups: Alewife→JFK/UMass, Ashmont branch, Braintree branch). Layout uses viewport-relative heights (e.g. 38vh for DataGrids, min-heights for split/report). Env loaded from **repo root `.env` first**, then app dir. Rules: [`.cursor/rules/coding_style.mdc`](../.cursor/rules/coding_style.mdc), [cursor_readme_format.mdc](../.cursor/rules/cursor_readme_format.mdc), [developer_readme_format.mdc](../.cursor/rules/developer_readme_format.mdc).

## Project structure

Paths below are relative to **Shiny App V3** unless noted.

- **`app.py`** — Main entry. UI: sidebar (Run API query, grouped dep/arr dropdowns, Run AI Commuter Report, Save as .docx, panel ratio slider, map layers, last API call), split layout (`split_layout`: left = tabs with viewport-relative heights, right = report panel). Server: `_do_refresh()` uses `input.dep_station()` and `input.arr_station()`; fetches alerts, `fetch_predictions_at_stop(dep)`, `fetch_predictions_at_stop(arr)`, vehicles, shapes, predictions_all_stops; caches raw responses in `api_cache` and stores dep/arr stop IDs in `api_cache_stations`. AI report: `@reactive.extended_task` `ai_report_task(dep_name, arr_name, cache)` — **cache is read in the button effect and passed in** so the task never touches reactive state (avoids "no current reactive context"). Task runs `_run_ai_report_sync(dep_name, arr_name, cache)` via `run_in_executor`. Before invoking, if `api_cache_stations()` is None or differs from current dep/arr, `_do_refresh()` is called first. `_apply_ai_report_result` effect reads `ai_report_task.result()` and sets `ai_report_text` / `ai_report_error`. Run: `shiny run app.py` from this directory.
- **`api/mbta_client.py`** — Loads `.env` from repo root first then app dir. `fetch_alerts()`, `fetch_predictions_at_stop(stop_id)`, `fetch_predictions_all_stops()`, `fetch_vehicles()`, `fetch_shapes(route_id)`, `fetch_shapes_for_routes(route_ids)`.
- **`api/parsers.py`** — Pure functions: `parse_alerts`, `parse_departures`, `parse_near_term_arrivals`, `parse_future_arrivals`, `parse_vehicles_for_map`, `parse_vehicles_for_map_enriched`, `parse_red_line_shape`. Display datetimes in Eastern in `app.py`.
- **`ai_reporter/reporter.py`** — Loads `.env` (repo root first). `build_alerts_df`, `build_predictions_df`, `build_vehicles_df` from raw API responses; `format_data_for_ollama_compact`; `get_report_prompt(dep_name, arr_name)`; `query_ollama_cloud(user_content)`; `write_report_docx(report_text, output_dir)` — filename `MBTA Red Line Commuter Report YYYY.MM.DD_HHMM.docx` (Eastern).
- **`ui/layout.py`** — `RED_LINE_STOPS`, `RED_LINE_STOPS_GROUPED` (dict of dicts for optgroup dropdowns), `make_station_dropdowns()`, `get_station_name(stop_id)`.
- **`requirements.txt`** — shiny, pandas, requests, python-dotenv, plotly, shinywidgets, polyline, python-docx.
- **`.env.example`** — `MBTA_API_KEY`, `OLLAMA_API_KEY`. Copy to `.env` (repo root or app dir).
- **`Dockerfile`**, **`.do/app.yaml`** — Deploy; expose 8000, env secrets for both keys.
- **`.cursor/rules/`** (repo root) — Apply when editing `.py` or `README*.md`.

## Tech stack & environment

- **Python**: 3.9+. Install: `pip install -r requirements.txt` from `Shiny App V3/`.
- **Shiny for Python**: UI and server in `app.py`; reactive values and effects; `reactive.extended_task` + `run_in_executor` for non-blocking AI report; **cache passed into task** (no reactive reads inside the thread).
- **Map**: Plotly `go.Scattermapbox` via shinywidgets; route geometries from MBTA `/shapes`.
- **Report UI**: Markdown in a card; CSS for `.commuter-report-body table` adds borders/grid lines.
- **Environment**: `.env` from repo root first, then `Shiny App V3/.env`. Variables: `MBTA_API_KEY`, `OLLAMA_API_KEY`.

## Entry points

- **Run app**: From `Shiny App V3/`, run `shiny run app.py` (default port 8000).
- **Run API query**: User clicks button; `_do_refresh()` runs with current `input.dep_station()` and `input.arr_station()`; updates tables, map, `api_cache`, and `api_cache_stations`.
- **Run AI Commuter Report**: If `api_cache_stations()` is None or ≠ current (dep_id, arr_id), calls `_do_refresh()` first. Then invokes `ai_report_task(dep_name, arr_name, api_cache())`; task runs `_run_ai_report_sync` in thread pool; result applied in `_apply_ai_report_result` to `ai_report_text` / `ai_report_error`.
- **Save as .docx**: Reads `ai_report_text()`, calls `write_report_docx(..., output_dir=reports_dir)`, sets `ai_report_docx_saved` and shows notification.

## Conventions & patterns

- **Style**: [`.cursor/rules/coding_style.mdc`](../.cursor/rules/coding_style.mdc) (section headers, comments, pandas, naming).
- **Layout**: API in `api/`, AI report in `ai_reporter/`, UI helpers in `ui/`; app orchestrates in `app.py`.
- **Cache**: `api_cache` holds last API responses; `api_cache_stations` holds `(dep_stop_id, arr_stop_id)` for that cache. Reporter receives cache as an argument (never reads reactive state in the thread).
- **Time**: Store/filter in UTC; display in Eastern. Docx filename uses Eastern (`ZoneInfo("America/New_York")`).

## APIs and libraries

- **MBTA V3 API**: [Swagger](https://api-v3.mbta.com/docs/swagger/index.html). Endpoints: `/alerts`, `/predictions`, `/vehicles`, `/shapes`. Used in [`api/mbta_client.py`](api/mbta_client.py).
- **Ollama Cloud**: Chat API for AI report; see [`ai_reporter/reporter.py`](ai_reporter/reporter.py) (`OLLAMA_CHAT_URL`, `query_ollama_cloud`).
- **Shiny for Python**: [Install & run](https://shiny.posit.co/py/docs/install-create-run.html), [ExtendedTask (non-blocking)](https://shiny.posit.co/py/docs/nonblocking.html).
- **Plotly**, **shinywidgets**, **python-docx**, **Requests**, **python-dotenv**, **polyline**.

## Key flows

- **Refresh**: `_do_refresh()` → `fetch_alerts()`, `fetch_predictions_at_stop(dep)`, `fetch_predictions_at_stop(arr)`, `fetch_vehicles()`, `fetch_shapes()`, parse and set table/map state, then `fetch_predictions_all_stops()` and enrich map; set `api_cache` and `api_cache_stations`.
- **AI report**: If cache stations ≠ current dep/arr → `_do_refresh()`. Then `ai_report_task.invoke(dep_name, arr_name, api_cache())` → thread runs `_run_ai_report_sync(dep_name, arr_name, cache)` (build DFs from `cache`, format for Ollama, get prompt, `query_ollama_cloud`) → `_apply_ai_report_result` reads `ai_report_task.result()` and sets `ai_report_text` / `ai_report_error`.

## Reference links

| Resource | URL |
|----------|-----|
| MBTA V3 API | https://api-v3.mbta.com/docs/swagger/index.html |
| MBTA API key | https://api-v3.mbta.com/portal |
| Ollama | https://ollama.com |
| Shiny for Python | https://shiny.posit.co/py/docs/install-create-run.html |
| Shiny non-blocking | https://shiny.posit.co/py/docs/nonblocking.html |
| Plotly Python | https://plotly.com/python/ |
| shinywidgets | https://shiny.posit.co/py/packages/shinywidgets/ |
| Coding style | [.cursor/rules/coding_style.mdc](../.cursor/rules/coding_style.mdc) |
