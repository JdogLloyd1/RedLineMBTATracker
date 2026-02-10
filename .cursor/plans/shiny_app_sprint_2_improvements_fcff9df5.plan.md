---
name: Shiny App Sprint 2 Improvements
overview: "Plan code and documentation updates for the Shiny app: larger map, single Red Line trace plus optional other lines, train hover (ID, direction, destination, next station, time, delay) and direction arrow, wider resizable tables, auto-refresh UI, and a deep dive to fix over-filtered Departures/Arrivals tables (timezone and time-window logic)."
todos: []
isProject: false
---

# Shiny App Sprint 2 – Improvements Plan

## 1. Make the live map bigger

- In [Shiny App/app.py](Shiny App/app.py), in `map_widget()` where the Plotly figure is built, increase `height` in `fig.update_layout()` (currently `500`). Use a larger fixed value (e.g. `700` or `800`) or a CSS-like value if the widget supports it (e.g. `"80vh"` for viewport height). Prefer a fixed pixel value that works with `render_widget` (e.g. `700`).

---

## 2. Map layer options: Red Line once, add other lines for growth

**Problem:** Red Line appears many times because [parsers.py](Shiny App/api/parsers.py) returns one `(lons, lats)` per shape, and [app.py](Shiny App/app.py) adds one trace per shape, all named "Red Line". The MBTA `/shapes` endpoint returns many shapes per route (e.g. per direction or branch).

**Changes:**

- **Single Red Line trace:** In [api/parsers.py](Shiny App/api/parsers.py), add a function (e.g. `parse_route_shapes_merged(shapes_response)`) that returns a **single** geometry for the Red Line: merge all decoded polylines into one combined line (concatenate coordinates, or take the longest/first shape). Keep the existing `parse_red_line_shape` behavior available if needed, but use the merged result for the Red Line trace in the app so only **one** "Red Line" trace is drawn.
- **Other lines for growth:** In [api/mbta_client.py](Shiny App/api/mbta_client.py), add a function such as `fetch_shapes_for_routes(route_ids: list[str])` that fetches shapes for each route (e.g. `["Red", "Green-B", "Green-C", "Green-D", "Green-E", "Blue", "Orange", "Silver"]` or a configurable list). Return a dict mapping route_id to shapes response (or a single combined response if the API supports multiple routes in one call). In parsers, add a helper that returns one merged (lons, lats) per route so each line is one trace.
- **UI layer toggles:** In [app.py](Shiny App/app.py), add a small control (e.g. checkboxes or a multi-select) in the sidebar or above the map to "Show routes: Red (default on), Green, Blue, Orange, Silver (off by default)." Store selected route IDs in reactive state; when building the map, only add traces for selected routes. Fetch shapes for other lines once (or on first toggle) and cache in a reactive value.
- **Legend:** Use distinct colors per line (e.g. Red `#DA291C`, Green, Blue, Orange, Silver from MBTA branding). Set `name` per trace to the route label (e.g. "Red Line", "Green Line") so the legend shows one entry per line and is useful.

---

## 3. Train marker hover and direction arrow

**Hover content:** For each train marker, show: Train ID, direction of travel, final destination, expected time at next station, next station name, minutes behind schedule.

**Data:**

- **From vehicles response (already have):** vehicle_id, lat, lon, bearing, current stop (from included stop). Vehicles response uses `include=trip,stop`; from included **trip** we can get `headsign` (destination) and `direction_id` (direction).
- **Next station and time:** The current predictions call uses `filter[stop]=place-alfcl`, so we only get predictions at Alewife. To get "next station" and "expected time at next station" for every train, we need predictions at **all** Red Line stops for that route. Add a second API call: predictions with `filter[route]=Red` only (no `filter[stop]`), with `include=schedule,trip,stop,vehicle`. Then for each vehicle_id, find the prediction row(s) for that vehicle where the stop is not the current stop, and take the one with the smallest future `arrival_time` or `departure_time` — that gives next stop (from included stop name) and expected time. Minutes behind = (predicted time − scheduled time) in minutes from the same prediction row.

**Implementation:**

- In [api/mbta_client.py](Shiny App/api/mbta_client.py): add `fetch_predictions_all_stops()` (or similar) with `filter[route]=Red`, `include=schedule,trip,stop,vehicle` (no `filter[stop]`).
- In [api/parsers.py](Shiny App/api/parsers.py): add a function that builds a **vehicle enrichment** structure: for each vehicle from the vehicles response, attach destination and direction from trip; then using the "all stops" predictions response, for each vehicle_id find the next-stop prediction (soonest future time), and attach next_stop_name, next_stop_time (scheduled and predicted), and minutes_behind. Update `parse_vehicles_for_map` (or add a new function used by the app) to return list of dicts with: lat, lon, bearing, vehicle_id, direction (e.g. "Northbound"/"Southbound" from direction_id), destination, next_stop_name, next_stop_time_expected, minutes_behind. Handle missing data (e.g. no prediction for next stop) with "—" or "Unknown".
- In [app.py](Shiny App/app.py) map: use this enriched list; for the train scatter trace set `hovertemplate` (or `customdata` + `hovertemplate`) to show Train ID, direction, destination, next station, expected time, minutes behind. Use a single string for each marker so Plotly shows it on hover.
- **Direction arrow:** Use Plotly’s ability to rotate a symbol by angle. For `go.Scattermapbox` with `mode="markers"`, set `marker=dict(symbol="triangle-up", size=..., angle=bearing)` if supported; otherwise use a unicode arrow or a second trace with arrow-like symbols. If `angle` is not available for mapbox markers, use a small line segment from (lat, lon) in the direction of bearing (e.g. short segment from position to position + offset in bearing direction) as a separate trace so each train has a direction indicator.

---

