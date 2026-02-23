# app.py
# MBTA Red Line Tracker V2 – Shiny for Python with AI Commuter Report
# Run: shiny run app.py (from Shiny App V2 directory)

# 0. Setup #################################################################

import asyncio
import concurrent.futures
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

# #region agent log
def _dbg_log(location: str, message: str, data: dict, hypothesis_id: str = ""):
    try:
        log_path = Path(__file__).resolve().parent.parent / "debug-ce9241.log"
        payload = {"sessionId": "ce9241", "location": location, "message": message, "data": data, "timestamp": int(datetime.now(EASTERN).timestamp() * 1000)}
        if hypothesis_id:
            payload["hypothesisId"] = hypothesis_id
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")
    except Exception:
        pass
# #endregion

from shiny import App, reactive, render, ui
import pandas as pd
import plotly.graph_objects as go
from shinywidgets import output_widget, render_widget

from math import radians, cos, sin

from api.mbta_client import (
    fetch_alerts,
    fetch_predictions,
    fetch_predictions_all_stops,
    fetch_vehicles,
    fetch_shapes,
    fetch_predictions_at_stop,
)
from api.parsers import (
    parse_alerts,
    parse_departures,
    parse_near_term_arrivals,
    parse_future_arrivals,
    parse_vehicles_for_map,
    parse_vehicles_for_map_enriched,
    parse_red_line_shape,
)
from ai_reporter.reporter import (
    build_alerts_df,
    build_predictions_df,
    build_vehicles_df,
    format_data_for_ollama_compact,
    get_report_prompt,
    query_ollama_cloud,
    write_report_docx,
)
from ui.layout import get_station_name, make_station_dropdowns

# Map layer choices
MAP_ROUTE_IDS = {
    "Red": ["Red"],
    "Green": ["Green-B", "Green-C", "Green-D", "Green-E"],
    "Blue": ["Blue"],
    "Orange": ["Orange"],
    "Silver": ["Silver"],
}
MAP_COLORS = {
    "Red": "#DA291C",
    "Green": "#00843D",
    "Blue": "#003DA5",
    "Orange": "#ED8B00",
    "Silver": "#7C8793",
}

# Thread pool for running sync I/O (API calls) in background
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)

# 1. Reactive state ########################################################

api_error = reactive.value(None)
df_alerts = reactive.value(pd.DataFrame())
df_departures = reactive.value(pd.DataFrame())
df_near_term = reactive.value(pd.DataFrame())
df_future = reactive.value(pd.DataFrame())
vehicles_map = reactive.value([])
shapes_by_route = reactive.value({})
last_api_call_time = reactive.value(None)
skip_next_timer_refresh = reactive.value(False)
# AI report: text, error, last saved docx filename
ai_report_text = reactive.value("")
ai_report_error = reactive.value("")
ai_report_docx_saved = reactive.value(None)

MIN_AUTO_REFRESH_MINUTES = 0.5
MAX_DEBUG_LINES = 50

# 2. UI #####################################################################


def make_sidebar():
    return ui.sidebar(
        ui.input_action_button("refresh", "Run API query", class_="btn-primary"),
        ui.p(
            "Fetch Red Line data for the selected departure station: "
            "alerts, departures, arrivals, and live map.",
            class_="text-muted small",
        ),
        ui.hr(),
        make_station_dropdowns(),
        ui.hr(),
        ui.input_action_button("run_ai_report", "Run AI Commuter Report", class_="btn-success"),
        ui.p(
            "Generates a summary report via Ollama Cloud.",
            class_="text-muted small",
        ),
        ui.input_action_button("save_docx", "Save as .docx", class_="btn btn-outline-primary"),
        ui.p(
            "Export the current report to reports/ (only enabled after generating a report).",
            class_="text-muted small",
        ),
        ui.hr(),
        ui.input_numeric(
            "refresh_interval_min",
            "Auto-refresh (minutes)",
            value=0,
            min=0,
            step=0.1,
        ),
        ui.p(
            "0 = off. When > 0, data refreshes automatically.",
            class_="text-muted small",
        ),
        ui.input_numeric(
            "map_height",
            "Map height (px)",
            value=700,
            min=400,
            max=900,
            step=50,
        ),
        ui.input_slider(
            "panel_ratio",
            "Left panel width %",
            min=40,
            max=70,
            value=55,
            step=5,
        ),
        ui.hr(),
        ui.output_ui("last_api_call_ui"),
        ui.hr(),
        ui.input_checkbox_group(
            "map_routes",
            "Map layers",
            choices={
                "Red": "Red Line",
                "Green": "Green Line",
                "Blue": "Blue Line",
                "Orange": "Orange Line",
                "Silver": "Silver Line",
            },
            selected=["Red"],
        ),
        title="Red Line Tracker V2",
        width=300,
    )


