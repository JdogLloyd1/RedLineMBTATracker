# Cursor-oriented README: MBTA Red Line Tracker V2 (Shiny App)

Context for AI-assisted editing. This folder contains the Shiny for Python app that extends V1 with Ollama Cloud AI Commuter Report, station dropdowns, split layout, and .docx vaulting. Use with [`.cursor/rules/`](../.cursor/rules/).

## Table of Contents

- [Project summary](#project-summary)
- [Project structure](#project-structure)
- [Tech stack & environment](#tech-stack--environment)
- [Entry points](#entry-points)
- [Conventions & patterns](#conventions--patterns)
- [APIs and libraries](#apis-and-libraries)
- [Reference links](#reference-links)

## Project summary

Shiny App V2 = V1 (alerts, departures, arrivals, live map, auto-refresh) + AI Commuter Report via Ollama Cloud. Station dropdowns (dep default Alewife, arr default Central) apply to API refresh and AI report. Split layout (left: tabs; right: report). Report saved as `MBTA Red Line Commuter Report YYYY.MM.DD_HHMM.docx` in `reports/`. Token-optimized data formatting; revised prompt for consistent output. Rules: [`.cursor/rules/coding_style.mdc`](../.cursor/rules/coding_style.mdc), [`.cursor/rules/cursor_readme_format.mdc`](../.cursor/rules/cursor_readme_format.mdc).

## Project structure

Paths relative to **Shiny App V2** unless noted.

- **`app.py`** — Main entry. UI: sidebar (Run API query, station dropdowns, Run AI Commuter Report, auto-refresh, map height, panel ratio, map layers), split layout (`split_layout` render: left tabs, right report). Server: `_do_refresh()` uses `input.dep_station()` for predictions; `_run_ai_report()` fetches at dep/arr stops, builds dataframes, `format_data_for_ollama_compact`, `get_report_prompt(dep_name, arr_name)`, `query_ollama_cloud`, `write_report_docx`. Run: `shiny run app.py`.
- **`api/`** — MBTA client and parsers (from V1).
  - **`api/mbta_client.py`** — `fetch_alerts()`, `fetch_predictions(stop_id)`, `fetch_predictions_at_stop(stop_id)`, `fetch_predictions_all_stops()`, `fetch_vehicles()`, `fetch_shapes()`, `fetch_shapes_for_routes()`.
  - **`api/parsers.py`** — `parse_alerts`, `parse_departures`, `parse_near_term_arrivals`, `parse_future_arrivals`, `parse_vehicles_for_map`, `parse_vehicles_for_map_enriched`, `parse_red_line_shape`, etc.
- **`ai_reporter/`** — Ollama integration.
  - **`ai_reporter/reporter.py`** — `build_alerts_df`, `build_predictions_df`, `build_vehicles_df`, `format_data_for_ollama_compact`, `get_report_prompt(dep_name, arr_name)`, `query_ollama_cloud`, `write_report_docx`. Prompt is parameterized by station names. .docx naming: `MBTA Red Line Commuter Report YYYY.MM.DD_HHMM.docx`.
- **`ui/layout.py`** — `RED_LINE_STOPS`, `make_station_dropdowns()`, `get_station_name(stop_id)`.
- **`Dockerfile`** — Python 3.11-slim, uvicorn on 8080, non-root user. Build from `Shiny App V2` dir.
- **`.do/app.yaml`** — Optional DigitalOcean App Platform spec. Set `MBTA_API_KEY` and `OLLAMA_API_KEY` as secrets.

## Tech stack & environment

- **Python**: 3.10+. `pip install -r requirements.txt` from `Shiny App V2/`.
- **Env**: `.env` with `MBTA_API_KEY`, `OLLAMA_API_KEY`. Loaded from app dir or repo root.

## Entry points

- **Run**: `shiny run app.py` from `Shiny App V2/`.
- **Refresh**: `_do_refresh()` uses `input.dep_station()` for predictions call.
- **AI Report**: `_run_ai_report()` on button click; fetches at dep/arr, builds dfs, formats compact, prompts Ollama, writes .docx.

## Conventions & patterns

- **Style**: [`.cursor/rules/coding_style.mdc`](../.cursor/rules/coding_style.mdc).
- **Layout**: API in `api/`, AI logic in `ai_reporter/`, UI helpers in `ui/`.
- **Stations**: `RED_LINE_STOPS` in `ui/layout.py`; default dep=place-alfcl (Alewife), arr=place-cntsq (Central).

## APIs and libraries

- **MBTA V3 API**: [Swagger](https://api-v3.mbta.com/docs/swagger/index.html).
- **Ollama Cloud**: [Ollama](https://ollama.com) for chat API.
- **Shiny for Python**: [Install & run](https://shiny.posit.co/py/docs/install-create-run.html).
- **python-docx**: [python-docx](https://python-docx.readthedocs.io/).

## Reference links

| Resource | URL |
|----------|-----|
| MBTA V3 API | https://api-v3.mbta.com/docs/swagger/index.html |
| MBTA API key | https://api-v3.mbta.com/portal |
| Ollama | https://ollama.com |
| Shiny for Python | https://shiny.posit.co/py/docs/install-create-run.html |
| python-docx | https://python-docx.readthedocs.io/ |
| Coding style | [.cursor/rules/coding_style.mdc](../.cursor/rules/coding_style.mdc) |