## 4. Tables: wider and adjustable columns

- In [app.py](Shiny App/app.py), for each `render.DataGrid` call, set `width` to a full-width value (e.g. `"100%"` or a large pixel value so tables use the full content width). Increase `height` if desired (e.g. 400px) so tables feel wider and less cramped.
- Shiny for Python’s DataGrid may not expose per-column resizing in the current API. Check the latest [Data Grid docs](https://shiny.posit.co/py/components/outputs/data-grid/) for parameters like `resizable=True` or column options. If supported, enable column resizing; if not, document "columns resizable" as a future improvement and ensure tables are at least full width and readable.

---

## 5. Auto-refresh (interval in minutes)

- **UI:** In the sidebar in [app.py](Shiny App/app.py), add an input for refresh interval: e.g. `ui.input_numeric("refresh_interval_min", "Auto-refresh (minutes)", value=0, min=0, step=1)` or a select with options "Off", "1", "2", "5", "10" minutes. Treat 0 or "Off" as no auto-refresh.
- **Logic:** In the server, keep the existing `@reactive.event(input.refresh)` effect that runs the fetch/parse and updates reactive values. Add a second reactive effect that:
  - Depends on `input.refresh_interval_min` (and optionally `input.refresh` so a manual refresh resets the timer).
  - If interval &gt; 0: call the same fetch/parse logic (extract into a helper to avoid duplication), then call `reactive.invalidate_later(interval_seconds)` with `interval_seconds = input.refresh_interval_min() * 60` to re-run the effect after that delay. When the effect re-runs, it fetches again and schedules the next run, creating a loop.
  - If interval is 0: do not call `invalidate_later`, so auto-refresh stops.
- Ensure only one "refresh" flow runs (shared helper for fetch + parse + setting reactive values). Avoid double-fetch when user clicks "Run API query" while auto-refresh is on; both can call the same helper.

---

## 6. Deep dive: Departures and Arrivals tables over-filtered

**Observed:** Earliest data in the tables is "tomorrow morning" even though trains are running now; the live map shows trains correctly. So the issue is in how we build or filter the tables, not the vehicles API.

**Hypotheses and actions:**

1. **Timezone handling**
  Prediction and schedule times from the MBTA may be in Eastern time or UTC. If the API returns naive strings (no "Z" or offset), `datetime.fromisoformat` gives a naive datetime; `pd.to_datetime(..., utc=True)` then treats naive as **local** to the server. If the server is in UTC, that’s wrong for Eastern.  
  - **Action:** In [api/parsers.py](Shiny App/api/parsers.py), in `_parse_iso`, ensure all datetimes are normalized to UTC. If the string has no timezone (no "Z", no "+00:00", no "-05:00" etc.), assume **America/New_York** (MBTA’s timezone), localize, then convert to UTC before returning. Use a consistent "now" in UTC for all comparisons (`datetime.now(timezone.utc)`).
2. **Departures: no time filter**
  Departures are built from predictions with `direction_id == 0` at Alewife. There is no explicit time window in the current code, so we should show all such predictions. Verify we are not inadvertently dropping rows (e.g. only including rows that have a non-null schedule). If we require schedule for display, still include rows that have only prediction times (scheduled can be "—" or null). Sort departures by scheduled or estimated departure time ascending so the soonest is first.
3. **Arrivals: time window**
  Near-term (10 min) and future (60 min) arrivals filter with `arrival_dt >= now` and `arrival_dt <= now + delta`. If `now` is wrong (e.g. server local instead of UTC) or if `arrival_time_dt` is wrong (e.g. naive Eastern interpreted as UTC), the window could exclude "now" and show only tomorrow.  
  - **Action:** Ensure `now = datetime.now(timezone.utc)` and that `arrival_time_dt` is always timezone-aware UTC after parsing. Re-check `pd.to_datetime(raw["arrival_time_dt"], utc=True)` when some values might be timezone-aware already (should still work).
4. **Prediction resource shape**
  With `filter[stop]=place-alfcl`, each prediction is for Alewife. Confirm we are not filtering by another field (e.g. dropping when `schedule_id` is None). Include all direction_id==0 (departures) and direction_id==1 (arrivals) rows that have any of pred_dep, pred_arr, sched_dep, sched_arr.
5. **Debugging**
  Add a short comment or optional debug block in parsers: log a sample of raw `departure_time`/`arrival_time` from the API and the parsed UTC values, and the value of `now` used for filtering. This will help confirm timezone and window logic without changing behavior in production.

**Summary of code changes:**

- [api/parsers.py](Shiny App/api/parsers.py): (a) Normalize all parsed times to UTC in `_parse_iso` (treat naive as America/New_York). (b) For departures, include every direction_id==0 prediction that has any time, sort by departure time. (c) For arrivals, keep 10/60 min windows but ensure both `now` and `arrival_time_dt` are UTC. (d) Optionally log sample raw/parsed times and `now` for verification.

---

## 7. Documentation updates

- [Shiny App/README.md](Shiny App/README.md): Briefly mention the new behaviors: larger map, single Red Line trace with optional other lines, train hover (ID, direction, destination, next station, time, delay) and direction arrow, wider/adjustable tables, auto-refresh (minutes), and the timezone fix for Departures/Arrivals. Keep installation and run instructions unchanged unless needed.

---

## Implementation order (suggested)

1. **Tables over-filtering** (parsers timezone + logic) so data appears correctly.
2. **Map size** and **Red Line once + other lines** (parsers + client + app map).
3. **Train hover + arrow** (new predictions call, parsers enrichment, app map hover/arrow).
4. **Tables width/resize** (app.py DataGrid).
5. **Auto-refresh** (sidebar input + reactive effect + shared fetch helper).
6. **README** updates.

This order fixes data first, then improves map and tables, then adds automation and docs.