def make_tabs():
    return ui.navset_card_tab(
        ui.nav_panel("Service Alerts", ui.output_data_frame("alerts_table"), value="alerts"),
        ui.nav_panel("Departures", ui.output_data_frame("departures_table"), value="departures"),
        ui.nav_panel("Near-term Arrivals", ui.output_data_frame("near_term_table"), value="near_term"),
        ui.nav_panel("Future Arrivals", ui.output_data_frame("future_table"), value="future"),
        ui.nav_panel("Live Map", output_widget("map_widget"), value="map"),
        id="main_tabs",
    )


def app_ui(request):
    return ui.page_sidebar(
        make_sidebar(),
        ui.div(
            ui.output_ui("error_banner"),
            ui.h2("MBTA Red Line – Alewife", class_="mt-3 mb-3"),
            ui.p(
                "Click 'Run API query' to load data. Use station dropdowns to change departure/arrival. "
                "Click 'Run AI Commuter Report' to generate a summary.",
                class_="text-muted mb-3",
            ),
            ui.output_ui("split_layout"),
            ui.hr(),
            ui.div(
                ui.h6("Debug log", class_="text-muted"),
                ui.input_action_button("debug_clear", "Clear debug log", class_="btn btn-sm btn-outline-secondary mb-2"),
                ui.output_ui("debug_log_ui"),
                class_="mt-3 p-2 border rounded",
            ),
            class_="p-3",
        ),
        title="Red Line Tracker V2",
        fillable=True,
    )


# 2.5 Sync worker functions (run in thread pool, no reactive access) #########


def _do_refresh_sync(dep_stop: str) -> dict:
    """Fetch and parse MBTA data. Returns dict with data or error. Runs in thread."""
    dep_stop = dep_stop or "place-alfcl"
    alerts_resp = fetch_alerts()
    predictions_resp = fetch_predictions(dep_stop)
    vehicles_resp = fetch_vehicles()
    shapes_resp = fetch_shapes()
    err = None
    if alerts_resp.get("error"):
        err = alerts_resp.get("message", "API error")
    elif predictions_resp.get("error"):
        err = predictions_resp.get("message", "API error")
    elif vehicles_resp.get("error"):
        err = vehicles_resp.get("message", "API error")
    elif shapes_resp.get("error"):
        err = shapes_resp.get("message", "API error")
    if err:
        # #region agent log
        _dbg_log("app.py:_do_refresh_sync", "sync refresh error", {"error": err[:80]}, "H4")
        # #endregion
        return {"error": err}
    predictions_all_resp = fetch_predictions_all_stops()
    if predictions_all_resp.get("error"):
        predictions_all_resp = None
    red_shapes = parse_red_line_shape(shapes_resp)
    # #region agent log
    _dbg_log("app.py:_do_refresh_sync", "sync refresh completed", {"has_error": False}, "H4")
    # #endregion
    return {
        "error": None,
        "df_alerts": parse_alerts(alerts_resp),
        "df_departures": parse_departures(predictions_resp),
        "df_near_term": parse_near_term_arrivals(predictions_resp, vehicles_resp),
        "df_future": parse_future_arrivals(predictions_resp, vehicles_resp),
        "vehicles_map": parse_vehicles_for_map_enriched(vehicles_resp, predictions_all_resp),
        "red_shapes": red_shapes,
        "last_api_call_time": datetime.now(EASTERN),
    }


def _run_ai_report_sync(dep_stop: str, arr_stop: str, dep_name: str, arr_name: str) -> dict:
    """Fetch, format, query Ollama. Returns dict with report or error. Does NOT write docx."""
    try:
        alerts_resp = fetch_alerts()
        pred_dep_resp = fetch_predictions_at_stop(dep_stop)
        pred_arr_resp = fetch_predictions_at_stop(arr_stop)
        vehicles_resp = fetch_vehicles()
        for name, resp in [
            ("alerts", alerts_resp),
            ("predictions dep", pred_dep_resp),
            ("predictions arr", pred_arr_resp),
            ("vehicles", vehicles_resp),
        ]:
            if resp.get("error"):
                return {"error": f"MBTA API error ({name}): {resp.get('message', 'Unknown')}"}
        df_a = build_alerts_df(alerts_resp)
        df_pd = build_predictions_df(pred_dep_resp)
        df_pa = build_predictions_df(pred_arr_resp)
        df_v = build_vehicles_df(vehicles_resp)
        formatted = format_data_for_ollama_compact(
            df_a, df_pd, df_pa, df_v, dep_label=dep_name, arr_label=arr_name
        )
        prompt = get_report_prompt(dep_name, arr_name)
        user_content = prompt.strip() + "\n\n---\nData:\n" + formatted
        report = query_ollama_cloud(user_content)
        return {"report": report}
    except Exception as e:
        return {"error": str(e)}


def _fetch_map_layers_sync(route_names: list) -> dict:
    """Fetch shapes for given route names. Returns dict name -> list of (lons, lats). Runs in thread."""
    out = {}
    for name in route_names or []:
        if name not in MAP_ROUTE_IDS:
            continue
        ids = MAP_ROUTE_IDS[name]
        all_geoms = []
        for rid in ids:
            resp = fetch_shapes(rid) if rid else None
            if resp and not resp.get("error"):
                all_geoms.extend(parse_red_line_shape(resp))
        if all_geoms:
            out[name] = all_geoms
    return out


# 3. Server ##################################################################


def server(input, output, session):
    # Session-scoped debug log so updates invalidate this session's outputs
    debug_log = reactive.value([])

    def _debug_append(msg: str) -> None:
        ts = datetime.now(EASTERN).strftime("%H:%M:%S")
        lines = list(debug_log())
        lines.append(f"[{ts}] {msg}")
        if len(lines) > MAX_DEBUG_LINES:
            lines = lines[-MAX_DEBUG_LINES:]
        debug_log.set(lines)

    # Explicit reactive calcs for sidebar inputs so UI and debug log reliably
    # invalidate when they change (avoids dependency-tracking issues with raw input reads).
    @reactive.calc
    def _layout_inputs():
        ratio = input.panel_ratio()
        height = input.map_height()
        return (ratio if ratio is not None else 55, height if height is not None else 700)

    @reactive.calc
    def _map_routes_selected():
        return list(input.map_routes() or ["Red"])

    _last_logged_layout = reactive.value(None)

    @reactive.effect
    def _log_layout_input_changes():
        layout = _layout_inputs()
        # #region agent log
        ratio, height = layout
        _dbg_log("app.py:_log_layout_input_changes", "layout inputs", {"ratio": ratio, "height": height}, "H5")
        # #endregion
        if layout != _last_logged_layout():
            _last_logged_layout.set(layout)
            ratio, height = layout
            _debug_append(f"Sidebar: panel_ratio={ratio}%, map_height={height}px")

    @reactive.extended_task
    async def refresh_task(dep_stop: str):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, _do_refresh_sync, dep_stop)

    @reactive.extended_task
    async def ai_report_task(dep_stop: str, arr_stop: str, dep_name: str, arr_name: str):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            _executor,
            _run_ai_report_sync,
            dep_stop,
            arr_stop,
            dep_name,
            arr_name,
        )

    @reactive.extended_task
    async def fetch_map_layers_task(route_names: list):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, _fetch_map_layers_sync, route_names)

    def _cancel_background_tasks():
        """Cancel extended tasks on session end so the app can close without waiting."""
        for task in (refresh_task, ai_report_task, fetch_map_layers_task):
            try:
                task.cancel()
            except Exception:
                pass

    session.on_ended(_cancel_background_tasks)

    @reactive.effect
    @reactive.event(input.refresh)
    def _on_refresh_clicked():
        # #region agent log
        dep = input.dep_station() or "place-alfcl"
        _dbg_log("app.py:_on_refresh_clicked", "Run API query button fired", {"dep": dep}, "H3")
        # #endregion
        _debug_append(f"Run API query clicked, dep={dep}")
        skip_next_timer_refresh.set(True)
        ui.notification_show("Fetching data...", duration=2, type="message")
        refresh_task.invoke(dep)

    @reactive.effect
    def _apply_refresh_result():
        status = refresh_task.status()
        # #region agent log
        _dbg_log("app.py:_apply_refresh_result", "effect run", {"status": status, "will_apply": status in ("success", "error")}, "H1_H4")
        # #endregion
        if status not in ("success", "error"):
            # Re-check after 2s so we don't starve the reactive loop (0.25s was blocking other events).
            if status == "running":
                reactive.invalidate_later(2.0)
            return
        try:
            result = refresh_task.result()
        except Exception as e:
            # #region agent log
            _dbg_log("app.py:_apply_refresh_result", "result() exception", {"exc": str(e)[:100]}, "H8")
            # #endregion
            api_error.set(str(e))
            _debug_append(f"Refresh result: exception — {e}")
            return
        if not isinstance(result, dict):
            return
        if result.get("error"):
            api_error.set(result["error"])
            _debug_append(f"Refresh result: error — {result['error'][:80]}")
            return
        # #region agent log
        _dbg_log("app.py:_apply_refresh_result", "applying result", {"keys": list(result.keys())}, "H8")
        # #endregion
        _debug_append("Refresh result: success")
        api_error.set(None)
        df_alerts.set(result.get("df_alerts", pd.DataFrame()))
        df_departures.set(result.get("df_departures", pd.DataFrame()))
        df_near_term.set(result.get("df_near_term", pd.DataFrame()))
        df_future.set(result.get("df_future", pd.DataFrame()))
        vehicles_map.set(result.get("vehicles_map", []))
        red_shapes = result.get("red_shapes")
        if red_shapes:
            current = dict(shapes_by_route())
            current["Red"] = red_shapes
            shapes_by_route.set(current)
        last_api_call_time.set(result.get("last_api_call_time"))

    @reactive.effect
    @reactive.event(input.run_ai_report)
    def _on_ai_report_clicked():
        dep = input.dep_station() or "place-alfcl"
        arr = input.arr_station() or "place-cntsq"
        dep_name = get_station_name(dep)
        arr_name = get_station_name(arr)
        # #region agent log
        _dbg_log("app.py:_on_ai_report_clicked", "Run AI report button fired", {"dep": dep_name, "arr": arr_name}, "H3")
        # #endregion
        _debug_append(f"Run AI report clicked: {dep_name} → {arr_name}")
        ai_report_error.set("")
        ai_report_docx_saved.set(None)
        ai_report_text.set("Generating report...")
        ui.notification_show("Generating AI report...", duration=3, type="message")
        ai_report_task.invoke(dep, arr, dep_name, arr_name)

    @reactive.effect
    def _apply_ai_report_result():
        # Only read result when task has completed; avoids SilentException spinner
        status = ai_report_task.status()
        # #region agent log
        _dbg_log("app.py:_apply_ai_report_result", "effect run", {"status": status, "will_apply": status in ("success", "error")}, "H4")
        # #endregion
        if status not in ("success", "error"):
            if status == "running":
                reactive.invalidate_later(2.0)
            return
        try:
            result = ai_report_task.result()
        except Exception as e:
            ai_report_error.set(str(e))
            ai_report_text.set("")
            _debug_append(f"AI report result: exception — {e}")
            return
        if not isinstance(result, dict):
            return
        if result.get("error"):
            ai_report_error.set(result["error"])
            ai_report_text.set("")
            _debug_append(f"AI report result: error — {result['error'][:80]}")
            return
        report = result.get("report", "")
        ai_report_text.set(report)
        _debug_append("AI report result: success")

    @reactive.effect
    def _auto_refresh_timer():
        # Do not read input.refresh() here — it made this effect run on every button click
        # and could contribute to blocking the reactive loop.
        interval_min = input.refresh_interval_min()
        # #region agent log
        _dbg_log("app.py:_auto_refresh_timer", "effect run", {"interval_min": interval_min, "skip": skip_next_timer_refresh()}, "H1_H2")
        # #endregion
        if interval_min is None or interval_min <= 0:
            return
        delay_sec = max(float(interval_min), MIN_AUTO_REFRESH_MINUTES) * 60
        if skip_next_timer_refresh():
            skip_next_timer_refresh.set(False)
            reactive.invalidate_later(delay_sec)
            return
        dep = input.dep_station() or "place-alfcl"
        refresh_task.invoke(dep)
        reactive.invalidate_later(delay_sec)

    @reactive.effect
    @reactive.event(input.save_docx)
    def _on_save_docx_clicked():
        _debug_append("Save as .docx clicked")
        txt = ai_report_text()
        if not txt or txt == "Generating report...":
            _debug_append("Save docx: skipped (no report)")
            return
        try:
            reports_dir = Path(__file__).resolve().parent / "reports"
            out_path = write_report_docx(txt, output_dir=reports_dir)
            ai_report_docx_saved.set(out_path.name)
            _debug_append(f"Save docx: saved {out_path.name}")
            ui.notification_show(f"Saved to {out_path.name}", duration=3, type="message")
        except Exception as e:
            _debug_append(f"Save docx: error — {e}")
            ui.notification_show(f"Error saving: {e}", duration=5, type="error")

    @reactive.effect
    @reactive.event(input.debug_clear)
    def _on_debug_clear():
        debug_log.set([])

    @reactive.effect
    def _trigger_fetch_map_layers():
        selected = _map_routes_selected()
        cache = dict(shapes_by_route())
        to_fetch = [r for r in selected if r not in cache and r in MAP_ROUTE_IDS]
        if not to_fetch:
            return
        fetch_map_layers_task.invoke(to_fetch)

    @reactive.effect
    def _apply_map_layers_result():
        status = fetch_map_layers_task.status()
        if status not in ("success", "error"):
            return
        try:
            result = fetch_map_layers_task.result()
        except Exception:
            return
        if not isinstance(result, dict) or not result:
            return
        current = dict(shapes_by_route())
        for name, geoms in result.items():
            if geoms:
                current[name] = geoms
        shapes_by_route.set(current)

    @render.ui
    def split_layout():
        """Split layout: left (tabs), right (report). Width from panel_ratio slider."""
        ratio, _ = _layout_inputs()
        left_w = max(4, min(8, int(12 * ratio / 100)))
        right_w = 12 - left_w
        report_txt = ai_report_text()
        report_err = ai_report_error()
        docx_saved = ai_report_docx_saved()
        if report_err:
            report_content = ui.div(
                ui.div(ui.strong("Error: "), report_err, class_="alert alert-danger", role="alert"),
            )
        elif report_txt:
            parts = [
                ui.h4("AI Commuter Report", class_="mb-2"),
                ui.div(
                    ui.markdown(report_txt),
                    class_="p-3 bg-light rounded",
                    style="max-height: 500px; overflow-y: auto;",
                ),
            ]
            if docx_saved:
                parts.insert(1, ui.p("Saved to: " + docx_saved, class_="text-success small mb-2"))
            report_content = ui.div(*parts)
        else:
            report_content = ui.div(
                ui.h4("AI Commuter Report", class_="mb-2"),
                ui.p(
                    "Click 'Run AI Commuter Report' in the sidebar to generate a summary.",
                    class_="text-muted",
                ),
            )
        return ui.row(
            ui.column(left_w, make_tabs()),
            ui.column(
                right_w,
                ui.div(
                    report_content,
                    class_="border-start ps-3",
                ),
            ),
        )

    @render.ui
    def error_banner():
        err = api_error()
        if not err:
            return ui.div()
        return ui.div(
            ui.div(ui.strong("Error: "), err, class_="alert alert-danger mb-3", role="alert"),
        )

    @render.ui
    def last_api_call_ui():
        t = last_api_call_time()
        if t is None:
            return ui.p("Last API call: —", class_="text-muted small")
        if t.tzinfo is None:
            t = t.replace(tzinfo=EASTERN)
        else:
            t = t.astimezone(EASTERN)
        return ui.p(
            "Last API call: " + t.strftime("%Y-%m-%d %H:%M:%S %Z"),
            class_="text-muted small",
        )

    @render.ui
    def debug_log_ui():
        ratio, height = _layout_inputs()
        lines = debug_log()
        header = ui.p(
            f"Panel ratio: {ratio}% | Map height: {height}px (sliders should update this line)",
            class_="small text-muted mb-2",
        )
        if not lines:
            return ui.div(header, ui.p("(no events yet — click Run API query or Run AI report)", class_="text-muted small"))
        text = "\n".join(lines)
        return ui.div(
            header,
            ui.pre(text, class_="small mb-0", style="white-space: pre-wrap; word-break: break-word; max-height: 200px; overflow-y: auto; font-size: 11px;"),
            class_="bg-dark text-light rounded p-2",
        )

    def _format_df_for_display(df, datetime_cols=None):
        datetime_cols = datetime_cols or []
        out = df.copy()
        for col in datetime_cols:
            if col in out.columns:
                out[col] = (
                    pd.to_datetime(out[col], utc=True)
                    .dt.tz_convert("America/New_York")
                    .dt.strftime("%Y-%m-%d %H:%M")
                )
        return out

    def _refresh_data():
        """Read refresh task result so outputs invalidate when task completes. Returns (df_alerts, df_departures, df_near_term, df_future) or (empty, empty, empty, empty)."""
        status = refresh_task.status()
        if status not in ("success", "error"):
            return (
                pd.DataFrame(),
                pd.DataFrame(),
                pd.DataFrame(),
                pd.DataFrame(),
            )
        try:
            res = refresh_task.result()
        except Exception:
            return (
                pd.DataFrame(),
                pd.DataFrame(),
                pd.DataFrame(),
                pd.DataFrame(),
            )
        if not isinstance(res, dict) or res.get("error"):
            return (
                pd.DataFrame(),
                pd.DataFrame(),
                pd.DataFrame(),
                pd.DataFrame(),
            )
        return (
            res.get("df_alerts", pd.DataFrame()),
            res.get("df_departures", pd.DataFrame()),
            res.get("df_near_term", pd.DataFrame()),
            res.get("df_future", pd.DataFrame()),
        )

    @render.data_frame
    def alerts_table():
        df, _, _, _ = _refresh_data()
        if df.empty:
            return render.DataGrid(pd.DataFrame(), width="100%", height="400px")
        return render.DataGrid(
            _format_df_for_display(df, ["Start Time", "End Time"]),
            width="100%",
            height="400px",
        )

    @render.data_frame
    def departures_table():
        _, df, _, _ = _refresh_data()
        if df.empty:
            return render.DataGrid(pd.DataFrame(), width="100%", height="400px")
        return render.DataGrid(
            _format_df_for_display(
                df,
                ["Scheduled Departure Time", "Actual Estimated Departure Time"],
            ),
            width="100%",
            height="400px",
        )

    @render.data_frame
    def near_term_table():
        _, _, df, _ = _refresh_data()
        if df.empty:
            return render.DataGrid(pd.DataFrame(), width="100%", height="400px")
        return render.DataGrid(
            _format_df_for_display(
                df,
                ["Scheduled Arrival Time", "Actual Estimated Arrival Time"],
            ),
            width="100%",
            height="400px",
        )

    @render.data_frame
    def future_table():
        _, _, _, df = _refresh_data()
        if df.empty:
            return render.DataGrid(pd.DataFrame(), width="100%", height="400px")
        return render.DataGrid(
            _format_df_for_display(
                df,
                ["Scheduled Arrival Time", "Actual Estimated Arrival Time"],
            ),
            width="100%",
            height="400px",
        )

    @render_widget
    def map_widget():
        _, height = _layout_inputs()
        height = min(900, max(400, int(height)))
        cache = dict(shapes_by_route())
        vehicles = list(vehicles_map())
        # Read from refresh task so map invalidates when API result arrives
        status = refresh_task.status()
        if status in ("success", "error"):
            try:
                res = refresh_task.result()
                if isinstance(res, dict) and not res.get("error"):
                    vehicles = res.get("vehicles_map", []) or vehicles
                    if res.get("red_shapes"):
                        cache["Red"] = res["red_shapes"]
            except Exception:
                pass
        selected = _map_routes_selected()
        center_lat = 42.373
        center_lon = -71.118
        fig = go.Figure()
        for name in selected:
            if name not in cache:
                continue
            geoms = cache[name]
            if not isinstance(geoms, list):
                geoms = [geoms]
            color = MAP_COLORS.get(name, "#333333")
            label = f"{name} Line" if name != "Green" else "Green Line"
            for lons, lats in geoms:
                fig.add_trace(
                    go.Scattermapbox(
                        lon=lons,
                        lat=lats,
                        mode="lines",
                        line=dict(width=4, color=color),
                        name=label,
                        showlegend=False,
                    )
                )
        if vehicles:
            lats = [v["lat"] for v in vehicles]
            lons = [v["lon"] for v in vehicles]
            customdata = [
                [
                    v.get("vehicle_id", "—"),
                    v.get("direction", "—"),
                    v.get("destination", "—"),
                    v.get("next_stop_name", "—"),
                    v.get("next_stop_time_expected", "—"),
                    v.get("minutes_behind") if v.get("minutes_behind") is not None else "—",
                ]
                for v in vehicles
            ]
            hovertemplate = (
                "<b>Train ID</b>: %{customdata[0]}<br>"
                "<b>Direction</b>: %{customdata[1]}<br>"
                "<b>Destination</b>: %{customdata[2]}<br>"
                "<b>Next station</b>: %{customdata[3]}<br>"
                "<b>Expected at next</b>: %{customdata[4]}<br>"
                "<b>Minutes behind</b>: %{customdata[5]}<extra></extra>"
            )
            fig.add_trace(
                go.Scattermapbox(
                    lon=lons,
                    lat=lats,
                    mode="markers",
                    marker=dict(size=14, color="#FFC72C", symbol="circle"),
                    name="Trains",
                    legendgroup="Trains",
                    customdata=customdata,
                    hovertemplate=hovertemplate,
                )
            )
            arrow_lats, arrow_lons = [], []
            for v in vehicles:
                lat, lon = v["lat"], v["lon"]
                bearing = v.get("bearing")
                if bearing is not None:
                    br = radians(float(bearing))
                    k = 0.0004
                    dlat = k * cos(br)
                    dlon = k * sin(br) / max(cos(radians(lat)), 0.01)
                    arrow_lats.extend([lat, lat + dlat, None])
                    arrow_lons.extend([lon, lon + dlon, None])
            if arrow_lons:
                fig.add_trace(
                    go.Scattermapbox(
                        lon=arrow_lons,
                        lat=arrow_lats,
                        mode="lines",
                        line=dict(width=4, color="#FFC72C"),
                        name="Trains",
                        legendgroup="Trains",
                        showlegend=False,
                        hoverinfo="skip",
                    )
                )
        fig.update_layout(
            mapbox=dict(
                style="open-street-map",
                center=dict(lat=center_lat, lon=center_lon),
                zoom=10,
            ),
            margin=dict(l=0, r=0, t=24, b=0),
            showlegend=True,
            height=height,
        )
        widget = go.FigureWidget(fig.data, fig.layout)
        widget._config["scrollZoom"] = True
        return widget


# 4. Run ####################################################################

app = App(app_ui, server)

# Background tasks that can block exit if not cleaned up:
# 1. ThreadPoolExecutor (_executor) – runs refresh_task, ai_report_task, fetch_map_layers_task
# 2. reactive.invalidate_later() – scheduled by _auto_refresh_timer when auto-refresh is on
# 3. Extended tasks (refresh_task, ai_report_task, fetch_map_layers_task) – cancelled in session.on_ended
def _on_shutdown():
    """Shut down thread pool without blocking on in-flight tasks (avoids Ctrl+C hang)."""
    _executor.shutdown(wait=False)

app.on_shutdown(_on_shutdown)

if __name__ == "__main__":
    from shiny import run_app
    run_app(app)
